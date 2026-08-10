"""
vools.bridge.nim.compress_shim - 压缩/解压 Nim 桥接 Python shim

提供独立的 gzip/zlib 压缩函数，通过 ctypes 加载编译好的 Nim DLL/SO。
如果 Nim 库不可用，回退到纯 Python 实现。
"""

import sys
import ctypes
from pathlib import Path

# 基础 Python fallback 实现
import gzip as _py_gzip
import zlib as _py_zlib


def _load_lib():
    """加载 Nim compress 共享库"""
    lib_dir = Path(__file__).parent.parent.parent / "lib"
    if sys.platform == "win32":
        lib_path = lib_dir / "vools_bridge_compress.dll"
    else:
        lib_path = lib_dir / "linux" / "libvools_bridge_compress.so"

    if not lib_path.exists():
        return None

    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.gzip_compress.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.gzip_compress.restype = ctypes.c_char_p
        lib.gzip_decompress.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.gzip_decompress.restype = ctypes.c_char_p
        lib.zlib_compress.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.zlib_compress.restype = ctypes.c_char_p
        lib.zlib_decompress.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.zlib_decompress.restype = ctypes.c_char_p
        return lib
    except Exception:
        return None


_lib = _load_lib()


def gzip_compress(data: bytes, level: int = 9) -> bytes:
    """
    gzip 压缩

    Args:
        data: 要压缩的字节数据
        level: 压缩级别 0-9，默认为 9

    Returns:
        gzip 压缩后的字节数据
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, str):
            data = data.encode('utf-8')
        return _py_gzip.compress(data, compresslevel=level)

    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _lib.gzip_compress(data, len(data), level)
    return bytes(result)


def gzip_decompress(data: bytes) -> bytes:
    """
    gzip 解压

    Args:
        data: gzip 压缩的字节数据

    Returns:
        解压后的字节数据
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, str):
            data = data.encode('latin-1')
        return _py_gzip.decompress(data)

    if isinstance(data, str):
        data = data.encode('latin-1')
    result = _lib.gzip_decompress(data, len(data))
    return bytes(result)


def zlib_compress(data: bytes, level: int = 9) -> bytes:
    """
    zlib 压缩

    Args:
        data: 要压缩的字节数据
        level: 压缩级别 0-9，默认为 9

    Returns:
        zlib 压缩后的字节数据
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, str):
            data = data.encode('utf-8')
        return _py_zlib.compress(data, level=level)

    if isinstance(data, str):
        data = data.encode('utf-8')
    result = _lib.zlib_compress(data, len(data), level)
    return bytes(result)


def zlib_decompress(data: bytes) -> bytes:
    """
    zlib 解压

    Args:
        data: zlib 压缩的字节数据

    Returns:
        解压后的字节数据
    """
    if _lib is None:
        # Fallback to Python
        if isinstance(data, str):
            data = data.encode('latin-1')
        return _py_zlib.decompress(data)

    if isinstance(data, str):
        data = data.encode('latin-1')
    result = _lib.zlib_decompress(data, len(data))
    return bytes(result)


def is_nim_compress_available() -> bool:
    """检查 Nim compress 库是否可用"""
    return _lib is not None
