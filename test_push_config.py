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


def test_gotify():
    logger.info("⏳开始测试 Gotify 消息推送配置...")
    push(
        push_message=f"✅测试消息推送\n Hello: ![](https://gotify.net/img/logo.png)",
        config={"enable": True, "gotify": project_config.push_config.gotify},
    )


def main_run():
    # 从 tests/test_pic.png 读取图片文件作为测试图片
    img_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tests/test_pic.png"
    )
    with open(img_path, "rb") as f:
        img_file = f.read()
        # 看看读取图片大小
        logger.info(f"图片大小：{len(img_file)}")

    # img_url = "https://gotify.net/img/logo.png"

    logger.info("⏳开始测试消息推送配置...")
    local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    push(
        push_message=f"✅测试消息推送\n{local_time}",
        img_file=img_file,
    )


if __name__ == "__main__":
    main_run()
