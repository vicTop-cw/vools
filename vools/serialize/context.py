"""
序列化协议上下文

提供 contextvars.ContextVar 机制，让 __getstate__ 方法感知当前序列化协议。
Serializer.dumps/loads 在调用后端前设置上下文，调用后重置。

注意：Python 3.6 使用兼容实现，不是 async-safe 的。
"""

from ..core.contextvars_compat import ContextVar
from ..core import dataclass
from typing import Optional, Any
__all__ = ['SerializeContext', 'get_context', 'get_protocol', 'set_context', 'reset_context', 'get_current_serializer']


@dataclass
class SerializeContext:
    """序列化上下文信息"""
    protocol: str          # 'pickle' | 'json' | 'msgpack'
    serializer: Optional[Any] = None  # Serializer 实例引用（用于 handler 回退）


# 使用 ContextVar 保证线程内上下文隔离
_ctx = ContextVar('vools_serialize_ctx', default=None)


def get_context() -> Optional[SerializeContext]:
    """获取当前序列化上下文"""
    return _ctx.get()


def get_protocol() -> Optional[str]:
    """获取当前序列化协议名称（'pickle', 'json', 'msgpack' 或 None）"""
    ctx = _ctx.get()
    return ctx.protocol if ctx else None


def set_context(protocol: str, serializer: Optional[Any] = None):
    """
    设置当前序列化上下文

    Args:
        protocol: 协议名称 ('pickle', 'json', 'msgpack')
        serializer: Serializer 实例引用

    Returns:
        contextvars.Token，用于后续 reset_context
    """
    return _ctx.set(SerializeContext(protocol=protocol, serializer=serializer))


def reset_context(token):
    """
    重置序列化上下文

    Args:
        token: set_context 返回的 Token
    """
    _ctx.reset(token)


def get_current_serializer() -> Optional[Any]:
    """获取当前的 Serializer 实例"""
    ctx = _ctx.get()
    return ctx.serializer if ctx else None