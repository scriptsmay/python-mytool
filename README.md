# python-mytool

## Install

```
pip install -r requirements.txt
```

## 配置

数据文件存放在 `data/config.json` 中。

## 微博超话签到（ql_wb.py）

### 配置项（data/config.json）

- `weibo_cookie`：微博 App 抓包参数串（`s`/`gsid`/`aid`/`from`/`ua`/...），多账号用 `#` 分隔。
- `weibo_topics`（可选）：超话白名单。可填 containerid（`100808...`）或超话名（带/不带「超话」后缀均可），留空 = 签所有已关注超话。建议只填 wbox 活动清单内的 3 个，减少风控面。
- `weibo_sign_delay`（可选）：签到之间随机延迟秒数区间 `[min, max]`，默认 `[3, 8]`；`[0, 0]` = 不延迟。账号之间建议再 stagger cron 时间。

### 账号识别

脚本启动时会用 `/2/users/show` 取当前登录账号的 uid + 昵称并打印到日志（`👤 昵称(uid)`），便于多账号排查。如果这个探针失败，说明 token 已失效，整轮会告警推送。

### 注意

- `s`/`gsid` 是按号派生的会话凭据，**不要提交到 git**，只放 `data/config.json`（已在 `.gitignore`）。
- 签到在微博凌晨重置后立刻执行（00:05）；签到档只签清单内超话，`auto_follow` 仍需在浏览器侧完成一次关注。

## Run

```
python main.py
```

## 项目结构

```
my_project/
├── .vscode/                   # VS Code配置（可选）
│   └── settings.json
├── config/                    # 配置文件
│   ├── __init__.py
├── models/                    # 数据模型
│   ├── __init__.py
├── services/                  # api逻辑
│   ├── __init__.py
├── utils/                     # 工具函数
│   ├── __init__.py
├── data/                      # 数据文件
├── logs/                      # 日志文件
├── requirements.txt           # 依赖列表
├── .gitignore
├── main.py                    # 主入口文件
└── README.md
```

## 使用青龙面板运行（V2.12+）

### 订阅管理

```text
名称： 米忽悠游戏签到
类型： 公开仓库
链接： https://github.com/scriptsmay/python-mytool.git
定时类型： crontab
定时规则： 2 2 28 * *
白名单： ql_*.py
依赖文件： .py|config.example.json
```

### 依赖管理

打开 `requirements_ql.txt` 文件，将里面的内容复制到依赖管理中安装。

python3 -> 创建依赖 -> 自动拆分 ✓ ：

```
httpx
qrcode
pydantic
tenacity
pytz
pydantic-settings
bs4
```
