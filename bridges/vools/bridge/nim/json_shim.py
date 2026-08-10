"""
vools.bridge.nim.json_shim - Nim JSON bridge shim

提供 json_encode 和 json_decode 函数的 Nim 实现。
当 Nim 库不可用时，回退到纯 Python 实现。
"""

import os
import sys
import ctypes
from pathlib import Path

# 库路径
_LIB_DIR = Path(__file__).parent.parent.parent / "lib"
if sys.platform == "win32":
    _LIB_PATH = _LIB_DIR / "windows" / "vools_datetime.dll"
else:
    _LIB_PATH = _LIB_DIR / "linux" / "libvools_datetime.so"


def _load_lib():
    """加载 Nim 共享库"""
    lib_path = _LIB_PATH if _LIB_PATH and _LIB_PATH.exists() else None
    
    if lib_path is None or not lib_path.exists():
        return None
    
    try:
        lib = ctypes.CDLL(str(lib_path))
        
        # 设置函数签名
        lib.json_encode.restype = ctypes.c_char_p
        lib.json_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.json_decode.restype = ctypes.c_char_p
        lib.json_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.json_encode_bytes.restype = ctypes.c_char_p
        lib.json_encode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.json_decode_bytes.restype = ctypes.c_char_p
        lib.json_decode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        return lib
    except Exception:
        return None


_lib = _load_lib()


def json_encode(data: bytes) -> bytes:
    """
    Nim 版 json_encode - JSON 编码
    
    Args:
        data: 要编码的数据（bytes 或 str）
        
    Returns:
        编码后的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.json_encode(data, len(data))
    if result:
        return result
    return None


def json_decode(data: bytes) -> bytes:
    """
    Nim 版 json_decode - JSON 解码
    
    Args:
        data: 编码的数据（bytes）
        
    Returns:
        解码后的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.json_decode(data, len(data))
    if result:
        return result
    return None


def json_encode_bytes(data: bytes) -> bytes:
    """
    Nim 版 json_encode_bytes - 直接透传编码
    
    Args:
        data: 要透传的数据
        
    Returns:
        透传的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.json_encode_bytes(data, len(data))
    if result:
        return result
    return None


def json_decode_bytes(data: bytes) -> bytes:
    """
    Nim 版 json_decode_bytes - 直接透传解码
    
    Args:
        data: 要透传解码的数据
        
    Returns:
        透传的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.json_decode_bytes(data, len(data))
    if result:
        return result
    return None


def is_available():
    """检查 Nim JSON 桥接是否可用"""
    return _lib is not None