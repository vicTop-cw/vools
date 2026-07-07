"""
压缩/解压基准测试套件

对比纯 Python gzip/zlib vs Nim 桥接库实现的性能
"""

import gzip
import zlib
from typing import Dict, List, Any

# 尝试导入 Nim 桥接库
_nim_gzip_compress = None
_nim_gzip_decompress = None
_nim_zlib_compress = None
_nim_zlib_decompress = None

try:
    from vools.bridge.nim.compress_shim import (
        gzip_compress as _shim_gzip_compress,
        gzip_decompress as _shim_gzip_decompress,
        zlib_compress as _shim_zlib_compress,
        zlib_decompress as _shim_zlib_decompress,
    )
    _nim_gzip_compress = _shim_gzip_compress
    _nim_gzip_decompress = _shim_gzip_decompress
    _nim_zlib_compress = _shim_zlib_compress
    _nim_zlib_decompress = _shim_zlib_decompress
except ImportError:
    pass


def gzip_compress_py(data: bytes, level: int = 9) -> bytes:
    """纯 Python gzip 压缩"""
    return gzip.compress(data, compresslevel=level)


def gzip_decompress_py(data: bytes) -> bytes:
    """纯 Python gzip 解压"""
    return gzip.decompress(data)


def zlib_compress_py(data: bytes, level: int = 9) -> bytes:
    """纯 Python zlib 压缩"""
    return zlib.compress(data, level=level)


def zlib_decompress_py(data: bytes) -> bytes:
    """纯 Python zlib 解压"""
    return zlib.decompress(data)


def gzip_compress_bridge(data: bytes, level: int = 9) -> bytes:
    """桥接库 gzip 压缩（Nim 实现）"""
    if _nim_gzip_compress:
        return _nim_gzip_compress(data, level)
    return gzip_compress_py(data, level)


def gzip_decompress_bridge(data: bytes) -> bytes:
    """桥接库 gzip 解压（Nim 实现）"""
    if _nim_gzip_decompress:
        return _nim_gzip_decompress(data)
    return gzip_decompress_py(data)


def zlib_compress_bridge(data: bytes, level: int = 9) -> bytes:
    """桥接库 zlib 压缩（Nim 实现）"""
    if _nim_zlib_compress:
        return _nim_zlib_compress(data, level)
    return zlib_compress_py(data, level)


def zlib_decompress_bridge(data: bytes) -> bytes:
    """桥接库 zlib 解压（Nim 实现）"""
    if _nim_zlib_decompress:
        return _nim_zlib_decompress(data)
    return zlib_decompress_py(data)


def get_compress_suite() -> List[Dict[str, Any]]:
    """
    获取压缩/解压基准测试套件
    
    Returns:
        测试用例列表
    """
    # 不同大小的测试数据
    small_data = b"hello world " * 100       # ~1.2KB
    medium_data = b"hello world " * 1000     # ~12KB
    large_data = b"hello world " * 10000     # ~120KB

    # 预压缩的数据用于解压测试
    small_gzip = gzip.compress(small_data)
    medium_gzip = gzip.compress(medium_data)
    large_gzip = gzip.compress(large_data)

    small_zlib = zlib.compress(small_data)
    medium_zlib = zlib.compress(medium_data)
    large_zlib = zlib.compress(large_data)

    return [
        # gzip 压缩测试
        {
            "name": "data.seq.gzip_compress_small",
            "py_func": gzip_compress_py,
            "bridge_func": gzip_compress_bridge,
            "args": (small_data,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.gzip_compress_medium",
            "py_func": gzip_compress_py,
            "bridge_func": gzip_compress_bridge,
            "args": (medium_data,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.gzip_compress_large",
            "py_func": gzip_compress_py,
            "bridge_func": gzip_compress_bridge,
            "args": (large_data,),
            "expected_speedup": 2.0,
        },
        # gzip 解压测试
        {
            "name": "data.seq.gzip_decompress_small",
            "py_func": gzip_decompress_py,
            "bridge_func": gzip_decompress_bridge,
            "args": (small_gzip,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.gzip_decompress_medium",
            "py_func": gzip_decompress_py,
            "bridge_func": gzip_decompress_bridge,
            "args": (medium_gzip,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.gzip_decompress_large",
            "py_func": gzip_decompress_py,
            "bridge_func": gzip_decompress_bridge,
            "args": (large_gzip,),
            "expected_speedup": 2.0,
        },
        # zlib 压缩测试
        {
            "name": "data.seq.zlib_compress_small",
            "py_func": zlib_compress_py,
            "bridge_func": zlib_compress_bridge,
            "args": (small_data,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.zlib_compress_medium",
            "py_func": zlib_compress_py,
            "bridge_func": zlib_compress_bridge,
            "args": (medium_data,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.zlib_compress_large",
            "py_func": zlib_compress_py,
            "bridge_func": zlib_compress_bridge,
            "args": (large_data,),
            "expected_speedup": 2.0,
        },
        # zlib 解压测试
        {
            "name": "data.seq.zlib_decompress_small",
            "py_func": zlib_decompress_py,
            "bridge_func": zlib_decompress_bridge,
            "args": (small_zlib,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.zlib_decompress_medium",
            "py_func": zlib_decompress_py,
            "bridge_func": zlib_decompress_bridge,
            "args": (medium_zlib,),
            "expected_speedup": 2.0,
        },
        {
            "name": "data.seq.zlib_decompress_large",
            "py_func": zlib_decompress_py,
            "bridge_func": zlib_decompress_bridge,
            "args": (large_zlib,),
            "expected_speedup": 2.0,
        },
    ]
