import hmac
import time
import base64
import urllib.parse
import hashlib
from typing import Optional, Dict, Any, Union, List
from dataclasses import dataclass
from .request import get_new_session, get_new_session_use_proxy
from .logger import logger
from configparser import ConfigParser


@dataclass
class PushConfig:
    """推送配置类"""

    # 配置项定义
    enable: bool = True
    error_push_only: bool = False
    push_servers: List[str] = None
    push_block_keys: List[str] = None

    # 各推送服务的配置
    telegram: Dict[str, Any] = None
    dingrobot: Dict[str, Any] = None
    feishubot: Dict[str, Any] = None
    bark: Dict[str, Any] = None
    gotify: Dict[str, Any] = None
    webhook: Dict[str, Any] = None

    def __post_init__(self):
        if self.push_servers is None:
            self.push_servers = []
        if self.push_block_keys is None:
            self.push_block_keys = []
        if self.telegram is None:
            self.telegram = {}
        if self.dingrobot is None:
            self.dingrobot = {}
        if self.feishubot is None:
            self.feishubot = {}
        if self.bark is None:
            self.bark = {}
        if self.gotify is None:
            self.gotify = {}
        if self.webhook is None:
            self.webhook = {}


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

# 支持的推送方式
PUSH_METHODS = {
    "telegram": "telegram",
    "dingrobot": "dingrobot",
    "feishubot": "feishubot",
    "bark": "bark",
    "gotify": "gotify",
    "webhook": "webhook",
}


def get_push_title(status_id: int) -> str:
    """获取推送标题"""
    return PUSH_TITLES.get(status_id, PUSH_TITLES.get(-2))


class PushHandler:
    """推送处理器"""

    def __init__(
        self, config: Optional[PushConfig] = None, config_file: Optional[str] = None
    ):
        """
        初始化推送处理器

        Args:
            config: 推送配置对象
            config_file: 配置文件路径（如果提供config则优先使用config）
        """
        self.http = get_new_session()

        if config:
            self.config = config
        else:
            self.config = self._load_config_from_file(config_file)

    def _load_config_from_file(self, config_file: Optional[str] = None) -> PushConfig:
        """从配置文件加载配置"""
        cfg = ConfigParser()
        if config_file:
            cfg.read(config_file, encoding="utf-8")
        else:
            # 默认读取配置文件的逻辑
            cfg.read("config.ini", encoding="utf-8")

        # 构建 PushConfig 对象
        push_config = PushConfig(
            enable=cfg.getboolean("setting", "enable", fallback=True),
            error_push_only=cfg.getboolean(
                "setting", "error_push_only", fallback=False
            ),
            push_servers=[
                s.strip()
                for s in cfg.get("setting", "push_server", fallback="")
                .lower()
                .split(",")
                if s.strip()
            ],
            push_block_keys=[
                k.strip()
                for k in cfg.get("setting", "push_block_keys", fallback="").split(",")
                if k.strip()
            ],
        )

        # 加载各推送服务的配置
        if cfg.has_section("telegram"):
            push_config.telegram = {
                "api_url": cfg.get("telegram", "api_url", fallback=""),
                "bot_token": cfg.get("telegram", "bot_token", fallback=""),
                "chat_id": cfg.get("telegram", "chat_id", fallback=""),
                "http_proxy": cfg.get("telegram", "http_proxy", fallback=None),
            }

        if cfg.has_section("dingrobot"):
            push_config.dingrobot = {
                "webhook": cfg.get("dingrobot", "webhook", fallback=""),
                "secret": cfg.get("dingrobot", "secret", fallback=""),
            }

        if cfg.has_section("feishubot"):
            push_config.feishubot = {
                "webhook": cfg.get("feishubot", "webhook", fallback=""),
            }

        if cfg.has_section("bark"):
            push_config.bark = {
                "api_url": cfg.get("bark", "api_url", fallback=""),
                "token": cfg.get("bark", "token", fallback=""),
                "icon": cfg.get("bark", "icon", fallback=""),
            }

        if cfg.has_section("gotify"):
            push_config.gotify = {
                "api_url": cfg.get("gotify", "api_url", fallback=""),
                "token": cfg.get("gotify", "token", fallback=""),
                "priority": cfg.getint("gotify", "priority", fallback=5),
            }

        if cfg.has_section("webhook"):
            push_config.webhook = {
                "webhook_url": cfg.get("webhook", "webhook_url", fallback=""),
            }

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
        """安全地记录错误日志，隐藏敏感字段"""
        error_msg = str(exception)
        # 替换常见的敏感字段
        sensitive_keywords = ["token=", "secret=", "key=", "password="]
        for keyword in sensitive_keywords:
            idx = error_msg.find(keyword)
            if idx != -1:
                start_idx = idx + len(keyword)
                end_idx = start_idx + 10  # 截断显示长度
                error_msg = error_msg[:start_idx] + "***" + error_msg[end_idx:]
        logger.error(f"{service_name} 推送失败: {error_msg}")

    def telegram(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Telegram 推送"""
        try:
            config = self.config.telegram
            if not all(
                [
                    config.get("api_url", "").strip(),
                    config.get("bot_token", "").strip(),
                    config.get("chat_id", "").strip(),
                ]
            ):
                logger.warning("Telegram 配置不完整")
                return False

            message = self._prepare_message(status_id, push_message, img_file)
            http_proxy = config.get("http_proxy")
            session = get_new_session_use_proxy(http_proxy) if http_proxy else self.http

            response = session.post(
                url=f"https://{config['api_url']}/bot{config['bot_token']}/sendMessage",
                data={
                    "chat_id": config["chat_id"],
                    "text": message,
                },
            )
            response.raise_for_status()
            logger.info("Telegram 推送成功")
            return True
        except Exception as e:
            self._safe_log_error("Telegram", e)
            return False

    def dingrobot(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """钉钉群机器人推送"""
        try:
            config = self.config.dingrobot
            if not config.get("webhook", "").strip():
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

            response = self.http.post(
                url=api_url,
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "msgtype": "text",
                    "text": {"content": message},
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"钉钉推送结果: {result.get('errmsg', '未知')}")
            return result.get("errcode", 1) == 0
        except Exception as e:
            self._safe_log_error("钉钉", e)
            return False

    def feishubot(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """飞书机器人推送"""
        try:
            config = self.config.feishubot
            if not config.get("webhook", "").strip():
                logger.warning("飞书机器人配置不完整")
                return False

            message = self._prepare_message(status_id, push_message, img_file)

            response = self.http.post(
                url=config["webhook"],
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "msg_type": "text",
                    "content": {"text": message},
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"飞书推送结果: {result.get('msg', '未知')}")
            return result.get("StatusCode", 1) == 0
        except Exception as e:
            self._safe_log_error("飞书", e)
            return False

    def bark(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Bark 推送"""
        try:
            config = self.config.bark
            if not all(
                [
                    config.get("api_url", "").strip(),
                    config.get("token", "").strip(),
                ]
            ):
                logger.warning("Bark 配置不完整")
                return False

            send_title = urllib.parse.quote_plus(get_push_title(status_id))
            encoded_message = urllib.parse.quote_plus(push_message)

            icon_param = f"&icon=https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo/{config.get('icon', 'default')}.png"

            response = self.http.get(
                url=f'{config["api_url"]}/{config["token"]}/{send_title}/{encoded_message}?{icon_param}'
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Bark 推送结果: {result.get('message', '未知')}")
            return True
        except Exception as e:
            self._safe_log_error("Bark", e)
            return False

    def gotify(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """Gotify 推送"""
        try:
            config = self.config.gotify
            if not all(
                [
                    config.get("api_url", "").strip(),
                    config.get("token", "").strip(),
                ]
            ):
                logger.warning("Gotify 配置不完整")
                return False

            message = self._prepare_message(status_id, push_message, img_file)

            response = self.http.post(
                url=f'{config["api_url"]}/message?token={config["token"]}',
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "title": get_push_title(status_id),
                    "message": message,
                    "priority": config.get("priority", 5),
                },
            )
            response.raise_for_status()
            logger.info("Gotify 推送成功")
            return True
        except Exception as e:
            self._safe_log_error("Gotify", e)
            return False

    def webhook(
        self, status_id: int, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """WebHook 推送"""
        try:
            config = self.config.webhook
            if not config.get("webhook_url", "").strip():
                logger.warning("WebHook 配置不完整")
                return False

            message = self._prepare_message(status_id, push_message, img_file)

            response = self.http.post(
                url=config["webhook_url"],
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "title": get_push_title(status_id),
                    "message": message,
                },
            )
            response.raise_for_status()
            logger.info("WebHook 推送成功")
            return True
        except Exception as e:
            self._safe_log_error("WebHook", e)
            return False

    def push(
        self, status: int = 0, push_message: str = "", img_file: Optional[bytes] = None
    ) -> bool:
        """
        执行推送

        Args:
            status: 状态码
            push_message: 推送消息内容
            img_file: 图片文件二进制数据

        Returns:
            bool: 是否全部推送成功
        """
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
        all_success = True
        for push_server in self.config.push_servers:
            if push_server not in PUSH_METHODS:
                logger.warning(f"不支持的推送服务: {push_server}")
                continue

            logger.debug(f"使用推送服务: {push_server}")
            try:
                push_method = getattr(self, push_server)
                success = push_method(status, processed_message, img_file)
                if success:
                    logger.info(f"{push_server} - 推送成功")
                else:
                    logger.warning(f"{push_server} - 推送失败")
                    all_success = False
            except Exception as e:
                self._safe_log_error(push_server, e)
                all_success = False

        return all_success


# 全局推送函数（保持向后兼容）
def push(
    status: int = 0,
    push_message: str = "",
    img_file: Optional[bytes] = None,
    config: Optional[PushConfig] = None,
    config_file: Optional[str] = None,
) -> bool:
    """
    推送消息到指定平台

    Args:
        status: 推送状态码
        push_message: 推送消息内容
        img_file: 图片文件二进制数据
        config: 推送配置对象
        config_file: 配置文件路径

    Returns:
        bool: 推送是否成功
    """
    # 如果提供了config参数，优先使用
    if config:
        push_handler = PushHandler(config=config)
    # 如果提供了config_file参数，使用配置文件
    elif config_file:
        push_handler = PushHandler(config_file=config_file)
    # 如果有全局配置，使用全局配置
    elif _global_push_config:
        push_handler = PushHandler(config=_global_push_config)
    # 否则使用默认配置
    else:
        push_handler = PushHandler()

    return push_handler.push(status, push_message, img_file)


# 全局配置实例
_global_push_config: Optional[PushConfig] = None


def initConfig(config: PushConfig) -> None:
    """
    初始化全局推送配置

    Args:
        config: PushConfig 实例，用于设置全局推送配置
    """
    global _global_push_config
    _global_push_config = config


# 使用示例
if __name__ == "__main__":
    # 方式1: 使用默认配置
    push(0, f"推送验证{int(time.time())}")

    # 方式2: 通过代码配置
    custom_config = PushConfig(
        enable=True,
        error_push_only=False,
        push_servers=["telegram"],
        telegram={
            "api_url": "api.telegram.org",
            "bot_token": "your_bot_token",
            "chat_id": "your_chat_id",
        },
    )

    initConfig(custom_config)

    # 后续调用push时无需再传递配置
    push(0, f"推送验证{int(time.time())}")

    # 方式3: 使用指定配置文件
    # push(0, "测试消息", config_file="custom_config.ini")
