import logging
import sys
import io
from pathlib import Path


def setup_logger(config):
    """配置日志记录器"""
    log_level = config["logging"].get("log_level", "INFO").upper()
    log_format = config["logging"].get("log_format", "%(asctime)s - %(levelname)s - %(message)s")
    log_file = Path(config["logging"].get("log_file", "release.log"))
    
    logger = logging.getLogger("autopypi")
    logger.setLevel(log_level)
    
    formatter = logging.Formatter(log_format)
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def log_step(logger, step, status="running"):
    """记录步骤状态"""
    if status == "running":
        logger.info(f"> {step}")
    elif status == "success":
        logger.info(f"OK {step}")
    elif status == "error":
        logger.error(f"ERROR {step}")
    elif status == "warning":
        logger.warning(f"WARN {step}")


def log_separator(logger):
    """记录分隔线"""
    logger.info("-" * 60)