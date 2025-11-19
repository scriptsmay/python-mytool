from datetime import datetime
from typing import Union, Optional, Any, Dict, TYPE_CHECKING

from pydantic import BaseModel
from pydantic_settings import BaseSettings

# 修正导入路径 - 根据实际目录结构调整
try:
    from models.common import data_path
except ImportError:
    # 如果直接运行这个文件或者导入路径有问题，使用相对导入
    from common import data_path

if TYPE_CHECKING:
    IntStr = Union[int, str]

__all__ = [
    "project_config_path",
    "Preference",
    "SaltConfig",
    "DeviceConfig",
    "PluginConfig",
    "PluginEnv",
    "plugin_config",
    "plugin_env",
]

project_config_path = data_path / "config.json"
"""数据文件默认路径"""


class Preference(BaseModel):
    """
    偏好设置
    """

    github_proxy: Optional[str] = "https://mirror.ghproxy.com/"
    """GitHub加速代理 最终会拼接在原GitHub链接前面"""
    enable_connection_test: bool = True
    """是否开启连接测试"""
    connection_test_interval: Optional[float] = 30
    """连接测试间隔（单位：秒）"""
    timeout: float = 10
    """网络请求超时时间（单位：秒）"""
    max_retry_times: Optional[int] = 3
    """最大网络请求重试次数"""
    retry_interval: float = 2
    """网络请求重试间隔（单位：秒）（除兑换请求外）"""
    timezone: Optional[str] = "Asia/Shanghai"
    """兑换时所用的时区"""
    encoding: str = "utf-8"
    """文件读写编码"""
    sleep_time: float = 2
    """任务操作冷却时间(如米游币任务)"""
    global_geetest: bool = False
    """是否使用插件配置的全局打码接口，而不是用户个人配置的打码接口，默认关闭"""
    geetest_url: Optional[str] = None
    """极验Geetest人机验证打码接口URL"""
    geetest_params: Optional[Dict[str, Any]] = None
    """极验Geetest人机验证打码API发送的参数（除gt，challenge外）"""
    geetest_json: Optional[Dict[str, Any]] = {"gt": "{gt}", "challenge": "{challenge}"}
    """极验Geetest人机验证打码API发送的JSON数据 `{gt}`, `{challenge}` 为占位符"""
    override_device_and_salt: bool = False
    """是否读取插件数据文件中的 device_config 设备配置 和 salt_config 配置而不是默认配置（一般情况不建议开启）"""
    game_token_app_id: str = "2"
    """米游社二维码登录的应用标识符"""
    qrcode_query_interval: float = 1
    """检查米游社登录二维码扫描情况的请求间隔（单位：秒）"""
    qrcode_wait_time: float = 120
    """等待米游社登录二维码扫描的最长时间（单位：秒）"""

    # 修正：添加缺失的 resin_interval 属性
    resin_interval: int = 30
    """原石恢复提醒间隔（单位：分钟）"""

    @property
    def notice_time(self) -> bool:
        """检查是否在提醒时间内"""
        now_hour = datetime.now().hour
        now_minute = datetime.now().minute
        set_time = "20:00"
        notice_time = int(set_time[:2]) * 60 + int(set_time[3:])
        start_time = notice_time - self.resin_interval
        end_time = notice_time + self.resin_interval
        current_time = now_hour * 60 + now_minute
        return start_time <= current_time <= end_time

    class Config:
        """Pydantic配置"""

        extra = "ignore"


class SaltConfig(BaseModel):
    """
    生成Headers - DS所用salt值，非必要请勿修改
    """

    SALT_IOS: str = "9ttJY72HxbjwWRNHJvn0n2AYue47nYsK"
    """LK2 - 生成Headers iOS DS所需的salt"""
    SALT_ANDROID: str = "BIPaooxbWZW02fGHZL1If26mYCljPgst"
    """K2 - 生成Headers Android DS所需的salt"""
    SALT_DATA: str = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
    """6X - Android 设备传入content生成 DS 所需的 salt"""
    SALT_PARAMS: str = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
    """4X - Android 设备传入url参数生成 DS 所需的 salt"""
    SALT_PROD: str = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
    """PROD - 账号相关"""

    class Config:
        """Pydantic配置"""

        extra = "ignore"


class DeviceConfig(BaseModel):
    """
    设备信息
    Headers所用的各种数据，非必要请勿修改
    """

    USER_AGENT_MOBILE: str = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) miHoYoBBS/2.55.1"
    )
    """移动端 User-Agent(Mozilla UA)"""
    USER_AGENT_PC: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.0 Safari/605.1.15"
    )
    """桌面端 User-Agent(Mozilla UA)"""
    USER_AGENT_OTHER: str = "Hyperion/275 CFNetwork/1402.0.8 Darwin/22.2.0"
    """获取用户 ActionTicket 时Headers所用的 User-Agent"""
    USER_AGENT_ANDROID: str = (
        "Mozilla/5.0 (Linux; Android 11; MI 8 SE Build/RQ3A.211001.001; wv) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Version/4.0 Chrome/104.0.5112.97 Mobile Safari/537.36 "
        "miHoYoBBS/2.55.1"
    )
    """安卓端 User-Agent(Mozilla UA)"""
    USER_AGENT_ANDROID_OTHER: str = "okhttp/4.9.3"
    """安卓端 User-Agent(专用于米游币任务等)"""
    USER_AGENT_WIDGET: str = "WidgetExtension/231 CFNetwork/1390 Darwin/22.0.0"
    """iOS 小组件 User-Agent(原神实时便笺)"""

    X_RPC_DEVICE_MODEL_MOBILE: str = "iPhone10,2"
    """移动端 x-rpc-device_model"""
    X_RPC_DEVICE_MODEL_PC: str = "OS X 10.15.7"
    """桌面端 x-rpc-device_model"""
    X_RPC_DEVICE_MODEL_ANDROID: str = "MI 8 SE"
    """安卓端 x-rpc-device_model"""

    X_RPC_DEVICE_NAME_MOBILE: str = "iPhone"
    """移动端 x-rpc-device_name"""
    X_RPC_DEVICE_NAME_PC: str = "Microsoft Edge 103.0.1264.62"
    """桌面端 x-rpc-device_name"""
    X_RPC_DEVICE_NAME_ANDROID: str = "Xiaomi MI 8 SE"
    """安卓端 x-rpc-device_name"""

    X_RPC_SYS_VERSION: str = "16.2"
    """Headers所用的 x-rpc-sys_version"""
    X_RPC_SYS_VERSION_ANDROID: str = "11"
    """安卓端 x-rpc-sys_version"""

    X_RPC_CHANNEL: str = "appstore"
    """Headers所用的 x-rpc-channel"""
    X_RPC_CHANNEL_ANDROID: str = "miyousheluodi"
    """安卓端 x-rpc-channel"""

    X_RPC_APP_VERSION: str = "2.63.1"
    """Headers所用的 x-rpc-app_version"""
    X_RPC_PLATFORM: str = "ios"
    """Headers所用的 x-rpc-platform"""
    UA: str = '".Not/A)Brand";v="99", "Microsoft Edge";v="103", "Chromium";v="103"'
    """Headers所用的 sec-ch-ua"""
    UA_PLATFORM: str = '"macOS"'
    """Headers所用的 sec-ch-ua-platform"""

    class Config:
        """Pydantic配置"""

        extra = "ignore"


class PluginConfig(BaseSettings):
    """插件配置"""

    preference: Preference = Preference()

    class Config:
        """Pydantic配置"""

        extra = "ignore"
        env_file = ".env"


class PluginEnv(BaseSettings):
    """插件环境配置"""

    salt_config: SaltConfig = SaltConfig()
    device_config: DeviceConfig = DeviceConfig()

    class Config:
        """Pydantic配置"""

        env_prefix = "mystool_"
        env_file = ".env"
        extra = "ignore"


# 修正：添加logger的定义或导入
try:
    import logging

    logger = logging.getLogger(__name__)
except ImportError:
    # 简单的logger回退
    class SimpleLogger:
        def info(self, msg):
            print(f"INFO: {msg}")

        def exception(self, msg):
            print(f"ERROR: {msg}")

    logger = SimpleLogger()


# 初始化配置
try:
    if project_config_path.exists() and project_config_path.is_file():
        plugin_config = PluginConfig.parse_file(project_config_path)
    else:
        plugin_config = PluginConfig()
        # 创建默认配置文件
        try:
            str_data = plugin_config.json(indent=4)
            project_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(project_config_path, "w", encoding="utf-8") as f:
                f.write(str_data)
        except (AttributeError, TypeError, ValueError, PermissionError) as e:
            logger.exception(
                f"创建插件配置文件失败，请检查是否有权限读取和写入 {project_config_path}: {e}"
            )
            # 如果创建失败，使用默认配置
            plugin_config = PluginConfig()
        else:
            logger.info(
                f"插件配置文件 {project_config_path} 不存在，已创建默认插件配置文件。"
            )

    # 初始化环境配置
    plugin_env = PluginEnv()

except Exception as e:
    logger.exception(f"初始化配置失败: {e}")
    # 回退到默认配置
    plugin_config = PluginConfig()
    plugin_env = PluginEnv()
