"""
vools.bridge.nim.serialize_shim - Nim serialize bridge shim

提供 pickle_encode 和 pickle_decode 函数的 Nim 实现。
当 Nim 库不可用时，回退到纯 Python 实现。
"""

import os
import sys
import ctypes
from pathlib import Path

# 库路径
_LIB_DIR = Path(__file__).parent.parent.parent / "lib"
if sys.platform == "win32":
    _LIB_PATH = _LIB_DIR / "vools_bridge_serialize.dll"
    _LINUX_LIB_PATH = None
else:
    _LIB_PATH = None
    _LIB_DIR_LINUX = _LIB_DIR / "linux"
    _LIB_PATH = _LIB_DIR_LINUX / "libvools_bridge_serialize.so"


def _load_lib():
    """加载 Nim 共享库"""
    lib_path = _LIB_PATH if _LIB_PATH and _LIB_PATH.exists() else None
    
    if lib_path is None or not lib_path.exists():
        return None
    
    try:
        lib = ctypes.CDLL(str(lib_path))
        
        # 设置函数签名
        lib.pickle_encode.restype = ctypes.c_char_p
        lib.pickle_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.pickle_decode.restype = ctypes.c_char_p
        lib.pickle_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.msgpack_encode.restype = ctypes.c_char_p
        lib.msgpack_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.msgpack_decode.restype = ctypes.c_char_p
        lib.msgpack_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.pickle_encode_bytes.restype = ctypes.c_char_p
        lib.pickle_encode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        lib.pickle_decode_bytes.restype = ctypes.c_char_p
        lib.pickle_decode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int]
        
        return lib
    except Exception:
        return None


_lib = _load_lib()


def pickle_encode(data: bytes) -> bytes:
    """
    Nim 版 pickle_encode - 序列化数据
    
    Args:
        data: 要序列化的数据（bytes 或 str）
        
    Returns:
        序列化的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.pickle_encode(data, len(data))
    if result:
        return result
    return None


def pickle_decode(data: bytes) -> bytes:
    """
    Nim 版 pickle_decode - 反序列化数据
    
    Args:
        data: 序列化的数据（bytes）
        
    Returns:
        反序列化的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.pickle_decode(data, len(data))
    if result:
        return result
    return None


def msgpack_encode(data: bytes) -> bytes:
    """
    Nim 版 msgpack_encode - msgpack 风格序列化
    
    Args:
        data: 要序列化的数据
        
    Returns:
        序列化的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.msgpack_encode(data, len(data))
    if result:
        return result
    return None


def msgpack_decode(data: bytes) -> bytes:
    """
    Nim 版 msgpack_decode - msgpack 风格反序列化
    
    Args:
        data: 序列化的数据
        
    Returns:
        反序列化的 bytes，如果库不可用则返回 None
    """
    if _lib is None:
        return None
    
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    result = _lib.msgpack_decode(data, len(data))
    if result:
        return result
    return None


def is_available():
    """检查 Nim serialize 桥接是否可用"""
    return _lib is not None
