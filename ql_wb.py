"""
new Env('微博超话签到任务');
"""

import asyncio

from config import logger
from ql_common import ql_push


try:
    from core import manually_weibo_sign
except (ImportError, NameError) as e:
    ql_push("「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def main():
    """主异步函数"""
    logger.info("🚀开始执行微博超话签到任务...")

    # 顺序执行游戏签到和社区签到
    try:
        result = await manually_weibo_sign()
        if result:
            ql_push("微博超话签到", result)
        logger.info(f"✅微博超话签到完成")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        ql_push("微博超话签到失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
