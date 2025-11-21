import os
from utils import push, init_config

from config import logger


def ql_push(title, message):
    if os.getenv("mihuyo_push") == "1":
        try:
            from models import project_config

            init_config(project_config.push_config)
            push(title=title, push_message=message)
        except Exception as e:
            logger.error(f"❌初始化推送配置失败：{e}")
            print(f"❌初始化推送配置失败：{e}")
    elif "QLAPI" in globals():  # 判断 QLAPI 是否已在全局作用域中定义
        logger.info("🚀 使用 QLAPI 推送...")
        try:
            QLAPI.notify(title, message)
            logger.info("✅ QLAPI 通知发送成功")
        except Exception as e:
            logger.error(f"❌ QLAPI 通知失败：{e}")
