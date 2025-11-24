import asyncio
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mys_login
from config import logger


# debug
# import logging
# logger.setLevel(logging.DEBUG)


async def mys_login_task():
    """米游社登录"""

    try:
        task_result = await mys_login()
        is_success = task_result.is_success()
        if is_success:
            from models import project_config
            from utils import push

            push(
                title="米游社登录成功",
                push_message=task_result.message,
                config=project_config.push_config,
            )

        return task_result.message
    except Exception as e:
        error_msg = f"米游社登录过程中发生异常: {e}"
        logger.error(error_msg)
        return error_msg


if __name__ == "__main__":

    async def main():

        await mys_login_task()

    asyncio.run(main())
