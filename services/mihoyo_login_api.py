import http.cookies
from typing import Optional, Tuple

import httpx
import tenacity

from config import logger
from models import (
    BBSCookies,
    GetCookieStatus,
    QrCodeChallenge,
    QrLoginPollResult,
    QrLoginProvider,
    QrLoginState,
    LoginSession,
    project_config,
)
from services.common import (
    ApiResultHandler,
    get_async_retry,
    is_incorrect_return,
    HEADERS_PASSPORT_API,
)
from utils import generate_device_id

URL_CREATE_QR_LOGIN = (
    "https://passport-api.mihoyo.com/account/ma-cn-passport/{}/createQRLogin"
)
URL_QUERY_QR_LOGIN = (
    "https://passport-api.mihoyo.com/account/ma-cn-passport/{}/queryQRLoginStatus"
)

WEB_QR_HEADERS = {
    "x-rpc-app_id": "bll8iq97cem8",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

APP_QR_HEADERS = {
    "x-rpc-app_id": "ddxf5dufpuyo",
    "x-rpc-client_type": "3",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

USER_AGENT_WEB = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Safari/605.1.15"
)
USER_AGENT_APP = "HYPContainer/1.3.3.182"


def _build_client(session: LoginSession) -> httpx.AsyncClient:
    """根据 LoginSession 构建复用连接的 AsyncClient"""
    headers = {
        "User-Agent": session.user_agent,
        "x-rpc-device_id": session.device_id,
    }
    if session.provider == QrLoginProvider.WEB:
        headers.update(WEB_QR_HEADERS)
    else:
        headers.update(APP_QR_HEADERS)
    return httpx.AsyncClient(headers=headers, timeout=10)


async def _ensure_client(session: LoginSession) -> httpx.AsyncClient:
    """确保 LoginSession 持有复用的 AsyncClient"""
    if session.client is None:
        session.client = _build_client(session)
    return session.client


async def close_session(session: LoginSession) -> None:
    """关闭登录会话的 HTTP 客户端"""
    if session.client is not None:
        await session.client.aclose()
        session.client = None


async def create_qr_login(session: LoginSession) -> QrCodeChallenge:
    """创建二维码登录挑战。返回 ticket 和 url。"""
    client = await _ensure_client(session)
    try:
        path = "web" if session.provider == QrLoginProvider.WEB else "app"
        url = URL_CREATE_QR_LOGIN.format(path)
        resp = await client.post(url, json={})
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or {}
        ticket = data.get("ticket")
        qr_url = data.get("url")
        if not ticket or not qr_url:
            raise ValueError(f"创建二维码失败: 响应缺少 ticket/url, retcode={body.get('retcode')}")
        return QrCodeChallenge(ticket=ticket, url=qr_url)
    except httpx.HTTPStatusError as e:
        raise
    except ValueError:
        raise
    except Exception as e:
        # 关闭并重建，避免后续轮询复用异常连接
        await close_session(session)
        raise


def parse_set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    """从响应的 Set-Cookie 头中解析 Cookie 字段，使用标准库避免值中含 = 被截断"""
    result: dict[str, str] = {}
    for cookie_str in response.headers.get_list("set-cookie"):
        simple = http.cookies.SimpleCookie()
        try:
            simple.load(cookie_str)
        except http.cookies.CookieError:
            continue
        for key, morsel in simple.items():
            result[key] = morsel.value
    return result


async def query_qr_login(
    session: LoginSession,
    ticket: str,
) -> QrLoginPollResult:
    """查询二维码登录状态。确认时从 Set-Cookie 解析凭据。"""
    path = "web" if session.provider == QrLoginProvider.WEB else "app"
    url = URL_QUERY_QR_LOGIN.format(path)

    client = await _ensure_client(session)
    resp = await client.post(url, json={"ticket": ticket})
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data") or {}
    status = data.get("status", "")

    state_map = {
        "Created": QrLoginState.CREATED,
        "Scanned": QrLoginState.SCANNED,
        "Confirmed": QrLoginState.CONFIRMED,
        "Expired": QrLoginState.EXPIRED,
        "Canceled": QrLoginState.CANCELED,
    }
    state = state_map.get(status, QrLoginState.UNKNOWN)

    if state is QrLoginState.UNKNOWN and isinstance(body.get("retcode"), int) and body["retcode"] != 0:
        logger.warning(f"非零 retcode={body.get('retcode')}，视为不可用: {body.get('message')}")
        state = QrLoginState.EXPIRED

    cookies: dict[str, str] = {}
    tokens: dict[str, str] = {}
    user_info: dict[str, str] = {}

    if state == QrLoginState.CONFIRMED:
        cookies = parse_set_cookie_headers(resp)
        if "tokens" in data:
            raw_tokens = data["tokens"]
            if isinstance(raw_tokens, list):
                for t in raw_tokens:
                    if isinstance(t, dict) and "name" in t and "token" in t:
                        tokens[t["name"]] = t["token"]
        if "user_info" in data and isinstance(data["user_info"], dict):
            user_info = {k: str(v) for k, v in data["user_info"].items()}

    return QrLoginPollResult(
        state=state,
        cookies=cookies,
        tokens=tokens,
        user_info=user_info,
        retcode=body.get("retcode"),
        message=body.get("message"),
    )


URL_COOKIE_ACCOUNT_INFO_BY_STOKEN = (
    "https://passport-api.mihoyo.com/account/auth/api/getCookieAccountInfoBySToken"
)


async def get_cookie_account_info_by_stoken(
    cookies: BBSCookies, device_id: str = None, retry: bool = True
) -> Tuple[GetCookieStatus, Optional[str]]:
    """
    App QR 凭据兑换：用确认响应中的 stoken + uid/aid 和 mid 换取 cookie_token。

    仅在响应 ``retcode == 0`` 且返回非空 ``cookie_token`` 时视为成功；缺失或
    错误响应返回明确的失败状态。token、ticket 和原始响应一律不写入普通或 debug 日志。

    :param cookies: 米游社 Cookies，需要包含 stoken 和 mid
    :param device_id: X_RPC_DEVICE_ID
    :param retry: 是否允许重试
    :return: (兑换状态, cookie_token 或 None)
    """
    if not cookies.stoken:
        return GetCookieStatus(missing_stoken=True), None
    if not cookies.mid:
        return GetCookieStatus(missing_mid=True), None

    headers = HEADERS_PASSPORT_API.copy()
    headers["x-rpc-device_id"] = device_id if device_id else generate_device_id()
    headers["x-rpc-app_id"] = "ddxf5dufpuyo"

    try:
        async for attempt in get_async_retry(retry):
            with attempt:
                async with httpx.AsyncClient() as client:
                    res = await client.get(
                        URL_COOKIE_ACCOUNT_INFO_BY_STOKEN,
                        cookies=cookies.dict(v2_stoken=True, cookie_type=True),
                        headers=headers,
                        timeout=project_config.preference.timeout,
                    )
                api_result = ApiResultHandler.from_response(res.json())
                if api_result.success:
                    cookie_token = (api_result.data or {}).get("cookie_token")
                    if not cookie_token:
                        logger.warning("通过 stoken 兑换 cookie_token: 响应缺少 cookie_token")
                        return GetCookieStatus(missing_cookie_token=True), None
                    return GetCookieStatus(success=True), cookie_token
                elif api_result.login_expired:
                    logger.warning("通过 stoken 兑换 cookie_token: 登录失效")
                    return GetCookieStatus(login_expired=True), None
                else:
                    logger.warning("通过 stoken 兑换 cookie_token: 兑换失败")
                    return GetCookieStatus(), None
    except tenacity.RetryError as e:
        if is_incorrect_return(e):
            logger.exception("通过 stoken 兑换 cookie_token: 服务器没有正确返回")
            return GetCookieStatus(incorrect_return=True), None
        else:
            logger.exception("通过 stoken 兑换 cookie_token: 网络请求失败")
            return GetCookieStatus(network_error=True), None
    except Exception:
        logger.exception("通过 stoken 兑换 cookie_token: 请求异常")
        return GetCookieStatus(network_error=True), None
