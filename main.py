import asyncio
import os
import sys
import logging

# # 设置日志级别
# logging.basicConfig(
#     level=logging.DEBUG,  # 改为 DEBUG 可以看到所有日志
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# )

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core import manually_game_sign, manually_bbs_sign
from models import plugin_config
from utils import logger


def game_sign_task():
    return manually_game_sign()


def bbs_sign_task():
    return manually_bbs_sign()


async def main_task():
    logger.info("⏳开始执行任务...")
    await manually_game_sign()

    # 等待 sleep_time
    await asyncio.sleep(plugin_config.preference.sleep_time)

    await manually_bbs_sign()


if __name__ == "__main__":
    asyncio.run(main_task())
