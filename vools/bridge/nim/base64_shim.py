"""
vools.bridge.nim.base64_shim - Base64 Nim 桥接 Python shim

提供独立的 Base64 编解码函数，通过 ctypes 加载编译好的 Nim DLL/SO。
如果 Nim 库不可用，回退到纯 Python 实现。
"""

import sys
import ctypes
from pathlib import Path

# 基础 Python fallback 实现
import base64 as _py_base64


def _load_lib():
    """加载 Nim Base64 共享库"""
    lib_base = Path(__file__).parent.parent.parent / "lib"
    if sys.platform == "win32":
        lib_path = lib_base / "windows" / "vools_encoding.dll"
    else:
        lib_path = lib_base / "linux" / "libvools_encoding.so"

    if not lib_path.exists():
        return None

    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.base64_encode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.base64_encode.restype = ctypes.c_char_p
        lib.base64_decode.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.base64_decode.restype = ctypes.c_char_p
        return lib
    except Exception:
        return None


_lib = _load_lib()


def base64_encode(data: bytes) -> str:
    """
    Base64 编码

    Args:
        data: 要编码的字节数据

    Returns:
        Base64 编码后的字符串（不带 padding）
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, str):
            data = data.encode('utf-8')
        encoded = _py_base64.b64encode(data)
        # Remove trailing padding '='
        return encoded.rstrip(b'=').decode('ascii')

    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _lib.base64_encode(data, len(data))
    return result.decode('utf-8')


def base64_decode(data: str) -> bytes:
    """
    Base64 解码

    Args:
        data: Base64 编码的字符串（不带 padding）

    Returns:
        解码后的字节数据
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, bytes):
            data = data.decode('ascii')
        # Add padding if necessary
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += '=' * padding
        return _py_base64.b64decode(data)

    if isinstance(data, str):
        data = data.encode('ascii')
    result = _lib.base64_decode(data, len(data))
    return result


def is_nim_base64_available() -> bool:
    """检查 Nim Base64 库是否可用"""
    return _lib is not None
