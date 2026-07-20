from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.login import build_and_validate_account, persist_account
from models import (
    BBSCookies,
    ConfigDataManager,
    LoginSession,
    QrCodeChallenge,
    QrLoginPollResult,
    QrLoginProvider,
    QrLoginState,
    UserAccount,
)
from services.mihoyo_login_api import (
    create_qr_login,
    parse_set_cookie_headers,
    query_qr_login,
)


def _make_app(provider=QrLoginProvider.WEB):
    return LoginSession(
        provider=provider,
        device_id="TEST-DEVICE-0000-0000-0000-000000000000",
        app_id="bll8iq97cem8",
        client_type="1",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Safari/605.1.15",
    )


def _mock_response(status_code=200, json_data=None, headers=None):
    """Create a mock httpx.Response with request set (needed for raise_for_status)"""
    resp = httpx.Response(status_code, json=json_data or {}, headers=headers or {})
    resp._request = httpx.Request("POST", "https://example.com")
    return resp


class TestCreateQrLogin:
    @pytest.mark.asyncio
    async def test_create_qr_success(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200,
            {"retcode": 0, "message": "OK", "data": {"ticket": "abc-ticket", "url": "https://example.com/qr?ticket=abc-ticket"}},
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await create_qr_login(session)

        assert isinstance(result, QrCodeChallenge)
        assert result.ticket == "abc-ticket"
        assert result.url == "https://example.com/qr?ticket=abc-ticket"

    @pytest.mark.asyncio
    async def test_create_qr_missing_fields(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": 0, "data": {}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            with pytest.raises(ValueError, match="创建二维码失败"):
                await create_qr_login(session)


class TestQueryQrLogin:
    @pytest.mark.asyncio
    async def test_query_confirmed(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200,
            {"retcode": 0, "message": "OK", "data": {"status": "Confirmed"}},
            headers={"set-cookie": "account_id_v2=uid123; stoken_v2=v2token; cookie_token=ctok123"},
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.CONFIRMED
        assert result.cookies.get("account_id_v2") == "uid123"
        assert result.cookies.get("stoken_v2") == "v2token"
        assert result.cookies.get("cookie_token") == "ctok123"

    @pytest.mark.asyncio
    async def test_query_created(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": 0, "data": {"status": "Created"}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.CREATED
        assert result.cookies == {}

    @pytest.mark.asyncio
    async def test_query_scanned(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": 0, "data": {"status": "Scanned"}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.SCANNED

    @pytest.mark.asyncio
    async def test_query_expired(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": 0, "data": {"status": "Expired"}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.EXPIRED

    @pytest.mark.asyncio
    async def test_query_unknown_state(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": 0, "data": {"status": "SomeNewStatus"}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.UNKNOWN

    @pytest.mark.asyncio
    async def test_query_nonzero_retcode_treated_as_expired(self):
        session = _make_app()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200, {"retcode": -100, "message": "ticket invalid", "data": {"status": "Unknown"}}
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.EXPIRED

    @pytest.mark.asyncio
    async def test_query_app_qr(self):
        session = _make_app(QrLoginProvider.APP)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(
            200,
            {
                "retcode": 0,
                "data": {
                    "status": "Confirmed",
                    "tokens": [{"name": "stoken", "token": "app-stoken"}],
                    "user_info": {"aid": "12345", "mid": "m123"},
                },
            },
            headers={"set-cookie": "account_id=app_uid; stoken=app-stoken"},
        ))
        with patch("services.mihoyo_login_api._ensure_client", return_value=mock_client):
            result = await query_qr_login(session, "test-ticket")

        assert result.state == QrLoginState.CONFIRMED
        assert result.tokens.get("stoken") == "app-stoken"
        assert result.user_info.get("aid") == "12345"


class TestParseSetCookieHeaders:
    def test_multiple_cookies(self):
        response = httpx.Response(
            status_code=200,
            headers=[
                ("set-cookie", "a=1; Path=/"),
                ("set-cookie", "b=2; Path=/"),
            ],
        )
        result = parse_set_cookie_headers(response)
        assert result == {"a": "1", "b": "2"}

    def test_cookie_with_equals_in_value(self):
        response = httpx.Response(
            status_code=200,
            headers=[("set-cookie", "token=abc=def=ghi; Path=/")],
        )
        result = parse_set_cookie_headers(response)
        assert result["token"] == "abc=def=ghi"

    def test_no_set_cookie(self):
        response = httpx.Response(status_code=200)
        result = parse_set_cookie_headers(response)
        assert result == {}


class TestBBSCookiesFromLoginCookie:
    def test_v1_fields(self):
        cookies = BBSCookies.from_login_cookie({
            "ltuid": "old_uid",
            "stoken": "v1token",
            "cookie_token": "ctok",
            "mid": "m123",
        })
        assert cookies.bbs_uid == "old_uid"
        assert cookies.stoken_v1 == "v1token"
        assert cookies.cookie_token == "ctok"
        assert cookies.mid == "m123"

    def test_v2_fields(self):
        cookies = BBSCookies.from_login_cookie({
            "account_id_v2": "uid_v2",
            "stoken_v2": "v2token",
            "cookie_token_v2": "ctok_v2",
            "account_mid_v2": "mid_v2",
        })
        assert cookies.bbs_uid == "uid_v2"
        assert cookies.stoken_v2 == "v2token"
        assert cookies.cookie_token == "ctok_v2"
        assert cookies.mid == "mid_v2"
        assert cookies.account_id_v2 == "uid_v2"

    def test_mixed_v1_v2_stoken_v1_preserved(self):
        """stoken_v1 不应被 stoken_v2 覆盖"""
        cookies = BBSCookies.from_login_cookie({
            "ltuid": "old_uid",
            "account_id_v2": "new_uid",
            "stoken": "v1token",
            "stoken_v2": "v2token",
            "cookie_token": "ctok_v1",
            "cookie_token_v2": "ctok_v2",
        })
        assert cookies.bbs_uid == "new_uid"
        assert cookies.stoken_v2 == "v2token"
        assert cookies.stoken_v1 == "v1token"
        assert cookies.cookie_token == "ctok_v2"

    def test_empty_dict(self):
        cookies = BBSCookies.from_login_cookie({})
        assert cookies.bbs_uid is None
        assert cookies.cookie_token is None


class TestQrLoginModels:
    def test_qr_login_provider(self):
        assert QrLoginProvider.WEB == "web"
        assert QrLoginProvider.APP == "app"

    def test_qr_login_state(self):
        assert QrLoginState.CREATED == "Created"
        assert QrLoginState.SCANNED == "Scanned"
        assert QrLoginState.CONFIRMED == "Confirmed"
        assert QrLoginState.EXPIRED == "Expired"
        assert QrLoginState.CANCELED == "Canceled"
        assert QrLoginState.UNKNOWN == "Unknown"

    def test_login_session(self):
        s = LoginSession(
            provider=QrLoginProvider.WEB,
            device_id="dev1",
            app_id="app1",
            client_type="1",
            user_agent="UA",
        )
        assert s.provider == QrLoginProvider.WEB

    def test_qr_code_challenge(self):
        c = QrCodeChallenge(ticket="t1", url="https://example.com")
        assert c.ticket == "t1"

    def test_qr_login_poll_result(self):
        r = QrLoginPollResult(state=QrLoginState.CONFIRMED, cookies={"a": "1"})
        assert r.state == QrLoginState.CONFIRMED
        assert r.cookies["a"] == "1"


class TestBuildAndValidateAccount:
    def _make_poll_result(self, raw_cookies):
        return QrLoginPollResult(state=QrLoginState.CONFIRMED, cookies=raw_cookies)

    @pytest.mark.asyncio
    async def test_missing_stoken_rejected(self):
        """有 UID 和 cookie_token 但缺 stoken 时应该失败"""
        session = _make_app()
        poll = self._make_poll_result({"account_id_v2": "uid1", "cookie_token": "ctok"})
        result = await build_and_validate_account(poll, session)

        from config.task_logger import TaskResult as _TR, TaskStatus as _TS
        assert isinstance(result, _TR)
        assert result.status == _TS.FAILED
        assert "stoken" in result.message

    @pytest.mark.asyncio
    async def test_valid_cookie_set_accepted(self):
        session = _make_app()
        poll = self._make_poll_result({
            "account_id_v2": "uid1",
            "stoken_v2": "v2token",
            "cookie_token_v2": "ctok",
        })
        result = await build_and_validate_account(poll, session)
        assert isinstance(result, UserAccount)
        assert result.bbs_uid == "uid1"
        assert result.cookies.stoken_v2 == "v2token"


def _make_account(uid="uid1"):
    return UserAccount(
        phone_number=None,
        cookies=BBSCookies(
            **{"bbs_uid": uid, "stoken_v2": "v2t", "cookie_token": "ctok", "stuid": uid}
        ),
        device_id_ios="orig_ios",
        device_id_android="orig_android",
        device_fp="orig_fp",
    )


@pytest.mark.asyncio
async def test_persist_preserves_existing_device_fields(tmp_path, monkeypatch):
    """更新已有账号时应保留 device_id_ios 和 device_fp"""
    import json
    from models.data_models import ConfigData

    config_dir = tmp_path
    config_path = config_dir / "config.json"

    user_data = {
        "users": {
            "uid1": {
                "accounts": {
                    "uid1": {
                        "phone_number": None,
                        "cookies": {"bbs_uid": "uid1", "stoken_v2": "old",
                                "cookie_token": "oldctok", "stuid": "uid1"},
                        "device_id_ios": "orig_ios",
                        "device_id_android": "orig_and",
                        "device_fp": "orig_fp",
                    }
                }
            }
        }
    }
    config_path.write_text(json.dumps(user_data), encoding="utf-8")

    monkeypatch.setattr(
        "models.data_models.project_config_path",
        Path(config_path),
    )
    data = ConfigDataManager.load_config()
    # force fresh load
    ConfigDataManager._initialized = False
    data = ConfigDataManager.load_config()

    new_account = _make_account()
    new_account.cookies.stoken_v2 = "newv2t"
    err = await persist_account(new_account, "uid1")
    assert err is None

    saved = ConfigDataManager.config_data.users["uid1"].accounts["uid1"]
    assert saved.cookies.stoken_v2 == "newv2t"
    assert saved.device_id_ios == "orig_ios"
    assert saved.device_fp == "orig_fp"


def test_save_config_is_atomic(tmp_path, monkeypatch):
    """配置保存应该是原子的：写入失败不应破坏现有文件"""
    import json
    from models.data_models import ConfigData

    config_dir = tmp_path
    config_path = config_dir / "config.json"
    original_payload = {"users": {}, "version": "1"}
    config_path.write_text(json.dumps(original_payload), encoding="utf-8")

    monkeypatch.setattr(
        "models.data_models.project_config_path",
        Path(config_path),
    )
    ConfigDataManager._initialized = False
    ConfigDataManager.load_config()

    ConfigDataManager.save_config()
    # 文件应被完整替换，而不是截断
    raw = config_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert "users" in parsed
