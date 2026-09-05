import inspect
import json
import time
from datetime import datetime
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from typing import (
    Optional,
    NamedTuple,
    no_type_check,
    Dict,
    Any,
    TypeVar,
    Tuple,
    Union,
    AbstractSet,
    Mapping,
    Set,
    Literal,
    List,
    TYPE_CHECKING,
)
from uuid import UUID, uuid4

from httpx import Cookies
from pydantic import BaseModel, ValidationError, field_validator, ConfigDict, Field
from pydantic_settings import BaseSettings

from config._version import __version__
from config.logger import logger

# 改为在文件内部定义 logger
# import logging

# logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    IntStr = Union[int, str]
    DictStrAny = Dict[str, Any]
    AbstractSetIntStr = AbstractSet[IntStr]
    MappingIntStrAny = Mapping[IntStr, Any]

__all__ = [
    # 路径相关
    "root_path",
    "data_path",
    "project_config_path",
    # 基础模型
    "BaseModelWithSetter",
    "BaseModelWithUpdate",
    # 游戏数据模型
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
    # API状态模型
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
    # 推送配置模型
    "TelegramConfig",
    "DingRobotConfig",
    "FeishuBotConfig",
    "BarkConfig",
    "GotifyConfig",
    "WebhookConfig",
    "PushConfig",
    # 偏好设置和配置模型
    "Preference",
    "SaltConfig",
    "DeviceConfig",
    "ProjectConfig",
    "ProjectEnv",
    # 数据管理模型
    "BBSCookies",
    "UserAccount",
    "uuid4_validate",
    "UserData",
    "ConfigData",
    "ConfigDataManager",
    # 全局实例
    # "project_config",
    # "project_env",
]

# ==================== 路径配置 ====================
root_path = Path(__file__).parent.parent.absolute()
"""项目根目录"""

data_path = root_path / "data"
"""数据保存目录"""

project_config_path = data_path / "config.json"
"""插件配置文件路径"""

# ==================== 全局变量 ====================
_uuid_set: Set[str] = set()
"""已使用的用户UUID密钥集合"""
_new_uuid_in_init = False
"""插件反序列化用户数据时，是否生成了新的UUID密钥"""


# ==================== 工具函数 ====================
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


def uuid4_validate(v):
    """
    验证UUID是否为合法的UUIDv4

    :param v: UUID
    """
    try:
        UUID(v, version=4)
    except Exception:
        return False
    else:
        return True


# ==================== 基础模型类 ====================
class BaseModelWithSetter(BaseModel):
    """
    可以使用@property.setter的BaseModel
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


# ==================== 游戏数据模型 ====================
class GameRecord(BaseModel):
    """用户游戏数据"""

    region_name: str
    game_id: int
    level: int
    region: str
    game_role_id: str
    nickname: str


class GameInfo(BaseModel):
    """游戏信息数据"""

    id: int
    app_icon: str
    op_name: str
    en_name: str
    icon: str
    name: str


class MmtData(BaseModel):
    """短信验证码-人机验证任务申请-返回数据"""

    challenge: Optional[str] = None
    gt: Optional[str] = None
    mmt_key: Optional[str] = None
    new_captcha: Optional[bool] = None
    risk_type: Optional[str] = None
    success: Optional[int] = None
    use_v4: Optional[bool] = None


class Award(BaseModel):
    """签到奖励数据"""

    name: str
    icon: str
    cnt: int


class GameSignInfo(BaseModel):
    is_sign: bool
    total_sign_day: int
    sign_cnt_missed: int


class MissionData(BaseModel):
    points: int
    name: str
    mission_key: str
    threshold: int


class MissionState(BaseModel):
    current_myb: int
    state_dict: Dict[str, Tuple[MissionData, int]]


class GenshinNote(BaseModel):
    """原神实时便笺数据"""

    current_resin: Optional[int] = None
    finished_task_num: Optional[int] = None
    current_expedition_num: Optional[int] = None
    max_expedition_num: Optional[int] = None
    current_home_coin: Optional[int] = None
    max_home_coin: Optional[int] = None
    transformer: Optional[Dict[str, Any]] = None
    resin_recovery_time: Optional[int] = None

    @property
    def transformer_text(self):
        """参量质变仪状态文本"""
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
        """剩余树脂恢复文本"""
        return format_recovery_time(self.resin_recovery_time)


class StarRailNote(BaseModel):
    """崩铁实时便笺数据"""

    current_stamina: Optional[int] = None
    max_stamina: Optional[int] = None
    stamina_recover_time: Optional[int] = None
    current_train_score: Optional[int] = None
    max_train_score: Optional[int] = None
    current_rogue_score: Optional[int] = None
    max_rogue_score: Optional[int] = None
    accepted_expedition_num: Optional[int] = None
    total_expedition_num: Optional[int] = None
    has_signed: Optional[bool] = None

    @property
    def stamina_recover_text(self):
        """剩余体力恢复文本"""
        return format_recovery_time(self.stamina_recover_time)


class GenshinNoteNotice(GenshinNote):
    """原神便笺通知状态"""

    current_resin: bool = False
    current_resin_full: bool = False
    current_home_coin: bool = False
    transformer_ready: bool = False


class StarRailNoteNotice(StarRailNote):
    """星穹铁道便笺通知状态"""

    current_stamina: bool = False
    current_stamina_full: bool = False
    current_train_score: bool = False
    current_rogue_score: bool = False


# ==================== API状态模型 ====================
class BaseApiStatus(BaseModel):
    """API返回结果基类"""

    success: bool = False
    network_error: bool = False
    incorrect_return: bool = False
    login_expired: bool = False
    need_verify: bool = False
    invalid_ds: bool = False

    def __bool__(self):
        return self.success

    @property
    def error_type(self):
        """返回错误类型"""
        for key in sorted(self.__fields__.keys()):
            if getattr(self, key, False) and key != "success":
                return key
        return None


class QrLoginProvider(str, Enum):
    """二维码登录提供方"""
    WEB = "web"
    APP = "app"


class LoginSession(BaseModel):
    """登录会话，覆盖创建和轮询全过程"""
    provider: QrLoginProvider
    device_id: str
    app_id: str
    client_type: str
    user_agent: str
    client: Optional[Any] = None


class QrCodeChallenge(BaseModel):
    """二维码挑战数据"""
    ticket: str
    url: str


class QrLoginState(str, Enum):
    """二维码登录状态"""
    CREATED = "Created"
    SCANNED = "Scanned"
    CONFIRMED = "Confirmed"
    EXPIRED = "Expired"
    CANCELED = "Canceled"
    UNKNOWN = "Unknown"


class QrLoginPollResult(BaseModel):
    """二维码登录轮询结果"""
    state: QrLoginState
    cookies: dict[str, str] = {}
    tokens: dict[str, str] = {}
    user_info: dict[str, Any] = {}
    retcode: Optional[int] = None
    message: Optional[str] = None


class CreateMobileCaptchaStatus(BaseApiStatus):
    """发送短信验证码返回结果"""

    incorrect_geetest: bool = False
    not_registered: bool = False
    invalid_phone_number: bool = False
    too_many_requests: bool = False


class GetCookieStatus(BaseApiStatus):
    """获取Cookie返回结果"""

    incorrect_captcha: bool = False
    missing_login_ticket: bool = False
    missing_bbs_uid: bool = False
    missing_cookie_token: bool = False
    missing_stoken: bool = False
    missing_stoken_v1: bool = False
    missing_stoken_v2: bool = False
    missing_mid: bool = False


class MissionStatus(BaseApiStatus):
    """米游币任务返回结果"""

    failed_getting_post: bool = False
    already_signed: bool = False


class GetFpStatus(BaseApiStatus):
    """获取指纹返回结果"""

    invalid_arguments: bool = False


class BoardStatus(BaseApiStatus):
    """实时便笺返回结果"""

    game_record_failed: bool = False
    game_list_failed: bool = False


class GenshinNoteStatus(BoardStatus):
    """原神实时便笺返回结果"""

    no_genshin_account: bool = False


class StarRailNoteStatus(BoardStatus):
    """星铁实时便笺返回结果"""

    no_starrail_account: bool = False


class QueryGameTokenQrCodeStatus(BaseApiStatus):
    """查询游戏Token二维码返回结果"""

    qrcode_expired: bool = False
    qrcode_init: bool = False
    qrcode_scanned: bool = False


class GeetestResult(NamedTuple):
    """人机验证结果数据"""

    validate: str = ""
    seccode: str = ""


class GeetestResultV4(BaseModel):
    """GEETEST GT4 人机验证结果数据"""

    captcha_id: str = ""
    lot_number: str = ""
    pass_token: str = ""
    gen_time: str = ""
    captcha_output: str = ""


# ==================== 推送配置模型 ====================
class TelegramConfig(BaseModel):
    """Telegram推送配置"""

    api_url: str = "api.telegram.org"
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    http_proxy: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    model_config = ConfigDict(extra="ignore")


class DingRobotConfig(BaseModel):
    """钉钉机器人推送配置"""

    webhook: Optional[str] = None
    secret: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.webhook)

    model_config = ConfigDict(extra="ignore")


class FeishuBotConfig(BaseModel):
    """飞书机器人推送配置"""

    webhook: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    # 群机器人发消息时可以 @指定用户
    user_id: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.webhook)

    model_config = ConfigDict(extra="ignore")


class BarkConfig(BaseModel):
    """Bark推送配置"""

    api_url: Optional[str] = None
    token: Optional[str] = None
    icon: str = "default"

    def is_configured(self) -> bool:
        return bool(self.api_url and self.token)

    model_config = ConfigDict(extra="ignore")


class GotifyConfig(BaseModel):
    """Gotify推送配置"""

    api_url: Optional[str] = None
    token: Optional[str] = None
    priority: int = 5

    def is_configured(self) -> bool:
        return bool(self.api_url and self.token)

    model_config = ConfigDict(extra="ignore")


class WebhookConfig(BaseModel):
    """WebHook推送配置"""

    webhook_url: Optional[str] = None
    headers: Dict[str, str] = {}
    method: str = "POST"
    template: Optional[Dict[str, Any]] = None

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    model_config = ConfigDict(extra="ignore")


class ImageBedConfig(BaseModel):
    """图床配置"""

    api_url: Optional[str] = None
    token: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.api_url)

    model_config = ConfigDict(extra="ignore")


class PushConfig(BaseModel):
    """推送配置"""

    enable: bool = True
    error_push_only: bool = False
    push_servers: List[str] = []
    push_block_keys: List[str] = []
    timeout: float = 10.0
    max_retry_times: int = 3
    retry_interval: float = 2.0

    telegram: TelegramConfig = TelegramConfig()
    dingrobot: DingRobotConfig = DingRobotConfig()
    feishubot: FeishuBotConfig = FeishuBotConfig()
    bark: BarkConfig = BarkConfig()
    gotify: GotifyConfig = GotifyConfig()
    webhook: WebhookConfig = WebhookConfig()

    # 图床配置
    imgbed: ImageBedConfig = ImageBedConfig()

    model_config = ConfigDict(extra="ignore")


# ==================== 偏好设置和配置模型 ====================
class Preference(BaseModel):
    """偏好设置"""

    github_proxy: Optional[str] = "https://mirror.ghproxy.com/"
    enable_connection_test: bool = True
    connection_test_interval: Optional[float] = 30
    timeout: float = 10
    max_retry_times: Optional[int] = 3
    retry_interval: float = 2
    encoding: str = "utf-8"
    sleep_time: float = 2
    global_geetest: bool = False
    geetest_url: Optional[str] = None
    geetest_params: Optional[Dict[str, Any]] = None
    geetest_json: Optional[Dict[str, Any]] = {"gt": "{gt}", "challenge": "{challenge}"}
    override_device_and_salt: bool = False
    game_token_app_id: str = "2"
    qrcode_query_interval: float = 1
    qrcode_wait_time: float = 120
    qrcode_provider: str = "web"
    qrcode_app_fallback: bool = False
    myb_sign_enabled: bool = True
    """讨论区签到开关：米哈游 bbs-api signIn 鉴权失效期间可关闭，仅跳过签到子任务"""
    resin_interval: int = 30

    _TARGET_TIME_STR = "20:00"
    _TARGET_TIME_OBJ = datetime.strptime(_TARGET_TIME_STR, "%H:%M")

    @property
    def notice_time(self) -> bool:
        """检查是否在提醒时间内"""
        now = datetime.now()
        now_minute_total = now.hour * 60 + now.minute
        try:
            target_minute_total = (
                self._TARGET_TIME_OBJ.hour * 60 + self._TARGET_TIME_OBJ.minute
            )
        except ValueError:
            return False
        start_time = target_minute_total - self.resin_interval
        end_time = target_minute_total + self.resin_interval
        return start_time <= now_minute_total <= end_time

    model_config = ConfigDict(extra="ignore")


class SaltConfig(BaseModel):
    """生成Headers - DS所用salt值"""

    SALT_IOS: str = "9ttJY72HxbjwWRNHJvn0n2AYue47nYsK"
    SALT_ANDROID: str = "BIPaooxbWZW02fGHZL1If26mYCljPgst"
    SALT_DATA: str = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
    SALT_PARAMS: str = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
    SALT_PROD: str = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"

    model_config = ConfigDict(extra="ignore")


class DeviceConfig(BaseModel):
    """设备信息"""

    USER_AGENT_MOBILE: str = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) miHoYoBBS/2.55.1"
    )
    USER_AGENT_PC: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Safari/605.1.15"
    )
    USER_AGENT_OTHER: str = "Hyperion/275 CFNetwork/1402.0.8 Darwin/22.2.0"
    USER_AGENT_ANDROID: str = (
        "Mozilla/5.0 (Linux; Android 11; MI 8 SE Build/RQ3A.211001.001; wv) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Version/4.0 Chrome/104.0.5112.97 Mobile Safari/537.36 "
        "miHoYoBBS/2.55.1"
    )
    USER_AGENT_ANDROID_OTHER: str = "okhttp/4.9.3"
    USER_AGENT_WIDGET: str = "WidgetExtension/231 CFNetwork/1390 Darwin/22.0.0"

    X_RPC_DEVICE_MODEL_MOBILE: str = "iPhone10,2"
    X_RPC_DEVICE_MODEL_PC: str = "OS X 10.15.7"
    X_RPC_DEVICE_MODEL_ANDROID: str = "MI 8 SE"

    X_RPC_DEVICE_NAME_MOBILE: str = "iPhone"
    X_RPC_DEVICE_NAME_PC: str = "Microsoft Edge 103.0.1264.62"
    X_RPC_DEVICE_NAME_ANDROID: str = "Xiaomi MI 8 SE"

    X_RPC_SYS_VERSION: str = "16.2"
    X_RPC_SYS_VERSION_ANDROID: str = "11"

    X_RPC_CHANNEL: str = "appstore"
    X_RPC_CHANNEL_ANDROID: str = "miyousheluodi"

    X_RPC_APP_VERSION: str = "2.63.1"
    X_RPC_PLATFORM: str = "ios"
    UA: str = '".Not/A)Brand";v="99", "Microsoft Edge";v="103", "Chromium";v="103"'
    UA_PLATFORM: str = '"macOS"'

    model_config = ConfigDict(extra="ignore")


class ProjectConfig(BaseSettings):
    """插件配置"""

    preference: Preference = Preference()
    push_config: PushConfig = PushConfig()

    model_config = ConfigDict(extra="ignore", env_file=".env")


class ProjectEnv(BaseSettings):
    """插件环境配置"""

    salt_config: SaltConfig = SaltConfig()
    device_config: DeviceConfig = DeviceConfig()

    model_config = ConfigDict(env_prefix="mystool_", env_file=".env", extra="ignore")


# ==================== 数据管理模型 ====================
class BBSCookies(BaseModelWithSetter, BaseModelWithUpdate):
    """米游社Cookies数据"""

    stuid: Optional[str] = None
    ltuid: Optional[str] = None
    account_id: Optional[str] = None
    login_uid: Optional[str] = None
    stoken_v1: Optional[str] = None
    stoken_v2: Optional[str] = None
    cookie_token: Optional[str] = None
    login_ticket: Optional[str] = None
    ltoken: Optional[str] = None
    mid: Optional[str] = None
    # v2 字段
    ltuid_v2: Optional[str] = None
    account_id_v2: Optional[str] = None
    cookie_token_v2: Optional[str] = None
    ltoken_v2: Optional[str] = None
    ltmid_v2: Optional[str] = None
    account_mid_v2: Optional[str] = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        stoken = data.get("stoken")
        if stoken:
            self.stoken = stoken

    @classmethod
    def from_login_cookie(cls, raw: dict[str, str]) -> "BBSCookies":
        """从登录响应的 Cookie 字典归一化，支持 v1/v2 混合字段"""
        cookies = cls()

        # 保留原始 v2 字段
        for v2_field in ("account_id_v2", "ltuid_v2", "cookie_token_v2",
                         "ltoken_v2", "ltmid_v2", "account_mid_v2"):
            if raw.get(v2_field):
                setattr(cookies, v2_field, raw[v2_field])

        # 账号标识
        uid = (
            raw.get("account_id_v2")
            or raw.get("ltuid_v2")
            or raw.get("account_id")
            or raw.get("ltuid")
            or raw.get("login_uid")
            or raw.get("stuid")
        )
        if uid:
            cookies.bbs_uid = uid

        # token
        stoken_v2 = raw.get("stoken_v2")
        stoken_v1 = raw.get("stoken") or raw.get("stoken_v1")
        if stoken_v2:
            cookies.stoken_v2 = stoken_v2
        if stoken_v1:
            cookies.stoken_v1 = stoken_v1

        ct = raw.get("cookie_token_v2") or raw.get("cookie_token")
        if ct:
            cookies.cookie_token = ct

        lt = raw.get("ltoken_v2") or raw.get("ltoken")
        if lt:
            cookies.ltoken = lt

        mid = raw.get("account_mid_v2") or raw.get("ltmid_v2") or raw.get("mid")
        if mid:
            cookies.mid = mid

        if raw.get("login_ticket"):
            cookies.login_ticket = raw["login_ticket"]

        return cookies

    def is_correct(self) -> bool:
        """判断是否为正确的Cookies"""
        return bool(self.bbs_uid and self.stoken and self.cookie_token)

    @property
    def bbs_uid(self):
        """获取米游社UID"""
        for value in [self.stuid, self.ltuid, self.account_id, self.login_uid]:
            if value:
                return value
        return None

    @bbs_uid.setter
    def bbs_uid(self, value: str):
        self.stuid = value
        self.ltuid = value
        self.account_id = value
        self.login_uid = value

    @property
    def stoken(self):
        """获取stoken"""
        return self.stoken_v1 or self.stoken_v2

    @stoken.setter
    def stoken(self, value):
        if value.startswith("v2_"):
            self.stoken_v2 = value
        else:
            self.stoken_v1 = value

    def update(self, cookies: Union[Dict[str, str], Cookies, "BBSCookies"]):
        """更新Cookies"""
        if isinstance(cookies, dict):
            # 处理字典
            self.stoken = cookies.get("stoken") or self.stoken
            self.bbs_uid = cookies.get("bbs_uid") or self.bbs_uid

            # 更新其他字段
            for key, value in cookies.items():
                if (
                    hasattr(self, key)
                    and value is not None
                    and value != ""
                    and key not in ["stoken", "bbs_uid"]
                ):
                    setattr(self, key, value)

        else:
            # 处理对象实例
            for field in self.__annotations__:
                if hasattr(cookies, field):
                    value = getattr(cookies, field)
                    if value is not None and value != "":
                        setattr(self, field, value)

    def dict(
        self,
        *,
        include: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        exclude: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        v2_stoken: bool = False,
        cookie_type: bool = False,
    ) -> "DictStrAny":
        """获取Cookies字典"""
        self.bbs_uid = self.bbs_uid
        cookies_dict = super().model_dump(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset or skip_defaults or exclude_defaults,
            exclude_none=exclude_none,
        )

        if v2_stoken and self.stoken_v2:
            cookies_dict["stoken"] = self.stoken_v2
        else:
            cookies_dict["stoken"] = self.stoken_v1

        if cookie_type:
            cookies_dict.pop("stoken_v1", None)
            cookies_dict.pop("stoken_v2", None)
            empty_key = set()
            for key, value in cookies_dict.items():
                if not value:
                    empty_key.add(key)
            [cookies_dict.pop(key) for key in empty_key]

        return cookies_dict


class UserAccount(BaseModelWithSetter):
    """米游社账户数据"""

    phone_number: Optional[str] = None
    cookies: BBSCookies = BBSCookies()
    device_id_ios: str
    device_id_android: str
    device_fp: Optional[str] = None
    enable_mission: bool = True
    enable_game_sign: bool = True
    enable_resin: bool = True
    platform: Literal["ios", "android"] = "ios"
    game_sign_games: List[str] = [
        "GenshinImpact",
        "HonkaiImpact3",
        "HoukaiGakuen2",
        "TearsOfThemis",
        "StarRail",
        "ZenlessZoneZero",
    ]
    mission_games: List[str] = ["BBSMission"]
    user_stamina_threshold: int = 300
    """开拓力提醒阈值"""
    user_resin_threshold: int = 200
    """树脂提醒阈值"""

    def __init__(self, **data: Any):
        # from utils import generate_device_id

        # if not data.get("device_id_ios"):
        #     data["device_id_ios"] = generate_device_id()
        # if not data.get("device_id_android"):
        #     data["device_id_android"] = generate_device_id()
        super().__init__(**data)

    @property
    def bbs_uid(self):
        """获取米游社UID"""
        return self.cookies.bbs_uid

    @bbs_uid.setter
    def bbs_uid(self, value: str):
        self.cookies.bbs_uid = value

    @property
    def display_name(self):
        """显示名称"""
        # from utils.common import blur_phone

        return f"{self.bbs_uid}" if self.phone_number else self.bbs_uid


class UserData(BaseModelWithSetter):
    """用户数据类"""

    enable_notice: bool = True
    geetest_url: Optional[str] = None
    geetest_params: Optional[Dict[str, Any]] = None
    uuid: Optional[str] = None
    accounts: Dict[str, UserAccount] = {}

    @field_validator("uuid")
    def uuid_validator(cls, v):
        """验证UUID是否为合法的UUIDv4"""
        if v is None and not uuid4_validate(v):
            raise ValueError("UUID格式错误，不是合法的UUIDv4")

    def __init__(self, **data: Any):
        global _new_uuid_in_init
        super().__init__(**data)
        if self.uuid is None:
            new_uuid = uuid4()
            while str(new_uuid) in _uuid_set:
                new_uuid = uuid4()
            self.uuid = str(new_uuid)
            _new_uuid_in_init = True
        _uuid_set.add(self.uuid)

    def __hash__(self):
        return hash(self.uuid)


class ConfigData(BaseModel):
    """统一的配置数据模型"""

    # 插件配置
    version: str = Field(default=__version__)
    preference: Preference = Field(default_factory=Preference)
    push_config: PushConfig = Field(default_factory=PushConfig)

    # 用户数据
    users: Dict[str, UserData] = Field(default_factory=dict)

    # 微博cookie
    weibo_cookie: Optional[str] = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class ConfigDataManager:
    """统一的配置数据管理器"""

    config_data: Optional[ConfigData] = None
    _initialized: bool = False

    @classmethod
    def load_config(cls):
        """加载配置文件 - 只读不写"""
        if cls._initialized and cls.config_data is not None:
            return cls.config_data

        logger.info(f"正在加载配置文件...{project_config_path}")

        if project_config_path.exists() and project_config_path.is_file():
            try:
                with open(project_config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)

                logger.debug(f"读取到的配置数据: {config_dict}")

                # 使用宽松验证
                cls.config_data = ConfigData.model_validate(config_dict)
                cls._initialized = True

            except ValidationError as e:
                logger.warning(f"配置文件验证失败: {e}")
                cls._create_default_config()
            except Exception as e:
                logger.exception(f"读取配置文件失败: {e}")
                cls._create_default_config()
        else:
            logger.info("配置文件不存在，使用默认配置")
            cls._create_default_config()

        return cls.config_data

    @classmethod
    def _create_default_config(cls):
        """创建默认配置 - 不保存到文件"""
        logger.info("🆕 创建默认配置对象")
        cls.config_data = ConfigData()
        cls._initialized = True
        cls.save_config()

    @classmethod
    def save_config(cls):
        """原子保存配置文件：先写临时文件，再 os.replace 到位。"""
        import os
        import tempfile

        if cls.config_data is None:
            cls.load_config()
        logger.info(f"正在保存配置文件...{project_config_path}")
        config_dir = Path(project_config_path).parent
        payload = json.dumps(cls.config_data.model_dump(), indent=4, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, project_config_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info("✅ 配置文件保存成功")

    # 便捷访问方法 - 添加安全检查
    @classmethod
    def get_preference(cls) -> Preference:
        """获取偏好设置"""
        if cls.config_data is None:
            cls.load_config()
        return cls.config_data.preference

    @classmethod
    def get_push_config(cls) -> PushConfig:
        """获取推送配置"""
        if cls.config_data is None:
            cls.load_config()
        return cls.config_data.push_config

    @classmethod
    def get_users(cls) -> Dict[str, UserData]:
        """获取用户数据"""
        if cls.config_data is None:
            cls.load_config()
        logger.info(f"获取用户数据: {len(cls.config_data.users)} 个用户")
        return cls.config_data.users

    @classmethod
    def get_config_data(cls) -> ConfigData:
        """获取完整的配置数据"""
        if cls.config_data is None:
            cls.load_config()
        return cls.config_data
