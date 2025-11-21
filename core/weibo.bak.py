"""
参考代码：
@Project   : genshinhelper
@Author    : y1ndan
"""

import gettext
import logging
import os
import time
from urllib.parse import urlencode

import requests
import re

from bs4 import BeautifulSoup

log_level = logging.INFO

logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logger = logging

_localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "locale")
_translate = gettext.translation(
    "genshinhelper", _localedir, languages=[config.LANGUAGE], fallback=True
)
_ = _translate.gettext


def cookie_to_dict(cookie):
    if cookie and "=" in cookie:
        cookie = dict([line.strip().split("=", 1) for line in cookie.split(";")])
    return cookie


def nested_lookup(obj, key, with_keys=False, fetch_first=False):
    result = list(_nested_lookup(obj, key, with_keys=with_keys))
    if with_keys:
        values = [v for k, v in _nested_lookup(obj, key, with_keys=with_keys)]
        result = {key: values}
    if fetch_first:
        result = result[0] if result else result
    return result


def _nested_lookup(obj, key, with_keys=False):
    if isinstance(obj, list):
        for i in obj:
            yield from _nested_lookup(i, key, with_keys=with_keys)

    if isinstance(obj, dict):
        for k, v in obj.items():
            if key == k:
                if with_keys:
                    yield k, v
                else:
                    yield v

            if isinstance(v, list) or isinstance(v, dict):
                yield from _nested_lookup(v, key, with_keys=with_keys)


def request(*args, **kwargs):
    is_retry = True
    count = 0
    max_retries = 3
    sleep_seconds = 5
    while is_retry and count <= max_retries:
        try:
            s = requests.Session()
            response = s.request(*args, **kwargs)
            is_retry = False
        except Exception as e:
            if count == max_retries:
                raise e
            log.error(_("Request failed: {}").format(e))
            count += 1
            log.info(
                _("Trying to reconnect in {} seconds ({}/{})...").format(
                    sleep_seconds, count, max_retries
                )
            )
            time.sleep(sleep_seconds)
        else:
            return response


class Weibo(object):
    def __init__(self, params: str = None, cookie: str = None):
        """
        params: s=xxxxxx; gsid=xxxxxx; aid=xxxxxx; from=xxxxxx
        """
        self.params = cookie_to_dict(params.replace("&", ";")) if params else None
        self.cookie = cookie_to_dict(cookie)

        self.container_id = "100808fc439dedbb06ca5fd858848e521b8716"
        self.ua = "WeiboOverseas/4.4.6 (iPhone; iOS 14.0.1; Scale/2.00)"
        self.headers = {"User-Agent": self.ua}
        self.follow_data_url = "https://api.weibo.cn/2/cardlist"
        self.sign_url = "https://api.weibo.cn/2/page/button"
        self.event_url = f"https://m.weibo.cn/api/container/getIndex?containerid={self.container_id}_-_activity_list"
        self.mybox_url = "https://ka.sina.com.cn/html5/mybox"
        self.draw_url = "https://ka.sina.com.cn/innerapi/draw"
        self._follow_data = []

    @property
    def follow_data(self):
        if not self._follow_data:
            url = self.follow_data_url
            self.params["containerid"] = "100803_-_followsuper"
            self.params["count"] = "30"

            follow_list = self.get_card_type_11(1)

            for i in follow_list:
                action = nested_lookup(i, "action", fetch_first=True)
                request_url = (
                    "".join(re.findall("request_url=(.*)%26container", action))
                    if action
                    else None
                )
                follow = {
                    "name": nested_lookup(i, "title_sub", fetch_first=True),
                    "level": int(re.findall("\d+", i["desc1"])[0]),
                    "is_sign": (
                        False
                        if nested_lookup(i, "name", fetch_first=True) == "签到"
                        else True
                    ),
                    "request_url": request_url,
                }
                self._follow_data.append(follow)

            self._follow_data.sort(key=lambda k: (k["level"]), reverse=True)
        return self._follow_data

    def get_card_type_11(self, since_id):
        url = self.follow_data_url
        self.params["since_id"] = since_id  # 添加 since_id 到请求参数中
        response = request(
            "get",
            url,
            params=self.params,
            headers=self.headers,
            cookies=self.cookie,
            verify=False,
        ).json()
        if response is None:
            return []
        card_group = nested_lookup(response, "card_group", fetch_first=True)
        follow_list = [i for i in card_group if i["card_type"] == "8"]
        return follow_list

    def sign(self):
        result = []
        for follow in self.follow_data:
            if not follow["is_sign"]:
                url = self.sign_url
                self.params["request_url"] = follow["request_url"]
                if self.params.get("containerid"):
                    del self.params["containerid"]
                # turn off certificate verification
                response = request(
                    "get",
                    url,
                    params=self.params,
                    headers=self.headers,
                    cookies=self.cookie,
                    verify=False,
                ).json()
                follow["sign_response"] = response
                if int(response.get("result", -1)) == 1:
                    follow["is_sign"] = True
                    follow["request_url"] = None

            result.append(follow)
        return result

    @property
    def event_list(self):
        url = self.event_url
        response = request("get", url).json()
        return nested_lookup(response, "group", fetch_first=True)

    def check_event(self):
        return True if self.event_list else False

    def get_event_gift_ids(self):
        return [
            i
            for event in self.event_list
            for i in re.findall(r"gift/(\d*)", str(event["scheme"]))
        ]

    def get_mybox_codes(self):
        url = self.mybox_url
        response = request(
            "get", url, headers=self.headers, cookies=self.cookie, allow_redirects=False
        )
        if response.status_code != 200:
            raise Exception(
                "Failed to get my box codes: "
                "The cookie seems to be invalid, please re-login to https://ka.sina.com.cn"
            )

        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        # print(soup.prettify())
        boxs = soup.find_all(class_="giftbag")
        mybox_codes = []
        for box in boxs:
            item = {
                "id": box.find(class_="deleBtn").get("data-itemid"),
                "title": box.find(class_="title itemTitle").text,
                "code": box.find("span").parent.contents[1],
            }
            mybox_codes.append(item)
        return mybox_codes

    def unclaimed_gift_ids(self):
        event_gift_ids = self.get_event_gift_ids()
        mybox_gift_ids = [item.get("id") for item in self.get_mybox_codes()]
        return [i for i in event_gift_ids if i not in mybox_gift_ids]

    def get_code(self, id: str):
        url = self.draw_url
        self.headers.update({"Referer": f"https://ka.sina.com.cn/html5/gift/{id}"})
        data = {"gid": 10725, "itemId": id, "channel": "wblink"}
        response = request(
            "get", url, params=data, headers=self.headers, cookies=self.cookie
        ).json()
        code = nested_lookup(response, "kahao")

        result = (
            {"success": True, "id": id, "code": code}
            if code
            else {"success": False, "id": id, "response": response}
        )
        return result


# 使用示例
if __name__ == "__main__":
    cookie = "abcdefghijklmnopqrstuvwxyz"
    task = Weibo(params=cookie)
    resp = task.sign()
    result = []
    for i in resp:
        lv = i["level"]
        name = i["name"]
        is_sign = i["is_sign"]
        response = i.get("sign_response")

        status = response
        if is_sign and not response:
            status = "☑️"
        if is_sign and response:
            status = "✅"

        message = f"⚜️ [Lv.{lv}]{name} {status}\n    "
        result.append(message)

    logger.info("\n".join(result))
