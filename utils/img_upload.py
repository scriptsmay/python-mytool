"""
图床上传模块
支持将本地图片、二进制数据、文件对象上传到自建图床
使用 httpx 异步/同步客户端
支持失败重试机制
"""

import httpx
import os
import time
import io
from pathlib import Path
from typing import Dict, Any, Optional, Union, BinaryIO
import logging
import asyncio

# 配置日志
logger = logging.getLogger(__name__)


class ImageUploader:
    """图床上传器 - 支持多种输入格式和重试机制"""

    def __init__(
        self,
        api_url: str = "http://127.0.0.1/api/index.php",
        token: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        初始化图床上传器

        Args:
            api_url: 图床API地址
            token: 图床API token
            timeout: 请求超时时间
            max_retries: 最大重试次数，默认3次
            retry_delay: 重试延迟时间（秒），默认1秒
            retry_backoff: 重试延迟倍数，用于指数退避，默认2.0
        """
        self.api_url = api_url
        self.token = token
        self.enabled = True
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff

        # 创建HTTP客户端
        self.client = self._create_client()

    def _create_client(self) -> httpx.Client:
        """创建同步HTTP客户端"""
        return httpx.Client(timeout=self.timeout, follow_redirects=True)

    async def _create_async_client(self) -> httpx.AsyncClient:
        """创建异步HTTP客户端"""
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    def validate_config(self) -> bool:
        """验证配置是否完整"""
        if not self.enabled:
            logger.warning("图床功能未启用")
            return False

        if not self.token:
            logger.error("图床token未配置")
            return False

        if not self.api_url:
            logger.error("图床API地址未配置")
            return False

        return True

    def _should_retry(self, error: Exception) -> bool:
        """
        判断是否应该重试

        Args:
            error: 异常对象

        Returns:
            bool: 是否应该重试
        """
        # 网络错误、超时、5xx服务器错误应该重试
        if isinstance(error, (httpx.RequestError, httpx.TimeoutException)):
            return True

        # HTTP状态码错误，5xx服务器错误重试
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= 500

        return False

    def _handle_upload_error(
        self, error: Exception, attempt: int, max_retries: int
    ) -> Dict[str, Any]:
        """处理上传错误"""
        error_msg = f"图床上传失败: {error}"

        if attempt < max_retries:
            logger.warning(f"{error_msg}，准备第 {attempt + 1}/{max_retries} 次重试")
            return {"retry": True, "error": error}
        else:
            logger.error(f"{error_msg}，已达到最大重试次数 {max_retries}")
            error_msg = f"图床上传失败，已重试{max_retries}次: {error}"
            return {"success": False, "error": error_msg}

    def upload(
        self,
        image_source: Union[str, Path, bytes, BinaryIO],
        filename: Optional[str] = None,
        token: Optional[str] = None,
        api_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        上传图片到图床（同步版本）

        Args:
            image_source: 图片源，支持：
                - 字符串/Path: 本地文件路径
                - bytes: 二进制数据
                - BinaryIO: 文件对象
            filename: 文件名，如果不提供则自动生成
            token: 图床token，如果不提供则使用实例token
            api_url: 图床API地址，如果不提供则使用实例API地址
            max_retries: 最大重试次数，覆盖实例配置
            retry_delay: 重试延迟时间，覆盖实例配置

        Returns:
            dict: 上传结果

        Raises:
            ValueError: 参数错误
            Exception: 上传失败
        """
        if not self.validate_config():
            raise Exception("图床配置不完整或未启用")

        token = token or self.token
        api_url = api_url or self.api_url
        max_retries = max_retries if max_retries is not None else self.max_retries
        retry_delay = retry_delay if retry_delay is not None else self.retry_delay

        # 准备文件数据
        files, final_filename = self._prepare_file_data(image_source, filename)

        # 重试机制
        for attempt in range(max_retries + 1):  # +1 包含第一次尝试
            try:
                # 构建请求数据
                data = {"token": token}

                # 发送POST请求
                response = self.client.post(
                    api_url, files=files, data=data, timeout=self.timeout
                )

                # 检查响应状态
                response.raise_for_status()

                # 解析响应
                result = response.json()

                logger.info(f"图床上传成功: {final_filename} (尝试次数: {attempt + 1})")
                return {
                    "success": True,
                    "data": result,
                    "image_url": self._extract_image_url(result),
                    "filename": final_filename,
                    "attempts": attempt + 1,
                }

            except Exception as e:
                # 处理错误并决定是否重试
                error_result = self._handle_upload_error(e, attempt, max_retries)

                if error_result.get("retry"):
                    # 计算延迟时间（指数退避）
                    delay = retry_delay * (self.retry_backoff**attempt)
                    logger.info(f"等待 {delay:.2f} 秒后重试...")
                    time.sleep(delay)
                    continue
                else:
                    return error_result

        # 理论上不会执行到这里，但为了安全返回错误
        return {
            "success": False,
            "error": f"图床上传失败，已达到最大重试次数 {max_retries}",
            "attempts": max_retries + 1,
        }

    async def upload_async(
        self,
        image_source: Union[str, Path, bytes, BinaryIO],
        filename: Optional[str] = None,
        token: Optional[str] = None,
        api_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        上传图片到图床（异步版本）

        Args:
            image_source: 图片源
            filename: 文件名
            token: 图床token
            api_url: 图床API地址
            max_retries: 最大重试次数，覆盖实例配置
            retry_delay: 重试延迟时间，覆盖实例配置

        Returns:
            dict: 上传结果
        """
        if not self.validate_config():
            raise Exception("图床配置不完整或未启用")

        token = token or self.token
        api_url = api_url or self.api_url
        max_retries = max_retries if max_retries is not None else self.max_retries
        retry_delay = retry_delay if retry_delay is not None else self.retry_delay

        # 准备文件数据
        files, final_filename = self._prepare_file_data(image_source, filename)

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            # 重试机制
            for attempt in range(max_retries + 1):  # +1 包含第一次尝试
                try:
                    # 构建请求数据
                    data = {"token": token}

                    # 发送POST请求
                    response = await client.post(api_url, files=files, data=data)

                    # 检查响应状态
                    response.raise_for_status()

                    # 解析响应
                    result = response.json()

                    logger.info(
                        f"图床上传成功(异步): {final_filename} (尝试次数: {attempt + 1})"
                    )
                    return {
                        "success": True,
                        "data": result,
                        "image_url": self._extract_image_url(result),
                        "filename": final_filename,
                        "attempts": attempt + 1,
                    }

                except Exception as e:
                    # 处理错误并决定是否重试
                    error_result = self._handle_upload_error(e, attempt, max_retries)

                    if error_result.get("retry"):
                        # 计算延迟时间（指数退避）
                        delay = retry_delay * (self.retry_backoff**attempt)
                        logger.info(f"等待 {delay:.2f} 秒后重试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        return error_result

            # 理论上不会执行到这里，但为了安全返回错误
            return {
                "success": False,
                "error": f"图床上传失败，已达到最大重试次数 {max_retries}",
                "attempts": max_retries + 1,
            }

    def _prepare_file_data(
        self,
        image_source: Union[str, Path, bytes, BinaryIO],
        filename: Optional[str] = None,
    ) -> tuple:
        """
        准备文件上传数据

        Returns:
            tuple: (files_dict, filename)
        """
        if isinstance(image_source, (str, Path)):
            # 本地文件路径
            file_path = Path(image_source)
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            final_filename = filename or file_path.name
            files = {
                "image": (
                    final_filename,
                    open(file_path, "rb"),
                    self._get_mime_type(file_path),
                )
            }

        elif isinstance(image_source, bytes):
            # 二进制数据
            final_filename = filename or f"image_{int(time.time())}.jpg"
            files = {"image": (final_filename, io.BytesIO(image_source), "image/jpeg")}

        elif hasattr(image_source, "read"):
            # 文件对象
            final_filename = filename or f"image_{int(time.time())}.jpg"

            # 如果文件对象有name属性，使用它
            if hasattr(image_source, "name") and image_source.name:
                final_filename = filename or Path(image_source.name).name

            files = {
                "image": (
                    final_filename,
                    image_source,
                    self._get_mime_type(final_filename),
                )
            }

        else:
            raise ValueError(f"不支持的图片源类型: {type(image_source)}")

        return files, final_filename

    def _get_mime_type(self, file_path: Union[str, Path]) -> str:
        """根据文件扩展名获取MIME类型"""
        ext = Path(file_path).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        return mime_map.get(ext, "application/octet-stream")

    def _extract_image_url(self, result: Dict[str, Any]) -> Optional[str]:
        """从响应结果中提取图片URL"""
        if isinstance(result, dict):
            # 尝试不同的响应格式
            if "data" in result and isinstance(result["data"], dict):
                return result["data"].get("url")
            elif "url" in result:
                return result["url"]
            elif "links" in result and isinstance(result["links"], dict):
                return result["links"].get("url")
        return None

    def close(self):
        """关闭HTTP客户端"""
        if hasattr(self, "client"):
            self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 全局函数
def upload_image(
    image_source: Union[str, Path, bytes, BinaryIO],
    token: str,
    api_url: str = "http://127.0.0.1/api/index.php",
    filename: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    上传图片到图床（便捷函数）

    Args:
        image_source: 图片源
        token: 图床token
        api_url: 图床API地址
        filename: 文件名
        max_retries: 最大重试次数，默认3次
        retry_delay: 重试延迟时间，默认1秒
        **kwargs: 其他参数

    Returns:
        dict: 上传结果
    """
    with ImageUploader(
        api_url=api_url,
        token=token,
        max_retries=max_retries,
        retry_delay=retry_delay,
        **kwargs,
    ) as uploader:
        return uploader.upload(image_source, filename)


async def upload_image_async(
    image_source: Union[str, Path, bytes, BinaryIO],
    token: str,
    api_url: str = "http://127.0.0.1/api/index.php",
    filename: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs,
) -> Dict[str, Any]:
    """
    异步上传图片到图床（便捷函数）

    Args:
        image_source: 图片源
        token: 图床token
        api_url: 图床API地址
        filename: 文件名
        max_retries: 最大重试次数，默认3次
        retry_delay: 重试延迟时间，默认1秒
        **kwargs: 其他参数

    Returns:
        dict: 上传结果
    """
    uploader = ImageUploader(
        api_url=api_url,
        token=token,
        max_retries=max_retries,
        retry_delay=retry_delay,
        **kwargs,
    )
    try:
        return await uploader.upload_async(image_source, filename)
    finally:
        uploader.close()
