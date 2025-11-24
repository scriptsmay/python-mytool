import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manually_bbs_sign
from utils import push, init_config
from config import logger


async def bbs_sign_task():
    logger.info("🏠开始执行社区签到...")
    result = await manually_bbs_sign()
    try:
        from models import project_config

        init_config(project_config.push_config)
        push("米哈游社区签到", push_message=result.message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")

    logger.info(f"✅社区签到完成")


if __name__ == "__main__":
    """单独运行社区签到"""

    asyncio.run(bbs_sign_task())
