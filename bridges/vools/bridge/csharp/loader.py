"""
vools.bridge.csharp.loader - 预编译 C# 库加载器

加载 vools/lib/ 下的预编译 C# DLL。
"""

from ..core.loader import load_library

_CS_LIBS = {}


def get_cs_lib(name, setup_func=None):
    """
    获取 C# 共享库

    参数：
        name: 库名称（不含扩展名）
        setup_func: 可选的函数签名设置函数

    返回：
        ctypes.CDLL 实例，加载失败返回 None
    """
    if name in _CS_LIBS:
        return _CS_LIBS[name]

    lib = load_library('csharp', name, setup_func)
    _CS_LIBS[name] = lib
    return lib


def is_csharp_available():
    """
    检查 C# 桥接是否可用

    返回：
        bool: 是否有可用的 C# 库或编译器
    """
    from .compiler import csharp_compiler_available
    return csharp_compiler_available() or get_cs_lib('vools_csharp_demo') is not None