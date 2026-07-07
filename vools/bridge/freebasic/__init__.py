"""
vools.bridge.freebasic - FreeBASIC 语言桥接模块

提供 FreeBASIC 动态编译与跨语言桥接能力，对齐 vools.bridge.nim 的 API 形态。

设计目标：免序列化（serialization-free）交互
- list 参数走 POINTER + 长度，不走 CSV/JSON
- 通过 transport 模块可注入 zero-copy 实现（如 zinc）

前置条件：
- 安装 FreeBASIC，并将 fbc64 加入 PATH
- 参考: https://www.freebasic.net/

使用示例：
    from vools.bridge.freebasic import fbc, compile_and_run, fbc_compiler_available

    if fbc_compiler_available():
        @fbc
        def fib(n: int) -> int:
            return '''
            If n <= 1 Then
                Return 1
            Else
                Return fib(n-1) + fib(n-2)
            End If
            '''

        print(fib(10))
"""

import os

from .types import (
    PY_TO_FB_TYPE,
    FB_TO_CTYPES,
    get_fb_type,
    infer_fb_argtypes,
    is_array_type,
    get_ctype_for,
)
from .transport import (
    Transport,
    CtypesTransport,
    ZincTransport,
    get_transport,
    set_transport,
)
from .loader import (
    FbLibraryLoader,
    get_fbc_lib,
    is_fbc_available,
    get_fb_lib,
    list_fb_libs,
    _get_lib_info as get_fb_lib_info,
    _get_global_fb_loader as get_global_fb_loader,
    _LIBS_BASE_DIR as LIBS_BASE_DIR,
    _load_manifest as _load_manifest,
)
from .sqlite3_shim import sqlite3_version, is_sqlite3_available, connect, _load_lib as _sqlite3_load_lib
from .compiler import (
    FbcBridge,
    _fbc_bridge,
    fbc,
    compile_and_run,
    compile_and_run_async,
    fbc_compiler_available,
    FbcFuture,
    _compile_fbc_code,
    _call_fbc_func,
    _generate_fbc_wrapper,
    _BAS_CACHE_DIR,
)

LIBS_DIR = os.path.join(os.path.dirname(__file__), 'libs')
MODULES_DIR = os.path.join(os.path.dirname(__file__), 'modules')

# SQLite3 模块（用于高级用户）
try:
    sqlite3_module = _sqlite3_load_lib()
except Exception:
    sqlite3_module = None

from .modules import (
    get_module as _get_fb_module,
    list_modules as _list_fb_modules,
    get_inc_paths as _get_fb_inc_paths,
    get_lib_paths as _get_fb_lib_paths,
)

# 暴露 .bas 模块加载 API
def get_fb_module(name: str) -> str:
    """
    读取一个 FreeBASIC 封装模块的源码内容（.bas 文件）。

    参数：
        name: 模块名（不含 .bas 后缀），如 'sqlite3_wrapper'、'cairo_wrapper'

    返回：
        模块源码字符串（可在 @fbc 装饰器的 module_code 参数中引用）
    """
    return _get_fb_module(name)


def list_fb_modules() -> list:
    """
    列出所有可用的 FreeBASIC 封装模块

    返回：
        模块名列表，如 ['sqlite3_wrapper', 'cairo_wrapper', 'sdl3_wrapper']
    """
    return _list_fb_modules()


def get_fb_inc_paths(name: str) -> list:
    """
    获取指定封装模块需要的头文件搜索路径（绝对路径列表）

    参数：
        name: 模块名

    返回：
        路径列表，可通过 compile_and_run(..., inc_paths=...) 传给 fbc
    """
    return _get_fb_inc_paths(name)


def get_fb_lib_paths(name: str) -> list:
    """
    获取指定封装模块需要的库搜索路径（DLL 所在目录的绝对路径列表）

    参数：
        name: 模块名

    返回：
        路径列表，可通过 compile_and_run(..., lib_paths=...) 传给 fbc
    """
    return _get_fb_lib_paths(name)

__all__ = [
    # 桥接类
    'FbcBridge',
    '_fbc_bridge',
    # 类型映射
    'PY_TO_FB_TYPE',
    'FB_TO_CTYPES',
    'get_fb_type',
    'infer_fb_argtypes',
    'is_array_type',
    'get_ctype_for',
    # Transport
    'Transport',
    'CtypesTransport',
    'ZincTransport',
    'get_transport',
    'set_transport',
    # 库加载
    'get_fbc_lib',
    'is_fbc_available',
    'get_fb_lib',
    'list_fb_libs',
    'FbLibraryLoader',
    'get_fb_lib_info',
    'get_global_fb_loader',
    'LIBS_BASE_DIR',
    # SQLite3 shim
    'sqlite3_version',
    'is_sqlite3_available',
    'connect',
    'sqlite3_module',
    # 路径常量
    'LIBS_DIR',
    'MODULES_DIR',
    # .bas 封装模块
    'get_fb_module',
    'list_fb_modules',
    'get_fb_inc_paths',
    'get_fb_lib_paths',
    # 编译器
    'fbc',
    'compile_and_run',
    'compile_and_run_async',
    'fbc_compiler_available',
    'FbcFuture',
    '_compile_fbc_code',
    '_call_fbc_func',
    '_generate_fbc_wrapper',
    '_BAS_CACHE_DIR',
]
