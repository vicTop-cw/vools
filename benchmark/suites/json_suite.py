"""
JSON 编解码基准测试套件

对比纯 Python json vs Nim/Rust 桥接库实现的性能
"""

import json
from typing import Dict, List, Any

# 尝试导入 Nim JSON 桥接
_nim_json_encode = None
_nim_json_decode = None

try:
    from vools.bridge.nim import nim_json_encode, nim_json_decode
    if callable(nim_json_encode):
        _nim_json_encode = nim_json_encode
    if callable(nim_json_decode):
        _nim_json_decode = nim_json_decode
except ImportError:
    pass

# 尝试导入 orjson 作为高性能备选
_has_orjson = False
try:
    import orjson
    _has_orjson = True
except ImportError:
    pass


def json_encode_py(obj: Any) -> bytes:
    """纯 Python JSON 编码"""
    return json.dumps(obj).encode('utf-8')


def json_decode_py(data: bytes) -> Any:
    """纯 Python JSON 解码"""
    return json.loads(data.decode('utf-8'))


def json_encode_orjson(obj: Any) -> bytes:
    """orjson JSON 编码"""
    return orjson.dumps(obj)


def json_decode_orjson(data: bytes) -> Any:
    """orjson JSON 解码"""
    return orjson.loads(data)


def json_encode_bridge(obj: Any) -> bytes:
    """桥接库 JSON 编码（Nim 实现）"""
    if _nim_json_encode:
        result = _nim_json_encode(obj)
        if result is not None:
            return result
    # 回退到 orjson
    if _has_orjson:
        return json_encode_orjson(obj)
    return json_encode_py(obj)


def json_decode_bridge(data: bytes) -> Any:
    """桥接库 JSON 解码（Nim 实现）"""
    if _nim_json_decode:
        result = _nim_json_decode(data)
        if result is not None:
            return json_decode_py(result)
    # 回退到 orjson
    if _has_orjson:
        return json_decode_orjson(data)
    return json_decode_py(data)


def get_json_suite() -> List[Dict[str, Any]]:
    """
    获取 JSON 编解码基准测试套件
    
    Returns:
        测试用例列表
    """
    # 不同复杂度的测试数据
    small_obj = {"key": "value", "num": 123, "list": [1, 2, 3]}
    medium_obj = {
        "users": [
            {"id": i, "name": f"user_{i}", "email": f"user_{i}@example.com"}
            for i in range(50)
        ],
        "metadata": {"version": "1.0", "count": 50}
    }
    large_obj = {
        "data": [
            {
                "id": i,
                "name": f"item_{i}",
                "description": "Lorem ipsum dolor sit amet" * 10,
                "tags": ["tag1", "tag2", "tag3"],
                "values": list(range(100))
            }
            for i in range(200)
        ]
    }
    
    # 预编码的 JSON 用于解码测试
    small_json = json.dumps(small_obj).encode('utf-8')
    medium_json = json.dumps(medium_obj).encode('utf-8')
    large_json = json.dumps(large_obj).encode('utf-8')
    
    return [
        {
            "name": "serialize.json_encode_small",
            "py_func": json_encode_py,
            "bridge_func": json_encode_bridge,
            "args": (small_obj,),
            "expected_speedup": 2.0,
        },
        {
            "name": "serialize.json_decode_small",
            "py_func": json_decode_py,
            "bridge_func": json_decode_bridge,
            "args": (small_json,),
            "expected_speedup": 2.0,
        },
        {
            "name": "serialize.json_encode_medium",
            "py_func": json_encode_py,
            "bridge_func": json_encode_bridge,
            "args": (medium_obj,),
            "expected_speedup": 2.0,
        },
        {
            "name": "serialize.json_decode_medium",
            "py_func": json_decode_py,
            "bridge_func": json_decode_bridge,
            "args": (medium_json,),
            "expected_speedup": 2.0,
        },
        {
            "name": "serialize.json_encode_large",
            "py_func": json_encode_py,
            "bridge_func": json_encode_bridge,
            "args": (large_obj,),
            "expected_speedup": 2.0,
        },
        {
            "name": "serialize.json_decode_large",
            "py_func": json_decode_py,
            "bridge_func": json_decode_bridge,
            "args": (large_json,),
            "expected_speedup": 2.0,
        },
    ]
