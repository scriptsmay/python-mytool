import re
import time
import asyncio
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
import urllib3
import warnings

from utils import logger
from models import project_config

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
    *args, max_retries: int = 3, sleep_seconds: int = 5, **kwargs
) -> requests.Response:
    """带重试机制的请求函数"""
    count = 0
    while count <= max_retries:
        try:
            session = requests.Session()
            # 确保禁用SSL验证
            kwargs.setdefault("verify", False)
            response = session.request(*args, **kwargs)
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


async def run_task(name: str, cookies: List[str], task_func) -> List[Any]:
    """运行任务的通用函数"""
    if not cookies:
        return [0, 0, f"🏆 {name}", "❌ 未配置cookie", ""]

    success_count = 0
    failure_count = 0
    result_list = []

    account_count = len(cookies)
    account_str = "账号" if account_count == 1 else "账号"
    logger.info(f"您配置了 {account_count} 个「{name}」{account_str}")

    for i, cookie in enumerate(cookies, start=1):
        logger.info(f"准备执行第 {i} 个账号的任务...")
        try:
            # 注意：这里需要await，因为task_func是异步的
            raw_result = await task_func(cookie)
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


class WeiboSign:
    """微博签到类"""

    def __init__(self, cookie: Optional[str] = None, params: Optional[str] = None):
        """
        初始化微博签到

        Args:
            cookie: 微博cookie字符串
            params: s=xxxxxx; gsid=xxxxxx; aid=xxxxxx; from=xxxxxx
        """
        self.cookie = cookie_to_dict(cookie) if cookie else {}
        self.params = cookie_to_dict(params.replace("&", ";")) if params else {}

        self.container_id = "100808fc439dedbb06ca5fd858848e521b8716"
        self.user_agent = "WeiboOverseas/4.4.6 (iPhone; iOS 14.0.1; Scale/2.00)"
        self.headers = {"User-Agent": self.user_agent}
        self._follow_data = []

    @property
    def follow_data(self) -> List[Dict[str, Any]]:
        """获取关注列表数据"""
        if not self._follow_data:
            self.params.update(
                {"containerid": "100803_-_followsuper", "count": "30", "since_id": "1"}
            )

            follow_list = self._get_follow_list()
            self._process_follow_data(follow_list)
            self._follow_data.sort(key=lambda x: x["level"], reverse=True)

        return self._follow_data

    def _get_follow_list(self) -> List[Dict[str, Any]]:
        """获取关注列表"""
        url = "https://api.weibo.cn/2/cardlist"
        response = request_with_retry(
            "GET",
            url,
            params=self.params,
            headers=self.headers,
            cookies=self.cookie,
            verify=False,
        )

        if response.status_code != 200:
            raise Exception(f"获取关注列表失败: HTTP {response.status_code}")

        data = response.json()
        card_group = nested_lookup(data, "card_group", fetch_first=True) or []
        return [item for item in card_group if item.get("card_type") == "8"]

    def _process_follow_data(self, follow_list: List[Dict[str, Any]]) -> None:
        """处理关注数据"""
        for item in follow_list:
            action = nested_lookup(item, "action", fetch_first=True)
            request_url = (
                "".join(re.findall(r"request_url=(.*)%26container", action or ""))
                if action
                else None
            )

            level_match = re.findall(r"\d+", item.get("desc1", ""))
            level = int(level_match[0]) if level_match else 0

            follow_info = {
                "name": nested_lookup(item, "title_sub", fetch_first=True) or "未知",
                "level": level,
                "is_sign": nested_lookup(item, "name", fetch_first=True) != "签到",
                "request_url": request_url,
            }
            self._follow_data.append(follow_info)

    async def sign_all(self) -> List[Dict[str, Any]]:
        """执行所有签到"""
        logger.info("⏳开始执行微博签到...")

        if not self.follow_data:
            logger.warning("没有找到关注列表，可能cookie无效")
            return []

        result = []
        for follow in self.follow_data:
            if not follow["is_sign"] and follow["request_url"]:
                sign_result = await self._perform_sign(follow)
                result.append(sign_result)
            else:
                result.append(follow)

        logger.info(f"✅微博签到完成，处理了 {len(result)} 个超话")
        return result

    async def _perform_sign(self, follow: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个签到"""
        url = "https://api.weibo.cn/2/page/button"
        params = self.params.copy()
        params["request_url"] = follow["request_url"]
        params.pop("containerid", None)

        response = request_with_retry(
            "GET",
            url,
            params=params,
            headers=self.headers,
            cookies=self.cookie,
            verify=False,
        )

        if response.status_code != 200:
            follow["sign_response"] = {"error": f"HTTP {response.status_code}"}
            return follow

        data = response.json()
        follow["sign_response"] = data
        if data.get("result") == 1:
            follow["is_sign"] = True
            follow["request_url"] = None
            logger.info(f"✅签到成功: {follow['name']}")
        else:
            logger.warning(f"❌签到失败: {follow['name']}, 响应: {data}")

        return follow

    def get_event_list(self) -> List[Dict[str, Any]]:
        """获取活动列表"""
        url = f"https://m.weibo.cn/api/container/getIndex?containerid={self.container_id}_-_activity_list"
        response = request_with_retry("GET", url)
        if response.status_code == 200:
            data = response.json()
            return nested_lookup(data, "group", fetch_first=True) or []
        return []

    def has_events(self) -> bool:
        """检查是否有活动"""
        return bool(self.get_event_list())

    def get_event_gift_ids(self) -> List[str]:
        """获取活动礼品ID"""
        event_list = self.get_event_list()
        gift_ids = []
        for event in event_list:
            scheme = str(event.get("scheme", ""))
            gift_ids.extend(re.findall(r"gift/(\d*)", scheme))
        return gift_ids

    def get_mybox_codes(self) -> List[Dict[str, str]]:
        """获取我的礼包码"""
        url = "https://ka.sina.com.cn/html5/mybox"
        response = request_with_retry(
            "GET", url, headers=self.headers, cookies=self.cookie, allow_redirects=False
        )

        if response.status_code != 200:
            raise Exception(
                "获取礼包码失败: cookie可能已失效，请重新登录 https://ka.sina.com.cn"
            )

        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        boxes = soup.find_all(class_="giftbag")

        codes = []
        for box in boxes:
            code_element = box.find("span")
            if code_element and code_element.parent:
                code_info = {
                    "id": box.find(class_="deleBtn").get("data-itemid", ""),
                    "title": (
                        box.find(class_="title itemTitle").text
                        if box.find(class_="title itemTitle")
                        else "未知"
                    ),
                    "code": (
                        code_element.parent.contents[1]
                        if len(code_element.parent.contents) > 1
                        else "未知"
                    ),
                }
                codes.append(code_info)

        return codes

    def get_unclaimed_gifts(self) -> List[str]:
        """获取未领取的礼品"""
        try:
            event_gift_ids = self.get_event_gift_ids()
            mybox_gift_ids = [item["id"] for item in self.get_mybox_codes()]
            return [
                gift_id for gift_id in event_gift_ids if gift_id not in mybox_gift_ids
            ]
        except Exception as e:
            logger.warning(f"获取未领取礼品失败: {e}")
            return []

    def draw_gift(self, gift_id: str) -> Dict[str, Any]:
        """领取礼品"""
        url = "https://ka.sina.com.cn/innerapi/draw"
        headers = self.headers.copy()
        headers["Referer"] = f"https://ka.sina.com.cn/html5/gift/{gift_id}"

        data = {"gid": 10725, "itemId": gift_id, "channel": "wblink"}
        response = request_with_retry(
            "GET", url, params=data, headers=headers, cookies=self.cookie
        )

        if response.status_code != 200:
            return {
                "success": False,
                "id": gift_id,
                "error": f"HTTP {response.status_code}",
            }

        data = response.json()
        code = nested_lookup(data, "kahao", fetch_first=True)

        return {
            "success": bool(code),
            "id": gift_id,
            "code": code,
            "response": data if not code else None,
        }


async def single_weibo_sign(weibo_cookie: str) -> str:
    """
    执行单个微博账号签到任务

    Args:
        weibo_cookie: 微博cookie字符串

    Returns:
        签到结果消息
    """
    try:
        weibo = WeiboSign(params=weibo_cookie)
        sign_results = await weibo.sign_all()

        if not sign_results:
            return "❌ 没有找到需要签到的超话，可能cookie无效或已全部签到"

        messages = []
        signed_count = 0
        already_signed_count = 0

        for result in sign_results:
            level = result["level"]
            name = result["name"]
            is_sign = result["is_sign"]
            response = result.get("sign_response")

            if is_sign and not response:
                status = "☑️ 已签到"
                already_signed_count += 1
            elif is_sign and response:
                status = "✅ 成功"
                signed_count += 1
            else:
                status = "❌ 失败"

            message = f"⚜️ [Lv.{level}] {name} {status}"
            messages.append(message)

        summary = f"\n📊 总结: 成功签到 {signed_count} 个，已签到 {already_signed_count} 个，失败 {len(sign_results) - signed_count - already_signed_count} 个"
        result_msg = "\n".join(messages) + summary

        logger.info(f"微博签到完成: {result_msg}")
        return result_msg

    except Exception as e:
        error_msg = f"❌ 微博签到失败: {str(e)}"
        logger.error(error_msg)
        return error_msg


async def run_wb_task(cookies: str) -> str:
    """运行微博任务的主函数"""
    all_cookies = get_cookies(cookies)

    if not all_cookies:
        tip = "❌ 请先配置微博cookie环境变量或config.json文件!"
        logger.warning(tip)
        return tip

    try:
        # 运行微博任务
        task_result = await run_task("微博超话签到", all_cookies, single_weibo_sign)

        total_success_cnt = task_result[0]
        total_failure_cnt = task_result[1]
        task_name = task_result[2]
        status_fmt = task_result[3]
        message_content = task_result[4]

        if total_success_cnt == 0 and total_failure_cnt == 0:
            return "❌ 没有有效的微博账号配置"

        title = f"{task_name} - {status_fmt}"
        content = f"{title}\n\n{message_content}"

        logger.info(f"微博任务完成: {status_fmt}")
        return content

    except Exception as e:
        error_msg = f"❌ 微博任务执行失败: {e}"
        logger.error(error_msg)
        return error_msg


async def manually_weibo_sign() -> str:
    """手动执行微博签到的入口函数（与其他模块保持一致）"""

    return await run_wb_task(project_config.weibo_cookie)


# 保留原有使用方式供兼容
if __name__ == "__main__":
    # 示例用法
    cookie = "your_weibo_cookie_here"

    async def main():
        result = await run_wb_task(cookie)
        print(result)

    asyncio.run(main())
