"""
vools.bridge.julia.types - Python ↔ Julia ↔ ctypes 类型映射

提供 Julia 桥接的类型系统，包括：
- Python 类型到 Julia C ABI 类型映射
- Julia C ABI 类型到 ctypes 类型映射
- 参数类型推断函数
"""

import ctypes
from typing import Any, Optional, Union, List, Tuple

# =============================================================================
# Python 类型 → Julia C ABI 类型
# =============================================================================

# Python 类型 → Julia 端类型（用于直接 Julia 调用，非 ccall）
PY_TO_JULIA_TYPE = {
    int: 'Int64',
    float: 'Float64',
    bool: 'Bool',
    str: 'String',       # Julia 原生字符串类型
    bytes: 'Vector{UInt8}',
    bytearray: 'Vector{UInt8}',
    list: 'Vector{Any}',
    tuple: 'Tuple',
    type(None): 'Nothing',
}

# Julia 类型别名映射（处理字符串形式注解）
_JULIA_TYPE_ALIASES = {
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
    'str': 'String',
    'string': 'String',
    'bytes': 'Vector{UInt8}',
    'bytearray': 'Vector{UInt8}',
    'list': 'Vector{Any}',
    'tuple': 'Tuple',
    'array': 'Vector{Any}',
    'void': 'Nothing',
    'nothing': 'Nothing',
    'none': 'Nothing',
    'nonetype': 'Nothing',
    'ptr': 'Ptr{Cvoid}',
    'pointer': 'Ptr{Cvoid}',
    'cvoid': 'Ptr{Cvoid}',
}


def get_julia_type(py_type: Any) -> str:
    """
    根据 Python 类型获取 Julia 端 C ABI 类型字符串

    参数：
        py_type: Python 类型 / 类型注解（可为字符串形式）

    返回：
        Julia 端 C ABI 类型字符串，未知则返回 'Int64'
    """
    # None 处理
    if py_type is None or py_type is type(None):
        return 'Nothing'

    # 直接匹配
    if py_type in PY_TO_JULIA_TYPE:
        return PY_TO_JULIA_TYPE[py_type]

    # 字符串形式注解（来自 typing 或 forward reference）
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        # 处理泛型形式 list[int], Array{Float64,1} 等
        if normalized.startswith('list[') or normalized.startswith('array['):
            return 'Ptr{Cvoid}'
        if normalized in _JULIA_TYPE_ALIASES:
            return _JULIA_TYPE_ALIASES[normalized]
        # 处理带模块前缀的，例如 'builtins.int' -> 'int'
        short = normalized.split('.')[-1]
        if short in _JULIA_TYPE_ALIASES:
            return _JULIA_TYPE_ALIASES[short]
        # 处理 Julia 特殊类型
        if 'Cstring' in normalized or 'Cstring' in py_type:
            return 'Cstring'
        if 'Ptr{Cvoid}' in normalized or 'Ptr' in normalized:
            return 'Ptr{Cvoid}'
        return 'Int64'

    # typing.List 等
    if hasattr(py_type, '__origin__'):
        from typing import List, Tuple, Any
        if py_type.__origin__ is list or py_type.__origin__ is List:
            return 'Ptr{Cvoid}'
        if py_type.__origin__ is tuple or py_type.__origin__ is Tuple:
            return 'Ptr{Cvoid}'

    # 默认返回 Int64
    return 'Int64'


# =============================================================================
# Julia C ABI 类型 → ctypes 类型
# =============================================================================

# Julia C ABI 类型 → ctypes 类型映射
JULIA_TO_CTYPES = {
    'Int8': ctypes.c_int8,
    'Int16': ctypes.c_int16,
    'Int32': ctypes.c_int32,
    'Int64': ctypes.c_int64,
    'UInt8': ctypes.c_uint8,
    'UInt16': ctypes.c_uint16,
    'UInt32': ctypes.c_uint32,
    'UInt64': ctypes.c_uint64,
    'Float32': ctypes.c_float,
    'Float64': ctypes.c_double,
    'Bool': ctypes.c_bool,
    'Cstring': ctypes.c_char_p,
    'Ptr{Cvoid}': ctypes.c_void_p,
    'Ptr{Void}': ctypes.c_void_p,
    'Nothing': None,
    'Void': None,
}


def get_ctypes_type(julia_type: str):
    """
    根据 Julia 端 C ABI 类型获取 ctypes 类型

    参数：
        julia_type: Julia 端 C ABI 类型字符串

    返回：
        ctypes 类型；Nothing/Void 返回 None
    """
    return JULIA_TO_CTYPES.get(julia_type, ctypes.c_int64)


# =============================================================================
# 参数类型推断
# =============================================================================

def infer_julia_argtypes(args: List) -> List:
    """
    根据运行时值推断 Julia 端入参类型

    参数：
        args: Python 参数列表

    返回：
        Julia 类型字符串列表
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
            result.append('Cstring')
        elif isinstance(arg, (bytes, bytearray)):
            result.append('Ptr{Cvoid}')
        elif isinstance(arg, (list, tuple)):
            result.append('Ptr{Cvoid}')
        else:
            result.append('Ptr{Cvoid}')
    return result


def infer_ctypes_types(args: List) -> List:
    """
    根据运行时值推断 ctypes 入参类型

    参数：
        args: Python 参数列表

    返回：
        ctypes 类型列表
    """
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append(ctypes.c_bool)
        elif isinstance(arg, int):
            result.append(ctypes.c_int64)
        elif isinstance(arg, float):
            result.append(ctypes.c_double)
        elif isinstance(arg, str):
            result.append(ctypes.c_char_p)
        elif isinstance(arg, (bytes, bytearray)):
            result.append(ctypes.c_void_p)
        elif isinstance(arg, (list, tuple)):
            result.append(ctypes.c_void_p)
        else:
            result.append(ctypes.c_void_p)
    return result


def infer_ret_type(annotation: Any) -> Tuple:
    """
    从函数返回类型注解推断 Julia 和 ctypes 返回类型

    参数：
        annotation: 返回类型注解

    返回：
        (julia_type_str, ctypes_type)
    """
    if annotation is None or annotation is type(None):
        return ('Nothing', None)

    julia_type = get_julia_type(annotation)
    ctypes_type = get_ctypes_type(julia_type)
    return (julia_type, ctypes_type)


def convert_args(args: List, ctypes_types: List) -> List:
    """
    将 Python 参数转换为 ctypes 参数

    参数：
        args: 原始 Python 参数
        ctypes_types: ctypes 类型列表

    返回：
        转换后的 ctypes 参数列表
    """
    converted = []
    for value, ct_type in zip(args, ctypes_types):
        if ct_type == ctypes.c_char_p:
            if isinstance(value, str):
                converted.append(value.encode('utf-8'))
            elif isinstance(value, bytes):
                converted.append(value)
            else:
                converted.append(str(value).encode('utf-8'))
        elif ct_type == ctypes.c_bool:
            converted.append(bool(value))
        elif ct_type in (ctypes.c_int8, ctypes.c_int16, ctypes.c_int32, ctypes.c_int64):
            converted.append(int(value))
        elif ct_type in (ctypes.c_float, ctypes.c_double):
            converted.append(float(value))
        elif ct_type == ctypes.c_void_p:
            if isinstance(value, (list, tuple)):
                # 数组转换
                arr = value
                n = len(arr)
                if n == 0:
                    c_arr = (ctypes.c_int64 * 1)()
                    converted.append(ctypes.cast(c_arr, ctypes.c_void_p))
                else:
                    elem_ct = ctypes.c_int64
                    if arr and isinstance(arr[0], float):
                        elem_ct = ctypes.c_double
                    elif arr and isinstance(arr[0], bool):
                        elem_ct = ctypes.c_bool
                    c_arr = (elem_ct * n)(*arr)
                    converted.append(ctypes.cast(c_arr, ctypes.c_void_p))
            else:
                converted.append(value)
        else:
            converted.append(value)
    return converted


def is_array_type(julia_type: str) -> bool:
    """
    判断 Julia 端入参类型是否为数组（需要配长度参数）

    参数：
        julia_type: Julia 类型字符串

    返回：
        bool
    """
    return julia_type in ('Ptr{Cvoid}', 'Ptr{Void}', 'Ptr')


# =============================================================================
# 类型映射类（兼容旧 API）
# =============================================================================

class JuliaTypeMapper:
    """Julia 类型映射器"""

    @staticmethod
    def python_to_julia(py_type: Any) -> str:
        return get_julia_type(py_type)

    @staticmethod
    def julia_to_ctypes(julia_type: str):
        return get_ctypes_type(julia_type)

    @staticmethod
    def infer_argtypes(args: List) -> List:
        return infer_julia_argtypes(args)

    @staticmethod
    def infer_ctypes_types(args: List) -> List:
        return infer_ctypes_types(args)

    @staticmethod
    def infer_ret_type(annotation: Any) -> Tuple:
        return infer_ret_type(annotation)

    @staticmethod
    def convert_args(args: List, ctypes_types: List) -> List:
        return convert_args(args, ctypes_types)
