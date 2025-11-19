import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 数据库配置
# DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/app.db")

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = BASE_DIR / "logs" / "app.log"

# 确保日志目录存在
LOG_FILE.parent.mkdir(exist_ok=True)