# logger.py
import logging
import sys
from pathlib import Path
from typing import Optional

# try:
#     import pyqrcode

#     QR_TERMINAL_AVAILABLE = True
# except ImportError:
#     QR_TERMINAL_AVAILABLE = False
QR_TERMINAL_AVAILABLE = False


class CustomLogger(logging.Logger):
    def success(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log(logging.INFO, f"✅ {msg}", args, **kwargs)

    def qr(self, data: str, description: str = ""):
        """
        使用qrcode-terminal打印二维码（更简单的实现）
        """
        if not QR_TERMINAL_AVAILABLE:
            self.warning("QR code generation requires 'qrcode-terminal' package")
            self.info(f"QR Data: {data}")
            return

        if description:
            self.info(f"📱 QR Code - {description}")
        else:
            self.info("📱 QR Code")

        self.info(f"Data: {data}")

        # 实际测试的时候，这个二维码由于太复杂，终端输出特别大会被截断，无法完全展示，
        # 考虑还是改成推送图片消息的形式
        # qr_data = pyqrcode.create(data)
        # print(qr_data.terminal(quiet_zone=0))


# 注册自定义logger类
logging.setLoggerClass(CustomLogger)


def setup_logger(
    name: str = "project",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
) -> CustomLogger:

    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(level)

        if format_string is None:
            format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        formatter = logging.Formatter(format_string)
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
