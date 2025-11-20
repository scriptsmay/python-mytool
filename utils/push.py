import hmac
import time
import base64
import urllib.parse
import hashlib
from typing import Optional, Dict, Any, Union, List
from dataclasses import dataclass, field
from config.logger import logger
from configparser import ConfigParser

# 导入新的配置模型
try:
    from models.data_models import PushConfig as NewPushConfig
    from models.data_models import (
        TelegramConfig,
        DingRobotConfig,
        FeishuBotConfig,
        BarkConfig,
        GotifyConfig,
        WebhookConfig,
    )
except ImportError:
    # 回退到旧的 dataclass
    @dataclass
    class NewPushConfig:
        enable: bool = True
        error_push_only: bool = False
        push_servers: List[str] = field(default_factory=list)
        push_block_keys: List[str] = field(default_factory=list)
        telegram: Any = field(default_factory=dict)
        dingrobot: Any = field(default_factory=dict)
        feishubot: Any = field(default_factory=dict)
        bark: Any = field(default_factory=dict)
        gotify: Any = field(default_factory=dict)
        webhook: Any = field(default_factory=dict)


# 推送标题映射
PUSH_TITLES = {
    -99: "「米忽悠签到」依赖缺失",
    -2: "「米忽悠签到」StatusID 错误",
    -1: "「米忽悠签到」Config版本已更新",
    0: "「米忽悠签到」执行成功",
    1: "「米忽悠签到」执行失败",
    2: "「米忽悠签到」部分账号执行失败",
    3: "「米忽悠签到」社区/游戏道具签到触发验证码！",
}

# 支持的推送方式
SUPPORTED_PUSH_METHODS = {
    "telegram",
    "dingrobot",
    "feishubot",
    "bark",
    "gotify",
    "webhook",
}


# HTTP 客户端相关函数保持不变
def get_new_session(**kwargs) -> Any:
    """创建 HTTP 客户端实例"""
    try:
        import httpx

        return httpx.Client(
            timeout=30,
            transport=httpx.HTTPTransport(retries=3),
            follow_redirects=True,
            **kwargs,
        )
    except (ImportError, TypeError):
        import requests
        from requests.adapters import HTTPAdapter

        session = requests.Session()
        session.mount("http://", HTTPAdapter(max_retries=3))
        session.mount("https://", HTTPAdapter(max_retries=3))
        if "proxies" in kwargs:
            session.proxies.update(kwargs["proxies"])
        return session


def is_module_available(module_name: str) -> bool:
    """检查模块是否可用"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def get_new_session_use_proxy(http_proxy: str):
    """根据代理创建 Session"""
    proxies_dict = {
        "http://": f"http://{http_proxy}",
        "https://": f"http://{http_proxy}",
    }
    if is_module_available("httpx"):
        return get_new_session(proxies=proxies_dict)
    else:
        session = get_new_session()
        session.proxies = proxies_dict
        return session


def get_push_title(status_id: int) -> str:
    """获取推送标题"""
    return PUSH_TITLES.get(status_id, PUSH_TITLES.get(-2))


class PushHandler:
    """推送处理器"""

    def __init__(
        self,
        config: Optional[NewPushConfig] = None,
        config_file: Optional[str] = None,
        http_client: Optional[Any] = None,
    ):
        """
        初始化推送处理器
        """
        self.http = http_client or get_new_session()
        self.config = config or self._load_config_from_file(config_file)

    def _load_config_from_file(
        self, config_file: Optional[str] = None
    ) -> NewPushConfig:
        """从配置文件加载配置"""
        cfg = ConfigParser()
        cfg.read(config_file or "config.ini", encoding="utf-8")

        def get_list(section, key, fallback=""):
            value = cfg.get(section, key, fallback=fallback)
            return [item.strip() for item in value.split(",") if item.strip()]

        # 创建新的配置对象
        push_config = NewPushConfig(
            enable=cfg.getboolean("setting", "enable", fallback=True),
            error_push_only=cfg.getboolean(
                "setting", "error_push_only", fallback=False
            ),
            push_servers=get_list("setting", "push_server"),
            push_block_keys=get_list("setting", "push_block_keys"),
        )

        # 加载各服务配置
        service_configs = {
            "telegram": ["api_url", "bot_token", "chat_id", "http_proxy"],
            "dingrobot": ["webhook", "secret"],
            "feishubot": ["webhook"],
            "bark": ["api_url", "token", "icon"],
            "gotify": ["api_url", "token", "priority"],
            "webhook": ["webhook_url"],
        }

        for service, keys in service_configs.items():
            if cfg.has_section(service):
                config_dict = {}
                for key in keys:
                    if key == "priority":
                        config_dict[key] = cfg.getint(service, key, fallback=5)
                    else:
                        config_dict[key] = cfg.get(service, key, fallback="")
                setattr(push_config, service, config_dict)

        return push_config

    def _msg_replace(self, msg: str) -> str:
        """消息内容关键词替换"""
        if not self.config.push_block_keys:
            return msg
        result = str(msg)
        for block_key in self.config.push_block_keys:
            if block_key:
                result = result.replace(block_key, "*" * len(block_key))
        return result

    def _prepare_message(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> str:
        """准备消息内容"""
        title = get_push_title(status_id)
        message = f"{title}\n\n{push_message}"
        if img_file:
            base64_data = base64.b64encode(img_file).decode("utf-8")
            message = f"{message}\n\n![图片](data:image/png;base64,{base64_data})"
        return message

    def _safe_log_error(self, service_name: str, exception: Exception):
        """安全地记录错误日志"""
        error_msg = str(exception)
        for sensitive in ["token=", "secret=", "key=", "password="]:
            if sensitive in error_msg:
                error_msg = error_msg.split(sensitive)[0] + f"{sensitive}***"
        logger.error(f"{service_name} 推送失败: {error_msg}")

    def _get_config_value(self, config_obj, key, default=None):
        """安全获取配置值，兼容字典和对象"""
        if hasattr(config_obj, key):
            return getattr(config_obj, key)
        elif isinstance(config_obj, dict):
            return config_obj.get(key, default)
        return default

    def _is_config_configured(self, config_obj, required_keys: List[str]) -> bool:
        """检查配置是否完整"""
        for key in required_keys:
            value = self._get_config_value(config_obj, key, "")
            if not str(value).strip():
                return False
        return True

    def _send_request(self, method: str, url: str, **kwargs) -> bool:
        """统一的请求发送方法"""
        try:
            session = self.http
            if method.upper() == "GET":
                response = session.get(url, timeout=30, **kwargs)
            else:
                response = session.post(url, timeout=30, **kwargs)
            response.raise_for_status()
            return True
        except Exception as e:
            self._safe_log_error("HTTP请求", e)
            return False

    def check_telegram_connectivity(self) -> bool:
        """检查 Telegram API 连通性"""
        config = self.config.telegram
        if not self._is_config_configured(config, ["api_url", "bot_token"]):
            return False

        api_url = self._get_config_value(config, "api_url")
        bot_token = self._get_config_value(config, "bot_token")

        try:
            # 简单的连通性测试
            test_url = f"https://{api_url}/bot{bot_token}/getMe"
            logger.debug(f"Telegram API 连通性测试: {test_url}")
            response = self.http.get(test_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Telegram API 连通性检查失败: {e}")
            return False

    def telegram(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Telegram 推送"""
        if not self.check_telegram_connectivity():
            logger.warning("Telegram 配置不完整或无法连接")
            return False
        config = self.config.telegram
        if not self._is_config_configured(config, ["api_url", "bot_token", "chat_id"]):
            logger.warning("Telegram 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)
        http_proxy = self._get_config_value(config, "http_proxy")
        session = get_new_session_use_proxy(http_proxy) if http_proxy else self.http

        api_url = self._get_config_value(config, "api_url")
        bot_token = self._get_config_value(config, "bot_token")
        chat_id = self._get_config_value(config, "chat_id")

        return self._send_request(
            "POST",
            url=f"https://{api_url}/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
        )

    def dingrobot(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """钉钉群机器人推送"""
        config = self.config.dingrobot
        if not self._is_config_configured(config, ["webhook"]):
            logger.warning("钉钉机器人配置不完整")
            return False

        api_url = self._get_config_value(config, "webhook")
        secret = self._get_config_value(config, "secret")

        # 签名计算
        if secret:
            timestamp = str(round(time.time() * 1000))
            sign_string = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                key=secret.encode("utf-8"),
                msg=sign_string.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
            api_url = f"{api_url}&timestamp={timestamp}&sign={sign}"

        message = self._prepare_message(status_id, push_message, img_file)

        return self._send_request(
            "POST",
            url=api_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msgtype": "text", "text": {"content": message}},
        )

    def feishubot(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """飞书机器人推送"""
        config = self.config.feishubot
        if not self._is_config_configured(config, ["webhook"]):
            logger.warning("飞书机器人配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)
        webhook_url = self._get_config_value(config, "webhook")

        return self._send_request(
            "POST",
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msg_type": "text", "content": {"text": message}},
        )

    def bark(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Bark 推送"""
        config = self.config.bark
        if not self._is_config_configured(config, ["api_url", "token"]):
            logger.warning("Bark 配置不完整")
            return False

        send_title = urllib.parse.quote_plus(get_push_title(status_id))
        encoded_message = urllib.parse.quote_plus(push_message)
        icon = self._get_config_value(config, "icon", "default")
        icon_param = (
            f"&icon=https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo/{icon}.png"
        )

        api_url = self._get_config_value(config, "api_url")
        token = self._get_config_value(config, "token")

        return self._send_request(
            "GET",
            url=f"{api_url}/{token}/{send_title}/{encoded_message}?{icon_param}",
        )

    def gotify(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Gotify 推送"""
        config = self.config.gotify
        if not self._is_config_configured(config, ["api_url", "token"]):
            logger.warning("Gotify 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)
        api_url = self._get_config_value(config, "api_url")
        token = self._get_config_value(config, "token")
        priority = self._get_config_value(config, "priority", 5)

        return self._send_request(
            "POST",
            url=f"{api_url}/message?token={token}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "title": get_push_title(status_id),
                "message": message,
                "priority": priority,
            },
        )

    def webhook(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """WebHook 推送"""
        config = self.config.webhook
        if not self._is_config_configured(config, ["webhook_url"]):
            logger.warning("WebHook 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)
        webhook_url = self._get_config_value(config, "webhook_url")

        return self._send_request(
            "POST",
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"title": get_push_title(status_id), "message": message},
        )

    def push(
        self, status: int = 0, push_message: str = "", img_file: Optional[bytes] = None
    ) -> bool:
        """执行推送"""
        logger.debug(f"消息内容: {push_message}")

        # 检查推送条件
        if not self.config.enable:
            logger.info("推送功能已禁用")
            return True

        if self.config.error_push_only and status == 0:
            logger.info("仅错误时推送，当前状态为成功，跳过推送")
            return True

        # logger.info("正在执行推送...")
        processed_message = self._msg_replace(push_message)

        # 执行推送
        results = []
        for push_server in self.config.push_servers:
            if push_server not in SUPPORTED_PUSH_METHODS:
                logger.warning(f"不支持的推送服务: {push_server}")
                continue

            logger.debug(f"使用推送服务: {push_server}")
            try:
                push_method = getattr(self, push_server)
                success = push_method(status, processed_message, img_file)
                status_msg = "成功" if success else "失败"
                logger.info(f"{push_server} - 推送{status_msg}")
                results.append(success)
            except Exception as e:
                self._safe_log_error(push_server, e)
                results.append(False)

        return all(results) if results else True


# 全局配置和函数
_global_push_config: Optional[NewPushConfig] = None


def init_config(config: NewPushConfig) -> None:
    """初始化全局推送配置"""
    global _global_push_config
    _global_push_config = config


def push(
    status: int = 0,
    push_message: str = "",
    img_file: Optional[bytes] = None,
    config: Optional[NewPushConfig] = None,
    config_file: Optional[str] = None,
) -> bool:
    """推送消息到指定平台"""
    if config:
        push_handler = PushHandler(config=config)
    elif _global_push_config:
        push_handler = PushHandler(config=_global_push_config)
    elif config_file:
        push_handler = PushHandler(config_file=config_file)
    else:
        push_handler = PushHandler()

    return push_handler.push(status, push_message, img_file)
