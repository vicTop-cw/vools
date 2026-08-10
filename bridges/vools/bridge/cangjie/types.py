"""
vools.bridge.cangjie.types - Python ↔ Cangjie 类型映射

提供 Python 类型与仓颉(Cangjie)类型之间的双向映射,以及 ctypes 端桥接表。

设计目标:免序列化(serialization-free)交互
- 通过 ctypes 直接调用 C ABI 兼容的仓颉函数
- 类型映射基于仓颉官方文档和 FFI 规范
"""

import ctypes


# ----------------------------------------------------------------------------
# Python 类型 → 仓颉类型
# ----------------------------------------------------------------------------

PY_TO_CJ_TYPE = {
    int: 'Int64',
    float: 'Float64',
    bool: 'Bool',
    str: 'String',
    bytes: 'Array<Byte>',
    list: 'Array<T>',
    dict: 'Map<K, V>',
    tuple: 'Tuple',
    type(None): 'Unit',
}


# 字符串别名到仓颉类型的回退(用于 typing 或 str 形式注解)
_TYPE_ALIASES = {
    'int': 'Int64',
    'int8': 'Int8',
    'int16': 'Int16',
    'int32': 'Int32',
    'int64': 'Int64',
    'uint': 'UInt64',
    'uint8': 'UInt8',
    'uint16': 'UInt16',
    'uint32': 'UInt32',
    'uint64': 'UInt64',
    'float': 'Float64',
    'float32': 'Float32',
    'float64': 'Float64',
    'double': 'Float64',
    'bool': 'Bool',
    'boolean': 'Bool',
    'str': 'String',
    'string': 'String',
    'bytes': 'Array<Byte>',
    'byte': 'Byte',
    'list': 'Array<T>',
    'array': 'Array<T>',
    'dict': 'Map<K, V>',
    'map': 'Map<K, V>',
    'tuple': 'Tuple',
    'none': 'Unit',
    'nonetype': 'Unit',
    'unit': 'Unit',
    'void': 'Unit',
}


def get_cj_type(py_type):
    """
    根据 Python 类型获取仓颉类型

    参数:
        py_type: Python 类型 / 类型注解(可为字符串形式)

    返回:
        仓颉类型字符串,未知则返回 'Int64'
    """
    # 处理 None 类型
    if py_type is None or py_type is type(None):
        return 'Unit'

    # 直接匹配
    if py_type in PY_TO_CJ_TYPE:
        return PY_TO_CJ_TYPE[py_type]

    # 字符串形式注解(来自 typing 或 forward reference)
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _TYPE_ALIASES:
            return _TYPE_ALIASES[normalized]
        # 处理带模块前缀的,例如 'builtins.int' -> 'int'
        short = normalized.split('.')[-1]
        if short in _TYPE_ALIASES:
            return _TYPE_ALIASES[short]
        # 未知字符串类型默认 Int64
        return 'Int64'

    # 其他未知类型
    return 'Int64'


def infer_cj_argtypes(args):
    """
    根据运行时值推断仓颉参数类型

    返回:
        仓颉类型字符串列表
    """
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('Bool')
        elif isinstance(arg, int):
            result.append('Int64')
        elif isinstance(arg, float):
            result.append('Float64')
        elif isinstance(arg, str):
            result.append('String')
        elif isinstance(arg, bytes):
            result.append('Array<Byte>')
        elif isinstance(arg, list):
            result.append('Array<T>')
        elif isinstance(arg, tuple):
            result.append('Tuple')
        elif isinstance(arg, dict):
            result.append('Map<K, V>')
        else:
            result.append('Int64')
    return result


def is_array_type(cj_type):
    """判断仓颉类型是否为数组"""
    return cj_type.startswith('Array<') or cj_type in ('Array<T>', 'Array<Byte>')


# ----------------------------------------------------------------------------
# 仓颉类型 → ctypes 类型(用于 ctypes 端 C ABI 边界)
# ----------------------------------------------------------------------------

CJ_TO_CTYPES = {
    'Int8': ctypes.c_int8,
    'Int16': ctypes.c_int16,
    'Int32': ctypes.c_int32,
    'Int64': ctypes.c_int64,
    'UInt8': ctypes.c_uint8,
    'UInt16': ctypes.c_uint16,
    'UInt32': ctypes.c_uint32,
    'UInt64': ctypes.c_uint64,
    'Byte': ctypes.c_uint8,
    'Float32': ctypes.c_float,
    'Float64': ctypes.c_double,
    'Bool': ctypes.c_bool,
    'String': ctypes.c_char_p,  # UTF-8 字符串指针
    'Array<Byte>': ctypes.POINTER(ctypes.c_uint8),
    'Array<T>': ctypes.c_void_p,
    'Unit': None,
}


def get_ctype_for(cj_type):
    """
    根据仓颉类型获取 ctypes 类型

    返回:
        ctypes 类型,'Unit' 返回 None
    """
    return CJ_TO_CTYPES.get(cj_type, ctypes.c_int64)


def resolve_cj_ret_type(annotation):
    """从函数返回类型注解解析仓颉类型"""
    if annotation is None or annotation is type(None):
        return 'Unit'
    if isinstance(annotation, type):
        return PY_TO_CJ_TYPE.get(annotation, 'Int64')
    if isinstance(annotation, str):
        return get_cj_type(annotation)
    return 'Int64'