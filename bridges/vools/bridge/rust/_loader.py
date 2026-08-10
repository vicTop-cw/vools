"""
vools.bridge.rust._loader - Rust DLL 加载器

复用 bridge.core.loader 的 ctypes 基础设施。
"""

import os
import ctypes
from typing import Optional

from ..core.loader import SharedLibrary, load_from_path


def load_rust_dll(dll_path: str) -> Optional[SharedLibrary]:
    """
    加载 Rust 编译的 DLL

    参数：
        dll_path: DLL 文件路径

    返回：
        SharedLibrary 实例，加载失败返回 None
    """
    return load_from_path(dll_path)


def call_rust_function(
    dll: SharedLibrary,
    func_name: str,
    args: list,
    argtypes: list = None,
    restype: type = None
):
    """
    调用 Rust DLL 中的函数

    参数：
        dll: SharedLibrary 实例
        func_name: 函数名称
        args: 参数列表
        argtypes: 参数类型列表（可选）
        restype: 返回类型（可选）

    返回：
        函数返回值
    """
    return dll.call(func_name, *args, argtypes=argtypes, restype=restype)


def is_rust_dll_available(dll_path: str) -> bool:
    """
    检查 Rust DLL 是否可用

    参数：
        dll_path: DLL 文件路径

    返回：
        DLL 是否存在且可加载
    """
    if not os.path.exists(dll_path):
        return False

    try:
        dll = load_rust_dll(dll_path)
        return dll is not None
    except Exception:
        return False