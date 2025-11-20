import asyncio
import os
import sys
import json

from config import logger
from models import project_config
from utils import push, init_config
from core import manually_genshin_note_check, manually_starrail_note_check


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    init_config(project_config.push_config)
except Exception as e:
    logger.error(f"❌初始化推送配置失败：{e}")
    print(f"❌初始化推送配置失败：{e}")
    exit(1)


async def main_task():

    logger.info("⏳开始执行脚本note.py...")
    msg = await manually_genshin_note_check()
    # logger.info(msg)
    if msg:
        push(push_message=msg)

    await asyncio.sleep(project_config.preference.sleep_time)
    msg2 = await manually_starrail_note_check()
    # logger.info(msg2)
    push(push_message=msg2)

    logger.info("✅任务执行完毕！")


if __name__ == "__main__":
    asyncio.run(main_task())
