"""
vools.bridge.julia._loader - Julia 共享库加载和函数调用

提供 Julia 编译的共享库的加载和调用功能。
"""

import os
import ctypes
import platform
from typing import Any, List, Optional, Tuple

# =============================================================================
# 平台判断
# =============================================================================

_IS_WINDOWS = platform.system() == 'Windows'


def _setup_dll_search_paths(paths: List[str]) -> None:
    """
    设置 Windows DLL 搜索路径

    参数：
        paths: DLL 搜索路径列表
    """
    if not _IS_WINDOWS:
        return

    add_dll_dir = getattr(os, 'add_dll_directory', None)
    if add_dll_dir:
        for p in paths:
            if os.path.exists(p):
                try:
                    add_dll_dir(p)
                except OSError:
                    pass


def load_julia_dll(so_path: str, dll_dirs: List[str] = None):
    """
    加载 Julia 编译的共享库

    Windows 上需要先把 dll 所在目录加入 dll search path，
    避免运行时找不到 Julia 运行时 dll。

    参数：
        so_path: 共享库绝对路径
        dll_dirs: 额外的 DLL 搜索路径列表

    返回：
        ctypes.CDLL 对象
    """
    if not os.path.exists(so_path):
        raise FileNotFoundError(f'Julia 共享库不存在: {so_path}')

    # Windows: 把 dll 所在目录加入 dll search path
    if _IS_WINDOWS:
        add_dll_dir = getattr(os, 'add_dll_directory', None)
        if add_dll_dir:
            dll_dir = os.path.dirname(os.path.abspath(so_path))
            try:
                add_dll_dir(dll_dir)
            except OSError:
                pass

            # 添加额外路径
            if dll_dirs:
                for extra_dir in dll_dirs:
                    if os.path.exists(extra_dir):
                        try:
                            add_dll_dir(extra_dir)
                        except OSError:
                            pass

    return ctypes.CDLL(so_path)


def call_julia_function(
    so_path: str,
    func_name: str,
    args: tuple,
    param_julia_types: List[str],
    ret_julia_type: str,
) -> Any:
    """
    调用 Julia 编译的函数

    参数：
        so_path: 共享库绝对路径
        func_name: 函数名
        args: 原始 Python 参数
        param_julia_types: 与 args 位置对应的 Julia 端入参类型列表
        ret_julia_type: Julia 端返回类型字符串

    返回：
        Python 端的解码结果
    """
    from .types import get_ctypes_type, is_array_type

    lib = load_julia_dll(so_path)
    func = getattr(lib, func_name)

    # 构造 ctypes argtypes：标量 + 数组（拆为 ptr + len）
    c_argtypes = []
    c_args = []

    for value, julia_t in zip(args, param_julia_types):
        if is_array_type(julia_t):
            # 数组：拆为 (ptr, len)
            arr = value if value is not None else []
            n = len(arr)
            if n == 0:
                c_arr = (ctypes.c_int64 * 1)()
                c_args.append(ctypes.cast(c_arr, ctypes.c_void_p))
            else:
                # 元素类型：int 默认走 c_longlong
                elem_ct = ctypes.c_int64
                if arr and isinstance(arr[0], float):
                    elem_ct = ctypes.c_double
                elif arr and isinstance(arr[0], bool):
                    elem_ct = ctypes.c_bool
                c_arr = (elem_ct * n)(*arr)
                c_args.append(ctypes.cast(c_arr, ctypes.c_void_p))
            c_argtypes.append(ctypes.c_void_p)
            c_args.append(ctypes.c_int64(n))
            c_argtypes.append(ctypes.c_int64)
        else:
            # 标量类型
            ct = get_ctypes_type(julia_t)
            if julia_t == 'Cstring':
                if isinstance(value, str):
                    c_value = value.encode('utf-8')
                elif isinstance(value, bytes):
                    c_value = value
                else:
                    c_value = str(value).encode('utf-8')
                c_args.append(c_value)
                c_argtypes.append(ctypes.c_char_p)
            elif julia_t == 'Bool':
                c_args.append(ctypes.c_bool(bool(value)))
                c_argtypes.append(ctypes.c_bool)
            elif julia_t in ('Float32',):
                c_args.append(ctypes.c_float(float(value)))
                c_argtypes.append(ctypes.c_float)
            elif julia_t in ('Float64', 'Float32'):
                c_args.append(ctypes.c_double(float(value)))
                c_argtypes.append(ctypes.c_double)
            elif julia_t in ('Int64', 'Int32', 'Int16', 'Int8'):
                c_args.append(ctypes.c_int64(int(value)))
                c_argtypes.append(ctypes.c_int64)
            elif julia_t in ('UInt64', 'UInt32', 'UInt16', 'UInt8'):
                c_args.append(ctypes.c_uint64(int(value)))
                c_argtypes.append(ctypes.c_uint64)
            else:
                c_args.append(ctypes.c_int64(int(value)))
                c_argtypes.append(ctypes.c_int64)

    func.argtypes = c_argtypes

    # 设置返回类型
    restype = get_ctypes_type(ret_julia_type)
    func.restype = restype

    # 调用
    raw = func(*c_args)

    # 解码返回值
    if restype is ctypes.c_char_p and raw is not None:
        if isinstance(raw, bytes):
            return raw.decode('utf-8')
        return raw
    if restype is ctypes.c_bool:
        return bool(raw)
    if restype is ctypes.c_double:
        return float(raw)
    if restype in (ctypes.c_int64, ctypes.c_int32):
        return int(raw)
    return raw


def is_julia_dll_available(func_name: str, so_path: str) -> bool:
    """
    检查 Julia 共享库中的函数是否可用

    参数：
        func_name: 函数名
        so_path: 共享库路径

    返回：
        bool
    """
    if not os.path.exists(so_path):
        return False
    try:
        lib = load_julia_dll(so_path)
        return hasattr(lib, func_name)
    except Exception:
        return False


__all__ = [
    'load_julia_dll',
    'call_julia_function',
    'is_julia_dll_available',
]
