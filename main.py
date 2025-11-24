import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from task_game import game_sign
from task_bbs import bbs_sign_task
from task_wb import weibo_sign_task
from config import logger


async def main():
    """主异步函数"""
    logger.info("🚀开始执行所有任务...")

    # 顺序执行游戏签到和社区签到
    try:
        # 游戏签到
        game_result = await game_sign()
        logger.info(f"游戏签到✅\n{game_result.message}")

        # 等待一段时间再执行社区签到
        await asyncio.sleep(15)

        # 社区签到
        bbs_result = await bbs_sign_task()
        logger.info(f"社区签到✅\n{bbs_result.message}")

        await asyncio.sleep(15)
        # 微博超话签到
        wb_result = await weibo_sign_task()
        logger.info(f"微博超话签到✅\n{wb_result.message}")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
