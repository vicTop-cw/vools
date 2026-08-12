"""
CLR (.NET) 子包

提供基于 pythonnet 的 .NET 互操作支持。
"""
from ._base import CLRAssembly, DotNetObject

__all__ = ['CLRAssembly', 'DotNetObject']
