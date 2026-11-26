import hashlib
import http.cookies
import json
import random
import time
from urllib.parse import urlparse
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
    project_env,
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
                    if not isinstance(t, dict) or "token" not in t:
                        continue
                    # 实测响应存在两种形态：{name, token} 或 {token_type, token}，
                    # token_type 1=stoken、2=ltoken
                    if "name" in t:
                        tokens[t["name"]] = t["token"]
                    elif "token_type" in t:
                        type_map = {1: "stoken", 2: "ltoken"}
                        name = type_map.get(t["token_type"])
                        if name:
                            tokens[name] = t["token"]
                        else:
                            logger.warning(f"未知的二维码登录 token_type={t['token_type']}")
                    else:
                        logger.warning(f"二维码登录 tokens 元素字段异常: {sorted(t.keys())}")
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
    "https://passport-api.miyoushe.com/account/auth/api/getCookieAccountInfoBySToken"
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
    # 兑换接口已迁移到 passport-api.miyoushe.com，Host 头必须同步，
    # 否则服务端按旧 Host 判定为非官方链路，返回 -464。
    headers["Host"] = urlparse(URL_COOKIE_ACCOUNT_INFO_BY_STOKEN).netloc
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
                    return GetCookieStatus(
                        login_expired=True,
                        message=f"服务器返回 {api_result.retcode} {api_result.message}".strip(),
                    ), None
                else:
                    logger.warning("通过 stoken 兑换 cookie_token: 兑换失败")
                    return GetCookieStatus(
                        message=f"服务器返回 {api_result.retcode} {api_result.message}".strip(),
                    ), None
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


# 2026-11-20 米游社改版：App 扫码签发的 token_type=1 stoken 已被
# getCookieAccountInfoBySToken 拒绝（恒返 -464）。新链路走 passport
# 的 ma-cn-session/app/exchange，可从 stoken 换出 v2 格式的
# ltoken（dst_token_type=2）与 cookie_token（dst_token_type=4）。
URL_EXCHANGE_TOKEN = (
    "https://passport-api.mihoyo.com/account/ma-cn-session/app/exchange"
)
EXCHANGE_APP_VERSION = "2.109.0"
EXCHANGE_SDK_VERSION = "2.44.0"


def _gson_key_order(keys: list) -> list:
    """按 Java HashMap 桶序排列 JSON 键（exchange 的 DS 校验要求）。

    Gson 序列化 HashMap 时按 key 的 String.hashCode() 低 4 位分桶，
    插入序会被服务端 DS 校验判为签名错误。
    """
    def bucket(key: str) -> int:
        h = 0
        for ch in key:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        return h & 15

    return sorted(keys, key=bucket)


def _build_exchange_body(stoken: str, mid: str, dst_token_type: int) -> str:
    """构造 exchange 请求体，键序按 Gson 桶序（mid → dst_token_type → src_token）。"""
    fields = {
        "mid": mid,
        "dst_token_type": dst_token_type,
        "src_token": {"token": stoken, "token_type": 1},
    }
    ordered = {key: fields[key] for key in _gson_key_order(list(fields))}
    # 与 Gson 输出一致：无多余空格，分隔符不带空白
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def _exchange_ds(body: str) -> str:
    """passport exchange 接口专用 DS（SALT_PROD，body 原文参与签名）。

    与 X4 盐不同：这里必须用 passport SDK 的 SALT_PROD，
    且 query 为空字符串参与 md5。
    """
    t = str(int(time.time()))
    r = str(random.randint(100000, 200000))
    sign = hashlib.md5(
        f"salt={project_env.salt_config.SALT_PROD}&t={t}&r={r}&b={body}&q=".encode()
    ).hexdigest()
    return f"{t},{r},{sign}"


async def exchange_token_by_stoken(
    cookies: BBSCookies,
    dst_token_type: int,
    device_id: str = None,
    retry: bool = True,
) -> Tuple[GetCookieStatus, Optional[str]]:
    """用 v2 stoken + mid 通过 exchange 接口换 ltoken_v2 / cookie_token_v2。

    :param cookies: 含 stoken_v2 与 mid 的 BBSCookies
    :param dst_token_type: 2=ltoken_v2，4=cookie_token_v2
    :param device_id: X_RPC_DEVICE_ID（应与 stoken 签发设备一致）
    :param retry: 是否允许重试
    :return: (状态, token 或 None)；token 不写入日志
    """
    if not cookies.stoken:
        return GetCookieStatus(missing_stoken=True), None
    if not cookies.mid:
        return GetCookieStatus(missing_mid=True), None

    body = _build_exchange_body(cookies.stoken, cookies.mid, dst_token_type)
    dev_id = device_id if device_id else generate_device_id()
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "DS": _exchange_ds(body),
        "User-Agent": "okhttp/4.9.3",
        "x-rpc-app_id": "bll8iq97cem8",
        "x-rpc-client_type": "2",
        "x-rpc-device_id": dev_id,
        "x-rpc-device_name": "Mihoyo Capture",
        "x-rpc-device_model": "Mi 14",
        "x-rpc-game_biz": "bbs_cn",
        "x-rpc-app_version": EXCHANGE_APP_VERSION,
        "x-rpc-sdk_version": EXCHANGE_SDK_VERSION,
        "x-rpc-account_version": EXCHANGE_SDK_VERSION,
    }

    try:
        async for attempt in get_async_retry(retry):
            with attempt:
                async with httpx.AsyncClient() as client:
                    res = await client.post(
                        URL_EXCHANGE_TOKEN,
                        content=body,
                        headers=headers,
                        timeout=project_config.preference.timeout,
                    )
                api_result = ApiResultHandler.from_response(res.json())
                if api_result.success:
                    token = (api_result.data or {}).get("token", {}).get("token")
                    if not token:
                        logger.warning("exchange 换票: 响应缺少 token")
                        return GetCookieStatus(missing_cookie_token=True), None
                    return GetCookieStatus(success=True), token
                logger.warning("exchange 换票: 兑换失败")
                return GetCookieStatus(
                    message=f"服务器返回 {api_result.retcode} {api_result.message}".strip(),
                ), None
    except tenacity.RetryError as e:
        if is_incorrect_return(e):
            logger.exception("exchange 换票: 服务器没有正确返回")
            return GetCookieStatus(incorrect_return=True), None
        logger.exception("exchange 换票: 网络请求失败")
        return GetCookieStatus(network_error=True), None
    except Exception:
        logger.exception("exchange 换票: 请求异常")
        return GetCookieStatus(network_error=True), None
