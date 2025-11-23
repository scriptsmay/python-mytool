import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mys_login
from utils import push, init_config
from config import logger

import logging

logger.setLevel(logging.DEBUG)

try:
    from models import project_config

    init_config(project_config.push_config)

except Exception as e:
    logger.error(f"❌初始化推送配置失败：{e}")
    print(f"❌初始化推送配置失败：{e}")


async def mys_login_task():
    """米游社登录"""
    message = await mys_login()
    if message:
        push(title="米游社登录", push_message=message)
    return message


if __name__ == "__main__":

    async def main():
        logger.info("🎮开始执行米游社登录...")
        await mys_login_task()
        logger.info(f"✅米游社登录完成")

    asyncio.run(main())
