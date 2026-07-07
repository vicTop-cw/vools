"""
预置 32 位 DLL 文件

提供内置 DLL 文件的路径管理和列表功能。
"""
import os
from typing import List

DLLS_DIR = os.path.dirname(os.path.abspath(__file__))

BUILTIN_DLLS = [
    'VB6Plus.dll',
    'VB6OpenSSL.dll',
    'VB6MQTT.dll',
    'DirectCOM.dll',
    'RC6.dll',
    'RC6Widgets.dll',
    'vbRichClient5.dll',
    'cairo_sqlite.dll',
    'WebView2Loader.dll',
]


def get_dll_path(dll_name: str) -> str:
    """获取内置 DLL 的完整路径

    Args:
        dll_name: DLL 文件名

    Returns:
        DLL 文件的绝对路径
    """
    return os.path.join(DLLS_DIR, dll_name)


def list_builtin_dlls() -> List[str]:
    """列出所有内置 DLL 文件

    Returns:
        DLL 文件名列表
    """
    return list(BUILTIN_DLLS)


def dll_exists(dll_name: str) -> bool:
    """检查内置 DLL 是否存在

    Args:
        dll_name: DLL 文件名

    Returns:
        True-存在, False-不存在
    """
    return os.path.exists(get_dll_path(dll_name))


__all__ = [
    'DLLS_DIR',
    'BUILTIN_DLLS',
    'get_dll_path',
    'list_builtin_dlls',
    'dll_exists',
]
