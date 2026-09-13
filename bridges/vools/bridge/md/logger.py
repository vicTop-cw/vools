"""
vools.bridge.md logger — 日志系统

提供统一的日志接口，支持控制台和文件输出。
"""
import logging
import sys
from typing import Optional, Dict


_logger: Optional[logging.Logger] = None
_handlers: Dict[str, logging.Handler] = {}


def get_logger(name: str = "vools.bridge.md", level: int = logging.INFO) -> logging.Logger:
    """
    获取或创建日志器。

    Args:
        name: 日志器名称
        level: 日志级别

    Returns:
        Logger 实例
    """
    global _logger
    if _logger is None:
        _logger = logging.getLogger(name)
        _logger.setLevel(level)

        # 控制台输出
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        _logger.addHandler(console_handler)
        _handlers['console'] = console_handler

    return _logger


def set_level(level: int) -> None:
    """设置全局日志级别"""
    logger = get_logger()
    logger.setLevel(level)
    for handler in _handlers.values():
        handler.setLevel(level)


def add_file_handler(filepath: str, level: int = logging.DEBUG) -> None:
    """添加文件输出"""
    file_handler = logging.FileHandler(filepath, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    get_logger().addHandler(file_handler)
    _handlers[f'file_{filepath}'] = file_handler


def remove_file_handler(filepath: str) -> None:
    """移除文件输出"""
    key = f'file_{filepath}'
    if key in _handlers:
        get_logger().removeHandler(_handlers[key])
        _handlers.pop(key)
