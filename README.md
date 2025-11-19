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
