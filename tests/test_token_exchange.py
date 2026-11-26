"""2026-11-20 米游社改版：stoken 换票改用 ma-cn-session/app/exchange。

旧 getCookieAccountInfoBySToken 对 App 扫码签发的 token_type=1 stoken 恒返 -464。
新接口以 POST body 传 stoken，返回 v2 格式 ltoken/cookie_token。
"""

import hashlib
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from models import BBSCookies
from services.mihoyo_login_api import (
    URL_EXCHANGE_TOKEN,
    exchange_token_by_stoken,
)


def _cookies():
    """App QR 确认后的凭据：v2 stoken + mid，尚无 cookie_token/ltoken。"""
    return BBSCookies.from_login_cookie({
        "stoken": "v2_teststoken",
        "mid": "testmid",
        "account_id": "123456789",
    })


def _exchange_response(token_type=4):
    return httpx.Response(200, json={
        "retcode": 0,
        "message": "OK",
        "data": {"token": {"token_type": token_type, "token": f"v2_exchanged_{token_type}"}},
    })


def _body_text(kwargs):
    """从 client.post 的 kwargs 中取出原始 body 字符串。"""
    for key in ("content", "body"):
        value = kwargs.get(key)
        if isinstance(value, str):
            return value
    return None


class TestExchangeTokenRequest:
    """exchange 接口的请求形态必须符合新版 passport SDK。"""

    @pytest.mark.asyncio
    async def test_uses_post_exchange_endpoint(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            status, token = await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            args, kwargs = client.post.call_args
            assert args[0] == URL_EXCHANGE_TOKEN
            assert "ma-cn-session/app/exchange" in URL_EXCHANGE_TOKEN
            assert status.success is True
            assert token == "v2_exchanged_4"

    @pytest.mark.asyncio
    async def test_body_has_src_token_mid_and_dst_type(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            body = json.loads(_body_text(client.post.call_args.kwargs))
            assert body["src_token"] == {"token": "v2_teststoken", "token_type": 1}
            assert body["mid"] == "testmid"
            assert body["dst_token_type"] == 4

    @pytest.mark.asyncio
    async def test_body_keys_follow_gson_hash_order(self):
        """DS 校验要求 body 字段按 Java HashMap 桶序，不是插入序。"""
        def jhash(s):
            h = 0
            for ch in s:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            return h & 15

        expected_order = sorted(["mid", "dst_token_type", "src_token"], key=jhash)
        assert expected_order == ["mid", "dst_token_type", "src_token"]

        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            kw = client.post.call_args.kwargs
            body_text = _body_text(kw)
            # body 必须是字符串且键顺序符合 Gson 桶序
            assert isinstance(body_text, str)
            positions = [body_text.index(f'"{k}"') for k in expected_order]
            assert positions == sorted(positions)

    @pytest.mark.asyncio
    async def test_ds_uses_prod_salt_and_body(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            headers = client.post.call_args.kwargs["headers"]
            assert "DS" in headers
            t, r, sign = headers["DS"].split(",")
            assert t.isdigit() and r.isdigit()
            assert len(sign) == 32

    @pytest.mark.asyncio
    async def test_ds_signature_matches_prod_salt_and_body(self):
        """DS = md5(salt=SALT_PROD&t=..&r=..&b=<body>&q=) —— 不是 X4 盐。"""
        from models import project_env

        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            kw = client.post.call_args.kwargs
            t, r, sign = kw["headers"]["DS"].split(",")
            body = _body_text(kw)
            expected = hashlib.md5(
                f"salt={project_env.salt_config.SALT_PROD}&t={t}&r={r}&b={body}&q=".encode()
            ).hexdigest()
            assert sign == expected

    @pytest.mark.asyncio
    async def test_headers_use_bll8_appid_and_client_type_2(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(4))

            await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            headers = client.post.call_args.kwargs["headers"]
            assert headers["x-rpc-app_id"] == "bll8iq97cem8"
            assert headers["x-rpc-client_type"] == "2"
            assert headers["x-rpc-device_id"] == "d1"
            assert headers["x-rpc-game_biz"] == "bbs_cn"
            assert "x-rpc-sdk_version" in headers
            assert "x-rpc-account_version" in headers


class TestExchangeTokenResponse:
    """响应解析：retcode=0 且 token 非空才算成功。"""

    @pytest.mark.asyncio
    async def test_ltoken_dst_2_parsed(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=_exchange_response(2))

            status, token = await exchange_token_by_stoken(
                _cookies(), dst_token_type=2, device_id="d1", retry=False
            )

            assert status.success is True
            assert token == "v2_exchanged_2"
            body = json.loads(_body_text(client.post.call_args.kwargs))
            assert body["dst_token_type"] == 2

    @pytest.mark.asyncio
    async def test_nonzero_retcode_is_failure(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=httpx.Response(200, json={
                "retcode": -464, "message": "请使用最新版本产品",
            }))

            status, token = await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            assert status.success is False
            assert token is None
            assert "-464" in (status.message or "")

    @pytest.mark.asyncio
    async def test_missing_token_is_failure(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(return_value=httpx.Response(200, json={
                "retcode": 0, "message": "OK", "data": {},
            }))

            status, token = await exchange_token_by_stoken(
                _cookies(), dst_token_type=4, device_id="d1", retry=False
            )

            assert status.success is False
            assert token is None

    @pytest.mark.asyncio
    async def test_missing_stoken_rejected_before_request(self):
        with patch("services.mihoyo_login_api.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock()

            cookies = BBSCookies.from_login_cookie({"mid": "m1"})
            status, token = await exchange_token_by_stoken(
                cookies, dst_token_type=4, device_id="d1", retry=False
            )

            assert status.success is False
            client.post.assert_not_called()


class TestLoginIntegration:
    """登录流程应走 exchange 换票，并把 v2 票据落到 v2 字段。"""

    @pytest.mark.asyncio
    async def test_app_qr_uses_exchange_and_sets_v2_fields(self):
        from unittest.mock import patch
        from core.login import build_and_validate_account
        from models import (
            GetCookieStatus,
            LoginSession,
            QrLoginPollResult,
            QrLoginProvider,
            QrLoginState,
            UserAccount,
        )

        session = LoginSession(
            provider=QrLoginProvider.APP,
            device_id="d1",
            app_id="ddxf5dufpuyo",
            client_type="3",
            user_agent="HYPContainer/1.3.3.182",
        )
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={},
            tokens={"stoken": "v2_teststoken"},
            user_info={"aid": "123456789", "mid": "testmid"},
        )

        async def fake_exchange(cookies, dst_token_type, device_id=None, retry=True):
            return GetCookieStatus(success=True), f"v2_token_{dst_token_type}"

        with patch(
            "core.login.exchange_token_by_stoken", side_effect=fake_exchange
        ) as mock_exchange:
            result = await build_and_validate_account(poll, session)

        assert isinstance(result, UserAccount)
        # exchange 换出的 v2 票据（值带 v2_ 前缀）必须写入常规键名，
        # getGameRecordCard 只认 cookie_token/ltoken，不认 *_v2 字段。
        assert result.cookies.cookie_token == "v2_token_4"
        assert result.cookies.ltoken == "v2_token_2"
        assert mock_exchange.call_count == 2

    @pytest.mark.asyncio
    async def test_web_qr_with_cookie_token_skips_exchange(self):
        from unittest.mock import patch
        from core.login import build_and_validate_account
        from models import (
            LoginSession,
            QrLoginPollResult,
            QrLoginProvider,
            QrLoginState,
            UserAccount,
        )

        session = LoginSession(
            provider=QrLoginProvider.WEB,
            device_id="d1",
            app_id="bll8iq97cem8",
            client_type="1",
            user_agent="Mozilla/5.0",
        )
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id": "123", "stoken": "v1_stoken", "cookie_token_v2": "v2_existing_ctok", "ltoken_v2": "v2_existing_ltok"},
            tokens={},
            user_info={},
        )

        with patch("core.login.exchange_token_by_stoken") as mock_exchange:
            result = await build_and_validate_account(poll, session)

        assert isinstance(result, UserAccount)
        mock_exchange.assert_not_called()
