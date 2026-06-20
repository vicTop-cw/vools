"""
序列化后端基类
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
__all__ = ['BaseBackend']


class BaseBackend(ABC):
    """序列化后端基类"""

    name: str = "base"

    @abstractmethod
    def dumps(self, obj: Any) -> bytes:
        """
        序列化对象为字节串

        Args:
            obj: 要序列化的对象

        Returns:
            序列化后的字节串
        """
        raise NotImplementedError

    @abstractmethod
    def loads(self, data: bytes) -> Any:
        """
        从字节串反序列化对象

        Args:
            data: 序列化的字节串

        Returns:
            反序列化后的对象
        """
        raise NotImplementedError

    def dumps_hex(self, obj: Any) -> str:
        """
        序列化为十六进制字符串

        Args:
            obj: 要序列化的对象

        Returns:
            十六进制字符串
        """
        return self.dumps(obj).hex()

    def loads_hex(self, hex_str: str) -> Any:
        """
        从十六进制字符串反序列化

        Args:
            hex_str: 十六进制字符串

        Returns:
            反序列化后的对象
        """
        return self.loads(bytes.fromhex(hex_str))


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

    def can_handle(self, obj: Any) -> bool:
        """
        检查此后端是否能处理给定对象

        Args:
            obj: 要检查的对象

        Returns:
            如果能处理返回 True
        """
        return True