import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import logger
from models import project_config

# 从 tests/test_pic.png 读取图片文件作为测试图片
img_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests/test_pic.png"
)


def sync_upload():

    # 同步使用
    from utils.img_upload import ImageUploader, upload_image

    # 方式1: 使用类
    with ImageUploader(token="your_token") as uploader:
        # 上传本地文件
        result1 = uploader.upload("/path/to/image.jpg")

        # 上传二进制数据
        with open("/path/to/image.png", "rb") as f:
            binary_data = f.read()
        result2 = uploader.upload(binary_data, filename="custom_name.png")

        # 上传文件对象
        with open("/path/to/image.gif", "rb") as f:
            result3 = uploader.upload(f)

    # 方式2: 使用便捷函数
    result = upload_image(
        "/path/to/image.jpg", token="your_token", api_url="your_api_url"
    )
    logger.info(f"upload_image_result: {result}")


def async_upload():
    # 异步使用
    import asyncio

    async def main():
        from utils.img_upload import upload_image_async

        result = await upload_image_async("/path/to/image.jpg", token="your_token")
        if result["success"]:
            print(f"图片URL: {result["data"]["url"]}")

    asyncio.run(main())


def main_run():
    # 从 tests/test_pic.png 读取图片文件作为测试图片
    img_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tests/test_pic.png"
    )
    with open(img_path, "rb") as f:
        img_file = f.read()
        # 看看读取图片大小
        logger.info(f"图片大小：{len(img_file)}")

    from utils.img_upload import upload_image

    result = upload_image(
        img_path,
        token=project_config.push_config.imgbed.token,
        api_url=project_config.push_config.imgbed.api_url,
    )
    if result["success"]:
        result_url = result["data"]["url"]
        print(f"图片URL: {result_url}")


if __name__ == "__main__":
    main_run()
