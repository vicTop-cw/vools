"""
COM 对象包装基类

提供基于 comtypes 的 COM 对象封装。
"""
from typing import Optional, Any, Dict
import os
import sys


class COMObject:
    """COM 对象包装基类"""

    _com_module = None  # comtypes 模块引用

    def __init__(self, obj: Any = None):
        """初始化 COM 对象

        Args:
            obj: COM 对象实例
        """
        self._obj = obj
        self._cache: Dict[str, Any] = {}

    @classmethod
    def _get_comtypes(cls):
        """延迟加载 comtypes"""
        if cls._com_module is None:
            try:
                import comtypes
                cls._com_module = comtypes
            except ImportError:
                raise ImportError(
                    "comtypes 未安装。请确保 Python 32 位环境中已安装 comtypes:\n"
                    "在 32 位 Python 环境中运行: pip install comtypes"
                )
        return cls._com_module

    @classmethod
    def create(cls, prog_id: str) -> 'COMObject':
        """通过 ProgID 创建 COM 对象

        Args:
            prog_id: COM 对象的 ProgID，例如 'RC6.cRC6'

        Returns:
            COMObject 实例
        """
        comtypes = cls._get_comtypes()
        try:
            obj = comtypes.client.CreateObject(prog_id)
            return cls(obj)
        except Exception as e:
            raise RuntimeError(f"无法创建 COM 对象 {prog_id}: {e}")

    @classmethod
    def get_active(cls, prog_id: str) -> Optional['COMObject']:
        """获取已运行的 COM 对象

        Args:
            prog_id: COM 对象的 ProgID

        Returns:
            COMObject 实例，如果对象未运行返回 None
        """
        comtypes = cls._get_comtypes()
        try:
            obj = comtypes.client.GetActiveObject(prog_id)
            return cls(obj) if obj else None
        except Exception:
            return None

    def __getattr__(self, name: str) -> Any:
        """代理属性访问到 COM 对象"""
        if name.startswith('_'):
            return super().__getattribute__(name)
        return getattr(self._obj, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """代理属性设置到 COM 对象"""
        if name.startswith('_') or name in ('_obj', '_cache'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._obj, name, value)

    def __repr__(self) -> str:
        """返回 COM 对象的表示"""
        if self._obj is None:
            return f"<{self.__class__.__name__}: None>"
        return f"<{self.__class__.__name__}: {repr(self._obj)}>"


def create_com_object(prog_id: str, *, cls: type = COMObject) -> COMObject:
    """创建 COM 对象的便捷函数

    Args:
        prog_id: COM 对象的 ProgID
        cls: COM 对象包装类

    Returns:
        COMObject 实例
    """
    return cls.create(prog_id)
