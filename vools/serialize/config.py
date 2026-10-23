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
        backend: 后端名称，如 'pickle', 'json', 'msgpack'；None 表示恢复
            为未设置（使用各后端默认解析规则）

    Raises:
        ValueError: backend 不是已注册的后端名（BUG-399：原实现把任意值
            写入全局默认，直到下次 dumps 才以难懂的方式暴露）

    Note:
        BUG-399: 同 encoding/crypto 注册表（BUG-398）——入口必须校验，
        否则 `set_default_backend('nope')` / `set_default_backend(123)` 会
        污染全局默认，后续 dumps 抛 ValueError 或 TypeError。
    """
    global _DEFAULT_BACKEND
    if backend is None:
        _DEFAULT_BACKEND = None
        return
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError(
            f"默认后端名必须是非空字符串或 None，收到 "
            f"{type(backend).__name__}: {backend!r}")
    try:
        from .backends import _BACKENDS as _REGISTERED  # 延迟导入，避免循环
    except Exception:  # pragma: no cover - 防御性
        _REGISTERED = {}
    if _REGISTERED and backend not in _REGISTERED:
        raise ValueError(
            f"默认后端 {backend!r} 未注册；可用: {sorted(_REGISTERED)}")
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