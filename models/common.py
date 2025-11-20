import inspect
import time

# from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, NamedTuple, no_type_check, Dict, Any, TypeVar, Tuple

# import pytz
from pydantic import BaseModel

__all__ = [
    "root_path",
    "data_path",
    "BaseModelWithSetter",
    "BaseModelWithUpdate",
    "GameRecord",
    "GameInfo",
    "MmtData",
    "Award",
    "GameSignInfo",
    "MissionData",
    "MissionState",
    "GenshinNote",
    "StarRailNote",
    "GenshinNoteNotice",
    "StarRailNoteNotice",
    "BaseApiStatus",
    "CreateMobileCaptchaStatus",
    "GetCookieStatus",
    "MissionStatus",
    "GetFpStatus",
    "BoardStatus",
    "GenshinNoteStatus",
    "StarRailNoteStatus",
    "QueryGameTokenQrCodeStatus",
    "GeetestResult",
    "GeetestResultV4",
]

# 修改：使用 __file__ 替代 __name__
root_path = Path(__file__).parent.absolute()
"""项目根目录"""

data_path = root_path / "data"
"""数据保存目录"""


def format_recovery_time(seconds: int) -> str:
    """通用恢复时间格式化函数"""
    if not seconds:
        return ":未获得时间数据"
    elif seconds == 0:
        return "已准备就绪"
    else:
        recovery_timestamp = int(time.time()) + seconds
        recovery_datetime = datetime.fromtimestamp(recovery_timestamp)
        return f"将在{recovery_datetime.strftime('%m-%d %H:%M')}回满"


class BaseModelWithSetter(BaseModel):
    """
    可以使用@property.setter的BaseModel

    目前pydantic 1.10.7 无法使用@property.setter
    issue: https://github.com/pydantic/pydantic/issues/1577#issuecomment-790506164
    """

    @no_type_check
    def __setattr__(self, name, value):
        try:
            super().__setattr__(name, value)
        except Exception as e:
            setters = inspect.getmembers(
                self.__class__,
                predicate=lambda x: isinstance(x, property) and x.fset is not None,
            )
            for setter_name, func in setters:
                if setter_name == name:
                    object.__setattr__(self, name, value)
                    break
            else:
                raise e


class BaseModelWithUpdate(BaseModel):
    """
    可以使用update方法的BaseModel
    """

    _T = TypeVar("_T", bound=BaseModel)


class GameRecord(BaseModel):
    """
    用户游戏数据
    """

    region_name: str
    """服务器区名"""

    game_id: int
    """游戏ID"""

    level: int
    """用户游戏等级"""

    region: str
    """服务器区号"""

    game_role_id: str
    """用户游戏UID"""

    nickname: str
    """用户游戏昵称"""


class GameInfo(BaseModel):
    """
    游戏信息数据
    """

    id: int
    """游戏ID"""

    app_icon: str
    """游戏App图标链接(大)"""

    op_name: str
    """游戏代号(英文数字, 例如hk4e)"""

    en_name: str
    """游戏代号2(英文数字, 例如ys)"""

    icon: str
    """游戏图标链接(圆形, 小)"""

    name: str
    """游戏名称"""


class MmtData(BaseModel):
    """
    短信验证码-人机验证任务申请-返回数据
    """

    challenge: Optional[str] = None
    gt: Optional[str] = None
    """验证ID，即 极验文档 中的captchaId，极验后台申请得到"""
    mmt_key: Optional[str] = None
    """验证任务"""
    new_captcha: Optional[bool] = None
    """宕机情况下使用"""
    risk_type: Optional[str] = None
    """结合风控融合，指定验证形式"""
    success: Optional[int] = None
    use_v4: Optional[bool] = None
    """是否使用极验第四代 GT4"""


class Award(BaseModel):
    """
    签到奖励数据
    """

    name: str
    """签到获得的物品名称"""
    icon: str
    """物品图片链接"""
    cnt: int
    """物品数量"""


class GameSignInfo(BaseModel):
    is_sign: bool
    """今日是否已经签到"""
    total_sign_day: int
    """已签多少天"""
    sign_cnt_missed: int
    """漏签多少天"""


class MissionData(BaseModel):
    points: int
    """任务米游币奖励"""
    name: str
    """任务名字，如 讨论区签到"""
    mission_key: str
    """任务代号，如 continuous_sign"""
    threshold: int
    """任务完成的最多次数"""


class MissionState(BaseModel):
    current_myb: int
    """用户当前米游币数量"""
    state_dict: Dict[str, Tuple[MissionData, int]]
    """所有任务对应的完成进度 {mission_key, (MissionData, 当前进度)}"""


class GenshinNote(BaseModel):
    """
    原神实时便笺数据 (从米游社内相关页面API的返回数据初始化)
    """

    current_resin: Optional[int] = None
    """当前树脂数量"""
    finished_task_num: Optional[int] = None
    """每日委托完成数"""
    current_expedition_num: Optional[int] = None
    """探索派遣 进行中的数量"""
    max_expedition_num: Optional[int] = None
    """探索派遣 最多派遣数"""
    current_home_coin: Optional[int] = None
    """洞天财瓮 未收取的宝钱数"""
    max_home_coin: Optional[int] = None
    """洞天财瓮 最多可容纳宝钱数"""
    transformer: Optional[Dict[str, Any]] = None
    """参量质变仪相关数据"""
    resin_recovery_time: Optional[int] = None
    """剩余树脂恢复时间"""

    @property
    def transformer_text(self):
        """
        参量质变仪状态文本
        """
        try:
            if not self.transformer["obtained"]:
                return "未获得"
            elif self.transformer["recovery_time"]["reached"]:
                return "已准备就绪"
            else:
                return (
                    f"{self.transformer['recovery_time']['Day']} 天"
                    f"{self.transformer['recovery_time']['Hour']} 小时 "
                    f"{self.transformer['recovery_time']['Minute']} 分钟"
                )
        except (KeyError, TypeError):
            return None

    @property
    def resin_recovery_text(self):
        """
        剩余树脂恢复文本
        """
        return format_recovery_time(self.resin_recovery_time)


class StarRailNote(BaseModel):
    """
    崩铁实时便笺数据 (从米游社内相关页面API的返回数据初始化)
    """

    current_stamina: Optional[int] = None
    """当前开拓力"""
    max_stamina: Optional[int] = None
    """最大开拓力"""
    stamina_recover_time: Optional[int] = None
    """剩余体力恢复时间"""
    current_train_score: Optional[int] = None
    """当前每日实训值"""
    max_train_score: Optional[int] = None
    """最大每日实训值"""
    current_rogue_score: Optional[int] = None
    """当前模拟宇宙积分"""
    max_rogue_score: Optional[int] = None
    """最大模拟宇宙积分"""
    accepted_expedition_num: Optional[int] = None
    """已接受委托数量"""
    total_expedition_num: Optional[int] = None
    """最大委托数量"""
    has_signed: Optional[bool] = None
    """当天是否签到"""

    @property
    def stamina_recover_text(self):
        """
        剩余体力恢复文本
        """
        return format_recovery_time(self.stamina_recover_time)


class GenshinNoteNotice(GenshinNote):
    """
    原神便笺通知状态
    """

    current_resin: bool = False
    """是否达到阈值"""
    current_resin_full: bool = False
    """是否溢出"""
    current_home_coin: bool = False
    transformer_ready: bool = False  # 修改字段名避免歧义


class StarRailNoteNotice(StarRailNote):
    """
    星穹铁道便笺通知状态
    """

    current_stamina: bool = False
    """是否达到阈值"""
    current_stamina_full: bool = False
    """是否溢出"""
    current_train_score: bool = False
    current_rogue_score: bool = False


class BaseApiStatus(BaseModel):
    """
    API返回结果基类
    """

    success: bool = False
    """成功"""
    network_error: bool = False
    """连接失败"""
    incorrect_return: bool = False
    """服务器返回数据不正确"""
    login_expired: bool = False
    """登录失效"""
    need_verify: bool = False
    """需要进行人机验证"""
    invalid_ds: bool = False
    """Headers DS无效"""

    def __bool__(self):
        return self.success

    @property
    def error_type(self):
        """
        返回错误类型
        """
        for key in sorted(self.__fields__.keys()):  # 确保稳定顺序
            if getattr(self, key, False) and key != "success":
                return key
        return None


class CreateMobileCaptchaStatus(BaseApiStatus):
    """
    发送短信验证码 返回结果
    """

    incorrect_geetest: bool = False
    """人机验证结果数据无效"""
    not_registered: bool = False
    """手机号码未注册"""
    invalid_phone_number: bool = False
    """手机号码无效"""
    too_many_requests: bool = False
    """发送过于频繁"""


class GetCookieStatus(BaseApiStatus):
    """
    获取Cookie 返回结果
    """

    incorrect_captcha: bool = False
    """验证码错误"""
    missing_login_ticket: bool = False
    """Cookies 缺少 login_ticket"""
    missing_bbs_uid: bool = False
    """Cookies 缺少 bbs_uid (stuid, ltuid, ...)"""
    missing_cookie_token: bool = False
    """Cookies 缺少 cookie_token"""
    missing_stoken: bool = False
    """Cookies 缺少 stoken"""
    missing_stoken_v1: bool = False
    """Cookies 缺少 stoken_v1"""
    missing_stoken_v2: bool = False
    """Cookies 缺少 stoken_v2"""
    missing_mid: bool = False
    """Cookies 缺少 mid"""


class MissionStatus(BaseApiStatus):
    """
    米游币任务 返回结果
    """

    failed_getting_post: bool = False
    """获取文章失败"""
    already_signed: bool = False
    """已经完成过签到"""


class GetFpStatus(BaseApiStatus):
    """
    获取指纹 返回结果
    """

    invalid_arguments: bool = False
    """参数错误"""


class BoardStatus(BaseApiStatus):
    """
    实时便笺 返回结果
    """

    game_record_failed: bool = False
    """获取用户游戏数据失败"""
    game_list_failed: bool = False
    """获取游戏列表失败"""


class GenshinNoteStatus(BoardStatus):
    """
    原神实时便笺 返回结果
    """

    no_genshin_account: bool = False
    """用户没有任何原神账户"""


class StarRailNoteStatus(BoardStatus):
    """
    星铁实时便笺 返回结果
    """

    no_starrail_account: bool = False
    """用户没有任何星铁账户"""


class QueryGameTokenQrCodeStatus(BaseApiStatus):
    """
    查询游戏Token二维码 返回结果
    """

    qrcode_expired: bool = False
    """二维码已过期"""
    qrcode_init: bool = False
    """二维码未扫描"""
    qrcode_scanned: bool = False
    """二维码已扫描但未确认"""


class GeetestResult(NamedTuple):
    """
    人机验证结果数据
    """

    validate: str
    seccode: str


class GeetestResultV4(BaseModel):
    """
    GEETEST GT4 人机验证结果数据
    """

    captcha_id: str
    lot_number: str
    pass_token: str
    gen_time: str
    captcha_output: str
