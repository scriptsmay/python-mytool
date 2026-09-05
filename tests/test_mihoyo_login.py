from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core.login import build_and_validate_account, persist_account, verify_credentials
from models import (
    BBSCookies,
    BaseApiStatus,
    ConfigDataManager,
    GameRecord,
    GetCookieStatus,
    LoginSession,
    QrCodeChallenge,
    QrLoginPollResult,
    QrLoginProvider,
    QrLoginState,
    UserAccount,
)
from config.task_logger import execute_task_with_logging, TaskResult, TaskStatus
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

    @pytest.mark.asyncio
    async def test_app_qr_body_tokens_merged(self):
        """App QR 仅在 body 返回 tokens 时应能正常构建账号"""
        session = _make_app(QrLoginProvider.APP)
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id_v2": "uid1"},
            tokens={"stoken": "app-stoken", "cookie_token": "app-ctok"},
            user_info={"aid": "12345", "mid": "m123"},
        )
        result = await build_and_validate_account(poll, session)
        assert isinstance(result, UserAccount)
        assert result.bbs_uid == "uid1"

    @pytest.mark.asyncio
    async def test_verify_credentials_rejects_invalid(self):
        """verify_credentials 应拒绝无效凭据（login_expired）"""
        from core.login import verify_credentials
        from services.common import BaseApiStatus
        from unittest.mock import AsyncMock, patch

        account = _make_account()
        with patch(
            "core.login.get_game_record",
            return_value=(BaseApiStatus(login_expired=True), None),
        ):
            result = await verify_credentials(account)

        from config.task_logger import TaskResult as _TR, TaskStatus as _TS
        assert isinstance(result, _TR)
        assert result.status == _TS.FAILED


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


def test_persist_account_rollback_on_disk_failure(tmp_path, monkeypatch):
    """save_config 失败时内存配置应回滚，不应保留污染状态"""
    import asyncio
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
    ConfigDataManager._initialized = False
    ConfigDataManager.load_config()

    new_account = _make_account()
    new_account.cookies.stoken_v2 = "newv2t"

    # 模拟磁盘写入失败
    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(ConfigDataManager, "save_config", fail_save)

    err = asyncio.run(persist_account(new_account, "uid1"))

    from config.task_logger import TaskResult as _TR, TaskStatus as _TS
    assert isinstance(err, _TR)
    assert err.status == _TS.FAILED
    # 内存中应为旧值（回滚成功）
    saved = ConfigDataManager.config_data.users["uid1"].accounts["uid1"]
    assert saved.cookies.stoken_v2 == "old"


# ===================== ADR-002 新增测试 =====================


class TestAppQrTokenExchange:
    """App QR 确认响应仅含 stoken + user_info 时，应通过兑换接口构建完整账号"""

    @pytest.mark.asyncio
    async def test_app_qr_body_only_triggers_exchange(self):
        from unittest.mock import patch

        session = _make_app(QrLoginProvider.APP)
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id_v2": "uid1"},
            tokens={"stoken": "app-stoken"},
            user_info={"aid": "12345", "mid": "m123"},
        )
        with patch(
            "core.login.get_cookie_account_info_by_stoken",
            return_value=(GetCookieStatus(success=True), "exchanged-ctok"),
        ):
            result = await build_and_validate_account(poll, session)

        assert isinstance(result, UserAccount)
        assert result.bbs_uid == "uid1"
        assert result.cookies.cookie_token == "exchanged-ctok"
        assert result.cookies.stoken_v1 == "app-stoken"

    @pytest.mark.asyncio
    async def test_exchange_missing_cookie_token_fails(self):
        import asyncio
        from unittest.mock import patch

        session = _make_app(QrLoginProvider.APP)
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id_v2": "uid1"},
            tokens={"stoken": "app-stoken"},
            user_info={"aid": "12345", "mid": "m123"},
        )
        with patch(
            "core.login.get_cookie_account_info_by_stoken",
            return_value=(GetCookieStatus(missing_cookie_token=True), None),
        ):
            result = await build_and_validate_account(poll, session)

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_exchange_network_error_fails(self):
        from unittest.mock import patch

        session = _make_app(QrLoginProvider.APP)
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id_v2": "uid1"},
            tokens={"stoken": "app-stoken"},
            user_info={"aid": "12345", "mid": "m123"},
        )
        with patch(
            "core.login.get_cookie_account_info_by_stoken",
            return_value=(GetCookieStatus(network_error=True), None),
        ):
            result = await build_and_validate_account(poll, session)

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_exchange_success_no_credentials_in_logs(self, caplog):
        import logging
        from unittest.mock import patch

        caplog.set_level(logging.DEBUG)
        session = _make_app(QrLoginProvider.APP)
        poll = QrLoginPollResult(
            state=QrLoginState.CONFIRMED,
            cookies={"account_id_v2": "uid1"},
            tokens={"stoken": "app-stoken"},
            user_info={"aid": "12345", "mid": "m123"},
        )
        # 唯一敏感字符串，验证其不会出现在任何日志中
        with patch(
            "core.login.get_cookie_account_info_by_stoken",
            return_value=(GetCookieStatus(success=True), "UNIQUE_SECRET_TOKEN_9F2A"),
        ):
            await build_and_validate_account(poll, session)

        assert "UNIQUE_SECRET_TOKEN_9F2A" not in caplog.text
        assert "app-stoken" not in caplog.text


class TestUnifiedCredentialVerification:
    """Web QR 与 App QR 共用同一验证：游戏角色 + 米游币社区只读接口"""

    @pytest.mark.asyncio
    async def test_game_ok_community_fail_does_not_overwrite(self):
        from unittest.mock import patch

        account = _make_account()
        with patch(
            "core.login.get_game_record",
            return_value=(BaseApiStatus(success=True), [GameRecord(
                region_name="cn_gf01", game_id=2, level=60,
                region="cn_gf01", game_role_id="1", nickname="n",
            )]),
        ), patch(
            "core.login.get_missions",
            return_value=(BaseApiStatus(login_expired=True), None),
        ):
            result = await verify_credentials(account)

        assert isinstance(result, TaskResult)
        assert result.status == TaskStatus.FAILED
        assert "米游币社区" in result.message

    @pytest.mark.asyncio
    async def test_game_ok_community_ok_passes(self):
        from unittest.mock import patch

        account = _make_account()
        with patch(
            "core.login.get_game_record",
            return_value=(BaseApiStatus(success=True), [GameRecord(
                region_name="cn_gf01", game_id=2, level=60,
                region="cn_gf01", game_role_id="1", nickname="n",
            )]),
        ), patch(
            "core.login.get_missions",
            return_value=(BaseApiStatus(success=True), []),
        ):
            result = await verify_credentials(account)

        assert result is None


class TestPersistFullSnapshotRollback:
    """保存失败时回滚完整快照：新 UID 不残留，已有 UID 保持原值"""

    @pytest.mark.asyncio
    async def test_new_uid_absent_after_disk_failure(self, tmp_path, monkeypatch):
        import asyncio
        import json
        from models.data_models import ConfigData

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "users": {
                "uid1": {"accounts": {"uid1": {
                    "phone_number": None,
                    "cookies": {"bbs_uid": "uid1", "stoken_v2": "old",
                                "cookie_token": "oldctok", "stuid": "uid1"},
                    "device_id_ios": "orig_ios",
                    "device_id_android": "orig_and",
                }}}
            }
        }), encoding="utf-8")

        monkeypatch.setattr("models.data_models.project_config_path", Path(config_path))
        ConfigDataManager._initialized = False
        ConfigDataManager.load_config()

        new_account = _make_account(uid="uid999")
        monkeypatch.setattr(ConfigDataManager, "save_config", lambda: (_ for _ in ()).throw(OSError("disk full")))

        err = await persist_account(new_account, "uid999")
        assert isinstance(err, TaskResult)
        assert err.status == TaskStatus.FAILED
        # 新 UID 不得残留
        assert "uid999" not in ConfigDataManager.config_data.users

    @pytest.mark.asyncio
    async def test_existing_uid_preserved_after_disk_failure(self, tmp_path, monkeypatch):
        import asyncio
        import json
        from models.data_models import ConfigData

        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "users": {
                "uid1": {"accounts": {"uid1": {
                    "phone_number": None,
                    "cookies": {"bbs_uid": "uid1", "stoken_v2": "old",
                                "cookie_token": "oldctok", "stuid": "uid1"},
                    "device_id_ios": "orig_ios",
                    "device_id_android": "orig_and",
                    "device_fp": "orig_fp",
                }}}
            }
        }), encoding="utf-8")

        monkeypatch.setattr("models.data_models.project_config_path", Path(config_path))
        ConfigDataManager._initialized = False
        ConfigDataManager.load_config()

        new_account = _make_account()
        new_account.cookies.stoken_v2 = "newv2t"
        monkeypatch.setattr(ConfigDataManager, "save_config", lambda: (_ for _ in ()).throw(OSError("disk full")))

        err = await persist_account(new_account, "uid1")
        assert isinstance(err, TaskResult)
        assert err.status == TaskStatus.FAILED
        saved = ConfigDataManager.config_data.users["uid1"].accounts["uid1"]
        # cookies、设备字段、偏好均保持原值
        assert saved.cookies.stoken_v2 == "old"
        assert saved.cookies.cookie_token == "oldctok"
        assert saved.device_id_ios == "orig_ios"
        assert saved.device_fp == "orig_fp"


class TestTaskResultMerge:
    """execute_task_with_logging 应以返回的 TaskResult 为权威结果，保留原始数据"""

    @pytest.mark.asyncio
    async def test_preserves_data_counts_and_partial_status(self):
        async def impl():
            return TaskResult(
                status=TaskStatus.PARTIAL_SUCCESS,
                message="部分完成",
                data={"detail": [1, 2, 3]},
                success_count=2,
                failure_count=1,
                total_count=3,
            )

        result = await execute_task_with_logging("任务", impl)
        assert result.status == TaskStatus.PARTIAL_SUCCESS
        assert result.message == "部分完成"
        assert result.data == {"detail": [1, 2, 3]}
        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.total_count == 3

    @pytest.mark.asyncio
    async def test_partial_counts_mismatch_returns_diagnostic_failure(self):
        async def impl():
            return TaskResult(
                status=TaskStatus.PARTIAL_SUCCESS,
                message="m",
                success_count=2,
                failure_count=1,
                total_count=9,
            )

        result = await execute_task_with_logging("任务", impl)
        assert result.status == TaskStatus.FAILED
        assert "计数不一致" in result.message

    @pytest.mark.asyncio
    async def test_complete_result_preserved(self):
        async def impl():
            return TaskResult(
                status=TaskStatus.SUCCESS,
                message="全部成功",
                data={"n": 5},
                success_count=4,
                failure_count=0,
                total_count=4,
            )

        result = await execute_task_with_logging("任务", impl)
        assert result.status == TaskStatus.SUCCESS
        assert result.message == "全部成功"
        assert result.data == {"n": 5}
        assert result.success_count == 4

