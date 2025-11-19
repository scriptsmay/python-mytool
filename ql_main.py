"""
new Env('米忽悠家签到');
"""

import notify
import os
from utils import push, logger


def ql_push(status_code, title, message):
    if os.getenv("mihuyo_push") == "1":
        push.push(status_code, message)
    else:
        notify.send(title, message)


try:
    from main import main_task
except (ImportError, NameError) as e:
    ql_push(-99, "「米游社脚本」依赖缺失", "脚本加入新模块，请更新青龙拉取范围")
    print("依赖缺失", e)
    exit(-1)


if __name__ == "__main__":
    main_task()
