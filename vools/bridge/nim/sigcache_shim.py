"""
vools.bridge.nim.sigcache_shim - Nim 签名哈希库 Python 胶水层

使用 ctypes 加载编译好的 Nim 签名哈希共享库，提供高性能的签名哈希计算。
当库不可用时，使用纯 Python 回退实现。

主要功能：
    - hash_signature(data: str) -> str: 计算签名的 FNV-1a 哈希
    - hash_signature_int(data: str) -> int: 计算签名的整数哈希值
    - build_signature_str(func_name, params, ret_type) -> str: 构建签名字符串
"""

import ctypes
import sys
import os
from pathlib import Path
from typing import Optional, Tuple

__all__ = ['_lib', 'hash_signature', 'hash_signature_int', 'build_signature_str', 'is_available']

# 查找库路径 - sigcache DLL 不存在，保持查找不存在的路径以使用 Python 回退
_lib_base = Path(__file__).parent.parent.parent / "lib"
if sys.platform == "win32":
    _LIB_PATH = _lib_base / "windows" / "vools_sigcache.dll"
else:
    _LIB_PATH = _lib_base / "linux" / "libvools_sigcache.so"

# 尝试加载库
_lib = None

if _LIB_PATH.exists():
    try:
        _lib = ctypes.CDLL(str(_LIB_PATH))

        # 设置函数签名
        _lib.hash_signature.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.hash_signature.restype = ctypes.c_char_p

        _lib.hash_signature_int.argtypes = [ctypes.c_char_p, ctypes.c_int]
        _lib.hash_signature_int.restype = ctypes.c_uint64

        _lib.build_signature_str.argtypes = [
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int,
        ]
        _lib.build_signature_str.restype = ctypes.c_char_p

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to load Nim sigcache library from {_LIB_PATH}: {e}"
        )
        _lib = None
else:
    import logging
    logging.getLogger(__name__).debug(
        f"Nim sigcache library not found at {_LIB_PATH}, using Python fallback"
    )


def is_available() -> bool:
    """检查 Nim 签名哈希库是否可用"""
    return _lib is not None


# ====================================================================
# Python Fallback 实现
# ====================================================================

def _python_hash_signature(data: str) -> str:
    """纯 Python 实现的 FNV-1a 哈希（返回十六进制字符串）"""
    FNV_OFFSET = 0xcbf29ce484222325
    FNV_PRIME = 0x100000001b3

    hash_value = FNV_OFFSET
    for byte in data.encode('utf-8'):
        hash_value ^= byte
        hash_value = (hash_value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF

    # 转换为十六进制字符串
    return format(hash_value, '016x')


def _python_hash_signature_int(data: str) -> int:
    """纯 Python 实现的 FNV-1a 哈希（返回整数）"""
    FNV_OFFSET = 0xcbf29ce484222325
    FNV_PRIME = 0x100000001b3

    hash_value = FNV_OFFSET
    for byte in data.encode('utf-8'):
        hash_value ^= byte
        hash_value = (hash_value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF

    return hash_value


def _python_build_signature_str(func_name: str, params: str, ret_type: str) -> str:
    """纯 Python 实现：构建签名字符串"""
    return f"{func_name}({params}) -> {ret_type}"


# ====================================================================
# 公共 API
# ====================================================================

def hash_signature(data: str) -> str:
    """计算签名的 FNV-1a 哈希（返回十六进制字符串）

    Args:
        data: 签名字符串

    Returns:
        64 位哈希值的十六进制表示（16 个字符）

    用法:
        >>> from vools.bridge.nim.sigcache_shim import hash_signature
        >>> hash_signature("add(a: int, b: int) -> int")
        '7a8c3b2e1d4f6095'
    """
    if _lib is not None:
        data_bytes = data.encode('utf-8')
        result = _lib.hash_signature(data_bytes, len(data_bytes))
        return result.decode('utf-8')
    return _python_hash_signature(data)


def hash_signature_int(data: str) -> int:
    """计算签名的 FNV-1a 哈希（返回原始整数）

    Args:
        data: 签名字符串

    Returns:
        64 位哈希值（整数）

    用法:
        >>> from vools.bridge.nim.sigcache_shim import hash_signature_int
        >>> hash_signature_int("add(a: int, b: int) -> int")
        8970615437454269333
    """
    if _lib is not None:
        data_bytes = data.encode('utf-8')
        return _lib.hash_signature_int(data_bytes, len(data_bytes))
    return _python_hash_signature_int(data)


def build_signature_str(func_name: str, params: str, ret_type: str) -> str:
    """构建函数签名字符串

    Args:
        func_name: 函数名称
        params: 参数列表字符串（如 "a: int, b: int"）
        ret_type: 返回类型字符串（如 "int"）

    Returns:
        格式化的签名字符串：func_name(params) -> ret_type

    用法:
        >>> from vools.bridge.nim.sigcache_shim import build_signature_str
        >>> build_signature_str("add", "a: int, b: int", "int")
        'add(a: int, b: int) -> int'
    """
    if _lib is not None:
        fn_bytes = func_name.encode('utf-8')
        ps_bytes = params.encode('utf-8')
        rt_bytes = ret_type.encode('utf-8')
        result = _lib.build_signature_str(
            fn_bytes, len(fn_bytes),
            ps_bytes, len(ps_bytes),
            rt_bytes, len(rt_bytes),
        )
        return result.decode('utf-8')
    return _python_build_signature_str(func_name, params, ret_type)


# ====================================================================
# 便捷函数：直接从 inspect.Signature 生成哈希
# ====================================================================

def signature_hash_from_inspect(sig) -> str:
    """从 inspect.Signature 对象计算哈希

    Args:
        sig: inspect.Signature 对象

    Returns:
        签名的哈希值（十六进制字符串）

    用法:
        >>> import inspect
        >>> from vools.bridge.nim.sigcache_shim import signature_hash_from_inspect
        >>> sig = inspect.signature(lambda a: int)
        >>> signature_hash_from_inspect(sig)
        '...'
    """
    import inspect

    # 提取函数名
    func_name = getattr(sig, '__name__', 'unknown')

    # 提取参数信息
    params = []
    for pname, p in sig.parameters.items():
        pstr = pname
        if p.annotation != inspect.Parameter.empty:
            pstr += f": {p.annotation}"
        if p.default != inspect.Parameter.empty:
            pstr += f" = {p.default}"
        params.append(pstr)

    # 提取返回类型
    ret_type = 'None'
    if sig.return_annotation != inspect.Signature.empty:
        ret_type = str(sig.return_annotation)

    # 构建签名字符串并计算哈希
    sig_str = build_signature_str(func_name, ', '.join(params), ret_type)
    return hash_signature(sig_str)
