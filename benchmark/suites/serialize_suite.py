"""
序列化基准测试套件

对比纯 Python pickle vs Nim 桥接库实现的性能
"""

import pickle
from typing import Dict, List, Any, Callable

# 导入 vools 序列化函数
from vools.serialize.codec import pickle_encode, pickle_decode


def pickle_encode_py(obj: Any) -> bytes:
    """纯 Python pickle 编码（不经过 Nim 桥接）"""
    return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)


def pickle_decode_py(data: bytes) -> Any:
    """纯 Python pickle 解码（不经过 Nim 桥接）"""
    return pickle.loads(data)


# pickle_encode 和 pickle_decode 已经由 vools.serialize.codec 提供
# 它们内部会使用 Nim 桥接（如果可用）


def get_serialize_suite() -> List[Dict[str, Any]]:
    """
    获取序列化基准测试套件
    
    Returns:
        测试用例列表，每项包含:
        - name: 测试名称
        - py_func: 纯 Python 实现
        - bridge_func: 桥接库实现（暂时为 None，后续填入）
        - args: 传递给函数的参数
        - expected_speedup: 期望的速度提升倍数
    """
    # 测试数据
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
    
    return [
        {
            "name": "serialize.pickle_encode_small",
            "py_func": pickle_encode_py,
            "bridge_func": pickle_encode,
            "args": (small_obj,),
            "expected_speedup": 5.0,
        },
        {
            "name": "serialize.pickle_decode_small",
            "py_func": pickle_decode_py,
            "bridge_func": pickle_decode,
            "args": (pickle.dumps(small_obj),),
            "expected_speedup": 5.0,
        },
        {
            "name": "serialize.pickle_encode_medium",
            "py_func": pickle_encode_py,
            "bridge_func": pickle_encode,
            "args": (medium_obj,),
            "expected_speedup": 5.0,
        },
        {
            "name": "serialize.pickle_decode_medium",
            "py_func": pickle_decode_py,
            "bridge_func": pickle_decode,
            "args": (pickle.dumps(medium_obj),),
            "expected_speedup": 5.0,
        },
        {
            "name": "serialize.pickle_encode_large",
            "py_func": pickle_encode_py,
            "bridge_func": pickle_encode,
            "args": (large_obj,),
            "expected_speedup": 5.0,
        },
        {
            "name": "serialize.pickle_decode_large",
            "py_func": pickle_decode_py,
            "bridge_func": pickle_decode,
            "args": (pickle.dumps(large_obj),),
            "expected_speedup": 5.0,
        },
    ]
