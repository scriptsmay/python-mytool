"""
new Env('米忽悠家社区任务');
"""

import os
import asyncio
from utils import push, init_config

from task_bbs import bbs_sign
from config import logger


def ql_push(status_code, title, message):
    if os.getenv("mihuyo_push") == "1":
        try:
            from models import project_config

            init_config(project_config.push_config)
            push(status=status_code, push_message=message)
        except Exception as e:
            logger.error(f"❌初始化推送配置失败：{e}")
            print(f"❌初始化推送配置失败：{e}")
        push.push(status_code, message)
    elif "QLAPI" in globals():  # 判断 QLAPI 是否已在全局作用域中定义
        logger.info("🚀 使用 QLAPI 推送...")
        try:
            QLAPI.notify(title, message)
            logger.info("✅ QLAPI 通知发送成功")
        except Exception as e:
            logger.error(f"❌ QLAPI 通知失败：{e}")


try:
    from core import manually_game_sign, manually_bbs_sign
except (ImportError, NameError) as e:
    ql_push(-99, "「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def main():
    """主异步函数"""
    logger.info("🚀开始执行米哈游社区签到任务...")

    # 顺序执行游戏签到和社区签到
    try:

        # 执行社区签到
        logger.info("🏠开始执行社区签到...")
        bbs_result = await bbs_sign()
        logger.info(f"✅社区签到完成: {bbs_result}")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        ql_push(-1, "米哈游社区签到失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
