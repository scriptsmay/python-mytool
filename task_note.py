import asyncio
import os
import sys
import json

# 将当前目录加入搜索路径应在所有 import 前完成
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import logger
from models import project_config
from utils import push, init_config
from core import manually_genshin_note_check, manually_starrail_note_check


# 定义推送标题常量
TITLE_GENSHIN = "原神便签查询"
TITLE_STARRAIL = "星铁便签查询"


try:
    init_config(project_config.push_config)
except Exception as e:
    error_msg = f"❌初始化推送配置失败：{e}"
    logger.error(error_msg)
    print(error_msg)
    exit(1)


async def execute_genshin_check():
    """执行原神便签检查"""
    try:
        result = await manually_genshin_note_check()
        if result.is_success:
            push(title=TITLE_GENSHIN, push_message=result.message)
    except Exception as e:
        logger.error(f"执行原神便签检查时发生异常: {e}")


async def execute_starrail_check():
    """执行星铁便签检查"""
    try:
        result = await manually_starrail_note_check()
        if result.is_success:
            push(title=TITLE_STARRAIL, push_message=result.message)
    except Exception as e:
        logger.error(f"执行星铁便签检查时发生异常: {e}")


async def main_task():
    logger.info("⏳开始执行脚本note.py...")

    await execute_genshin_check()

    await asyncio.sleep(project_config.preference.sleep_time)

    await execute_starrail_check()

    logger.info("✅任务执行完毕！")


if __name__ == "__main__":
    asyncio.run(main_task())
