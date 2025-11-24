import hashlib
import io
import json

# import os
import random
import string
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Dict, Literal, Union, Optional, Tuple, Iterable, List, Any
from urllib.parse import urlencode

import httpx
import tenacity

from config.logger import logger
from qrcode import QRCode

from models import (
    GeetestResult,
    ConfigDataManager,
    Preference,
    project_config,
    project_env,
    UserData,
)

__all__ = [
    "custom_attempt_times",
    "get_async_retry",
    "generate_device_id",
    "cookie_str_to_dict",
    "cookie_dict_to_str",
    "generate_ds",
    "get_validate",
    "generate_seed_id",
    "generate_fp_locally",
    "get_file",
    "blur_phone",
    "generate_qr_img",
    "get_unique_users",
    "get_cookies",
    "cookie_to_dict",
    "nested_lookup",
    "request_with_retry",
    "run_task",
]


def get_cookies(cookies: str) -> List[str]:
    """解析cookies字符串为列表"""
    if not cookies:
        return []

    if "#" in cookies:
        return [cookie.strip() for cookie in cookies.split("#") if cookie.strip()]
    elif isinstance(cookies, list):
        return cookies
    else:
        return [cookie.strip() for cookie in cookies.splitlines() if cookie.strip()]


def cookie_to_dict(cookie: str) -> Dict[str, str]:
    """将cookie字符串转换为字典"""
    if not cookie or "=" not in cookie:
        return {}
    return dict([line.strip().split("=", 1) for line in cookie.split(";")])


def nested_lookup(
    obj: Any, key: str, with_keys: bool = False, fetch_first: bool = False
) -> Any:
    """嵌套查找对象中的键值"""
    result = list(_nested_lookup(obj, key, with_keys=with_keys))
    if with_keys:
        values = [v for k, v in _nested_lookup(obj, key, with_keys=with_keys)]
        result = {key: values}
    if fetch_first:
        result = result[0] if result else result
    return result


def _nested_lookup(obj: Any, key: str, with_keys: bool = False):
    """嵌套查找生成器"""
    if isinstance(obj, list):
        for item in obj:
            yield from _nested_lookup(item, key, with_keys=with_keys)

    if isinstance(obj, dict):
        for k, v in obj.items():
            if key == k:
                yield (k, v) if with_keys else v
            if isinstance(v, (list, dict)):
                yield from _nested_lookup(v, key, with_keys=with_keys)


def request_with_retry(
    *args,
    max_retries: int = project_config.preference.max_retry_times,
    sleep_seconds: int = 5,
    **kwargs,
) -> httpx.Response:
    """同步版本的带重试机制的请求函数"""
    count = 0

    # 提取 httpx.Client 的配置参数
    client_kwargs = {
        "verify": kwargs.pop("verify", False),  # 禁用SSL验证
        "timeout": kwargs.pop("timeout", 30),  # 超时时间
        "follow_redirects": kwargs.pop("follow_redirects", True),  # 跟随重定向
    }

    while count <= max_retries:
        try:
            with httpx.Client(**client_kwargs) as client:
                response = client.request(*args, **kwargs)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"服务器错误: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response

        except Exception as e:
            count += 1
            if count > max_retries:
                logger.error(f"请求失败，已达最大重试次数: {e}")
                raise e
            logger.warning(
                f"请求失败，{sleep_seconds}秒后重试 ({count}/{max_retries}): {e}"
            )
            time.sleep(sleep_seconds)


async def run_task(
    name: str, data_list: List[Union[str, UserData, Tuple[str, UserData]]], task_func
) -> List[Any]:
    """
    执行任务的通用函数

    Args:
        name: 任务名称
        data_list: 数据列表，可以是字符串、UserData对象或(user_id, user_data)元组
        task_func: 要执行的任务函数

    Returns:
        执行结果列表
    """
    if not data_list:
        return [0, 0, f"🏆 {name}", "❌ 未配置数据", ""]

    success_count = 0
    failure_count = 0
    result_list = []

    account_count = len(data_list)
    account_str = "账号" if account_count == 1 else "账号"
    logger.info(f"您配置了 {account_count} 个「{name}」{account_str}")

    for i, data in enumerate(data_list, start=1):
        logger.info(f"准备执行第 {i} 个账号的任务...")
        try:
            # 根据数据类型处理
            if isinstance(data, tuple) and len(data) == 2:
                # 如果是元组，解包为 (user_id, user_data)
                user_id, user_data = data
                raw_result = await task_func(user_data)  # 只传递 user_data
            else:
                # 如果是其他类型，直接传递
                raw_result = await task_func(data)

            success_count += 1
            result_str = str(raw_result)
        except Exception as e:
            logger.exception(f"第 {i} 个账号执行失败")
            raw_result = f"执行失败: {e}"
            failure_count += 1
            result_str = str(raw_result)

        result_fmt = f"🌈 第{i}个账号:\n{result_str}\n"
        result_list.append(result_fmt)

    task_name_fmt = f"🏆 {name}"
    status_fmt = f"✅ 成功: {success_count} · ❌ 失败: {failure_count}"
    message_box = [
        success_count,
        failure_count,
        task_name_fmt,
        status_fmt,
        "\n".join(result_list),
    ]
    return message_box


def custom_attempt_times(retry: bool):
    """
    自定义的重试机制停止条件\n
    根据是否要重试的bool值，给出相应的`tenacity.stop_after_attempt`对象

    :param retry True - 重试次数达到配置中 MAX_RETRY_TIMES 时停止; False - 执行次数达到1时停止，即不进行重试
    """
    if retry:
        return tenacity.stop_after_attempt(
            project_config.preference.max_retry_times + 1
        )
    else:
        return tenacity.stop_after_attempt(1)


def get_async_retry(retry: bool):
    """
    获取异步重试装饰器

    :param retry: True - 重试次数达到偏好设置中 max_retry_times 时停止; False - 执行次数达到1时停止，即不进行重试
    """
    return tenacity.AsyncRetrying(
        stop=custom_attempt_times(retry),
        retry=tenacity.retry_if_exception_type(BaseException),
        wait=tenacity.wait_fixed(project_config.preference.retry_interval),
    )


def generate_device_id() -> str:
    """
    生成随机的x-rpc-device_id
    """
    return str(uuid.uuid4()).upper()


def cookie_str_to_dict(cookie_str: str) -> Dict[str, str]:
    """
    将字符串Cookie转换为字典Cookie
    """
    cookie_str = cookie_str.replace(" ", "")
    # Cookie末尾缺少 ; 的情况
    if cookie_str[-1] != ";":
        cookie_str += ";"

    cookie_dict = {}
    start = 0
    while start != len(cookie_str):
        mid = cookie_str.find("=", start)
        end = cookie_str.find(";", mid)
        cookie_dict.setdefault(cookie_str[start:mid], cookie_str[mid + 1 : end])
        start = end + 1
    return cookie_dict


def cookie_dict_to_str(cookie_dict: Dict[str, str]) -> str:
    """
    将字符串Cookie转换为字典Cookie
    """
    cookie_str = ""
    for key in cookie_dict:
        cookie_str += key + "=" + cookie_dict[key] + ";"
    return cookie_str


def generate_ds(
    data: Union[str, dict, list, None] = None,
    params: Union[str, dict, None] = None,
    platform: Literal["ios", "android"] = "ios",
    salt: Optional[str] = None,
):
    """
    获取Headers中所需DS

    :param data: 可选，网络请求中需要发送的数据
    :param params: 可选，URL参数
    :param platform: 可选，平台，ios或android
    :param salt: 可选，自定义salt
    """
    if (
        data is None
        and params is None
        or salt is not None
        and salt != project_env.salt_config.SALT_PROD
    ):
        if platform == "ios":
            salt = salt or project_env.salt_config.SALT_IOS
        else:
            salt = salt or project_env.salt_config.SALT_ANDROID
        t = str(int(time.time()))
        a = "".join(random.sample(string.ascii_lowercase + string.digits, 6))
        re = hashlib.md5(f"salt={salt}&t={t}&r={a}".encode()).hexdigest()
        return f"{t},{a},{re}"
    else:
        if params:
            salt = project_env.salt_config.SALT_PARAMS if not salt else salt
        else:
            salt = project_env.salt_config.SALT_DATA if not salt else salt

        if not data:
            if salt == project_env.salt_config.SALT_PROD:
                data = {}
            else:
                data = ""
        if not params:
            params = ""

        if not isinstance(data, str):
            data = json.dumps(data).replace(" ", "")
        if not isinstance(params, str):
            params = urlencode(params)

        t = str(int(time.time()))
        r = str(random.randint(100000, 200000))
        c = hashlib.md5(
            f"salt={salt}&t={t}&r={r}&b={data}&q={params}".encode()
        ).hexdigest()
        return f"{t},{r},{c}"


async def get_validate(user: UserData, gt: str = None, challenge: str = None):
    """
    使用打码平台获取人机验证validate

    :param user: 用户数据对象
    :param gt: 验证码gt
    :param challenge: challenge
    :return: 如果配置了平台URL，且 gt, challenge 不为空，返回 GeetestResult
    """
    if not project_config.preference.global_geetest:
        if not (gt and challenge) or not user.geetest_url:
            return GeetestResult("", "")
        geetest_url = user.geetest_url
        params = {"gt": gt, "challenge": challenge}
        params.update(user.geetest_params or {})
    else:
        if not (gt and challenge) or not project_config.preference.geetest_url:
            return GeetestResult("", "")
        geetest_url = project_config.preference.geetest_url
        params = {"gt": gt, "challenge": challenge}
        params.update(project_config.preference.geetest_params or {})
    content = deepcopy(
        project_config.preference.geetest_json or Preference().geetest_json
    )
    for key, value in content.items():
        if isinstance(value, str):
            content[key] = value.format(gt=gt, challenge=challenge)
    debug_log = {"geetest_url": geetest_url, "params": params, "content": content}
    logger.debug(f"get_validate: {debug_log}")
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                geetest_url, params=params, json=content, timeout=60
            )
        geetest_data = res.json()
        logger.debug(f"人机验证结果：{geetest_data}")
        validate = geetest_data["data"]["validate"]
        seccode = geetest_data["data"].get("seccode") or f"{validate}|jordan"
        return GeetestResult(validate=validate, seccode=seccode)
    except Exception:
        logger.exception(f"获取人机验证validate失败")


def generate_seed_id(length: int = 8) -> str:
    """
    生成随机的 seed_id（即长度为8的十六进制数）

    :param length: 16进制数长度
    """
    max_num = int("FF" * length, 16)
    return hex(random.randint(0, max_num))[2:]


def generate_fp_locally(length: int = 13):
    """
    于本地生成 device_fp

    :param length: device_fp 长度
    """
    characters = string.digits + "abcdef"
    return "".join(random.choices(characters, k=length))


async def get_file(url: str, retry: bool = True):
    """
    下载文件

    :param url: 文件URL
    :param retry: 是否允许重试
    :return: 文件数据，若下载失败则返回 ``None``
    """
    try:
        async for attempt in get_async_retry(retry):
            with attempt:
                async with httpx.AsyncClient() as client:
                    res = await client.get(
                        url,
                        timeout=project_config.preference.timeout,
                        follow_redirects=True,
                    )
                return res.content
    except tenacity.RetryError:
        logger.exception(f"下载文件 - {url} 失败")
        return None


def blur_phone(phone: Union[str, int]) -> str:
    """
    模糊手机号

    :param phone: 手机号
    :return: 模糊后的手机号
    """
    if isinstance(phone, int):
        phone = str(phone)
    return f"☎️{phone[-4:]}"


def generate_qr_img(data: str):
    """
    生成二维码图片

    :param data: 二维码数据

    >>> b = generate_qr_img("https://github.com/Ljzd-PRO/nonebot-plugin-mystool")
    >>> isinstance(b, bytes)
    """
    qr_code = QRCode(border=2)
    qr_code.add_data(data)
    qr_code.make()
    image = qr_code.make_image()
    image_bytes = io.BytesIO()
    image.save(image_bytes)
    return image_bytes.getvalue()


def get_unique_users() -> Iterable[Tuple[str, UserData]]:
    """
    获取 不包含绑定用户数据 的所有用户数据以及对应的ID，即不会出现值重复项

    :return: dict_items[用户ID, 用户数据]
    """
    return ConfigDataManager.get_users().items()
