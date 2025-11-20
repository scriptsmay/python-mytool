import asyncio
import os
import sys

# import logging

# # 设置日志级别
# logging.basicConfig(
#     level=logging.DEBUG,  # 改为 DEBUG 可以看到所有日志
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# )

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core import manually_game_sign, manually_bbs_sign
from utils import push, init_config
from config import logger


def main_push(status_code, title, message):
    try:
        from models import project_config

        init_config(project_config.push_config)
        push(status=status_code, push_message=message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")


async def game_sign():
    title = "米哈游游戏签到"
    message = await manually_game_sign()
    main_push(0, title, message)
    return message


async def bbs_sign():
    title = "米哈游社区签到"
    message = await manually_bbs_sign()
    main_push(0, title, message)
    return message


async def main():
    """主异步函数"""
    logger.info("🚀开始执行米哈游签到任务...")

    # 顺序执行游戏签到和社区签到
    try:
        # 先执行游戏签到
        logger.info("🎮开始执行游戏签到...")
        game_result = await game_sign()
        logger.info(f"✅游戏签到完成: {game_result}")

        # 等待一段时间再执行社区签到
        await asyncio.sleep(5)

        # 执行社区签到
        logger.info("🏠开始执行社区签到...")
        bbs_result = await bbs_sign()
        logger.info(f"✅社区签到完成: {bbs_result}")

        logger.info("🎉所有签到任务执行完成！")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        main_push(-1, "米哈游签到失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
