"""
序列化模块配置管理
"""

from typing import Optional
__all__ = ['set_default_backend', 'get_default_backend', 'clear_default_backend']

# 全局默认后端
_DEFAULT_BACKEND: Optional[str] = None


def set_default_backend(backend: str) -> None:
    """
    设置全局默认序列化后端

    Args:
        backend: 后端名称，如 'pickle', 'json', 'msgpack'
    """
    global _DEFAULT_BACKEND
    _DEFAULT_BACKEND = backend


def get_default_backend() -> Optional[str]:
    """
    获取全局默认序列化后端

    Returns:
        默认后端名称，如果没有设置返回 None
    """
    return _DEFAULT_BACKEND


def clear_default_backend() -> None:
    """
    清除全局默认后端设置
    """
    global _DEFAULT_BACKEND
    _DEFAULT_BACKEND = None