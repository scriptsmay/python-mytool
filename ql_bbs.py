"""
cron:20 1 * * *
new Env('米忽悠家社区任务');
"""

import asyncio

try:
    from config import logger
    from dep_common import ql_push
    from core import manually_bbs_sign
except (ImportError, NameError) as e:
    ql_push("「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def main():
    logger.info("🚀开始执行米游社任务...")

    try:

        bbs_result = await manually_bbs_sign()
        if bbs_result.is_success:
            ql_push("米游社任务", bbs_result.message)
        logger.info(f"✅米游社任务执行结束")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        ql_push("米游社任务失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
