import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manually_bbs_sign
from utils import push, init_config
from config import logger


def main_push(status_code, title, message):
    """推送消息"""
    try:
        from models import project_config

        init_config(project_config.push_config)
        push(status=status_code, push_message=message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")


async def bbs_sign():
    """社区签到主函数"""
    title = "米哈游社区签到"
    message = await manually_bbs_sign()
    main_push(0, title, message)
    return message


if __name__ == "__main__":
    """单独运行社区签到"""

    async def main():
        logger.info("🏠开始执行社区签到...")
        result = await bbs_sign()
        logger.info(f"✅社区签到完成: {result}")

    asyncio.run(main())
