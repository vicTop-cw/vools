"""
Pickle 序列化后端
"""

import pickle
from typing import Any

from .base import BaseBackend
__all__ = ['PickleBackend']


class PickleBackend(BaseBackend):
    """Pickle 序列化后端"""

    name = "pickle"

    def __init__(self, protocol: int = None):
        """
        初始化 Pickle 后端

        Args:
            protocol: pickle 协议版本，None 表示使用默认协议
        """
        self.protocol = protocol

    def dumps(self, obj: Any) -> bytes:
        """
        使用 pickle 序列化对象

        Args:
            obj: 要序列化的对象

        Returns:
            pickle 序列化的字节串
        """
        return pickle.dumps(obj, protocol=self.protocol)

    def loads(self, data: bytes) -> Any:
        """
        使用 pickle 反序列化对象

        Args:
            data: pickle 序列化的字节串

        Returns:
            反序列化后的对象
        """
        return pickle.loads(data)