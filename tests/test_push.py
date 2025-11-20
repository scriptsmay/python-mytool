import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.push import (
    PushConfig,
    PushHandler,
    push,
    init_config,
    get_new_session,
    get_push_title,
    _global_push_config,
)


class TestPushConfig(unittest.TestCase):
    """测试PushConfig类"""

    def test_push_config_defaults(self):
        """测试PushConfig默认值"""
        config = PushConfig()
        self.assertTrue(config.enable)
        self.assertFalse(config.error_push_only)
        self.assertEqual(config.push_servers, [])
        self.assertEqual(config.push_block_keys, [])

    def test_push_config_custom_values(self):
        """测试PushConfig自定义值"""
        config = PushConfig(
            enable=False,
            error_push_only=True,
            push_servers=["telegram"],
            push_block_keys=["敏感词"],
        )
        self.assertFalse(config.enable)
        self.assertTrue(config.error_push_only)
        self.assertEqual(config.push_servers, ["telegram"])
        self.assertEqual(config.push_block_keys, ["敏感词"])


class TestPushFunctions(unittest.TestCase):
    """测试推送功能函数"""

    def test_get_push_title(self):
        """测试获取推送标题功能"""
        self.assertEqual(get_push_title(0), "「脚本」执行成功!")
        self.assertEqual(get_push_title(-1), "「脚本」Config版本已更新")
        self.assertEqual(get_push_title(-99), "「脚本」依赖缺失")
        self.assertEqual(get_push_title(999), "「脚本」StatusID 错误")  # 默认值

    def test_get_new_session_with_httpx(self):
        """测试获取新的会话实例 - 优先使用httpx"""
        # 模拟httpx模块存在
        with patch.dict("sys.modules", {"httpx": Mock()}):
            session = get_new_session()
            self.assertIsNotNone(session)

    def test_get_new_session_with_requests(self):
        """测试获取新的会话实例 - 使用requests回退"""
        # 模拟httpx模块不存在，但requests存在
        with patch.dict("sys.modules", {"httpx": None}):
            session = get_new_session()
            self.assertIsNotNone(session)

    def test_init_config_and_global_push(self):
        """测试初始化全局配置"""
        # 保存原始值
        original_config = globals()["_global_push_config"]

        # 初始化新配置
        test_config = PushConfig(enable=True, push_servers=["gotify"])
        init_config(test_config)

        # 验证全局变量已被更新
        from utils.push import _global_push_config

        self.assertEqual(_global_push_config, test_config)

        # 恢复原始配置
        globals()["_global_push_config"] = original_config


class TestPushHandler(unittest.TestCase):
    """测试PushHandler类"""

    def setUp(self):
        """测试前准备"""
        self.config = PushConfig(
            enable=True,
            push_servers=["bark"],
            bark={"api_url": "http://test.com", "token": "test_token"},
        )
        self.handler = PushHandler(config=self.config)

    def test_initialization_with_config(self):
        """测试使用配置初始化"""
        self.assertEqual(self.handler.config, self.config)

    def test_msg_replace(self):
        """测试消息内容替换功能"""
        config = PushConfig(push_block_keys=["敏感词", "隐私"])
        handler = PushHandler(config=config)

        # 测试替换敏感词 - 需要注意替换长度应与原词一致
        original_msg = "这是敏感词和隐私信息"
        result = handler._msg_replace(original_msg)
        # 根据代码逻辑，敏感词会被替换为相同长度的*字符
        expected = "这是***和**信息"  # "敏感词"是3个字符，"隐私"是2个字符
        self.assertEqual(result, expected)

        # 测试没有敏感词的情况
        normal_msg = "这是一条正常消息"
        result = handler._msg_replace(normal_msg)
        self.assertEqual(result, normal_msg)

    @patch("utils.push.PushHandler.bark")
    def test_push_with_enabled_config(self, mock_bark):
        """测试启用配置时的推送功能"""
        mock_bark.return_value = True
        result = self.handler.push(0, "测试消息")
        self.assertTrue(result)
        mock_bark.assert_called_once()

    @patch("utils.push.PushHandler.bark")
    def test_push_with_disabled_config(self, mock_bark):
        """测试禁用配置时的推送功能"""
        config = PushConfig(enable=False)
        handler = PushHandler(config=config)
        result = handler.push(0, "测试消息")
        self.assertTrue(result)  # 虽然没有实际推送，但返回True
        mock_bark.assert_not_called()

    @patch("utils.push.PushHandler.bark")
    def test_push_error_only_with_success_status(self, mock_bark):
        """测试仅错误推送时对成功状态的处理"""
        config = PushConfig(enable=True, error_push_only=True)
        handler = PushHandler(config=config)
        result = handler.push(0, "成功消息")  # 0表示成功
        self.assertTrue(result)  # 虽然没有实际推送，但返回True
        mock_bark.assert_not_called()

    @patch("utils.push.PushHandler.bark")
    def test_push_error_only_with_error_status(self, mock_bark):
        """测试仅错误推送时对错误状态的处理"""
        # 创建一个handler实例，确保它包含bark方法
        config = PushConfig(enable=True, error_push_only=True, push_servers=["bark"])
        handler = PushHandler(config=config)
        mock_bark.return_value = True
        result = handler.push(-1, "错误消息")  # -1表示错误
        self.assertTrue(result)
        # 验证推送方法被调用
        mock_bark.assert_called_once_with(-1, "错误消息", None)

    def test_prepare_message(self):
        """测试准备消息内容功能"""
        message = self.handler._prepare_message(0, "测试内容")
        self.assertIn("「脚本」执行成功!", message)
        self.assertIn("测试内容", message)

    def test_prepare_message_with_image(self):
        """测试准备带图片的消息内容功能"""
        img_data = b"fake image data"
        message = self.handler._prepare_message(0, "测试内容", img_file=img_data)
        self.assertIn("「脚本」执行成功!", message)
        self.assertIn("测试内容", message)
        self.assertIn("data:image/png;base64,", message)


class TestPushFunction(unittest.TestCase):
    """测试push函数"""

    @patch("utils.push.PushHandler")
    def test_push_with_config_param(self, mock_handler_class):
        """测试使用参数配置的推送功能"""
        mock_handler_instance = Mock()
        mock_handler_class.return_value = mock_handler_instance
        mock_handler_instance.push.return_value = True

        config = PushConfig()
        result = push(status=0, push_message="测试", config=config)

        mock_handler_class.assert_called_once_with(config=config)
        mock_handler_instance.push.assert_called_once_with(0, "测试", None)
        self.assertTrue(result)

    @patch("utils.push.PushHandler")
    @patch("utils.push._global_push_config", new=PushConfig())
    def test_push_with_global_config(self, mock_handler_class):
        """测试使用全局配置的推送功能"""
        mock_handler_instance = Mock()
        mock_handler_class.return_value = mock_handler_instance
        mock_handler_instance.push.return_value = True

        result = push(status=0, push_message="测试")

        # 验证PushHandler使用全局配置创建
        mock_handler_class.assert_called_once()
        mock_handler_instance.push.assert_called_once_with(0, "测试", None)
        self.assertTrue(result)


class TestPushHandlerSendMethods(unittest.TestCase):
    """测试推送处理器的各种推送方法"""

    def setUp(self):
        """测试前准备"""
        self.config = PushConfig(
            bark={"api_url": "http://test.com", "token": "test_token"},
            telegram={
                "api_url": "api.telegram.org",
                "bot_token": "bot123",
                "chat_id": "123456",
            },
            dingrobot={
                "webhook": "https://oapi.dingtalk.com/robot/send?access_token=test"
            },
            feishubot={"webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/test"},
            gotify={"api_url": "http://gotify.local", "token": "gotify_token"},
            webhook={"webhook_url": "http://example.com/webhook"},
        )
        self.handler = PushHandler(config=self.config)

    @patch.object(PushHandler, "_send_request")
    def test_bark_push(self, mock_send_request):
        """测试Bark推送"""
        mock_send_request.return_value = True
        result = self.handler.bark(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()

    @patch.object(PushHandler, "_send_request")
    def test_telegram_push(self, mock_send_request):
        """测试Telegram推送"""
        mock_send_request.return_value = True
        result = self.handler.telegram(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()

    @patch.object(PushHandler, "_send_request")
    def test_dingrobot_push(self, mock_send_request):
        """测试钉钉机器人推送"""
        mock_send_request.return_value = True
        result = self.handler.dingrobot(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()

    @patch.object(PushHandler, "_send_request")
    def test_feishubot_push(self, mock_send_request):
        """测试飞书机器人推送"""
        mock_send_request.return_value = True
        result = self.handler.feishubot(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()

    @patch.object(PushHandler, "_send_request")
    def test_gotify_push(self, mock_send_request):
        """测试Gotify推送"""
        mock_send_request.return_value = True
        result = self.handler.gotify(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()

    @patch.object(PushHandler, "_send_request")
    def test_webhook_push(self, mock_send_request):
        """测试WebHook推送"""
        mock_send_request.return_value = True
        result = self.handler.webhook(0, "测试消息")
        self.assertTrue(result)
        mock_send_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
