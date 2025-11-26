import hmac
import time
import base64
import urllib.parse
import hashlib
import httpx

from typing import Optional, Any, List
from dataclasses import dataclass, field
from config.logger import logger

from utils.img_upload import upload_image


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
        ImageBedConfig,
    )
except ImportError:
    # 回退到旧的 dataclass
    @dataclass
    class NewPushConfig:
        enable: bool = True
        error_push_only: bool = False
        # time
        timeout: float = 15.0
        max_retry_times: int = 3
        retry_interval: float = 2.0

        push_servers: List[str] = field(default_factory=list)
        push_block_keys: List[str] = field(default_factory=list)

        # push servers
        telegram: Any = field(default_factory=dict)
        dingrobot: Any = field(default_factory=dict)
        feishubot: Any = field(default_factory=dict)
        bark: Any = field(default_factory=dict)
        gotify: Any = field(default_factory=dict)
        webhook: Any = field(default_factory=dict)
        imgbed: Any = field(default_factory=dict)


# 推送标题默认
DEFAULT_PUSH_TITLE = "「米忽悠工具」执行任务"

# 支持的推送方式
SUPPORTED_PUSH_METHODS = {
    "telegram",
    "dingrobot",
    "feishubot",
    "bark",
    "gotify",
    "webhook",
}


def get_new_session(**kwargs) -> httpx.Client:
    """创建 HTTP 客户端实例"""
    import httpx

    return httpx.Client(
        timeout=30,
        transport=httpx.HTTPTransport(retries=3),
        follow_redirects=True,
        **kwargs,
    )


class PushHandler:
    """推送处理器"""

    def __init__(
        self,
        config: Optional[NewPushConfig] = None,
    ):
        """
        初始化推送处理器
        """
        self.http = get_new_session()
        self.config = config

    def _msg_replace(self, msg: str) -> str:
        """消息内容关键词替换"""
        if not self.config.push_block_keys:
            return msg
        result = str(msg)
        for block_key in self.config.push_block_keys:
            if block_key:
                result = result.replace(block_key, "*" * len(block_key))
        return result

    def _safe_log_error(self, service_name: str, exception: Exception):
        """安全地记录错误日志"""
        error_msg = str(exception)
        sensitive_keywords = [
            "token=",
            "secret=",
            "key=",
            "password=",
            "access_token",
            "auth_token",
            "authorization",
        ]
        for keyword in sensitive_keywords:
            if keyword in error_msg:
                idx = error_msg.find(keyword) + len(keyword)
                end_idx = error_msg.find("&", idx)
                if end_idx == -1:
                    end_idx = len(error_msg)
                error_msg = error_msg[:idx] + "***" + error_msg[end_idx:]
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
                response = session.get(url, **kwargs)
            else:
                response = session.post(url, **kwargs)
            response.raise_for_status()
            return True
        except Exception as e:
            self._safe_log_error("HTTP请求", e)
            return False

    def upload_image_to_imgbed(
        self,
        image_bytes: bytes,
    ) -> Optional[str]:
        """
        上传图片到图床，并返回图片地址

        :param image_bytes: 二进制图片数据
        :type image_bytes: bytes
        :return: 上传成功则返回图片地址，失败则返回None
        :rtype: Optional[str]
        """

        if not self._is_config_configured(self.config.imgbed, ["api_url", "token"]):
            logger.warning("图床配置不完整")
            return None

        api_url = self._get_config_value(self.config.imgbed, "api_url")
        token = self._get_config_value(self.config.imgbed, "token")

        result = upload_image(
            image_bytes,
            api_url=api_url,
            token=token,
            max_retries=self.config.max_retry_times,
            retry_delay=self.config.retry_interval,
        )
        if result["success"]:
            result_url = result["data"]["url"]
            print(f"图片URL: {result_url}")
            return result_url

        return None

    def upload_image_to_feishu(self, image_bytes: bytes) -> Optional[str]:
        """
        第一步：上传图片到飞书并获得 image_key
        """
        session = self.http

        if not self._is_config_configured(
            self.config.feishubot, ["app_id", "app_secret"]
        ):
            logger.warning("飞书配置 app_id 和 app_secret 不完整")
            return None

        app_id = self._get_config_value(self.config.feishubot, "app_id")
        app_secret = self._get_config_value(self.config.feishubot, "app_secret")

        # 获取 tenant_access_token
        token_url = (
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        )
        token_data = {
            "app_id": app_id,
            "app_secret": app_secret,
        }
        token_response = session.post(token_url, json=token_data)
        access_token = token_response.json()["tenant_access_token"]

        # 上传图片
        upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        files = {"image": ("qrcode.png", image_bytes, "image/png")}
        data = {"image_type": "message"}

        upload_response = session.post(
            upload_url, headers=headers, files=files, data=data
        )
        result = upload_response.json()

        if result["code"] == 0:
            logger.info("feishubot 图片上传成功")
            return result["data"]["image_key"]
        else:
            raise Exception(f"feishubot 图片上传失败: {result}")

        return None

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
        self,
        title: str,
        push_message: str,
        img_file: Optional[bytes] = None,
    ) -> bool:
        """Telegram 推送"""
        if not self.check_telegram_connectivity():
            logger.warning("Telegram 配置不完整或无法连接")
            return False
        config = self.config.telegram
        if not self._is_config_configured(config, ["api_url", "bot_token", "chat_id"]):
            logger.warning("Telegram 配置不完整")
            return False

        message = push_message

        api_url = self._get_config_value(config, "api_url")
        bot_token = self._get_config_value(config, "bot_token")
        chat_id = self._get_config_value(config, "chat_id")

        # 发送图片接口是另一个
        # https://api.telegram.org/bot<your_bot_token>/sendPhoto
        if img_file:
            url = f"https://{api_url}/bot{bot_token}/sendPhoto"
            files = {"photo": img_file}
            data = {"chat_id": chat_id, "caption": message}
            try:
                return self._send_request("POST", url, data=data, files=files)
                # logger.info("Telegram 图片推送成功")
            except Exception as e:
                self._safe_log_error("Telegram 图片推送", e)
                return False

        return self._send_request(
            "POST",
            url=f"https://{api_url}/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": f"{title}\n{message}"},
        )

    def dingrobot(
        self,
        title: str,
        push_message: str,
        img_file: Optional[bytes] = None,
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

        message = push_message
        # TODO: img_file 暂不支持

        return self._send_request(
            "POST",
            url=api_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"msgtype": "text", "text": {"content": f"{title}\n{message}"}},
        )

    def feishubot(
        self,
        title: str,
        push_message: str,
        img_file: Optional[bytes] = None,
    ) -> bool:
        """飞书机器人推送"""
        config = self.config.feishubot
        if not self._is_config_configured(config, ["webhook"]):
            logger.warning("飞书机器人配置不完整")
            return False

        webhook_url = self._get_config_value(config, "webhook")
        app_id = self._get_config_value(config, "app_id")
        app_secret = self._get_config_value(config, "app_secret")
        user_id = self._get_config_value(config, "user_id")

        # 构建内容块
        content_blocks = []

        # 1. 文字消息块
        text_block = [{"tag": "text", "text": push_message}]
        if user_id:
            text_block.append({"tag": "at", "user_id": user_id})
        content_blocks.append(text_block)

        # 2. 图片块（如果有）
        image_key = None
        if img_file and app_id and app_secret:
            try:
                image_key = self.upload_image_to_feishu(img_file)
                if image_key:
                    content_blocks.append(
                        [
                            {
                                "tag": "img",
                                "image_key": image_key,
                                "alt": "二维码",
                            }
                        ]
                    )
            except Exception as e:
                logger.warning(f"飞书图片上传失败，继续发送文字消息: {e}")

        # 3. 构建消息
        message_data = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": content_blocks,
                    }
                }
            },
        }

        return self._send_request(
            "POST",
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=message_data,
        )

    def bark(
        self,
        title: str,
        push_message: str,
        img_file: Optional[bytes] = None,
    ) -> bool:
        """Bark 推送"""
        config = self.config.bark
        if not self._is_config_configured(config, ["api_url", "token"]):
            logger.warning("Bark 配置不完整")
            return False

        send_title = urllib.parse.quote_plus(title)
        encoded_message = urllib.parse.quote_plus(push_message)
        icon = self._get_config_value(config, "icon", "default")
        icon_param = (
            f"&icon=https://cdn.jsdelivr.net/gh/tanmx/pic@main/mihoyo/{icon}.png"
        )

        api_url = self._get_config_value(config, "api_url")
        token = self._get_config_value(config, "token")

        # TODO: img_file 暂不支持

        return self._send_request(
            "GET",
            url=f"{api_url}/{token}/{send_title}/{encoded_message}?{icon_param}",
        )

    def gotify(
        self,
        title: str,
        push_message: str,
        img_file: Optional[bytes] = None,
    ) -> bool:
        """Gotify 推送"""
        config = self.config.gotify
        if not self._is_config_configured(config, ["api_url", "token"]):
            logger.warning("Gotify 配置不完整")
            return False

        message = push_message

        api_url = self._get_config_value(config, "api_url")
        token = self._get_config_value(config, "token")
        priority = self._get_config_value(config, "priority", 5)

        prepare_json = {
            "title": title or "默认标题",
            "priority": priority,
        }

        # 增加图床上传部分
        # 由于 gotify 不支持 base64 编码的文本方式，因此考虑改成oss外链
        if img_file:
            img_remote_url = self.upload_image_to_imgbed(img_file)
            if img_remote_url:
                message = f"{message}\n\n![图片]({img_remote_url})"
                # 添加 markdown 样式
                prepare_json["extras"] = {
                    "client::display": {"contentType": "text/markdown"}
                }

        prepare_json["message"] = message

        return self._send_request(
            "POST",
            url=f"{api_url}/message?token={token}",
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=prepare_json,
        )

    def webhook(
        self, title: str, push_message: str, img_file: Optional[bytes] = None
    ) -> bool:
        """WebHook 推送"""
        config = self.config.webhook
        if not self._is_config_configured(config, ["webhook_url"]):
            logger.warning("WebHook 配置不完整")
            return False

        message = push_message
        webhook_url = self._get_config_value(config, "webhook_url")

        return self._send_request(
            "POST",
            url=webhook_url,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={"title": title, "message": message},
        )

    def push(
        self,
        title: str = "默认标题",
        push_message: str = "",
        img_file: Optional[bytes] = None,
    ) -> bool:
        """执行推送"""
        logger.debug(f"标题：{title} 消息内容: {push_message}")

        # 检查推送条件
        if not self.config.enable:
            logger.warning("❗️推送功能已禁用")
            logger.info(f"打印推送内容:\n{title}\n{push_message}")
            return True

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
                success = push_method(title, processed_message, img_file)
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
    title: str = DEFAULT_PUSH_TITLE,
    push_message: str = "",
    img_file: Optional[bytes] = None,
    config: Optional[NewPushConfig] = None,
) -> bool:
    """推送消息到指定平台"""
    if config:
        push_handler = PushHandler(config=config)
    elif _global_push_config:
        push_handler = PushHandler(config=_global_push_config)
    else:
        push_handler = PushHandler()

    return push_handler.push(title, push_message, img_file)
