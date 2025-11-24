# logger.py
import logging
import sys
from pathlib import Path
from typing import Optional


class CustomLogger(logging.Logger):
    def success(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log(logging.INFO, f"✅ {msg}", args, **kwargs)


# 注册自定义logger类
logging.setLoggerClass(CustomLogger)

# [%(levelname)s]


def setup_logger(
    name: str = "project",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
    date_format: Optional[str] = None,
) -> CustomLogger:

    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)

        # 正确的格式字符串 - 使用标准的 logging 属性
        if format_string is None:
            format_string = "%(asctime)s[%(levelname)s]%(message)s"  # 精简格式

        # 正确的时间格式
        if date_format is None:
            date_format = "%Y-%m-%d %H:%M:%S"  # 默认使用时分秒

        formatter = logging.Formatter(format_string, datefmt=date_format)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


# 创建默认logger
logger = setup_logger("mys-tool")
