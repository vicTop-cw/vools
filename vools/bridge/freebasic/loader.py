"""
vools.bridge.freebasic.loader - 预编译 FreeBASIC 库加载器

处理 FreeBASIC 共享库的加载与函数签名初始化，复用 vools.bridge.core.loader。
本次不实现具体业务模块（crypto/seq/...），仅提供加载基础设施。
"""

import ctypes
from vools.bridge.core.loader import load_library

_FBC_LIBS = {}


def get_fbc_lib(name, setup_func=None):
    """
    获取 FreeBASIC 预编译共享库

    参数：
        name: 库名（如 'vools_fbc_demo'）
        setup_func: 可选的初始化函数（设置 argtypes/restype）

    返回：
        加载成功返回 CDLL 实例，失败返回 None
    """
    if name in _FBC_LIBS:
        return _FBC_LIBS[name]
    lib = load_library('fbc', name, setup_func)
    _FBC_LIBS[name] = lib
    return lib


def is_fbc_available():
    """
    检查 FreeBASIC 预编译库是否可用

    约定探测库名 `vools_fbc_demo`；若 vools/lib/ 下不存在则返回 False，
    调用方应回退到 Python 实现。
    """
    return get_fbc_lib('vools_fbc_demo') is not None
