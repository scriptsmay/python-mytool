import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import logger
from models import project_config
from utils import push, init_config

try:
    init_config(project_config.push_config)
except Exception as e:
    logger.error(f"❌初始化推送配置失败：{e}")
    print(f"❌初始化推送配置失败：{e}")
    exit(1)


def main_run():

    logger.info("⏳开始测试消息推送配置...")
    push(push_message=f"✅测试消息推送成功！{int(time.time())}")


if __name__ == "__main__":
    main_run()
