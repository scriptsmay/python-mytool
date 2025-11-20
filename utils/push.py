import hmac
import time
import base64
import urllib.parse
import hashlib
from typing import Optional, Dict, Any, Union, List
from dataclasses import dataclass, field
from config.logger import logger
from configparser import ConfigParser


@dataclass
class PushConfig:
    """推送配置类"""

    # 使用 field 提供默认值，简化 __post_init__
    enable: bool = True
    error_push_only: bool = False
    push_servers: List[str] = field(default_factory=list)
    push_block_keys: List[str] = field(default_factory=list)

    # 各推送服务的配置
    telegram: Dict[str, Any] = field(default_factory=dict)
    dingrobot: Dict[str, Any] = field(default_factory=dict)
    feishubot: Dict[str, Any] = field(default_factory=dict)
    bark: Dict[str, Any] = field(default_factory=dict)
    gotify: Dict[str, Any] = field(default_factory=dict)
    webhook: Dict[str, Any] = field(default_factory=dict)


# 推送标题映射
PUSH_TITLES = {
    -99: "「脚本」依赖缺失",
    -2: "「脚本」StatusID 错误",
    -1: "「脚本」Config版本已更新",
    0: "「脚本」执行成功!",
    1: "「脚本」执行失败!",
    2: "「脚本」部分账号执行失败！",
    3: "「脚本」社区/游戏道具签到触发验证码！",
}

# 支持的推送方式（可简化为列表或集合）
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
            transport=httpx.HTTPTransport(retries=10),
            follow_redirects=True,
            **kwargs,
        )
    except (ImportError, TypeError):
        import requests
        from requests.adapters import HTTPAdapter

        session = requests.Session()
        session.mount("http://", HTTPAdapter(max_retries=10))
        session.mount("https://", HTTPAdapter(max_retries=10))

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
        config: Optional[PushConfig] = None,
        config_file: Optional[str] = None,
        http_client: Optional[Any] = None,
    ):
        """
        初始化推送处理器

        Args:
            config: 推送配置对象
            config_file: 配置文件路径
            http_client: 可选的 HTTP 客户端实例
        """
        self.http = http_client or get_new_session()
        self.config = config or self._load_config_from_file(config_file)

    def _load_config_from_file(self, config_file: Optional[str] = None) -> PushConfig:
        """从配置文件加载配置"""
        cfg = ConfigParser()
        cfg.read(config_file or "config.ini", encoding="utf-8")

        # 简化的配置加载逻辑
        def get_list(section, key, fallback=""):
            value = cfg.get(section, key, fallback=fallback)
            return [item.strip() for item in value.split(",") if item.strip()]

        push_config = PushConfig(
            enable=cfg.getboolean("setting", "enable", fallback=True),
            error_push_only=cfg.getboolean(
                "setting", "error_push_only", fallback=False
            ),
            push_servers=get_list("setting", "push_server"),
            push_block_keys=get_list("setting", "push_block_keys"),
        )

        # 使用辅助方法加载各服务配置
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
        # 简化的敏感信息过滤
        for sensitive in ["token=", "secret=", "key=", "password="]:
            if sensitive in error_msg:
                error_msg = error_msg.split(sensitive)[0] + f"{sensitive}***"
        logger.error(f"{service_name} 推送失败: {error_msg}")

    def _check_required_config(
        self, config: Dict[str, Any], required_keys: List[str]
    ) -> bool:
        """检查必需配置项"""
        return all(config.get(key, "").strip() for key in required_keys)

    def _send_request(self, method: str, url: str, **kwargs) -> bool:
        """统一的请求发送方法"""
        try:
            session = self.http
            if method.upper() == "GET":
                response = session.get(url, **kwargs)
            else:  # POST
                response = session.post(url, **kwargs)

            response.raise_for_status()
            return True
        except Exception as e:
            self._safe_log_error("HTTP请求", e)
            return False

    def telegram(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Telegram 推送"""
        config = self.config.telegram
        if not self._check_required_config(config, ["api_url", "bot_token", "chat_id"]):
            logger.warning("Telegram 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)
        http_proxy = config.get("http_proxy")
        session = get_new_session_use_proxy(http_proxy) if http_proxy else self.http

        return self._send_request(
            "POST",
            url=f"https://{config['api_url']}/bot{config['bot_token']}/sendMessage",
            data={"chat_id": config["chat_id"], "text": message},
        )

    def dingrobot(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """钉钉群机器人推送"""
        config = self.config.dingrobot
        if not self._check_required_config(config, ["webhook"]):
            logger.warning("钉钉机器人配置不完整")
            return False

        api_url = config["webhook"]
        secret = config.get("secret")

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
        if not self._check_required_config(config, ["webhook"]):
            logger.warning("飞书机器人配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)

        return self._send_request(
            "POST",
            url=config["webhook"],
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msg_type": "text", "content": {"text": message}},
        )

    def bark(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Bark 推送"""
        config = self.config.bark
        if not self._check_required_config(config, ["api_url", "token"]):
            logger.warning("Bark 配置不完整")
            return False

        send_title = urllib.parse.quote_plus(get_push_title(status_id))
        encoded_message = urllib.parse.quote_plus(push_message)
        icon = config.get("icon", "default")
        icon_param = (
            f"&icon=https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo/{icon}.png"
        )

        return self._send_request(
            "GET",
            url=f'{config["api_url"]}/{config["token"]}/{send_title}/{encoded_message}?{icon_param}',
        )

    def gotify(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Gotify 推送"""
        config = self.config.gotify
        if not self._check_required_config(config, ["api_url", "token"]):
            logger.warning("Gotify 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)

        return self._send_request(
            "POST",
            url=f'{config["api_url"]}/message?token={config["token"]}',
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "title": get_push_title(status_id),
                "message": message,
                "priority": config.get("priority", 5),
            },
        )

    def webhook(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """WebHook 推送"""
        config = self.config.webhook
        if not self._check_required_config(config, ["webhook_url"]):
            logger.warning("WebHook 配置不完整")
            return False

        message = self._prepare_message(status_id, push_message, img_file)

        return self._send_request(
            "POST",
            url=config["webhook_url"],
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

        logger.info("正在执行推送...")
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

        return all(results)


# 全局配置和函数
_global_push_config: Optional[PushConfig] = None


def init_config(config: PushConfig) -> None:
    """初始化全局推送配置"""
    global _global_push_config
    _global_push_config = config


def push(
    status: int = 0,
    push_message: str = "",
    img_file: Optional[bytes] = None,
    config: Optional[PushConfig] = None,
    config_file: Optional[str] = None,
) -> bool:
    """推送消息到指定平台"""
    # 配置优先级: 参数config > 全局配置 > 配置文件 > 默认配置
    if config:
        push_handler = PushHandler(config=config)
    elif _global_push_config:
        push_handler = PushHandler(config=_global_push_config)
    elif config_file:
        push_handler = PushHandler(config_file=config_file)
    else:
        push_handler = PushHandler()

    return push_handler.push(status, push_message, img_file)


# 使用示例
if __name__ == "__main__":
    # 测试推送
    test_config = PushConfig(
        enable=True,
        push_servers=["bark"],  # 使用不需要真实配置的服务测试
        bark={"api_url": "http://example.com", "token": "test"},
    )

    push(0, f"测试推送 {int(time.time())}", config=test_config)
