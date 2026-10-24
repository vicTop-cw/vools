"""
Callable 对象序列化处理器

提供对各种 callable 对象（装饰器包装的函数、柯里化函数、函数式对象等）的序列化支持。
"""

from typing import Any, Callable, Dict, Type, Optional, Tuple
from abc import ABC, abstractmethod

from ...core.base import VoolsBase

__all__ = [
    'CallableHandler',
    'register_handler',
    'get_handler',
    'serialize_callable',
    'deserialize_callable',
]

# 处理器注册表
_HANDLERS: list = []


class CallableHandler(ABC, VoolsBase):
    """Callable 处理器抽象基类"""

    @property
    def handler_name(self) -> str:
        """处理器名称，用于序列化标识。默认使用类名，可重写以提供稳定名称。"""
        return self.__class__.__name__

    @abstractmethod
    def can_handle(self, obj: Any) -> bool:
        """检查此处理器是否能处理给定对象"""
        raise NotImplementedError

    @abstractmethod
    def get_state(self, obj: Any) -> Dict[str, Any]:
        """获取对象的序列化状态"""
        raise NotImplementedError

    # BUG-186: 此处原先误留一个悬空的 @abstractmethod（后接空行），
    # 装饰器实际应用到下方具体方法 do，导致未 override do 的子类
    # 实例化抛 TypeError。do 是带实现的普通方法，删除多余装饰器。
    def restore(self, state: Dict[str, Any]) -> Any:
        """从序列化状态恢复对象"""
        raise NotImplementedError


def register_handler(handler: CallableHandler) -> None:
    """注册 callable 处理器（BUG-446：入口校验，避免污染全局注册表）。

    原实现零校验：``register_handler(123)`` 会把 int 追加进模块级 ``_HANDLERS``，
    此后**任何** ``get_handler()`` 调用都会抛
    ``AttributeError: 'int' object has no attribute 'can_handle'``——一处误用
    直接破坏进程内所有 callable 序列化。

    Args:
        handler: 处理器实例（必须继承 CallableHandler）
    """
    if not isinstance(handler, CallableHandler):
        raise TypeError(
            f"register_handler() 需要 CallableHandler 实例，收到 "
            f"{type(handler).__name__}: {handler!r}")
    name = getattr(handler, "handler_name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"register_handler() 的 handler_name 需要非空字符串，收到 {name!r}")
    for existing in _HANDLERS:
        if existing is handler:
            return   # 同一实例重复注册：幂等
    _HANDLERS.append(handler)


def get_handler(obj: Any) -> Optional[CallableHandler]:
    """
    获取能处理给定对象的处理器

    Args:
        obj: 要处理的对象

    Returns:
        处理器实例，如果没有找到返回 None
    """
    for handler in _HANDLERS:
        if handler.can_handle(obj):
            return handler
    return None


def serialize_callable(obj: Any, backend_serializer) -> Tuple[str, Any]:
    """
    序列化 callable 对象

    Args:
        obj: 要序列化的 callable 对象
        backend_serializer: 后端序列化器

    Returns:
        (handler_name, handler_state) 元组
    """
    handler = get_handler(obj)
    if handler is None:
        # 无法处理，返回 None 表示使用默认 pickle 序列化
        return ('raw', backend_serializer.dumps(obj))

    state = handler.get_state(obj)
    # 序列化 handler state
    serialized_state = backend_serializer.dumps(state)
    return (handler.handler_name, serialized_state)


def deserialize_callable(handler_name: str, handler_state: Any, backend_deserializer) -> Any:
    """
    反序列化 callable 对象

    Args:
        handler_name: 处理器名称
        handler_state: 处理器状态
        backend_deserializer: 后端反序列化器

    Returns:
        恢复的 callable 对象
    """
    if handler_name == 'raw':
        return backend_deserializer.loads(handler_state)

    # 查找处理器
    for handler in _HANDLERS:
        if handler.handler_name == handler_name:
            # JSON 后端会将 bytes 转为 list，需转回 bytes
            if isinstance(handler_state, list) and all(isinstance(b, int) for b in handler_state):
                handler_state = bytes(handler_state)
            state = backend_deserializer.loads(handler_state)
            return handler.restore(state)

    raise ValueError(
        f"Unknown callable handler: '{handler_name}'. "
        f"Registered handlers: {[h.handler_name for h in _HANDLERS]}"
    )


# 导入并注册回退处理器（仅用于无 __getstate__ 的通用类型）
# 注意：已有 __getstate__ 的对象（_NONE, _X/_Y, _IndexHolder, PipeX/PipeY,
#   Hoder, Stuff, ConditionBuilder, Selector/Overloads, OverloadManager,
#   OvercurryManager, Curried/CurryDescriptor, DelayCurried, TaskDecorator,
#   vicText/vicDate/vicList）直接通过 __getstate__ 序列化，无需 handler。
from .decorator_handler import DecoratorHandler
from .functional_handler import FunctionalHandler

# 注册顺序：具体类型 → 通用兜底
register_handler(DecoratorHandler())
register_handler(FunctionalHandler())
