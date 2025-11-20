from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    FieldValidationInfo,
)
from typing import Optional, Dict, Any, List, ClassVar
from datetime import datetime


class TelegramConfig(BaseModel):
    """Telegram 推送配置"""

    api_url: str = "api.telegram.org"
    """Telegram API 地址"""
    bot_token: str = ""
    """Telegram Bot Token"""
    chat_id: str = ""
    """Telegram 聊天 ID"""
    http_proxy: Optional[str] = None
    """HTTP 代理地址"""

    @field_validator("api_url", "bot_token", "chat_id")
    @classmethod
    def check_required_fields(cls, v: str, info: FieldValidationInfo) -> str:
        field_name = info.field_name
        if not v and field_name in ["bot_token", "chat_id"]:
            raise ValueError(f"{field_name} 是必填字段")
        return v

    model_config = ConfigDict(extra="ignore")


class DingRobotConfig(BaseModel):
    """钉钉机器人推送配置"""

    webhook: str = ""
    """钉钉机器人 Webhook URL"""
    secret: str = ""
    """钉钉机器人签名密钥"""

    @field_validator("webhook")
    @classmethod
    def check_webhook(cls, v: str) -> str:
        if not v:
            raise ValueError("webhook 是必填字段")
        return v

    model_config = ConfigDict(extra="ignore")


class FeishuBotConfig(BaseModel):
    """飞书机器人推送配置"""

    webhook: str = ""
    """飞书机器人 Webhook URL"""

    @field_validator("webhook")
    @classmethod
    def check_webhook(cls, v: str) -> str:
        if not v:
            raise ValueError("webhook 是必填字段")
        return v

    model_config = ConfigDict(extra="ignore")


class BarkConfig(BaseModel):
    """Bark 推送配置"""

    api_url: str = ""
    """Bark API 地址"""
    token: str = ""
    """Bark 设备 Token"""
    icon: str = "default"
    """Bark 推送图标"""

    @field_validator("api_url", "token")
    @classmethod
    def check_required_fields(cls, v: str, info: FieldValidationInfo) -> str:
        if not v:
            raise ValueError(f"{info.field_name} 是必填字段")
        return v

    model_config = ConfigDict(extra="ignore")


class GotifyConfig(BaseModel):
    """Gotify 推送配置"""

    api_url: str = ""
    """Gotify API 地址"""
    token: str = ""
    """Gotify 应用 Token"""
    priority: int = Field(default=5, ge=0, le=10)
    """Gotify 推送优先级 (0-10)"""

    @field_validator("api_url", "token")
    @classmethod
    def check_required_fields(cls, v: str, info: FieldValidationInfo) -> str:
        if not v:
            raise ValueError(f"{info.field_name} 是必填字段")
        return v

    model_config = ConfigDict(extra="ignore")


class WebhookConfig(BaseModel):
    """WebHook 推送配置"""

    webhook_url: str = ""
    """WebHook URL"""
    headers: Dict[str, str] = Field(default_factory=dict)
    """自定义请求头"""
    method: str = "POST"
    """请求方法"""
    template: Optional[Dict[str, Any]] = None
    """消息模板"""

    @field_validator("webhook_url")
    @classmethod
    def check_webhook_url(cls, v: str) -> str:
        if not v:
            raise ValueError("webhook_url 是必填字段")
        return v

    @field_validator("method")
    @classmethod
    def check_method(cls, v: str) -> str:
        if v.upper() not in ["GET", "POST", "PUT"]:
            raise ValueError("method 必须是 GET、POST 或 PUT")
        return v.upper()

    model_config = ConfigDict(extra="ignore")


class PushConfig(BaseModel):
    """
    推送配置
    """

    enable: bool = True
    """是否启用推送功能"""
    error_push_only: bool = False
    """是否仅在出错时推送"""
    push_servers: List[str] = Field(default_factory=list)
    """推送服务器列表"""
    push_block_keys: List[str] = Field(default_factory=list)
    """消息内容屏蔽关键词列表"""
    timeout: float = 10
    """推送请求超时时间（单位：秒）"""
    max_retry_times: int = 3
    """推送最大重试次数"""
    retry_interval: float = 2
    """推送重试间隔（单位：秒）"""

    # 各推送服务的配置
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    """Telegram 推送配置"""
    dingrobot: DingRobotConfig = Field(default_factory=DingRobotConfig)
    """钉钉机器人推送配置"""
    feishubot: FeishuBotConfig = Field(default_factory=FeishuBotConfig)
    """飞书机器人推送配置"""
    bark: BarkConfig = Field(default_factory=BarkConfig)
    """Bark 推送配置"""
    gotify: GotifyConfig = Field(default_factory=GotifyConfig)
    """Gotify 推送配置"""
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    """WebHook 推送配置"""

    # 有效的推送服务器列表
    _valid_servers: ClassVar[List[str]] = [
        "telegram",
        "dingrobot",
        "feishubot",
        "bark",
        "gotify",
        "webhook",
    ]

    @field_validator("push_servers", mode="before")
    @classmethod
    def validate_push_servers_format(cls, v: Any) -> List[str]:
        """验证并格式化推送服务器列表"""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("push_servers", mode="after")
    @classmethod
    def validate_push_servers_content(cls, v: List[str]) -> List[str]:
        """验证推送服务器内容"""
        for server in v:
            if server not in cls._valid_servers:
                raise ValueError(
                    f"推送服务器必须是以下之一: {', '.join(cls._valid_servers)}"
                )
        return v

    @field_validator("push_block_keys", mode="before")
    @classmethod
    def validate_push_block_keys_format(cls, v: Any) -> List[str]:
        """验证并格式化屏蔽关键词列表"""
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    @field_validator("timeout", "retry_interval")
    @classmethod
    def validate_positive_numbers(cls, v: float) -> float:
        """验证正数"""
        if v <= 0:
            raise ValueError("必须大于 0")
        return v

    @field_validator("max_retry_times")
    @classmethod
    def validate_max_retry_times(cls, v: int) -> int:
        """验证最大重试次数"""
        if v < 0:
            raise ValueError("必须大于等于 0")
        return v

    @model_validator(mode="after")
    def validate_config_consistency(self) -> "PushConfig":
        """验证配置一致性"""
        # 检查启用的推送服务器是否有对应的配置
        for server in self.push_servers:
            server_config = getattr(self, server, None)
            if server_config and hasattr(server_config, "is_configured"):
                if not server_config.is_configured():
                    raise ValueError(f"{server} 配置不完整")
        return self

    @property
    def should_push(self) -> bool:
        """检查是否应该推送"""
        return self.enable

    def should_push_for_status(self, status: int) -> bool:
        """
        根据状态判断是否应该推送

        Args:
            status: 状态码

        Returns:
            bool: 是否应该推送
        """
        if not self.enable:
            return False

        if self.error_push_only and status == 0:
            return False

        return True

    def get_enabled_servers(self) -> List[str]:
        """获取启用的推送服务器列表"""
        return [server for server in self.push_servers if server]

    def is_server_enabled(self, server_name: str) -> bool:
        """检查指定推送服务器是否启用"""
        return server_name in self.push_servers

    def is_server_configured(self, server_name: str) -> bool:
        """检查指定推送服务器是否已配置"""
        if not self.is_server_enabled(server_name):
            return False

        server_config = getattr(self, server_name, None)
        if not server_config:
            return False

        # 检查必要配置字段
        if server_name == "telegram":
            return bool(server_config.bot_token and server_config.chat_id)
        elif server_name == "dingrobot":
            return bool(server_config.webhook)
        elif server_name == "feishubot":
            return bool(server_config.webhook)
        elif server_name == "bark":
            return bool(server_config.api_url and server_config.token)
        elif server_name == "gotify":
            return bool(server_config.api_url and server_config.token)
        elif server_name == "webhook":
            return bool(server_config.webhook_url)

        return False

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )


# 为各配置类添加配置检查方法
def add_config_check_methods():
    """为各配置类添加配置检查方法"""

    def is_configured_telegram(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def is_configured_dingrobot(self) -> bool:
        return bool(self.webhook)

    def is_configured_feishubot(self) -> bool:
        return bool(self.webhook)

    def is_configured_bark(self) -> bool:
        return bool(self.api_url and self.token)

    def is_configured_gotify(self) -> bool:
        return bool(self.api_url and self.token)

    def is_configured_webhook(self) -> bool:
        return bool(self.webhook_url)

    # 为各配置类添加方法
    TelegramConfig.is_configured = is_configured_telegram
    DingRobotConfig.is_configured = is_configured_dingrobot
    FeishuBotConfig.is_configured = is_configured_feishubot
    BarkConfig.is_configured = is_configured_bark
    GotifyConfig.is_configured = is_configured_gotify
    WebhookConfig.is_configured = is_configured_webhook


# 初始化配置检查方法
add_config_check_methods()


# 使用示例
if __name__ == "__main__":
    # 创建完整的配置
    config = PushConfig(
        enable=True,
        error_push_only=False,
        push_servers=["telegram", "dingrobot"],
        push_block_keys=["密码", "token"],
        timeout=15,
        max_retry_times=3,
        telegram=TelegramConfig(
            api_url="api.telegram.org",
            bot_token="123456:ABC-DEF1234ghIkl",
            chat_id="123456789",
        ),
        dingrobot=DingRobotConfig(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            secret="SECxxx",
        ),
    )

    # 验证配置
    print(config.model_dump_json(indent=2))
    print(f"启用的服务器: {config.get_enabled_servers()}")
    print(f"是否应该推送状态0: {config.should_push_for_status(0)}")
    print(f"Telegram 是否已配置: {config.is_server_configured('telegram')}")
