"""
序列化后端模块
"""

from .base import BaseBackend
from .pickle_backend import PickleBackend
from .json_backend import JsonBackend

# msgpack 是可选的
try:
    from .msgpack_backend import MsgpackBackend, is_available as _msgpack_available
    __all__ = ['BaseBackend', 'PickleBackend', 'JsonBackend', 'MsgpackBackend']
    MSGPACK_AVAILABLE = _msgpack_available()
except ImportError:
    __all__ = ['BaseBackend', 'PickleBackend', 'JsonBackend']
    MSGPACK_AVAILABLE = False


# 后端注册表
_BACKENDS = {
    'pickle': PickleBackend,
    'json': JsonBackend,
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
        name: 后端名称
        backend_class: 后端类
    """
    _BACKENDS[name] = backend_class
