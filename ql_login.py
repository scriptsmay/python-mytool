"""
cron:0 0 1 1 *
new Env('米游社登录');
"""

import asyncio

try:
    from config import logger
    from dep_common import ql_push
    from core import mys_login
except (ImportError, NameError) as e:
    ql_push("「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def main():
    """主异步函数"""
    logger.info("🚀开始执行米游社登录任务...")

    try:
        result = await mys_login()
        if result.is_success:
            ql_push("米游社登录成功", result.message)
        else:
            ql_push("米游社登录失败", result.message)

        # logger.info(f"✅账户登录完成")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        ql_push("米游社登录失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
