"""
COM/CLR 包装库

提供基于 COM 和 .NET 的 DLL 封装。
"""
from .com import COMObject, create_com_object

# 导出 COM 相关
__all__ = ['COMObject', 'create_com_object']
