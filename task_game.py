import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manually_game_sign
from utils import push, init_config
from config import logger


async def game_sign():
    """游戏签到主函数"""
    result = await manually_game_sign()
    try:
        from models import project_config

        init_config(project_config.push_config)
        push(title="米忽悠游戏签到任务", push_message=result.message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")

    return result


if __name__ == "__main__":
    """单独运行游戏签到"""

    asyncio.run(game_sign())
