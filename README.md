# python-mytool

## Install

```
pip install -r requirements.txt
```

## 配置

数据文件存放在 `data/config.json` 中。

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
