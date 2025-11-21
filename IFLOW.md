# python-mytool 项目文档

## 项目概述

这是一个用于米哈游游戏（包括原神、崩坏系列、星穹铁道、绝区零等）自动签到和米游币任务的 Python 工具。支持通过青龙面板等定时任务系统运行，实现自动化的游戏签到和社区任务完成。

## 项目架构

```
my_project/
├── .vscode/                   # VS Code配置
│   └── settings.json
├── config/                    # 配置文件
│   ├── __init__.py
│   ├── _version.py
│   └── settings.py
├── core/                      # 核心业务逻辑
│   ├── __init__.py
│   └── game.py
├── data/                      # 数据文件
│   └── config.example.json
├── models/                    # 数据模型
│   ├── __init__.py
│   ├── common.py
│   ├── config.py
│   ├── data.py
│   └── push_config.py
├── services/                  # API服务逻辑
│   ├── __init__.py
│   ├── common.py
│   ├── game_sign_api.py       # 游戏签到API
│   └── myb_missions_api.py    # 米游币任务API
├── utils/                     # 工具函数
│   ├── __init__.py
│   ├── common.py
│   ├── logger.py
│   └── push.py
├── main.py                    # 主入口文件
├── ql_main.py                 # 青龙面板入口文件
├── README.md
├── requirements.txt
└── IFLOW.md                   # 本项目文档
```

## 功能特性

### 游戏签到

- 支持多款米哈游游戏自动签到（原神、崩坏 3、崩坏学园 2、未定事件簿、星穹铁道、绝区零）
- 支持多账号管理
- 自动处理人机验证（Geetest）

### 米游币任务

- 自动完成每日签到、阅读、点赞、分享任务
- 支持多个游戏分区的米游币任务
- 智能识别任务完成状态

### 便笺提醒

- 支持原神、星穹铁道实时便笺查询
- 树脂、开拓力等资源溢出提醒
- 每日任务完成情况监控

## 配置说明

### 依赖安装

```bash
pip install -r requirements.txt
```

### 配置文件

- 配置文件路径: `data/config.json`
- 包含用户账号信息、推送设置、偏好配置等

### 环境变量

- 使用 `pydantic-settings` 进行配置管理
- 支持多种推送方式配置

## 运行方式

### 本地运行

```bash
python main.py
```

### 青龙面板运行（V2.12+）

#### 订阅管理

- 名称：米哈游游戏签到
- 类型：公开仓库
- 链接：https://github.com/scriptsmay/python-mytool.git
- 定时类型：crontab
- 定时规则：2 2 28 \* \*
- 白名单：ql_main.py
- 依赖文件：.py

## 核心模块说明

### models 模块

- `config.py`: 包含项目配置、偏好设置、设备配置、Salt 配置等
- `data.py`: 用户数据模型定义
- `push_config.py`: 推送配置定义

### services 模块

- `game_sign_api.py`: 游戏签到 API 实现
  - 支持原神、崩坏 3、崩坏学园 2、未定事件簿、星穹铁道、绝区零
  - 提供签到、获取奖励、获取签到信息等功能
- `myb_missions_api.py`: 米游币任务 API 实现
  - 支持签到、阅读、点赞、分享等任务
  - 提供任务状态查询功能

### core 模块

- `game.py`: 核心业务逻辑
  - `manually_game_sign()`: 手动游戏签到
  - `manually_bbs_sign()`: 手动米游币任务
  - 便笺检查功能

### utils 模块

- 通用工具函数
- 日志记录
- 推送功能

## 技术栈

- Python 3.8+
- Pydantic: 数据验证和设置管理
- httpx: HTTP 客户端
- tenacity: 重试机制
- pydantic-settings: 配置管理

## 配置选项

### 偏好设置 (Preference)

- `github_proxy`: GitHub 加速代理
- `timeout`: 网络请求超时时间
- `max_retry_times`: 最大网络请求重试次数
- `sleep_time`: 任务操作冷却时间

### 设备配置 (DeviceConfig)

- 包含不同平台的 User-Agent 设置
- 包含不同平台的设备信息设置
- 包含 API 请求所需的 Headers 设置

## 开发规范

- 使用 Pydantic 进行数据验证
- 使用异步编程提高并发性能
- 遵循 Python PEP 8 编码规范
- 使用 logging 模块进行日志记录
