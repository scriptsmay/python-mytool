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
    create_qr_login,
    query_qr_login,
)
from utils import generate_device_id, generate_qr_img, logger, push
from config.task_logger import execute_task_with_logging, TaskResult

_PUSH_TITLE_SUCCESS = "米游社登录成功"
_PUSH_TITLE_FAILURE = "米游社登录失败"


async def mys_login() -> TaskResult:
    """米游社登录"""
    return await execute_task_with_logging("米游社登录", _mys_login_impl)


def _build_login_session() -> LoginSession:
    """根据配置构建 LoginSession"""
    provider = QrLoginProvider.WEB
    if project_config.preference.qrcode_provider == "app":
        provider = QrLoginProvider.APP

    return LoginSession(
        provider=provider,
        device_id=generate_device_id(),
        app_id="bll8iq97cem8",
        client_type="1",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/16.0 Safari/605.1.15"
            if provider == QrLoginProvider.WEB
            else "HYPContainer/1.3.3.182"
        ),
    )


async def create_and_publish_qr(session: LoginSession) -> Union[QrCodeChallenge, str]:
    """创建二维码并推送。返回 QrCodeChallenge 或错误消息。"""
    try:
        challenge = await create_qr_login(session)
    except Exception as e:
        logger.error(f"创建二维码失败: {e}")
        return "获取登录二维码失败，请稍后重试"

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
) -> Union[QrLoginPollResult, str]:
    """轮询直到确认、过期或超时。返回 QrLoginPollResult 或错误消息。"""
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
            return "二维码已过期，请重新运行登录"
        elif result.state == QrLoginState.CANCELED:
            return "登录已取消"
        elif result.state == QrLoginState.UNKNOWN:
            logger.warning(f"未知二维码状态: retcode={result.retcode}, msg={result.message}")

        await asyncio.sleep(poll_interval)

    return "已扫码但未在App中确认，请重新运行登录时超时"


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
) -> Union[UserAccount, str]:
    """从轮询结果构建 UserAccount 并验证凭据有效性。"""
    raw_cookies = poll_result.cookies
    if not raw_cookies:
        return "扫码成功，但登录凭据不完整"

    cookies = BBSCookies.from_login_cookie(raw_cookies)
    bbs_uid = _extract_uid(cookies)

    if not bbs_uid:
        return "扫码成功，但登录凭据不完整：缺少账号标识"
    if not cookies.cookie_token and not cookies.cookie_token_v2:
        return "扫码成功，但登录凭据不完整：缺少 cookie_token"

    cookies.bbs_uid = bbs_uid

    account = UserAccount(
        phone_number=None,
        cookies=cookies,
        device_id_ios=session.device_id,
        device_id_android=generate_device_id(),
    )

    return account


async def persist_account(account: UserAccount, bbs_uid: str) -> str:
    """原子写入配置。保留用户自定义的签到开关、阈值、平台和设备配置。"""
    from models import UserData

    if bbs_uid not in ConfigDataManager.config_data.users:
        ConfigDataManager.config_data.users[bbs_uid] = UserData()

    user_data = ConfigDataManager.config_data.users[bbs_uid]
    existing = user_data.accounts.get(bbs_uid)

    if existing:
        existing.cookies = account.cookies
        existing.device_id_ios = account.device_id_ios
        existing.device_fp = account.device_fp
    else:
        user_data.accounts[bbs_uid] = account

    try:
        ConfigDataManager.save_config()
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return "登录成功，但保存配置失败"
    return ""


async def _mys_login_impl() -> Union[str, TaskResult]:
    """米游社登录实现（Passport Web QR 方案）"""
    session = _build_login_session()
    provider_label = "Web" if session.provider == QrLoginProvider.WEB else "App"
    logger.info(f"开始 {provider_label} QR 登录, device_id={session.device_id[:8]}...")

    # 1. 创建并推送二维码
    challenge = await create_and_publish_qr(session)
    if isinstance(challenge, str):
        return challenge

    # 2. 等待确认
    poll_result = await wait_for_confirmation(session, challenge)
    if isinstance(poll_result, str):
        return poll_result

    # 3. 构建和验证账号
    account_or_err = await build_and_validate_account(poll_result, session)
    if isinstance(account_or_err, str):
        return account_or_err
    account = account_or_err

    # 4. 持久化
    bbs_uid = account.bbs_uid or ""
    err = await persist_account(account, bbs_uid)
    if err:
        return err

    logger.info(f"米游社账户 {bbs_uid[:4]}**** 绑定成功")
    return f"米游社账户 {bbs_uid[:4]}**** 绑定成功"
