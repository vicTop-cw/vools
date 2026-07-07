"""
Base64 编解码基准测试套件

对比纯 Python base64 vs Nim 桥接库实现的性能
"""

import base64
from typing import Dict, List, Any

# 尝试导入 Nim 桥接库
_nim_base64_encode = None
_nim_base64_decode = None

try:
    from vools.bridge.nim.encoding import base64_encode, base64_decode
    _nim_base64_encode = base64_encode
    _nim_base64_decode = base64_decode
except ImportError:
    pass


def base64_encode_py(data: bytes) -> bytes:
    """纯 Python Base64 编码"""
    return base64.b64encode(data)


def base64_decode_py(data: bytes) -> bytes:
    """纯 Python Base64 解码"""
    return base64.b64decode(data)


def base64_encode_bridge(data: bytes) -> bytes:
    """桥接库 Base64 编码（Nim 实现）"""
    if _nim_base64_encode:
        return _nim_base64_encode(data)
    return base64_encode_py(data)


def base64_decode_bridge(data: bytes) -> bytes:
    """桥接库 Base64 解码（Nim 实现）"""
    if _nim_base64_decode:
        return _nim_base64_decode(data)
    return base64_decode_py(data)


def get_base64_suite() -> List[Dict[str, Any]]:
    """
    获取 Base64 编解码基准测试套件
    
    Returns:
        测试用例列表
    """
    # 不同大小的测试数据
    small_data = b"hello world" * 10
    medium_data = b"hello world" * 100
    large_data = b"hello world" * 1000
    
    # 预编码的数据用于解码测试
    small_encoded = base64.b64encode(small_data)
    medium_encoded = base64.b64encode(medium_data)
    large_encoded = base64.b64encode(large_data)
    
    return [
        {
            "name": "data.seq.base64_encode_small",
            "py_func": base64_encode_py,
            "bridge_func": base64_encode_bridge,
            "args": (small_data,),
            "expected_speedup": 3.0,
        },
        {
            "name": "data.seq.base64_encode_medium",
            "py_func": base64_encode_py,
            "bridge_func": base64_encode_bridge,
            "args": (medium_data,),
            "expected_speedup": 3.0,
        },
        {
            "name": "data.seq.base64_encode_large",
            "py_func": base64_encode_py,
            "bridge_func": base64_encode_bridge,
            "args": (large_data,),
            "expected_speedup": 3.0,
        },
        {
            "name": "data.seq.base64_decode_small",
            "py_func": base64_decode_py,
            "bridge_func": base64_decode_bridge,
            "args": (small_encoded,),
            "expected_speedup": 3.0,
        },
        {
            "name": "data.seq.base64_decode_medium",
            "py_func": base64_decode_py,
            "bridge_func": base64_decode_bridge,
            "args": (medium_encoded,),
            "expected_speedup": 3.0,
        },
        {
            "name": "data.seq.base64_decode_large",
            "py_func": base64_decode_py,
            "bridge_func": base64_decode_bridge,
            "args": (large_encoded,),
            "expected_speedup": 3.0,
        },
    ]
