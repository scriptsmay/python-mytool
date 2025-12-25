import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manually_weibo_sign, single_weibo_event_sign
from utils import push, init_config
from config import logger


# debugging
import logging

logger.setLevel(logging.DEBUG)
for handler in logger.handlers:
    handler.setLevel(logging.DEBUG)
# debugging end

try:
    from models import project_config

    init_config(project_config.push_config)

except Exception as e:
    logger.error(f"❌初始化推送配置失败：{e}")
    print(f"❌初始化推送配置失败：{e}")


async def weibo_sign_task():
    """微博超话签到主函数"""
    result = await manually_weibo_sign()
    if result.is_success:
        push(title="微博超话签到成功", push_message=result.message)
    return result


async def weibo_event():
    """微博事件签到主函数"""

    cookiestr = "xxxxxxx"
    result = await single_weibo_event_sign(cookiestr)
    logger.info(f"微博事件签到结果：{result}")

    return result


if __name__ == "__main__":

    async def main():
        # logger.info("🎮开始执行微博超话签到...")
        await weibo_sign_task()
        # await weibo_event()

    asyncio.run(main())
