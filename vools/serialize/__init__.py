"""
vools.serialize - Callable 序列化子包

支持多种序列化后端，提供装饰器简化序列化操作。

Example:
    >>> from vools.serialize import serialize, deserialize, Serializer
    >>> from vools import curry

    >>> # 基本用法
    >>> s = Serializer(backend='pickle')
    >>> data = s.dumps({"key": "value"})

    >>> # 使用装饰器
    >>> @serialize(backend='json')
    ... def get_data():
    ...     return {"name": "test"}

    >>> # 类装饰器
    >>> from vools.serialize import serializable
    >>> @serializable(backend='pickle')
    ... class MyData:
    ...     def __init__(self, name: str):
    ...         self.name = name
"""

__all__ = [
    # 核心类
    'Serializer',

    # 便捷函数
    'dumps',
    'loads',
    'dumps_hex',
    'loads_hex',

    # 装饰器
    'serialize',
    'deserialize',
    'serializable',
    'serialize_method',
    'deserialize_method',

    # 配置
    'set_default_backend',
    'get_default_backend',

    # 后端
    'BaseBackend',
    'PickleBackend',
    'JsonBackend',
    'MSGPACK_AVAILABLE',

    # 类型注册表
    'register_type',
    'get_type_handler',
    'get_type_deserializer',
]

# 延迟导入避免循环依赖
from .core import Serializer, dumps, loads, dumps_hex, loads_hex
from .decorators import (
    serialize,
    deserialize,
    serializable,
    serialize_method,
    deserialize_method,
)
from .config import set_default_backend, get_default_backend
from .backends import BaseBackend, PickleBackend, JsonBackend, MSGPACK_AVAILABLE
from .type_registry import register_type, get_type_handler, get_type_deserializer

# msgpack 可能不可用
try:
    from .backends import MsgpackBackend
    __all__.append('MsgpackBackend')
except ImportError:
    pass
