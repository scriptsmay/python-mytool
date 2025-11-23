import asyncio
import json
from typing import Union


from services.common import (
    get_ltoken_by_stoken,
    get_cookie_token_by_stoken,
    get_device_fp,
    fetch_game_token_qrcode,
    query_game_token_qrcode,
    get_token_by_game_token,
    get_cookie_token_by_game_token,
)
from models import (
    ConfigDataManager,
    project_config,
    UserAccount,
    BBSCookies,
    UserData,
    QueryGameTokenQrCodeStatus,
    GetCookieStatus,
)
from utils import logger, generate_device_id, generate_qr_img


async def mys_login():
    """米游社登录"""

    message_box = []

    # 1. 获取 GameToken 登录二维码
    device_id = generate_device_id()
    login_status, fetch_qrcode_ret = await fetch_game_token_qrcode(
        device_id, project_config.preference.game_token_app_id
    )
    if fetch_qrcode_ret:
        qrcode_url, qrcode_ticket = fetch_qrcode_ret
        logger.info(f"等待扫描：{project_config.preference.qrcode_wait_time}秒")
        # image_bytes = generate_qr_img(qrcode_url)
        try:
            # 在终端打印二维码
            logger.qr(qrcode_url, "请用米游社App扫描二维码进行登录")
            # logger.info(msg_img)
        except Exception as e:
            logger.exception("发送包含二维码的登录消息失败")
            # message_box.append()

        # 2. 从二维码登录获取 GameToken
        qrcode_query_times = round(
            project_config.preference.qrcode_wait_time
            / project_config.preference.qrcode_query_interval
        )
        bbs_uid, game_token = None, None
        for _ in range(qrcode_query_times):
            login_status, query_qrcode_ret = await query_game_token_qrcode(
                qrcode_ticket, device_id, project_config.preference.game_token_app_id
            )
            if query_qrcode_ret:
                bbs_uid, game_token = query_qrcode_ret
                logger.info(f"✅用户 {bbs_uid} 成功获取 game_token: {game_token}")
                break
            elif login_status.qrcode_expired:
                logger.warning("⚠️二维码已过期，登录失败")
            elif not login_status:
                await asyncio.sleep(project_config.preference.qrcode_query_interval)
                continue

        if bbs_uid and game_token:
            cookies = BBSCookies()
            cookies.bbs_uid = bbs_uid
            # 定义 bbs_uid 为 user_id
            user_id = bbs_uid

            # 修正：检查用户是否存在，不存在则创建
            if user_id not in ConfigDataManager.config_data.users:

                ConfigDataManager.config_data.users[user_id] = UserData()

            user = ConfigDataManager.config_data.users[user_id]
            account = ConfigDataManager.config_data.users[user_id].accounts.get(bbs_uid)
            """当前的账户数据对象"""
            if not account or not account.cookies:
                user.accounts.update(
                    {
                        bbs_uid: UserAccount(
                            phone_number=None,
                            cookies=cookies,
                            device_id_ios=device_id,
                            device_id_android=generate_device_id(),
                        )
                    }
                )
                account = user.accounts[bbs_uid]
            else:
                account.cookies.update(cookies)
            fp_status, account.device_fp = await get_device_fp(device_id)
            if fp_status:
                logger.info(f"✅用户 {bbs_uid} 成功获取 device_fp: {account.device_fp}")
            ConfigDataManager.save_config()

            if login_status:
                # 3. 通过 GameToken 获取 stoken_v2
                login_status, cookies = await get_token_by_game_token(
                    bbs_uid, game_token
                )
                if login_status:
                    logger.success(
                        f"用户 {bbs_uid} 成功获取 stoken_v2: {cookies.stoken_v2}"
                    )
                    account.cookies.update(cookies)
                    ConfigDataManager.save_config()

                    if account.cookies.stoken_v2:
                        # 5. 通过 stoken_v2 获取 ltoken
                        login_status, cookies = await get_ltoken_by_stoken(
                            account.cookies, device_id
                        )
                        if login_status:
                            logger.success(
                                f"用户 {bbs_uid} 成功获取 ltoken: {cookies.ltoken}"
                            )
                            account.cookies.update(cookies)
                            ConfigDataManager.save_config()

                        # 6.1. 通过 stoken_v2 获取 cookie_token
                        login_status, cookies = await get_cookie_token_by_stoken(
                            account.cookies, device_id
                        )
                        if login_status:
                            logger.success(
                                f"用户 {bbs_uid} 成功获取 cookie_token: {cookies.cookie_token}"
                            )
                            account.cookies.update(cookies)
                            ConfigDataManager.save_config()

                            logger.success(f"米游社账户 {bbs_uid} 绑定成功")
                            logger.info(f"🎉米游社账户 {bbs_uid} 绑定成功")
                    else:
                        # 6.2. 通过 GameToken 获取 cookie_token
                        login_status, cookies = await get_cookie_token_by_game_token(
                            bbs_uid, game_token
                        )
                        if login_status:
                            logger.success(
                                f"用户 {bbs_uid} 成功获取 cookie_token: {cookies.cookie_token}"
                            )
                            account.cookies.update(cookies)
                            ConfigDataManager.save_config()
        else:
            logger.warning("⚠️获取二维码扫描状态超时，请尝试重新登录")

    if not login_status:
        notice_text = "⚠️登录失败："
        if isinstance(login_status, QueryGameTokenQrCodeStatus):
            if login_status.qrcode_expired:
                notice_text += "登录二维码已过期！"
        if isinstance(login_status, GetCookieStatus):
            if login_status.missing_bbs_uid:
                notice_text += "Cookies缺少 bbs_uid（例如 ltuid, stuid）"
            elif login_status.missing_login_ticket:
                notice_text += "Cookies缺少 login_ticket！"
            elif login_status.missing_cookie_token:
                notice_text += "Cookies缺少 cookie_token！"
            elif login_status.missing_stoken:
                notice_text += "Cookies缺少 stoken！"
            elif login_status.missing_stoken_v1:
                notice_text += "Cookies缺少 stoken_v1"
            elif login_status.missing_stoken_v2:
                notice_text += "Cookies缺少 stoken_v2"
            elif login_status.missing_mid:
                notice_text += "Cookies缺少 mid"
        if login_status.login_expired:
            notice_text += "登录失效！"
        elif login_status.incorrect_return:
            notice_text += "服务器返回错误！"
        elif login_status.network_error:
            notice_text += "网络连接失败！"
        else:
            notice_text += "未知错误！"
        notice_text += " 如果部分步骤成功，你仍然可以尝试获取收货地址、兑换等功能"
        logger.error(notice_text)

        message_box.append(notice_text)
    return message_box
