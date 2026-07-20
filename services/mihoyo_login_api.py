import http.cookies

import httpx

from models import (
    QrCodeChallenge,
    QrLoginPollResult,
    QrLoginProvider,
    QrLoginState,
    LoginSession,
)

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


async def create_qr_login(session: LoginSession) -> QrCodeChallenge:
    """创建二维码登录挑战。返回 ticket 和 url。"""
    client = _build_client(session)
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
    finally:
        await client.aclose()


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

    client = _build_client(session)
    try:
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
    finally:
        await client.aclose()
