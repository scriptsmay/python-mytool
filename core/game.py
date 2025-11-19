import asyncio
from typing import Optional, Iterable, Dict

from pydantic import BaseModel, ConfigDict

from services import BaseGameSign, BaseMission, get_missions_state
from services.common import genshin_note, get_game_record, starrail_note
from models import (
    MissionStatus,
    plugin_config,
    UserData,
    GenshinNoteNotice,
    StarRailNoteNotice,
)
from utils import get_file, logger, push, get_unique_users, get_validate


async def manually_game_sign():
    """进行游戏签到"""

    msgs_list = []

    logger.info("⏳开始为所有用户执行游戏签到...")
    # 确保顺序执行
    users = list(get_unique_users())  # 转换为列表确保顺序
    for user_id_, user_ in users:
        logger.info(f"⏳开始为用户 {user_id_} 执行游戏签到...")
        await perform_game_sign(user=user_, msgs_list=msgs_list)
        logger.info(f"✅用户 {user_id_} 的游戏签到完成")

    if msgs_list:
        # 每个消息单独一行，更清晰
        result_msg = "\n".join([f"  • {msg}" for msg in msgs_list])
        logger.info(f"🎉执行完成，共 {len(msgs_list)} 条记录:\n{result_msg}")
    else:
        logger.info("🎉执行完成，无记录消息")


async def manually_bbs_sign():
    """顺序执行所有用户的米游币任务"""

    msgs_list = []

    users = list(get_unique_users())  # 转换为列表确保顺序
    for user_id_, user_ in users:
        logger.info(f"⏳开始为用户 {user_id_} 执行米游币任务...")
        await perform_bbs_sign(user=user_, msgs_list=msgs_list)
        logger.info(f"✅用户 {user_id_} 的米游币任务完成")

    # logger.info("🎉所有用户的米游币任务执行完成")
    if msgs_list:
        # 每个消息单独一行，更清晰
        result_msg = "\n".join([f"  • {msg}" for msg in msgs_list])
        logger.info(f"🎉执行完成，共 {len(msgs_list)} 条记录:\n{result_msg}")
    else:
        logger.info("🎉执行完成，无记录消息")


async def perform_game_sign(user: UserData, msgs_list=None):
    """
    执行游戏签到函数，并发送给用户签到消息。

    :param user: 用户数据
    :param user_ids: 发送通知的所有用户ID
    :param matcher: 事件响应器
    :param event: 事件
    """
    failed_accounts = []
    for account in user.accounts.values():
        # 自动签到时，要求用户打开了签到功能；手动签到时都可以调用执行。
        if not account.enable_game_sign:
            continue
        signed = False
        """是否已经完成过签到"""
        game_record_status, records = await get_game_record(account)
        if not game_record_status:
            logger.warning(
                f"⚠️账户 {account.display_name} 获取游戏账号信息失败，请重新尝试"
            )
            continue
        games_has_record = []

        for class_type in BaseGameSign.available_game_signs:
            signer = class_type(account, records)
            if not signer.has_record:
                continue
            else:
                games_has_record.append(signer)
                if class_type.en_name not in account.game_sign_games:
                    continue
            get_info_status, info = await signer.get_info(account.platform)
            if not get_info_status:
                logger.warning(f"⚠️账户 {account.display_name} 获取签到记录失败")
            else:
                signed = info.is_sign

            # 若没签到，则进行签到功能；若获取今日签到情况失败，仍可继续
            if (get_info_status and not info.is_sign) or not get_info_status:
                sign_status, mmt_data = await signer.sign(account.platform)
                if sign_status.need_verify:
                    if plugin_config.preference.geetest_url or user.geetest_url:
                        for i in range(3):
                            msgs_list.append(
                                f"⏳[验证码{i}] 正在尝试完成人机验证，请稍后..."
                            )

                            if not (
                                geetest_result := await get_validate(
                                    user, mmt_data.gt, mmt_data.challenge
                                )
                            ):
                                continue  # 如果没有获取到validate不进行签到，直接重试
                            sign_status, mmt_data = await signer.sign(
                                account.platform, mmt_data, geetest_result
                            )
                            if sign_status:
                                break

                if not sign_status and (user.enable_notice):
                    if sign_status.login_expired:
                        message = f"⚠️账户 {account.display_name} 🎮『{signer.name}』签到时服务器返回登录失效，请尝试重新登录绑定账户"
                    elif sign_status.need_verify:
                        message = (
                            f"⚠️账户 {account.display_name} 🎮『{signer.name}』签到时可能遇到验证码拦截，"
                            "请尝试使用命令『/账号设置』更改设备平台，若仍失败请手动前往米游社签到"
                        )
                    else:
                        message = f"⚠️账户 {account.display_name} 🎮『{signer.name}』签到失败，请稍后再试"
                    msgs_list.append(message)
                    if user.enable_notice:
                        # todo 发送通知
                        push(push_message=message)

                    await asyncio.sleep(plugin_config.preference.sleep_time)
                    continue

                await asyncio.sleep(plugin_config.preference.sleep_time)

            # 用户打开通知或手动签到时，进行通知
            if user.enable_notice:
                get_info_status, info = await signer.get_info(account.platform)
                get_award_status, awards = await signer.get_rewards()
                if not get_info_status or not get_award_status:
                    msg = f"⚠️账户 {account.display_name} 🎮『{signer.name}』获取签到结果失败！请手动前往米游社查看"
                else:
                    award = awards[info.total_sign_day - 1]
                    if info.is_sign:
                        status = "签到成功！" if not signed else "已经签到过了"
                        msg = (
                            f"🪪账户 {account.display_name}"
                            f"\n🎮『{signer.name}』"
                            f"\n🎮状态: {status}"
                            f"\n{signer.record.nickname}·{signer.record.level}"
                            "\n\n🎁今日签到奖励："
                            f"\n{award.name} * {award.cnt}"
                            f"\n\n📅本月签到次数：{info.total_sign_day}"
                        )
                        img_file = await get_file(award.icon)
                        msgs_list.append(msg)
                        push(push_message=msg, img_file=img_file)
                        # TODO 发送图片 img_file
                    else:
                        msg = (
                            f"⚠️账户 {account.display_name} 🎮『{signer.name}』签到失败！请尝试重新签到，"
                            "若多次失败请尝试重新登录绑定账户"
                        )

                push(push_message=msg)
            await asyncio.sleep(plugin_config.preference.sleep_time)

        if msgs_list:
            for msg in msgs_list:
                push(push_message=msg)

        if not games_has_record:
            push(
                push_message=f"⚠️您的米游社账户 {account.display_name} 下不存在任何游戏账号，已跳过签到"
            )

    # 如果全部登录失效，则关闭通知
    if len(failed_accounts) == len(user.accounts):
        user.enable_notice = False
        # PluginDataManager.write_plugin_data()


async def perform_bbs_sign(user: UserData, msgs_list=None):
    """
    执行米游币任务函数，并发送给用户任务执行消息。

    :param user: 用户数据
    :param user_ids: 发送通知的所有用户ID
    :param matcher: 事件响应器
    """
    failed_accounts = []
    for account in user.accounts.values():
        # 自动执行米游币任务时，要求用户打开了米游币任务功能；手动执行米游币任务时都可以调用执行。
        if not account.enable_mission:
            continue

        missions_state_status, missions_state = await get_missions_state(account)
        if not missions_state_status:
            if missions_state_status.login_expired:
                logger.warning(f"⚠️账户 {account.display_name} 登录失效，请重新登录")

            logger.info(
                f"⚠️账户 {account.display_name} 获取任务完成情况请求失败，你可以手动前往App查看"
            )

            continue
        myb_before_mission = missions_state.current_myb

        # 在此处进行判断。因为如果在多个分区执行任务，会在完成之前就已经达成米游币任务目标，导致其他分区任务不会执行。
        finished = all(
            current == mission.threshold
            for mission, current in missions_state.state_dict.values()
        )
        if not finished:
            if not account.mission_games:
                msgs_list.append(
                    f"⚠️🆔账户 {account.display_name} 未设置米游币任务目标分区，将跳过执行"
                )
            for class_name in account.mission_games:
                class_type = BaseMission.available_games.get(class_name)
                if not class_type:
                    msgs_list.append(
                        f"⚠️🆔账户 {account.display_name} 米游币任务目标分区『{class_name}』未找到，将跳过该分区"
                    )
                    continue
                mission_obj = class_type(account)
                msgs_list.append(
                    f"🆔账户 {account.display_name} ⏳开始在分区『{class_type.name}』执行米游币任务..."
                )

                # 执行任务
                sign_status, read_status, like_status, share_status = (
                    MissionStatus(),
                    MissionStatus(),
                    MissionStatus(),
                    MissionStatus(),
                )
                sign_points: Optional[int] = None
                for key_name in missions_state.state_dict:
                    if key_name == BaseMission.SIGN:
                        sign_status, sign_points = await mission_obj.sign(user)
                    elif key_name == BaseMission.VIEW:
                        read_status = await mission_obj.read()
                    elif key_name == BaseMission.LIKE:
                        like_status = await mission_obj.like()
                    elif key_name == BaseMission.SHARE:
                        share_status = await mission_obj.share()

                msgs_list.append(
                    f"🆔账户 {account.display_name} 🎮『{class_type.name}』米游币任务执行情况：\n"
                    f"📅签到：{'✓' if sign_status else '✕'} +{sign_points or '0'} 米游币🪙\n"
                    f"📰阅读：{'✓' if read_status else '✕'}\n"
                    f"❤️点赞：{'✓' if like_status else '✕'}\n"
                    f"↗️分享：{'✓' if share_status else '✕'}"
                )

        # 用户打开通知或手动任务时，进行通知
        if user.enable_notice:
            missions_state_status, missions_state = await get_missions_state(account)
            if not missions_state_status:
                if missions_state_status.login_expired:
                    msgs_list.append(
                        f"⚠️账户 {account.display_name} 登录失效，请重新登录"
                    )
                    continue
                msgs_list.append(
                    f"⚠️账户 {account.display_name} 获取任务完成情况请求失败，你可以手动前往App查看"
                )
                continue
            if all(
                current == mission.threshold
                for mission, current in missions_state.state_dict.values()
            ):
                notice_string = "🎉已完成今日米游币任务"
            else:
                notice_string = "⚠️今日米游币任务未全部完成"

            msg = f"{notice_string}" f"\n🆔账户 {account.display_name}"
            for key_name, (mission, current) in missions_state.state_dict.items():
                if key_name == BaseMission.SIGN:
                    mission_name = "📅签到"
                elif key_name == BaseMission.VIEW:
                    mission_name = "📰阅读"
                elif key_name == BaseMission.LIKE:
                    mission_name = "❤️点赞"
                elif key_name == BaseMission.SHARE:
                    mission_name = "↗️分享"
                else:
                    mission_name = mission.mission_key
                msg += (
                    f"\n{mission_name}：{'✓' if current >= mission.threshold else '✕'}"
                )
            msg += (
                f"\n🪙获得米游币: {missions_state.current_myb - myb_before_mission}"
                f"\n💰当前米游币: {missions_state.current_myb}"
            )

            msgs_list.append(msg)

        if msgs_list:
            for msg in msgs_list:
                # TODO 发送通知
                push(push_message=msg)

    # 如果全部登录失效，则关闭通知
    if len(failed_accounts) == len(user.accounts):
        user.enable_notice = False
        # PluginDataManager.write_plugin_data()


class NoteNoticeStatus(BaseModel):
    """
    账号便笺通知状态
    """

    genshin: GenshinNoteNotice = GenshinNoteNotice(
        current_resin=False,
        current_resin_full=False,
        current_home_coin=False,
        transformer=False,
    )
    starrail: StarRailNoteNotice = StarRailNoteNotice(
        current_stamina=False,
        current_stamina_full=False,
        current_train_score=False,
        current_rogue_score=False,
    )

    model_config = ConfigDict(extra="ignore")


note_notice_status: Dict[str, NoteNoticeStatus] = {}
"""记录账号对应的便笺通知状态"""


async def genshin_note_check(user: UserData, user_ids: Iterable[str]):
    """
    查看原神实时便笺函数，并发送给用户任务执行消息。

    :param user: 用户对象
    :param user_ids: 发送通知的所有用户ID
    :param matcher: 事件响应器
    """
    for account in user.accounts.values():
        note_notice_status.setdefault(account.bbs_uid, NoteNoticeStatus())
        genshin_notice = note_notice_status[account.bbs_uid].genshin
        if account.enable_resin and "GenshinImpact" in account.game_sign_games:
            genshin_board_status, note = await genshin_note(account)
            if not genshin_board_status:
                if genshin_board_status.login_expired:
                    logger.warning(f"⚠️账户 {account.display_name} 登录失效，请重新登录")
                elif genshin_board_status.no_genshin_account:
                    logger.warning(
                        f"⚠️账户 {account.display_name} 没有绑定任何原神账户，请绑定后再重试"
                    )
                elif genshin_board_status.need_verify:
                    logger.warning(
                        f"⚠️账户 {account.display_name} 获取实时便笺时被人机验证阻拦"
                    )
                logger.warning(
                    f"⚠️账户 {account.display_name} 获取实时便笺请求失败，你可以手动前往App查看"
                )
                continue

            msg = ""
            # 手动查询体力时，无需判断是否溢出
            do_notice = False
            """记录是否需要提醒"""
            # 体力溢出提醒
            if note.current_resin >= account.user_resin_threshold:
                # 防止重复提醒
                if not genshin_notice.current_resin_full:
                    if note.current_resin == 200:
                        genshin_notice.current_resin_full = True
                        msg += "❕您的树脂已经满啦\n"
                        do_notice = True
                    elif not genshin_notice.current_resin:
                        genshin_notice.current_resin_full = False
                        genshin_notice.current_resin = True
                        msg += "❕您的树脂已达到提醒阈值\n"
                        do_notice = True
            else:
                genshin_notice.current_resin = False
                genshin_notice.current_resin_full = False

            # 洞天财瓮溢出提醒
            if note.current_home_coin == note.max_home_coin:
                # 防止重复提醒
                if not genshin_notice.current_home_coin:
                    genshin_notice.current_home_coin = True
                    msg += "❕您的洞天财瓮已经满啦\n"
                    do_notice = True
            else:
                genshin_notice.current_home_coin = False

            # 参量质变仪就绪提醒
            if note.transformer:
                if note.transformer_text == "已准备就绪":
                    # 防止重复提醒
                    if not genshin_notice.transformer:
                        genshin_notice.transformer = True
                        msg += "❕您的参量质变仪已准备就绪\n\n"
                        do_notice = True
                else:
                    genshin_notice.transformer = False
            else:
                genshin_notice.transformer = True

            if not do_notice:
                logger.info(
                    f"原神实时便笺：账户 {account.display_name} 树脂:{note.current_resin},未满足推送条件"
                )
                return

            msg += (
                "❖原神·实时便笺❖"
                f"\n🆔账户 {account.display_name}"
                f"\n⏳树脂数量：{note.current_resin} / 200"
                f"\n⏱️树脂{note.resin_recovery_text}"
                f"\n🕰️探索派遣：{note.current_expedition_num} / {note.max_expedition_num}"
                f"\n📅每日委托：{4 - note.finished_task_num} 个任务未完成"
                f"\n💰洞天财瓮：{note.current_home_coin} / {note.max_home_coin}"
                f"\n🎰参量质变仪：{note.transformer_text if note.transformer else 'N/A'}"
            )

            # TODO 测试日志和推送
            logger.info(msg)
            push(push_message=msg)


async def starrail_note_check(user: UserData, user_ids: Iterable[str]):
    """
    查看星铁实时便笺函数，并发送给用户任务执行消息。

    :param user: 用户对象
    :param user_ids: 发送通知的所有用户ID
    :param matcher: 事件响应器
    """
    for account in user.accounts.values():
        note_notice_status.setdefault(account.bbs_uid, NoteNoticeStatus())
        starrail_notice = note_notice_status[account.bbs_uid].starrail
        if account.enable_resin and "StarRail" in account.game_sign_games:
            starrail_board_status, note = await starrail_note(account)
            if not starrail_board_status:
                if starrail_board_status.login_expired:
                    logger.warning(f"⚠️账户 {account.display_name} 登录失效，请重新登录")
                elif starrail_board_status.no_starrail_account:
                    logger.warning(
                        f"⚠️账户 {account.display_name} 没有绑定任何星铁账户，请绑定后再重试"
                    )
                elif starrail_board_status.need_verify:
                    logger.warning(
                        f"⚠️账户 {account.display_name} 获取实时便笺时被人机验证阻拦"
                    )
                logger.warning(
                    f"⚠️账户 {account.display_name} 获取实时便笺请求失败，你可以手动前往App查看"
                )
                continue

            msg = ""
            # 手动查询体力时，无需判断是否溢出
            do_notice = False
            """记录是否需要提醒"""
            # 体力溢出提醒
            if note.current_stamina >= account.user_stamina_threshold:
                # 防止重复提醒
                if not starrail_notice.current_stamina_full:
                    if note.current_stamina >= note.max_stamina:
                        starrail_notice.current_stamina_full = True
                        msg += "❕您的开拓力已经溢出\n"
                        if note.current_train_score != note.max_train_score:
                            msg += "❕您的每日实训未完成\n"
                        do_notice = True
                    elif not starrail_notice.current_stamina:
                        starrail_notice.current_stamina_full = False
                        starrail_notice.current_stamina = True
                        msg += "❕您的开拓力已达到提醒阈值\n"
                        if note.current_train_score != note.max_train_score:
                            msg += "❕您的每日实训未完成\n"
                        do_notice = True
            else:
                starrail_notice.current_stamina = False
                starrail_notice.current_stamina_full = False

            # 每周模拟宇宙积分提醒
            if note.current_rogue_score != note.max_rogue_score:
                if plugin_config.preference.notice_time:
                    msg += "❕您的模拟宇宙积分还没打满\n\n"
                    do_notice = True

            if not do_notice:
                logger.info(
                    f"崩铁实时便笺：账户 {account.display_name} 开拓力:{note.current_stamina},未满足推送条件"
                )
                return

            msg += (
                "❖星穹铁道·实时便笺❖"
                f"\n🆔账户 {account.display_name}"
                f"\n⏳开拓力数量：{note.current_stamina} / {note.max_stamina}"
                f"\n⏱开拓力{note.stamina_recover_text}"
                f"\n📒每日实训：{note.current_train_score} / {note.max_train_score}"
                f"\n📅每日委托：{note.accepted_expedition_num} / 4"
                f"\n🌌模拟宇宙：{note.current_rogue_score} / {note.max_rogue_score}"
            )

            # TODO 测试日志和推送
            logger.info(msg)
            push(push_message=msg)
