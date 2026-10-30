import re
import random
import time
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union

from bs4 import BeautifulSoup
import urllib3

# import warnings

from utils import (
    logger,
    cookie_to_dict,
    request_with_retry,
    nested_lookup,
    get_cookies,
    run_task,
)
from models import project_config
from config.task_logger import execute_task_with_logging, TaskResult, TaskLogger

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 微博 App 网关（鉴权只靠参数串里的 s/gsid，不发 Cookie 头）
API_BASE = "https://api.weibo.cn/2"


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
        self._profile: Optional[Dict[str, Any]] = None
        # 白名单（空 = 签全部已关注超话）与签到间隔（秒），来自 config.json
        self._allow = self._load_allowlist()
        self._delay = self._load_delay()

    # ---------- 账号识别 / 配置 ----------

    @staticmethod
    def _norm_topic(value: Any) -> str:
        """超话名归一化：去空白、去「超话」后缀、小写；containerid 原样小写。"""
        s = re.sub(r"\s+", "", str(value or "")).lower()
        suffix = "超话"
        if s.endswith(suffix):
            s = s[: -len(suffix)]
        return s

    def _load_allowlist(self) -> set:
        raw = getattr(project_config, "weibo_topics", None) or []
        if isinstance(raw, str):
            raw = [x for x in re.split(r"[,;\n]", raw)]
        return {self._norm_topic(x) for x in raw if str(x).strip()}

    def _load_delay(self) -> Tuple[float, float]:
        raw = getattr(project_config, "weibo_sign_delay", None)
        try:
            lo, hi = float(raw[0]), float(raw[1])
        except (TypeError, ValueError, IndexError):
            return (0.0, 0.0)
        if lo < 0 or hi < lo:
            return (0.0, 0.0)
        return (lo, hi)

    @property
    def profile(self) -> Dict[str, Any]:
        """当前登录账号资料。`/2/users/show` 不传 uid 时返回自己，顺带当 token 健康探针。"""
        if self._profile is None:
            resp = request_with_retry(
                "GET",
                f"{API_BASE}/users/show",
                params=self.params,
                headers=self.headers,
                verify=False,
            )
            try:
                data = resp.json()
            except ValueError:
                data = {}
            if resp.status_code != 200 or not data.get("id"):
                reason = data.get("errmsg") or data.get("errno") or f"HTTP {resp.status_code}"
                raise Exception(f"账号资料获取失败（token 可能已失效）: {reason}")
            self._profile = data
        return self._profile

    @property
    def label(self) -> str:
        """日志用的账号标识：昵称(uid)；拿不到时退化为「未知账号」。"""
        if not self._profile:
            return "未知账号"
        return f"{self._profile.get('screen_name')}({self._profile.get('id')})"

    @staticmethod
    def _containerid(item: Dict[str, Any]) -> str:
        """从卡片里取超话 containerid（scheme / action / openurl 三处兜底）。"""
        for raw in (item.get("scheme"), item.get("action"), item.get("openurl")):
            m = re.search(r"(?:containerid|pageid)=(\w+)", str(raw or ""))
            if m:
                return m.group(1)
        return ""

    def _allowed(self, follow: Dict[str, Any]) -> bool:
        if not self._allow:
            return True
        cid = str(follow.get("containerid") or "").lower()
        return bool(cid and cid in self._allow) or self._norm_topic(
            follow.get("name")
        ) in self._allow

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
                "containerid": self._containerid(item),
            }
            self._follow_data.append(follow_info)

    async def sign_all(self) -> List[Dict[str, Any]]:
        """执行所有签到。

        先做账号资料探针（拿不到 = token 失效，整轮直接失败，避免静默）；
        再按 weibo_topics 白名单过滤；逐条签到之间带随机延迟（weibo_sign_delay）。
        """
        prof = self.profile  # token 失效会在这里抛
        logger.info(
            f"👤 {prof.get('screen_name')}({prof.get('id')}) 开始微博签到"
            f"（关注超话 {len(self.follow_data)} 个）"
        )

        if not self.follow_data:
            logger.warning(f"[{self.label}] 没有找到关注列表，可能cookie无效")
            return []

        targets = [f for f in self.follow_data if self._allowed(f)]
        skipped = len(self.follow_data) - len(targets)
        if self._allow:
            logger.info(
                f"[{self.label}] 白名单命中 {len(targets)} 个，跳过清单外 {skipped} 个"
            )
            if not targets:
                logger.error(
                    f"[{self.label}] 白名单没有命中任何已关注超话，检查 weibo_topics 配置"
                )
                return []

        result = []
        attempted = 0
        for follow in targets:
            if not follow["is_sign"] and follow["request_url"]:
                lo, hi = self._delay
                if attempted and hi > 0:
                    time.sleep(random.uniform(lo, hi))
                sign_result = await self._perform_sign(follow)
                result.append(sign_result)
                attempted += 1
            else:
                result.append(follow)

        logger.info(f"[{self.label}] 微博签到完成，处理了 {len(result)} 个超话")
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
            logger.warning(
                f"[{self.label}] ❌签到失败: {follow['name']}, 响应: {follow['sign_response']}"
            )
            return follow

        data = response.json()
        follow["sign_response"] = data
        if data.get("result") == 1:
            follow["is_sign"] = True
            follow["request_url"] = None
            logger.info(f"[{self.label}] ✅签到成功: {follow['name']}")
        else:
            logger.warning(f"[{self.label}] ❌签到失败: {follow['name']}, 响应: {data}")

        return follow

    def get_event_list(self) -> List[Dict[str, Any]]:
        """获取活动列表"""
        url = f"https://m.weibo.cn/api/container/getIndex?containerid={self.container_id}_-_activity_list"
        response = request_with_retry("GET", url)
        print(f"状态码: {response.status_code}")
        print(f"响应头: {response.headers}")
        print(f"响应体: {response.text}")

        if response.status_code == 200:
            data = response.json()
            logger.info(f"获取活动列表成功: {data}")
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


async def single_weibo_sign(weibo_cookie: str) -> Tuple[str, bool]:
    """执行单个微博账号签到。返回 (结果文本, 是否完全成功)。

    完全成功 = token 有效 且（signed + already > 0）且失败数为 0。
    任何失败都算作账号失败，便于上层推送告警，避免把失败藏起来。
    """
    try:
        weibo = WeiboSign(params=weibo_cookie)
        sign_results = await weibo.sign_all()

        if not sign_results:
            return (
                f"👤 {weibo.label}\n"
                "❌ 没有找到需要签到的超话（token 失效 / 未关注任何超话 / 白名单未命中）",
                False,
            )

        messages = [f"👤 {weibo.label}"]
        signed_count = 0
        already_signed_count = 0
        failed_count = 0

        for result in sign_results:
            level = result["level"]
            name = result["name"]
            is_sign = result["is_sign"]
            response = result.get("sign_response")

            if is_sign and not response:
                status = "☑️ 已签到"
                already_signed_count += 1
            elif is_sign and response:
                status = "✅"
                signed_count += 1
            else:
                status = "❌"
                failed_count += 1

            message = f"⚜️ [Lv.{level}] {name} {status}"
            messages.append(message)

        summary = (
            f"\n📊 总结: 新签 {signed_count} 个，已签 {already_signed_count} 个，"
            f"失败 {failed_count} 个（共 {len(sign_results)} 个）"
        )
        messages.append(summary)
        text = "\n".join(messages)

        logger.info(f"[{weibo.label}] {summary.strip()}")
        return text, failed_count == 0 and (signed_count + already_signed_count) > 0

    except Exception as e:
        error_msg = f"❌ 微博签到失败: {e}"
        logger.error(f"{error_msg}")
        return error_msg, False


async def _weibo_sign_impl() -> TaskResult:
    """微博签到实现"""

    async with TaskLogger("微博签到") as task_logger:
        all_cookies = get_cookies(project_config.weibo_cookie)

        if not all_cookies:
            task_logger.log_failure("未配置微博cookie环境变量或config.json文件")
            return task_logger.get_result()

        logger.info(f"您配置了 {len(all_cookies)} 个「微博超话签到」账号")

        lines: List[str] = []
        ok_cnt = 0
        fail_cnt = 0
        for i, raw in enumerate(all_cookies, start=1):
            logger.info(f"准备执行第 {i} 个账号的任务...")
            try:
                text, ok = await single_weibo_sign(raw)
            except Exception as e:
                logger.exception(f"第 {i} 个账号执行失败")
                text, ok = f"执行异常: {e}", False
            if ok:
                ok_cnt += 1
            else:
                fail_cnt += 1
            lines.append(f"🌈 第{i}个账号:\n{text}\n")

        if ok_cnt > 0:
            task_logger.log_success(f"成功签到 {ok_cnt} 个账号")
        if fail_cnt > 0:
            task_logger.log_failure(f"失败 {fail_cnt} 个账号")

        task_name = "🏆 微博超话签到"
        status_fmt = f"✅ 成功: {ok_cnt} · ❌ 失败: {fail_cnt}"
        content = f"{task_name} - {status_fmt}\n\n" + "\n".join(lines)

        task_logger.log_info(f"微博任务完成: {status_fmt}")

        result = task_logger.get_result()
        result.message = content
        return result


async def manually_weibo_sign() -> TaskResult:
    """手动执行微博签到的入口函数"""

    return await _weibo_sign_impl()


async def weibo_event_task() -> TaskResult:
    """微博签到实现"""

    async with TaskLogger("微博超话活动") as task_logger:
        all_cookies = get_cookies(project_config.weibo_cookie)

        if not all_cookies:
            task_logger.log_failure("未配置微博cookie环境变量或config.json文件")
            return task_logger.get_result()

        try:
            # 运行微博任务
            task_result = await run_task(
                "超话活动", all_cookies, single_weibo_event_sign
            )

            total_success_cnt = task_result[0]
            total_failure_cnt = task_result[1]
            task_name = task_result[2]
            status_fmt = task_result[3]
            message_content = task_result[4]

            if total_success_cnt == 0 and total_failure_cnt == 0:
                task_logger.log_warning("没有有效的微博账号配置")
                return task_logger.get_result()

            # 记录统计信息
            if total_success_cnt > 0:
                task_logger.log_success(f"成功 {total_success_cnt} 个账号")
            if total_failure_cnt > 0:
                task_logger.log_failure(f"失败 {total_failure_cnt} 个账号")

            title = f"{task_name} - {status_fmt}"
            content = f"{title}\n\n{message_content}"

            task_logger.log_info(f"微博任务完成: {status_fmt}")

            result = task_logger.get_result()
            result.message = content  # 使用详细的消息内容

            return result

        except Exception as e:
            task_logger.log_failure(f"微博超话任务执行失败: {e}")
            return task_logger.get_result()


async def single_weibo_event_sign(weibo_cookie: str) -> str:
    """
    执行单个微博超话活动任务

    Args:
        weibo_cookie: 微博cookie字符串

    Returns:
        任务结果
    """
    try:
        weibo = WeiboSign(params=weibo_cookie)
        event_result = weibo.has_events()

        if not event_result:
            return "暂时没有超话活动"

        messages = []

        gift_box = weibo.get_unclaimed_gifts()
        logger.info(f"已获取礼包码: {gift_box}")

        messages.append(f"🎁 礼包码: {gift_box}")

        result_msg = "\n".join(messages)

        logger.info(f"超话任务结果: {result_msg}")
        return result_msg

    except Exception as e:
        error_msg = f"❌ 超话任务失败: {str(e)}"
        logger.error(error_msg)
        return error_msg


# 测试单个cookie使用
if __name__ == "__main__":
    # 示例用法
    cookie = "your_weibo_cookie_here"

    async def main():
        result, _ = await single_weibo_sign(cookie)
        print(result)

    asyncio.run(main())
