"""
CLR (.NET) 包装基类

提供基于 pythonnet 的 .NET 互操作封装。
"""
import os
import sys
from typing import Optional, Any, Dict


class CLRAssembly:
    """CLR 程序集包装类"""

    _pythonnet_loaded = False
    _clr = None

    @classmethod
    def _ensure_pythonnet(cls):
        """确保 pythonnet 已加载"""
        if not cls._pythonnet_loaded:
            try:
                import clr
                cls._clr = clr
                cls._pythonnet_loaded = True
            except ImportError:
                raise ImportError(
                    "pythonnet 未安装。请确保 Python 32 位环境中已安装 pythonnet:\n"
                    "在 32 位 Python 环境中运行: pip install pythonnet"
                )
        return cls._clr

    @classmethod
    def load_assembly(cls, assembly_name: str) -> Any:
        """加载 .NET 程序集

        Args:
            assembly_name: 程序集名称或路径

        Returns:
            程序集对象
        """
        clr = cls._ensure_pythonnet()
        clr.AddReference(assembly_name)
        return clr

    @classmethod
    def get_type(cls, type_name: str, assembly: Optional[str] = None) -> type:
        """获取 .NET 类型

        Args:
            type_name: 类型全名 (例如 'System.String')
            assembly: 程序集名称

        Returns:
            .NET 类型
        """
        if assembly:
            cls.load_assembly(assembly)
        import System
        return getattr(System, type_name.split('.')[-1])


class DotNetObject:
    """.NET 对象包装基类"""

    def __init__(self, obj: Any):
        """初始化 .NET 对象

        Args:
            obj: .NET 对象实例
        """
        self._obj = obj

    def __getattr__(self, name: str) -> Any:
        """代理属性访问到 .NET 对象"""
        if name.startswith('_'):
            return super().__getattribute__(name)
        return getattr(self._obj, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """代理属性设置到 .NET 对象"""
        if name.startswith('_') or name == '_obj':
            object.__setattr__(self, name, value)
        else:
            setattr(self._obj, name, value)

    def __repr__(self) -> str:
        """返回 .NET 对象的表示"""
        return f"<DotNetObject: {repr(self._obj)}>"
