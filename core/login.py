import asyncio
from typing import Union

from models import (
    BBSCookies,
    ConfigDataManager,
    LoginSession,
    QrCodeChallenge,
    QrLoginProvider,
    QrLoginPollResult,
    QrLoginState,
    UserAccount,
    project_config,
)
from services.mihoyo_login_api import (
    close_session,
    create_qr_login,
    get_cookie_account_info_by_stoken,
    query_qr_login,
)
from services.common import get_game_record
from services.myb_missions_api import get_missions
from utils import generate_device_id, generate_qr_img, logger, push
from config.task_logger import execute_task_with_logging, TaskResult, TaskStatus

_PUSH_TITLE_SUCCESS = "米游社登录成功"
_PUSH_TITLE_FAILURE = "米游社登录失败"


async def mys_login() -> TaskResult:
    """米游社登录"""
    return await execute_task_with_logging("米游社登录", _mys_login_impl)


def _failed_result(message: str) -> TaskResult:
    return TaskResult(status=TaskStatus.FAILED, message=message)


def _success_result(message: str) -> TaskResult:
    return TaskResult(status=TaskStatus.SUCCESS, message=message)


def _build_login_session() -> LoginSession:
    """根据配置构建 LoginSession"""
    provider = QrLoginProvider.WEB
    if project_config.preference.qrcode_provider == "app":
        provider = QrLoginProvider.APP

    is_app = provider == QrLoginProvider.APP
    return LoginSession(
        provider=provider,
        device_id=generate_device_id(),
        app_id="ddxf5dufpuyo" if is_app else "bll8iq97cem8",
        client_type="3" if is_app else "1",
        user_agent="HYPContainer/1.3.3.182" if is_app else (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/16.0 Safari/605.1.15"
        ),
    )


async def create_and_publish_qr(session: LoginSession) -> Union[QrCodeChallenge, TaskResult]:
    """创建二维码并推送。返回 QrCodeChallenge 或失败 TaskResult。"""
    try:
        challenge = await create_qr_login(session)
    except Exception as e:
        logger.error(f"创建二维码失败: {e}")
        return _failed_result("获取登录二维码失败，请稍后重试")

    image_bytes = generate_qr_img(challenge.url)
    try:
        notice = (
            "请注意！！！需要配置推送渠道！"
            "目前仅支持：1、telegram 2、feishubot "
            "配置了图片推送参数（app_id 和 app_secret）才会发送登录二维码！"
        )
        if project_config.push_config.enable:
            if (
                project_config.push_config.telegram.is_configured()
                or project_config.push_config.feishubot.is_configured()
            ):
                notice = None
                push(
                    push_message="请用米游社App扫描二维码进行登录",
                    img_file=image_bytes,
                    config=project_config.push_config,
                )
        if notice:
            logger.warning(notice)
            logger.info(f"二维码URL: {challenge.url}")
    except Exception as e:
        logger.warning(f"发送包含二维码的登录消息失败: {e}")
        logger.info(f"二维码URL: {challenge.url}")

    return challenge


async def wait_for_confirmation(
    session: LoginSession,
    challenge: QrCodeChallenge,
) -> Union[QrLoginPollResult, TaskResult]:
    """轮询直到确认、过期或超时。返回 QrLoginPollResult 或失败 TaskResult。"""
    deadline = (
        asyncio.get_running_loop().time()
        + project_config.preference.qrcode_wait_time
    )
    scanned_notified = False
    poll_interval = project_config.preference.qrcode_query_interval

    while asyncio.get_running_loop().time() < deadline:
        try:
            result = await query_qr_login(session, challenge.ticket)
        except Exception as e:
            logger.error(f"登录接口网络异常: {e}")
            await asyncio.sleep(poll_interval)
            continue

        if result.state == QrLoginState.CREATED:
            pass
        elif result.state == QrLoginState.SCANNED:
            if not scanned_notified:
                logger.info("已扫码，请在App中确认登录")
                try:
                    push(
                        push_message="已扫码，请在米游社App中确认登录",
                        config=project_config.push_config,
                    )
                except Exception:
                    pass
                scanned_notified = True
        elif result.state == QrLoginState.CONFIRMED:
            logger.info("二维码已确认")
            return result
        elif result.state == QrLoginState.EXPIRED:
            waited = project_config.preference.qrcode_wait_time
            logger.info(f"二维码已过期，已等待{waited}秒")
            return _failed_result("二维码已过期，请重新运行登录")
        elif result.state == QrLoginState.CANCELED:
            return _failed_result("登录已取消")
        elif result.state == QrLoginState.UNKNOWN:
            logger.warning(f"未知二维码状态: retcode={result.retcode}, msg={result.message}")

        await asyncio.sleep(poll_interval)

    return _failed_result("已扫码但未在App中确认，请重新运行登录时超时")


def _extract_uid(cookies: BBSCookies) -> str:
    """从归一化 Cookie 中取得唯一 bbs_uid"""
    return (
        cookies.account_id_v2
        or cookies.ltuid_v2
        or cookies.account_id
        or cookies.ltuid
        or cookies.login_uid
        or cookies.stuid
        or ""
    )


async def build_and_validate_account(
    poll_result: QrLoginPollResult,
    session: LoginSession,
) -> Union[UserAccount, TaskResult]:
    """从轮询结果归一化并构建 UserAccount。

    仅负责把 Set-Cookie、body tokens 和 user_info 合并为 BBSCookies 并做字段级别
    校验。App QR 通常只在 body 返回 ``stoken`` 和 ``user_info``，此时 ``cookie_token``
    需要通过 :func:`get_cookie_account_info_by_stoken` 单独兑换，本函数不再伪造它。
    """
    raw_cookies = dict(poll_result.cookies)
    if not raw_cookies and not poll_result.tokens:
        return _failed_result("扫码成功，但登录凭据不完整")

    # App QR 可能在响应 body 中返回 tokens 和 user_info，而 Set-Cookie 仅有
    # 账号查询字段。合并两者再归一化。
    for name, token in poll_result.tokens.items():
        raw_cookies.setdefault(name, token)
    if poll_result.user_info:
        if "aid" in poll_result.user_info:
            raw_cookies.setdefault("account_id", str(poll_result.user_info["aid"]))
        if "mid" in poll_result.user_info:
            raw_cookies.setdefault("mid", str(poll_result.user_info["mid"]))

    cookies = BBSCookies.from_login_cookie(raw_cookies)
    bbs_uid = _extract_uid(cookies)

    if not bbs_uid:
        return _failed_result("扫码成功，但登录凭据不完整：缺少账号标识")
    if not cookies.stoken:
        return _failed_result("扫码成功，但登录凭据不完整：缺少 stoken")

    cookies.bbs_uid = bbs_uid

    if not cookies.cookie_token and not cookies.cookie_token_v2:
        # 确认响应可能只在 Set-Cookie（Web QR 常见）或 body tokens（App QR 常见）
        # 携带部分凭据；只要 stoken + mid 齐全就兑换 cookie_token，不区分链路
        exchange_result = await _exchange_stoken_for_cookie_token(cookies, session)
        if isinstance(exchange_result, TaskResult):
            return exchange_result
        cookies = exchange_result

    account = UserAccount(
        phone_number=None,
        cookies=cookies,
        device_id_ios=session.device_id,
        device_id_android=generate_device_id(),
    )

    return account


async def _exchange_stoken_for_cookie_token(
    cookies: BBSCookies,
    session: LoginSession,
) -> Union[BBSCookies, TaskResult]:
    """用 stoken + mid 兑换 cookie_token。成功返回补全后的 BBSCookies，失败返回 TaskResult。"""
    if not cookies.mid:
        return _failed_result("扫码成功，但登录凭据不完整：缺少 mid，无法兑换 cookie_token")

    status, cookie_token = await get_cookie_account_info_by_stoken(
        cookies, device_id=session.device_id, retry=False
    )
    if not status.success or not cookie_token:
        if status.network_error:
            return _failed_result("兑换 cookie_token 网络异常，请稍后重试")
        if status.login_expired:
            return _failed_result("凭据已过期或无效，无法完成登录")
        return _failed_result("扫码成功，但无法通过 stoken 兑换 cookie_token")

    cookies.cookie_token = cookie_token
    return cookies


async def verify_credentials(account: UserAccount) -> Union[None, TaskResult]:
    """验证凭据真实有效，返回 None 表示通过。

    Web QR 与 App QR 共用同一套验证：先检查游戏角色接口能力，再检查米游币社区
    只读接口能力。任一验证返回登录失效、非成功状态、结构错误或网络错误都视为失败，
    且网络错误与凭据失效返回不同的可诊断错误。只有两步都通过才允许后续落盘，因此
    旧的已绑定账号不会被不可用凭据覆盖。
    """
    # 1. 游戏角色接口能力
    try:
        game_status, _records = await get_game_record(account, retry=False)
    except Exception as e:
        logger.error(f"游戏角色接口验证请求异常: {e}")
        return _failed_result("凭据验证请求失败（游戏角色），请稍后重试")

    if game_status.login_expired:
        return _failed_result("新凭据已过期或无效，无法完成登录（游戏角色）")
    if not game_status.success:
        if game_status.network_error:
            return _failed_result("凭据验证网络异常（游戏角色），请稍后重试")
        return _failed_result("凭据验证失败（游戏角色），请稍后重试")

    # 2. 米游币社区只读接口能力
    community_status = await _verify_community_access(account)
    if community_status is not None:
        return community_status

    return None


async def _verify_community_access(account: UserAccount) -> Union[None, TaskResult]:
    """检查 stoken + cookie_token 组合可用于米游币社区任务。返回 None 表示通过。"""
    try:
        status, _missions = await get_missions(account, retry=False)
    except Exception as e:
        logger.error(f"米游币社区接口验证请求异常: {e}")
        return _failed_result("凭据验证请求失败（米游币社区），请稍后重试")

    if status.login_expired:
        return _failed_result("新凭据已过期或无效，无法完成登录（米游币社区）")
    if not status.success:
        if status.network_error:
            return _failed_result("凭据验证网络异常（米游币社区），请稍后重试")
        return _failed_result("凭据验证失败（米游币社区），请稍后重试")
    return None


async def persist_account(account: UserAccount, bbs_uid: str) -> Union[None, TaskResult]:
    """原子写入配置。已有账号保留原有 device_id_ios/device_fp，只更新 cookies。

    在任何 ``users`` / ``accounts`` 变更前深拷贝完整 ``ConfigData``；保存失败时恢复
    完整快照，确保新 UID、空 ``UserData``、账号对象和已有配置均不残留。保存成功后才
    向上层返回成功。
    """
    import copy
    from models import UserData

    # 在任何变更前先备份完整内存配置
    backup = copy.deepcopy(ConfigDataManager.config_data)

    if bbs_uid not in ConfigDataManager.config_data.users:
        ConfigDataManager.config_data.users[bbs_uid] = UserData()

    user_data = ConfigDataManager.config_data.users[bbs_uid]
    existing = user_data.accounts.get(bbs_uid)

    if existing:
        existing.cookies = account.cookies
    else:
        user_data.accounts[bbs_uid] = account

    try:
        ConfigDataManager.save_config()
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        ConfigDataManager.config_data = backup
        return _failed_result("登录成功，但保存配置失败")
    return None


async def _mys_login_impl() -> Union[TaskResult, str]:
    """米游社登录实现（Passport Web QR 方案，可选 App QR 回退）"""
    session = _build_login_session()
    provider_label = "Web" if session.provider == QrLoginProvider.WEB else "App"
    logger.info(f"开始 {provider_label} QR 登录, device_id={session.device_id[:8]}...")

    try:
        # 1. 创建并推送二维码
        challenge = await create_and_publish_qr(session)
        if isinstance(challenge, TaskResult):
            return challenge

        # 2. 等待确认
        poll_result = await wait_for_confirmation(session, challenge)
        if isinstance(poll_result, TaskResult):
            return poll_result

        # 3. 构建和验证账号
        account_or_err = await build_and_validate_account(poll_result, session)
        if isinstance(account_or_err, TaskResult):
            # Web QR 缺少 stoken 且启用 App QR 回退时，尝试 App QR
            if (
                session.provider == QrLoginProvider.WEB
                and project_config.preference.qrcode_app_fallback
            ):
                logger.info("Web QR 凭据不完整，回退到 App QR")
                return await _app_qr_fallback()
            return account_or_err
        account = account_or_err

        # 3.1 凭据业务验证
        verify_err = await verify_credentials(account)
        if verify_err:
            return verify_err

        # 4. 持久化
        bbs_uid = account.bbs_uid or ""
        err = await persist_account(account, bbs_uid)
        if err:
            return err
    finally:
        await close_session(session)

    logger.info(f"米游社账户 {bbs_uid[:4]}**** 绑定成功")
    return _success_result(f"米游社账户 {bbs_uid[:4]}**** 绑定成功")


async def _app_qr_fallback() -> TaskResult:
    """App QR 回退：Web QR 失败时创建新的 App 二维码并等待确认。"""
    session = _build_login_session()
    session.provider = QrLoginProvider.APP
    session.app_id = "ddxf5dufpuyo"
    session.client_type = "3"
    session.user_agent = "HYPContainer/1.3.3.182"
    session.client = None
    logger.info(f"开始 App QR 回退登录, device_id={session.device_id[:8]}...")

    try:
        challenge = await create_and_publish_qr(session)
        if isinstance(challenge, TaskResult):
            return challenge

        poll_result = await wait_for_confirmation(session, challenge)
        if isinstance(poll_result, TaskResult):
            return poll_result

        account_or_err = await build_and_validate_account(poll_result, session)
        if isinstance(account_or_err, TaskResult):
            return account_or_err
        account = account_or_err

        verify_err = await verify_credentials(account)
        if verify_err:
            return verify_err

        bbs_uid = account.bbs_uid or ""
        err = await persist_account(account, bbs_uid)
        if err:
            return err
    finally:
        await close_session(session)

    logger.info(f"米游社账户 {bbs_uid[:4]}**** 绑定成功（App QR 回退）")
    return _success_result(f"米游社账户 {bbs_uid[:4]}**** 绑定成功")
