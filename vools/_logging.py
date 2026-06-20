"""
vools 统一日志配置模块

所有 vools 内部模块应使用此模块获取 logger：
    from vools._logging import get_logger
    log = get_logger(__name__)

禁止在模块顶层直接使用 print() 输出调试信息。
"""

import logging
import sys
from typing import Optional
__all__ = ['configure_logging', 'get_logger']

_DEFAULT_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(
    level: int = logging.INFO,
    format_str: Optional[str] = None,
    date_format: Optional[str] = None,
    stream=None,
) -> None:
    """
    配置 vools 全局日志。

    在应用入口调用一次即可，后续模块通过 get_logger() 获取 logger。

    Args:
        level: 日志级别，默认 INFO
        format_str: 日志格式字符串
        date_format: 日期格式字符串
        stream: 输出流，默认 stderr
    """
    global _configured

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            format_str or _DEFAULT_FORMAT,
            datefmt=date_format or _DEFAULT_DATE_FORMAT,
        )
    )

    root = logging.getLogger("vools")
    root.setLevel(level)
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    获取 vools 模块 logger。

    自动确保 logger 名称以 "vools" 为前缀，
    并在首次调用时自动初始化默认配置。

    Args:
        name: 通常传 __name__

    Returns:
        logging.Logger 实例
    """
    if not _configured and not logging.getLogger("vools").handlers:
        configure_logging()

    if not name.startswith("vools"):
        name = f"vools.{name}"

    return logging.getLogger(name)