"""
序列化后端模块
"""

from .base import BaseBackend
from .pickle_backend import PickleBackend
from .json_backend import JsonBackend
from .vb_json_backend import VBJsonBackend

# msgpack 是可选的
try:
    from .msgpack_backend import MsgpackBackend, is_available as _msgpack_available
    __all__ = ['BaseBackend', 'PickleBackend', 'JsonBackend', 'MsgpackBackend', 'VBJsonBackend']
    MSGPACK_AVAILABLE = _msgpack_available()
except ImportError:
    __all__ = ['BaseBackend', 'PickleBackend', 'JsonBackend', 'VBJsonBackend']
    MSGPACK_AVAILABLE = False


# 后端注册表
_BACKENDS = {
    'pickle': PickleBackend,
    'json': JsonBackend,
    'vb_json': VBJsonBackend,
}


def get_backend(name: str):
    """
    获取指定名称的后端类

    Args:
        name: 后端名称

    Returns:
        后端类

    Raises:
        ValueError: 如果后端不存在
    """
    if name == 'msgpack':
        if not MSGPACK_AVAILABLE:
            raise ValueError(
                f"Backend '{name}' is not available. "
                f"Install msgpack: pip install msgpack"
            )
    if name not in _BACKENDS:
        if name == 'msgpack':
            _BACKENDS['msgpack'] = MsgpackBackend
        else:
            raise ValueError(
                f"Unknown backend: '{name}'. "
                f"Available backends: {list(_BACKENDS.keys())}"
            )
    return _BACKENDS[name]


def register_backend(name: str, backend_class):
    """
    注册自定义后端

    Args:
        name: 后端名称（非空字符串）
        backend_class: 后端类（需继承 BaseBackend 或鸭子兼容）

    Raises:
        ValueError: name 不是非空字符串
        TypeError: backend_class 不是类

    Note:
        BUG-399: 原实现直接写字典、零校验——非字符串名称或任意对象都能
        "注册成功"，直到 get_backend/dumps 时才以 AttributeError 之类的
        形式暴露；同名覆盖还会静默替换内置后端。
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"后端名必须是非空字符串，收到 {type(name).__name__}: {name!r}")
    if not isinstance(backend_class, type):
        raise TypeError(
            f"backend_class 必须是类，收到 "
            f"{type(backend_class).__name__}: {backend_class!r}")
    _existing = _BACKENDS.get(name)
    if _existing is not None and _existing is not backend_class:
        import warnings as _w
        _w.warn(
            f"序列化后端 {name!r} 被覆盖：{_existing!r} -> {backend_class!r}"
            f"（如需替换内置后端请确认这是有意为之）",
            RuntimeWarning, stacklevel=2)
    _BACKENDS[name] = backend_class
