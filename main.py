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

from task_game import game_sign
from task_bbs import bbs_sign_task
from task_wb import weibo_sign_task
from config import logger


def main_push(title, message):
    """推送消息"""
    try:
        from models import project_config
        from utils import push, init_config

        init_config(project_config.push_config)
        push(title=title, push_message=message)
    except Exception as e:
        logger.error(f"❌初始化推送配置失败：{e}")
        print(f"❌初始化推送配置失败：{e}")


async def main():
    """主异步函数"""
    logger.info("🚀开始执行米哈游签到任务...")

    # 顺序执行游戏签到和社区签到
    try:
        messagebox = []
        # 先执行游戏签到
        game_result = await game_sign()
        messagebox.append(game_result)

        # 等待一段时间再执行社区签到
        await asyncio.sleep(15)

        # 执行社区签到
        bbs_result = await bbs_sign_task()
        messagebox.append(bbs_result)

        await asyncio.sleep(15)
        # 微博超话签到
        wb_result = await weibo_sign_task()
        messagebox.append(wb_result)

        logger.info("🎉所有任务执行完成！")
        main_push("米哈游任务执行完成", "\n".join(messagebox))

    except Exception as e:
        logger.error(f"❌任务执行失败: {e}")
        main_push("米哈游任务失败", f"执行过程中出现错误: {e}")
        raise


if __name__ == "__main__":
    # 使用 asyncio.run() 运行主函数
    asyncio.run(main())
