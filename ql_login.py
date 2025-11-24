"""
cron:0 0 1 1 *
new Env('米游社登录');
"""

import asyncio

# 常量定义
SUCCESS_TITLE = "米游社登录成功"
FAILURE_TITLE = "米游社登录失败"
DEPENDENCY_ERROR_MSG = "脚本加入新模块，请更新青龙拉取范围"
DEPENDENCY_ERROR_TITLE = "「米游社脚本」依赖缺失"

try:
    from config import logger
    from dep_common import ql_push
    from core import mys_login
except (ImportError, NameError) as e:
    ql_push(DEPENDENCY_ERROR_TITLE, DEPENDENCY_ERROR_MSG)
    print("依赖缺失", e)
    exit(-1)


async def handle_login_failure(error):
    """处理登录失败的逻辑"""
    error_msg = f"执行过程中出现错误: {error}"
    logger.error(f"❌任务执行失败: {error}")
    ql_push(FAILURE_TITLE, error_msg)


async def main_login_task():
    """主异步函数"""
    try:
        result = await mys_login()
        if result.is_success:
            await ql_push(SUCCESS_TITLE, result.message)
    except Exception as e:
        await handle_login_failure(e)
        raise


def run_main():
    """运行主函数，兼容不同环境"""
    try:
        asyncio.run(main_login_task())
    except RuntimeError:
        # 兼容Jupyter等环境
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_login_task())


if __name__ == "__main__":
    run_main()
