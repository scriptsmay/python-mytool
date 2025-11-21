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
    message = await manually_game_sign()
    try:
        from models import project_config

        init_config(project_config.push_config)
        push(title="米忽悠游戏签到任务", push_message=message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")
    return message


if __name__ == "__main__":
    """单独运行游戏签到"""

    async def main():
        logger.info("🎮开始执行游戏签到...")
        result = await game_sign()
        logger.info(f"✅游戏签到完成: {result}")

    asyncio.run(main())
