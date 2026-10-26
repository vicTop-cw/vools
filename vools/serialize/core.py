"""
序列化核心模块
"""

from typing import Any, Optional

from .backends import get_backend, BaseBackend
from .config import get_default_backend
from ..core.base import VoolsBase
__all__ = ['Serializer', 'dumps', 'loads', 'dumps_hex', 'loads_hex']


class Serializer(VoolsBase):
    """
    序列化器核心类

    支持多种序列化后端，提供统一的序列化/反序列化接口。

    Example:
        >>> from vools.serialize import Serializer
        >>> s = Serializer(backend='pickle')
        >>> data = s.dumps({"key": "value"})
        >>> obj = s.loads(data)

        >>> # 使用十六进制字符串
        >>> hex_str = s.dumps_hex({"key": "value"})
        >>> obj = s.loads_hex(hex_str)
    """

    def __init__(self, backend: Optional[str] = None, **backend_kwargs):
        """
        初始化序列化器

        Args:
            backend: 后端名称，如 'pickle', 'json', 'msgpack'
                    如果为 None，则使用全局默认后端
            **backend_kwargs: 传递给后端的额外参数
        """
        if backend is None:
            backend = get_default_backend() or 'pickle'

        self._backend_name = backend
        backend_cls = get_backend(backend)
        self._backend: BaseBackend = backend_cls(**backend_kwargs)

    @property
    def backend_name(self) -> str:
        """获取当前后端名称"""
        return self._backend_name

    def dumps(self, obj: Any) -> bytes:
        """
        序列化对象为字节串

        在调用后端前设置协议上下文，使对象的 __getstate__
        能感知当前协议并自适应输出格式。

        Args:
            obj: 要序列化的对象

        Returns:
            序列化后的字节串
        """
        from .context import set_context, reset_context
        token = set_context(self._backend_name, self)
        try:
            return self._backend.dumps(obj)
        finally:
            reset_context(token)

    def loads(self, data: bytes) -> Any:
        """
        从字节串反序列化对象

        设置协议上下文，并兼容旧 __callable__ 包装格式。

        Args:
            data: 序列化的字节串

        Returns:
            反序列化后的对象
        """
        from .context import set_context, reset_context
        token = set_context(self._backend_name, self)
        try:
            result = self._backend.loads(data)

            # 向后兼容：旧 __callable__ 包装格式
            if isinstance(result, dict) and result.get('__callable__'):
                from .callable import deserialize_callable
                return deserialize_callable(result['handler'], result['state'], self)

            return result
        finally:
            reset_context(token)

    def dumps_hex(self, obj: Any) -> str:
        """
        序列化为十六进制字符串

        Args:
            obj: 要序列化的对象

        Returns:
            十六进制字符串
        """
        from .context import set_context, reset_context
        token = set_context(self._backend_name, self)
        try:
            return self._backend.dumps_hex(obj)
        finally:
            reset_context(token)

    def loads_hex(self, hex_str: str) -> Any:
        """
        从十六进制字符串反序列化

        Args:
            hex_str: 十六进制字符串

        Returns:
            反序列化后的对象
        """
        from .context import set_context, reset_context
        token = set_context(self._backend_name, self)
        try:
            result = self._backend.loads_hex(hex_str)

            # 向后兼容：旧 __callable__ 包装格式
            if isinstance(result, dict) and result.get('__callable__'):
                from .callable import deserialize_callable
                return deserialize_callable(result['handler'], result['state'], self)

            return result
        finally:
            reset_context(token)


    def __repr__(self) -> str:
        return f"Serializer(backend='{self._backend_name}')"


# 全局便捷函数
_default_serializer: Optional[Serializer] = None


def _get_serializer(backend: Optional[str] = None) -> Serializer:
    """获取序列化器实例"""
    global _default_serializer
    if backend is None:
        backend = get_default_backend() or 'pickle'
    if _default_serializer is None or _default_serializer.backend_name != backend:
        _default_serializer = Serializer(backend=backend)
    return _default_serializer


def dumps(obj: Any, backend: Optional[str] = None) -> bytes:
    """
    序列化对象为字节串

    Args:
        obj: 要序列化的对象
        backend: 后端名称，None 使用全局默认

    Returns:
        序列化后的字节串
    """
    return _get_serializer(backend).dumps(obj)


def loads(data: bytes, backend: Optional[str] = None) -> Any:
    """
    从字节串反序列化对象

    Args:
        data: 序列化的字节串
        backend: 后端名称，None 使用全局默认

    Returns:
        反序列化后的对象

    Raises:
        TypeError: ``data`` 不是 bytes / bytearray / memoryview 时（BUG-497：
            原实现把类型错误留给底层——``loads("str")`` 抛
            "a bytes-like object is required, not 'str'"、
            ``loads(None)`` 抛 ``'NoneType' object is not...``，都看不出是哪个参数）。

    安全提示（BUG-497 补文档）：
        **pickle 后端（默认）反序列化会执行任意代码**，只允许对可信来源的
        字节串调用；处理不可信输入请显式使用 ``backend="json"``。
    """
    # BUG-497: 入口校验 inputs 类型，避免把"参数传错"误读成"数据损坏"
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"loads 的 data 必须是 bytes/bytearray/memoryview，收到 "
            f"{type(data).__name__}: {data!r}")
    return _get_serializer(backend).loads(bytes(data))


def dumps_hex(obj: Any, backend: Optional[str] = None) -> str:
    """
    序列化为十六进制字符串

    Args:
        obj: 要序列化的对象
        backend: 后端名称，None 使用全局默认

    Returns:
        十六进制字符串
    """
    return _get_serializer(backend).dumps_hex(obj)


def loads_hex(hex_str: str, backend: Optional[str] = None) -> Any:
    """
    从十六进制字符串反序列化

    Args:
        hex_str: 十六进制字符串
        backend: 后端名称，None 使用全局默认

    Returns:
        反序列化后的对象

    Raises:
        TypeError: ``hex_str`` 不是 str/bytes 时（BUG-497：原实现直接把
            ``None`` 交给 ``bytes.fromhex``，报错看不出是哪个参数）。

    安全提示（BUG-497 补文档）：同 ``loads`` —— pickle 后端反序列化会执行任意代码，
    只用于可信数据。
    """
    # BUG-497: 入口类型校验 + 允许 bytes 十六进制串（bytes.fromhex 本就支持）
    if not isinstance(hex_str, (str, bytes, bytearray)):
        raise TypeError(
            f"loads_hex 的 hex_str 必须是 str 或 bytes，收到 "
            f"{type(hex_str).__name__}: {hex_str!r}")
    if isinstance(hex_str, (bytes, bytearray)):
        hex_str = bytes(hex_str).decode("ascii", "strict")
    return _get_serializer(backend).loads_hex(hex_str)