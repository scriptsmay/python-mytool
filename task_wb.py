import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import manually_weibo_sign
from utils import push, init_config
from config import logger

try:
    from models import project_config

    init_config(project_config.push_config)

except Exception as e:
    logger.error(f"❌初始化推送配置失败：{e}")
    print(f"❌初始化推送配置失败：{e}")


async def weibo_sign_task():
    """微博超话签到主函数"""
    message = await manually_weibo_sign()
    if message:
        push(title="微博超话签到", push_message=message)
    return message


if __name__ == "__main__":

    async def main():
        logger.info("🎮开始执行微博超话签到...")
        await weibo_sign_task()
        logger.info(f"✅微博超话签到完成")

    asyncio.run(main())
