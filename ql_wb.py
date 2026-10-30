"""
cron:5 0 * * *
new Env('微博超话签到任务');
"""

import asyncio


try:
    from config import logger
    from dep_common import ql_push
    from core import manually_weibo_sign
except (ImportError, NameError) as e:
    ql_push("「微博脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


async def main():
    """主异步函数"""
    logger.info("🚀开始执行微博超话签到任务...")

    try:
        result = await manually_weibo_sign()
        # 以前只在完全成功时推送，失败被静默吃掉；现在按状态推送，失败也告警
        if result.is_success:
            ql_push("微博超话签到", result.message)
            logger.info("✅微博超话签到完成")
        else:
            ql_push("微博超话签到异常", result.message)
            logger.warning(f"⚠️微博超话签到未完全成功: {result.status.value}")

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        ql_push("微博超话签到失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
