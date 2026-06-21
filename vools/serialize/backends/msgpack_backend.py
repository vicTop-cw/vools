"""
Msgpack 序列化后端
"""

from typing import Any

from .base import BaseBackend
__all__ = ['MsgpackBackend', 'is_available']

# 尝试导入 msgpack，如果不可用则后端不可用
try:
    import msgpack
    _HAS_MSGPACK = True
except ImportError:
    _HAS_MSGPACK = False


class MsgpackBackend(BaseBackend):
    """Msgpack 高效二进制序列化后端"""

    name = "msgpack"

    def __init__(self, raw: bool = False):
        """
        初始化 Msgpack 后端

        Args:
            raw: 如果为 True，则返回 bytes 而不是 str（仅旧版 msgpack 支持）
        """
        if not _HAS_MSGPACK:
            raise ImportError(
                "msgpack is not installed. "
                "Install it with: pip install msgpack"
            )
        self.raw = raw

    def dumps(self, obj: Any) -> bytes:
        """
        使用 msgpack 序列化对象

        使用 vools_preprocess 预处理对象树（处理内置子类），
        再使用 vools_default 回调处理非原生类型。

        Args:
            obj: 要序列化的对象

        Returns:
            msgpack 序列化的字节串
        """
        from ...serialize.codec import vools_preprocess, vools_default
        obj = vools_preprocess(obj)
        try:
            return msgpack.packb(obj, default=vools_default, raw=self.raw)
        except TypeError:
            # msgpack >= 1.0 移除了 raw 参数
            return msgpack.packb(obj, default=vools_default)


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def loads(self, data: bytes) -> Any:
        """
        使用 msgpack 反序列化对象

        使用 vools_object_hook 回调重建 vools 对象。

        Args:
            data: msgpack 序列化的字节串

        Returns:
            反序列化后的对象
        """
        from ...serialize.codec import vools_object_hook
        try:
            return msgpack.unpackb(data, object_hook=vools_object_hook, raw=self.raw)
        except TypeError:
            # msgpack >= 1.0 移除了 raw 参数和不支持 object_hook
            # 使用 post_process 模拟 object_hook
            result = msgpack.unpackb(data)
            from ...serialize.codec import post_process_msgpack
            return post_process_msgpack(result)


# 后端可用性检查函数
def is_available() -> bool:
    """检查 msgpack 后端是否可用"""
    return _HAS_MSGPACK