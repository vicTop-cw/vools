"""
vools.bridge.mojo.types - Python <-> Mojo 类型映射

提供 Python 类型与 Mojo C ABI 类型之间的双向映射，以及 ctypes 端桥接表。

设计目标：免序列化（serialization-free）交互。
- list[int] / list[float] 不再走 CSV/JSON 中转，而是直接拆为
  (UnsafePointer[Int64], Int64) / (UnsafePointer[Float64], Int64) 两个 Mojo 形参。
- str / bytes 走 UnsafePointer[c_char]（utf-8 c_char_p），不依赖 Mojo 原生 String。
- 数值在 cdecl 边界统一 Int64 / Float64，避免平台 long 长度差异。

运行环境：Mojo 1.0b1（WSL Linux 下的 Modular Mojo 工具链）。
"""

import ctypes


# ----------------------------------------------------------------------------
# Python 类型 -> Mojo 类型（cdecl 边界）
# ----------------------------------------------------------------------------

PY_TO_MOJO_TYPE = {
    int: 'Int64',
    float: 'Float64',
    bool: 'Bool',
    str: 'UnsafePointer[c_char]',
    bytes: 'UnsafePointer[c_char]',
    list: 'OpaquePointer',
    dict: 'OpaquePointer',
    tuple: 'OpaquePointer',
    type(None): 'None',
}


# 字符串别名到 Mojo 类型的回退（用于 typing 或 str 形式注解）
_TYPE_ALIASES = {
    'int': 'Int64',
    'i64': 'Int64',
    'long': 'Int64',
    'int64': 'Int64',
    'int32': 'Int32',
    'i32': 'Int32',
    'uint8': 'UInt8',
    'uint16': 'UInt16',
    'uint32': 'UInt32',
    'uint64': 'UInt64',
    'float': 'Float64',
    'f64': 'Float64',
    'double': 'Float64',
    'float32': 'Float32',
    'f32': 'Float32',
    'bool': 'Bool',
    'boolean': 'Bool',
    'str': 'UnsafePointer[c_char]',
    'string': 'UnsafePointer[c_char]',
    'bytes': 'UnsafePointer[c_char]',
    'byteptr': 'UnsafePointer[c_char]',
    'list': 'OpaquePointer',
    'list[int]': 'UnsafePointer[Int64]',
    'list[float]': 'UnsafePointer[Float64]',
    'list[i64]': 'UnsafePointer[Int64]',
    'list[f64]': 'UnsafePointer[Float64]',
    'list[double]': 'UnsafePointer[Float64]',
    'dict': 'OpaquePointer',
    'tuple': 'OpaquePointer',
    'none': 'None',
    'nonetype': 'None',
    'void': 'None',
    'opaquepointer': 'OpaquePointer',
    'void*': 'OpaquePointer',
}


def get_mojo_type(py_type):
    """
    根据 Python 类型获取 Mojo 类型

    参数：
        py_type: Python 类型 / 类型注解（可为字符串形式）

    返回：
        Mojo 类型字符串，未知则返回 'Int64'
    """
    # 处理 None 类型
    if py_type is None or py_type is type(None):
        return 'None'

    # 直接匹配
    if py_type in PY_TO_MOJO_TYPE:
        return PY_TO_MOJO_TYPE[py_type]

    # 字符串形式注解（来自 typing 或 forward reference）
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _TYPE_ALIASES:
            return _TYPE_ALIASES[normalized]
        # 处理带模块前缀的，例如 'builtins.int' -> 'int'
        short = normalized.split('.')[-1]
        if short in _TYPE_ALIASES:
            return _TYPE_ALIASES[short]
        # 未知字符串类型默认 Int64
        return 'Int64'

    # 泛型别名类型（如 list[int]、list[float]），转为字符串后匹配
    origin = getattr(py_type, '__origin__', None)
    if origin is not None and hasattr(py_type, '__args__'):
        normalized = str(py_type).lower()
        if normalized in _TYPE_ALIASES:
            return _TYPE_ALIASES[normalized]
        # 回退到 origin 名称
        origin_name = getattr(origin, '__name__', '')
        if origin_name in _TYPE_ALIASES:
            return _TYPE_ALIASES[origin_name]

    # 其他未知类型
    return 'Int64'


def infer_mojo_argtypes(args):
    """
    根据运行时值推断 Mojo 参数类型

    与 fbc.py 区别：list 不再用 OpaquePointer + CSV，而是按元素类型分类。
    - 元素全为 int（非 bool） -> 'UnsafePointer[Int64]'
    - 元素全为 float -> 'UnsafePointer[Float64]'
    - 其他 list -> 'OpaquePointer'

    返回：
        Mojo 类型字符串列表
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
            result.append('UnsafePointer[c_char]')
        elif isinstance(arg, bytes):
            result.append('UnsafePointer[c_char]')
        elif isinstance(arg, list):
            if arg and all(isinstance(x, int) and not isinstance(x, bool) for x in arg):
                result.append('UnsafePointer[Int64]')
            elif arg and all(isinstance(x, float) for x in arg):
                result.append('UnsafePointer[Float64]')
            elif arg and all(isinstance(x, bool) for x in arg):
                result.append('UnsafePointer[Bool]')
            elif not arg:
                # 空列表 → 默认 Int64 数组（最常见的场景）
                result.append('UnsafePointer[Int64]')
            else:
                result.append('OpaquePointer')
        elif isinstance(arg, tuple):
            result.append('OpaquePointer')
        elif isinstance(arg, dict):
            result.append('OpaquePointer')
        else:
            result.append('OpaquePointer')
    return result


def is_array_type(mojo_type):
    """
    判断 Mojo 类型是否为数组（POINTER 形式需要附加长度参数）

    当前支持的数组类型：UnsafePointer[Int64] / UnsafePointer[Float64]
    """
    return mojo_type in ('UnsafePointer[Int64]', 'UnsafePointer[Float64]')


def array_length_type(mojo_type):
    """
    对于数组类型，返回其追加的长度参数类型；非数组返回 None
    """
    if mojo_type in ('UnsafePointer[Int64]', 'UnsafePointer[Float64]'):
        return 'Int64'
    return None


# ----------------------------------------------------------------------------
# Mojo 类型 -> ctypes 类型（用于 ctypes 端 cdecl 边界）
# ----------------------------------------------------------------------------

MOJO_TO_CTYPES = {
    'Int64': ctypes.c_longlong,
    'Int32': ctypes.c_int32,
    'Int16': ctypes.c_int16,
    'Int8': ctypes.c_int8,
    'UInt64': ctypes.c_uint64,
    'UInt32': ctypes.c_uint32,
    'UInt16': ctypes.c_uint16,
    'UInt8': ctypes.c_uint8,
    'Float64': ctypes.c_double,
    'Float32': ctypes.c_float,
    'Bool': ctypes.c_int,            # Mojo Bool 在 cdecl 边界是 0/1 int
    'UnsafePointer[c_char]': ctypes.c_char_p,
    'UnsafePointer[Int8]': ctypes.POINTER(ctypes.c_int8),
    'UnsafePointer[UInt8]': ctypes.POINTER(ctypes.c_uint8),
    'UnsafePointer[Int16]': ctypes.POINTER(ctypes.c_int16),
    'UnsafePointer[Int32]': ctypes.POINTER(ctypes.c_int32),
    'UnsafePointer[Int64]': ctypes.POINTER(ctypes.c_longlong),
    'UnsafePointer[Float32]': ctypes.POINTER(ctypes.c_float),
    'UnsafePointer[Float64]': ctypes.POINTER(ctypes.c_double),
    'OpaquePointer': ctypes.c_void_p,
    'None': None,
}


def get_ctype_for(mojo_type):
    """
    根据 Mojo 类型获取 ctypes 类型

    返回：
        ctypes 类型，'None' 返回 None
    """
    return MOJO_TO_CTYPES.get(mojo_type, ctypes.c_longlong)
