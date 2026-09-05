# game.py
import asyncio
from typing import Dict, List, Type

from pydantic import BaseModel, ConfigDict, Field

from services import BaseGameSign, BaseMission, get_missions_state
from services.common import genshin_note, get_game_record, starrail_note
from models import (
    MissionStatus,
    project_config,
    UserData,
    UserAccount,
    GenshinNote,
    GenshinNoteNotice,
    StarRailNote,
    StarRailNoteNotice,
    BaseApiStatus,
    MissionState,
)
from utils import (
    get_file,
    logger,
    push,
    init_config,
    get_unique_users,
    get_validate,
    run_task,
)
from config.task_logger import execute_task_with_logging, TaskResult, TaskLogger


# 初始化推送配置
try:
    init_config(project_config.push_config)
except Exception as e:
    logger.error(f"初始化消息推送配置失败: {e}")
    init_config(enable=False)


async def common_task_run(task_name: str, task_func) -> TaskResult:
    async with TaskLogger(task_name) as task_logger:
        users = list(get_unique_users())

        if not users:
            task_logger.log_failure("未配置任何用户账户")
            return task_logger.get_result()

        try:
            # 运行任务
            task_result = await run_task(task_name, users, task_func)

            total_success_cnt = task_result[0]
            total_failure_cnt = task_result[1]
            detail_task_name = task_result[2]
            status_fmt = task_result[3]
            message_content = task_result[4]

            if total_success_cnt == 0 and total_failure_cnt == 0:
                task_logger.log_warning("没有有效的账号配置")
                return task_logger.get_result()

            # 记录统计信息
            if total_success_cnt > 0:
                task_logger.log_success(f"成功签到 {total_success_cnt} 个账号")
            if total_failure_cnt > 0:
                task_logger.log_failure(f"失败 {total_failure_cnt} 个账号")

            title = f"{detail_task_name} - {status_fmt}"
            content = f"{title}\n\n{message_content}"

            task_logger.log_info(f"{task_name}任务完成: {status_fmt}")

            result = task_logger.get_result()
            result.message = content  # 使用详细的消息内容

            return result

        except Exception as e:
            task_logger.log_failure(f"任务执行失败: {e}")
            return task_logger.get_result()


async def manually_game_sign() -> TaskResult:
    """进行游戏签到"""
    return await common_task_run("游戏签到", _game_sign_impl)


async def manually_bbs_sign() -> TaskResult:
    """执行米游币任务"""

    return await common_task_run("米游币任务", _bbs_sign_impl)


async def manually_genshin_note_check() -> TaskResult:
    """进行原神便签查询"""
    return await common_task_run("原神便签查询", _genshin_note_impl)


async def manually_starrail_note_check() -> TaskResult:
    """进行星穹铁道便签查询"""
    return await common_task_run("星穹铁道便签查询", _starrail_note_impl)


async def _genshin_note_impl(user: UserData) -> str:
    """原神便签查询实现"""
    msgs_list = []
    await genshin_note_check(user=user, msgs_list=msgs_list)

    return _format_result(msgs_list, "原神便签")


async def _starrail_note_impl(user: UserData) -> str:
    """星穹铁道便签查询实现"""
    msgs_list = []
    await starrail_note_check(user=user, msgs_list=msgs_list)

    return _format_result(msgs_list, "星穹铁道便签")


def _format_result(msgs_list: List[str], task_name: str) -> str:
    """格式化结果消息"""
    if msgs_list:
        result_msg = "\n----------------\n".join([f"{msg}" for msg in msgs_list])
        # logger.info(f"🎉{task_name}执行完成，共 {len(msgs_list)} 条记录")
        return result_msg
    else:
        # logger.info(f"🎉{task_name}执行完成，无记录消息")
        return "无记录"


async def _game_sign_impl(user: UserData) -> str:
    """
    执行游戏签到

    Args:
        user (UserData): 单个用户数据

    Returns:
        str: 执行结果消息
    """
    msgs_list = []

    for j, account in enumerate(user.accounts.values(), start=1):
        logger.info(f"⏳开始执行游戏签到...")
        await _process_account_game_sign(account, user, msgs_list)
        logger.info(f"✅游戏角色签到完成")

    return _format_result(msgs_list, "")


async def _process_account_game_sign(
    account: UserAccount,
    user: UserData,
    msgs_list: List[str],
) -> None:
    """处理单个账户的游戏签到"""
    game_record_status, records = await get_game_record(account)
    if not game_record_status:
        logger.warning(f"⚠️ 获取游戏账号信息失败，请重新尝试")
        return

    games_with_record = [
        class_type(account, records)
        for class_type in BaseGameSign.available_game_signs
        if class_type(account, records).has_record
    ]

    if not games_with_record:
        message = f"⚠️ 用户不存在任何游戏账号，已跳过签到"
        msgs_list.append(message)
        return

    for k, signer in enumerate(games_with_record, start=1):
        if signer.en_name not in account.game_sign_games:
            continue
        game_detail = f"游戏({signer.name})"
        logger.info(f"⏳开始为{game_detail}执行签到...")
        await _process_single_game_sign(signer, account, user, msgs_list, game_detail)
        logger.info(f"✅{game_detail}签到完成")


async def _process_single_game_sign(
    signer: BaseGameSign,
    account: UserAccount,
    user: UserData,
    msgs_list: List[str],
    game_detail: str,
) -> None:
    """处理单个游戏的签到"""
    get_info_status, info = await signer.get_info(account.platform)
    signed = info.is_sign if get_info_status else False

    # 尝试签到
    if not get_info_status or not signed:
        await _attempt_sign(signer, account, user, msgs_list, game_detail)

    # 获取签到结果
    await _process_sign_result(signer, account, msgs_list, signed, game_detail)


async def _attempt_sign(
    signer: BaseGameSign,
    account: UserAccount,
    user: UserData,
    msgs_list: List[str],
    game_detail: str,
) -> None:
    """尝试进行签到"""
    sign_status, mmt_data = await signer.sign(account.platform)

    if sign_status.need_verify:
        await _handle_verification(
            signer, account, user, mmt_data, msgs_list, game_detail
        )

    await asyncio.sleep(project_config.preference.sleep_time)


async def _handle_verification(
    signer: BaseGameSign,
    account: UserAccount,
    user: UserData,
    mmt_data,
    msgs_list: List[str],
    game_detail: str,
) -> None:
    """处理人机验证"""
    for i in range(3):
        logger.info(f"⏳{game_detail} [验证码{i+1}] 正在尝试完成人机验证，请稍后...")

        geetest_result = await get_validate(user, mmt_data.gt, mmt_data.challenge)
        if not geetest_result:
            continue

        sign_status, mmt_data = await signer.sign(
            account.platform, mmt_data, geetest_result
        )
        if sign_status:
            break

    if not sign_status and user.enable_notice:
        _handle_sign_failure(signer, account, sign_status, msgs_list, game_detail)


def _handle_sign_failure(
    signer: BaseGameSign,
    account: UserAccount,
    sign_status: BaseApiStatus,
    msgs_list: List[str],
    game_detail: str,
) -> None:
    """处理签到失败情况"""
    if sign_status.login_expired:
        message = f"⚠️{game_detail} 签到时服务器返回登录失效，请尝试重新登录绑定账户"
    elif sign_status.need_verify:
        message = (
            f"⚠️{game_detail} 签到时可能遇到验证码拦截，"
            "请尝试使用命令『/账号设置』更改设备平台，若仍失败请手动前往米游社签到"
        )
    else:
        message = f"⚠️{game_detail} 签到失败，请稍后再试"

    msgs_list.append(message)


async def _process_sign_result(
    signer: BaseGameSign,
    account: UserAccount,
    msgs_list: List[str],
    originally_signed: bool,
    game_detail: str,
) -> None:
    """处理签到结果"""
    get_info_status, info = await signer.get_info(account.platform)
    get_award_status, awards = await signer.get_rewards()

    if not get_info_status or not get_award_status:
        msg = f"⚠️{game_detail} 获取签到结果失败！请手动前往米游社查看"
    else:
        award = awards[info.total_sign_day - 1]
        status = "签到成功！" if not originally_signed else "已经签到过了"

        msg = (
            f"🪪{game_detail}"
            f" | {signer.record.nickname}·lv{signer.record.level}"
            f" | 🎮状态: {status}"
            f"\n🎁今日签到奖励：{award.name} * {award.cnt}"
            f"\n📅本月签到次数：{info.total_sign_day}"
        )

        if info.is_sign:
            img_file = await get_file(award.icon)
            # TODO: 优化图片推送方式
            logger.info("签到成功")
        else:
            msg = (
                f"⚠️{game_detail} 签到失败！请尝试重新签到，"
                "若多次失败请尝试重新登录绑定账户"
            )

    msgs_list.append(msg)
    await asyncio.sleep(project_config.preference.sleep_time)


async def _bbs_sign_impl(user: UserData) -> str:
    """
    执行米游币任务

    Args:
        user (UserData): 单个用户数据

    Returns:
        str: 执行结果消息
    """
    msgs_list = []

    for j, account in enumerate(user.accounts.values(), start=1):
        if account.enable_mission:
            logger.info(f"⏳ 开始执行米游币任务...")
            await _process_account_bbs_sign(account, user, msgs_list)
            logger.info(f"✅ 米游币任务完成")
        else:
            logger.info(f"⏭️ 第{j}个角色的米游币任务已禁用，跳过执行")

    return _format_result(msgs_list, "")


async def _process_account_bbs_sign(
    account: UserAccount, user: UserData, msgs_list: List[str]
) -> None:
    """处理单个账户的米游币任务"""
    missions_state_status, missions_state = await get_missions_state(account)
    if not missions_state_status:
        _handle_missions_state_failure(account, missions_state_status, msgs_list)
        return

    myb_before_mission = missions_state.current_myb
    finished = all(
        current == mission.threshold
        for mission, current in missions_state.state_dict.values()
    )

    if not finished:
        await _execute_missions(account, user, missions_state, msgs_list)

    if user.enable_notice:
        await _send_mission_notice(account, myb_before_mission, msgs_list)


def _handle_missions_state_failure(
    account: UserAccount,
    missions_state_status: MissionStatus,
    msgs_list: List[str],
) -> None:
    """处理任务状态获取失败"""
    if missions_state_status.login_expired:
        msg = f"⚠️ 登录失效，请重新登录"
        msgs_list.append(msg)
        logger.warning(msg)

    info_msg = f"⚠️ 获取任务完成情况请求失败，你可以手动前往App查看"
    msgs_list.append(info_msg)
    logger.info(info_msg)


async def _execute_missions(
    account: UserAccount,
    user: UserData,
    missions_state: MissionState,
    msgs_list: List[str],
) -> None:
    """执行各项任务"""
    if not account.mission_games:
        msgs_list.append(f"⚠️未设置米游币任务目标分区，将跳过执行")
        return

    for class_name in account.mission_games:
        class_type = BaseMission.available_games.get(class_name)
        if not class_type:
            msgs_list.append(f"⚠️米游币任务目标分区『{class_name}』未找到，将跳过该分区")
            continue

        await _execute_single_mission(
            account, user, class_type, missions_state, msgs_list
        )


async def _execute_single_mission(
    account: UserAccount,
    user: UserData,
    class_type: Type[BaseMission],
    missions_state: MissionState,
    msgs_list: List[str],
) -> None:
    """执行单个分区任务"""
    mission_obj = class_type(account)
    sign_status, read_status, like_status, share_status = (
        MissionStatus(),
        MissionStatus(),
        MissionStatus(),
        MissionStatus(),
    )
    sign_points = None

    logger.info(f"⏳ 开始执行『{class_type.name}』分区任务...")

    for key_name in missions_state.state_dict:
        if key_name == BaseMission.SIGN:
            if not project_config.preference.myb_sign_enabled:
                # 讨论区签到接口鉴权失效（详见知识库 mystool changelog 2026-09-05），
                # 配置关闭后跳过，避免每账号产生两条错误日志
                sign_status = MissionStatus(login_expired=True)
                logger.info(f"『{class_type.name}』分区签到已通过配置关闭，跳过")
                continue
            sign_status, sign_points = await mission_obj.sign(user)
        elif key_name == BaseMission.VIEW:
            read_status = await mission_obj.read()
        elif key_name == BaseMission.LIKE:
            like_status = await mission_obj.like()
        elif key_name == BaseMission.SHARE:
            share_status = await mission_obj.share()

    if hasattr(sign_status, "need_verify") and sign_status.need_verify:
        sign_icon = "⏳"
        sign_result = "需要人机验证"
    elif sign_status:
        sign_icon = "✓"
        sign_result = f"+{sign_points or '0'} 米游币🪙"
    else:
        sign_icon = "✕"
        sign_result = "失败"

    msgs_list.append(
        f"🎮『{class_type.name}』米游币任务执行情况：\n"
        f"📅签到：{sign_icon} {sign_result} | "
        f"📰阅读：{'✓' if read_status else '✕'} | "
        f"❤️点赞：{'✓' if like_status else '✕'} | "
        f"↗️分享：{'✓' if share_status else '✕'}"
    )

    logger.info(f"『{class_type.name}』分区任务完成")


async def _send_mission_notice(
    account: UserAccount,
    myb_before_mission: int,
    msgs_list: List[str],
) -> None:
    """发送任务完成通知"""
    missions_state_status, missions_state = await get_missions_state(account)
    if not missions_state_status:
        _handle_missions_state_failure(account, missions_state_status, msgs_list)
        return

    # 这里改成有增加就是完成任务了
    is_finished = missions_state.current_myb > myb_before_mission

    notice_string = (
        "🎉已完成今日米游币任务" if is_finished else "⚠️今日米游币任务未全部完成"
    )

    msg = f"{notice_string}"

    msg += (
        f"\n🪙获得米游币: {missions_state.current_myb - myb_before_mission}"
        f" | 💰当前米游币: {missions_state.current_myb}"
    )

    msgs_list.append(msg)


# def _get_mission_name(key_name: str) -> str:
#     """获取任务名称"""
#     mission_names = {
#         BaseMission.SIGN: "📅签到",
#         BaseMission.VIEW: "📰阅读",
#         BaseMission.LIKE: "❤️点赞",
#         BaseMission.SHARE: "↗️分享",
#     }
#     return mission_names.get(key_name, key_name)


class NoteNoticeStatus(BaseModel):
    """账号便笺通知状态"""

    genshin: GenshinNoteNotice = Field(default_factory=GenshinNoteNotice)
    starrail: StarRailNoteNotice = Field(default_factory=StarRailNoteNotice)
    model_config = ConfigDict(extra="ignore")


note_notice_status: Dict[str, NoteNoticeStatus] = {}
"""记录账号对应的便笺通知状态"""


async def genshin_note_check(
    user: UserData, msgs_list: List[str], account_index: int = None
) -> None:
    """查看原神实时便笺"""

    for j, account in enumerate(user.accounts.values(), start=1):
        if "GenshinImpact" in account.game_sign_games:
            await _process_genshin_note(account, msgs_list)


async def _process_genshin_note(account: UserAccount, msgs_list: List[str]) -> None:
    """处理原神便笺"""
    note_notice_status.setdefault(account.bbs_uid, NoteNoticeStatus())
    genshin_notice = note_notice_status[account.bbs_uid].genshin

    genshin_board_status, note = await genshin_note(account)
    if not genshin_board_status:
        msg = _handle_note_failure(account, genshin_board_status, "原神")
        msgs_list.append(msg)
        return

    msg = _build_genshin_note_message(account, note, genshin_notice)
    msgs_list.append(msg)


def _build_genshin_note_message(
    account: UserAccount,
    note: GenshinNote,
    genshin_notice: GenshinNoteNotice,
) -> str:
    """构建原神便笺消息"""
    msg_parts = []

    # 树脂提醒
    if note.current_resin >= account.user_resin_threshold:
        if not genshin_notice.current_resin_full:
            if note.current_resin == 200:
                genshin_notice.current_resin_full = True
                msg_parts.append("❕您的树脂已经满啦")
            elif not genshin_notice.current_resin:
                genshin_notice.current_resin_full = False
                genshin_notice.current_resin = True
                msg_parts.append("❕您的树脂已达到提醒阈值")
    else:
        genshin_notice.current_resin = False
        genshin_notice.current_resin_full = False

    # 洞天财瓮提醒
    if (
        note.current_home_coin == note.max_home_coin
        and not genshin_notice.current_home_coin
    ):
        genshin_notice.current_home_coin = True
        msg_parts.append("❕您的洞天财瓮已经满啦")
    else:
        genshin_notice.current_home_coin = False

    base_msg = (
        f"❖原神·实时便笺❖"
        f"\n⏳树脂数量：{note.current_resin} / 200"
        f"\n⏱️树脂{note.resin_recovery_text}"
        f"\n🕰️探索派遣：{note.current_expedition_num} / {note.max_expedition_num}"
        f"\n📅每日委托：{4 - note.finished_task_num} 个任务未完成"
        f"\n💰洞天财瓮：{note.current_home_coin} / {note.max_home_coin}"
    )

    return "\n".join(msg_parts) + "\n" + base_msg if msg_parts else base_msg


async def starrail_note_check(user: UserData, msgs_list: List[str]) -> None:
    """查看星铁实时便笺"""

    if not user:
        msgs_list.append("⚠️未配置用户")
        return

    for j, account in enumerate(user.accounts.values(), start=1):
        if "StarRail" in account.game_sign_games:
            await _process_starrail_note(account, msgs_list)
            # logger.info(f"✅ {account.display_name}的星穹铁道便签查询完成")


async def _process_starrail_note(account: UserAccount, msgs_list: List[str]) -> None:
    """处理星铁便笺"""
    note_notice_status.setdefault(account.bbs_uid, NoteNoticeStatus())
    starrail_notice = note_notice_status[account.bbs_uid].starrail

    starrail_board_status, note = await starrail_note(account)
    if not starrail_board_status:
        _handle_note_failure(account, starrail_board_status, "星铁")
        return

    msg = _build_starrail_note_message(account, note, starrail_notice)
    msgs_list.append(msg)


def _build_starrail_note_message(
    account: UserAccount,
    note: StarRailNote,
    starrail_notice: StarRailNoteNotice,
) -> str:
    """构建星铁便笺消息"""
    msg_parts = []

    # 开拓力提醒
    if note.current_stamina >= account.user_stamina_threshold:
        if not starrail_notice.current_stamina_full:
            if note.current_stamina >= note.max_stamina:
                starrail_notice.current_stamina_full = True
                msg_parts.append("❕您的开拓力已经溢出")
            elif not starrail_notice.current_stamina:
                starrail_notice.current_stamina_full = False
                starrail_notice.current_stamina = True
                msg_parts.append("❕您的开拓力已达到提醒阈值")

            if note.current_train_score != note.max_train_score:
                msg_parts.append("❕您的每日实训未完成")
    else:
        starrail_notice.current_stamina = False
        starrail_notice.current_stamina_full = False

    # 模拟宇宙积分提醒
    if (
        note.current_rogue_score != note.max_rogue_score
        and project_config.preference.notice_time
    ):
        msg_parts.append("❕您的模拟宇宙积分还没打满")

    base_msg = (
        f"❖星穹铁道·实时便笺❖"
        f"\n⏳开拓力数量：{note.current_stamina} / {note.max_stamina}"
        f"\n⏱开拓力{note.stamina_recover_text}"
        f"\n📒每日实训：{note.current_train_score} / {note.max_train_score}"
        f"\n📅每日委托：{note.accepted_expedition_num} / 4"
        f"\n🌌模拟宇宙：{note.current_rogue_score} / {note.max_rogue_score}"
    )

    return "\n".join(msg_parts) + "\n" + base_msg if msg_parts else base_msg


def _handle_note_failure(
    account: UserAccount,
    status: BaseApiStatus,
    game_name: str,
) -> None:
    """处理便笺获取失败"""
    failed_msg = f"⚠️ 获取实时便笺请求失败，你可以手动前往App查看"
    if status.login_expired:
        failed_msg = f"⚠️ 登录失效，请重新登录"
    elif getattr(status, f"no_{game_name.lower()}_account", False):
        failed_msg = f"⚠️ 没有绑定任何{game_name}账户，请绑定后再重试"
    elif status.need_verify:
        failed_msg = f"⚠️ 获取实时便笺时被人机验证阻拦"

    logger.warning(failed_msg)
    return f"查询失败：{failed_msg}"
