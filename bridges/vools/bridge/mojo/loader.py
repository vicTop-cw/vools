"""
vools.bridge.mojo.loader - 预编译 Mojo 共享库加载器

处理 Mojo 1.0b1 编译产物（Linux .so）的加载与函数签名初始化，
复用 vools.bridge.core.loader。
本次不实现具体业务模块（crypto/seq/...），仅提供加载基础设施。
"""

import ctypes
import os

from ..core.loader import load_library

_MOJO_LIBS = {}


def get_mojo_lib(name, setup_func=None):
    """
    获取 Mojo 预编译共享库

    参数：
        name: 库名（如 'vools_mojo_demo'，实际查找 lib<vools_mojo_demo>.so）
        setup_func: 可选的初始化函数（设置 argtypes/restype）

    返回：
        加载成功返回 CDLL 实例，失败返回 None
    """
    if name in _MOJO_LIBS:
        return _MOJO_LIBS[name]
    lib = load_library('mojo', name, setup_func)
    _MOJO_LIBS[name] = lib
    return lib


def is_mojo_available():
    """
    检查 Mojo 预编译库是否可用

    约定探测库名 `vools_mojo_demo`；若 vools/lib/mojo/ 下不存在则返回 False，
    调用方应回退到 Python 实现。
    """
    return get_mojo_lib('vools_mojo_demo') is not None
