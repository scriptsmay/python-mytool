"""
new Env('米忽悠家签到');
"""

import notify
import os
import asyncio
from utils import push, logger


def ql_push(status_code, title, message):
    if os.getenv("mihuyo_push") == "1":
        push.push(status_code, message)
    else:
        notify.send(title, message)


try:
    from core import manually_game_sign, manually_bbs_sign
except (ImportError, NameError) as e:
    ql_push(-99, "「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def game_sign():
    title = "米哈游游戏签到"
    message = await manually_game_sign()
    ql_push(0, title, message)
    return message


async def bbs_sign():
    title = "米哈游社区签到"
    message = await manually_bbs_sign()
    ql_push(0, title, message)
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
        ql_push(-1, "米哈游签到失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
