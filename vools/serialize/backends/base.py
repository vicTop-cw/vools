"""
序列化后端基类
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ...core.base import VoolsBase
__all__ = ['BaseBackend']


class BaseBackend(ABC, VoolsBase):
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
            hex_str: 十六进制字符串（str 或 bytes）

        Returns:
            反序列化后的对象

        Raises:
            TypeError: hex_str 不是 str/bytes 时（BUG-351：原先
                ``loads_hex(None)`` 抛裸 "TypeError: fromhex() argument must be str"）。
            ValueError: 含非十六进制字符（保留 bytes.fromhex 原生信息）。
        """
        if not isinstance(hex_str, (str, bytes, bytearray)):
            raise TypeError(
                f"{type(self).__name__}.loads_hex 的 hex_str 必须是 str 或 bytes，收到 "
                f"{type(hex_str).__name__}: {hex_str!r}")
        if isinstance(hex_str, (bytes, bytearray, memoryview)):
            # bytes.fromhex() 只接受 str，bytes 需先按 ASCII 解码
            try:
                hex_str = bytes(hex_str).decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"{type(self).__name__}.loads_hex 的 hex_str 必须是 ASCII 十六进制，"
                    f"解码失败：{exc}") from exc
        return self.loads(bytes.fromhex(hex_str))

    @staticmethod
    def _require_bytes(value: Any, where: str) -> bytes:
        """校验并归一化字节输入（BUG-351：后端对象直用时缺少顶层已有的校验）。"""
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                f"{where} 的 data 必须是 bytes/bytearray/memoryview，收到 "
                f"{type(value).__name__}: {value!r}")
        return bytes(value)


    def can_handle(self, obj: Any) -> bool:
        """
        检查此后端是否能处理给定对象

        Args:
            obj: 要检查的对象

        Returns:
            如果能处理返回 True
        """
        return True