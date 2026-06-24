"""
vools.bridge.csharp.types - Python ↔ C# ↔ ctypes 类型映射

提供三层类型映射：
1. Python → C# 类型（用于生成 C# 代码）
2. C# → ctypes 类型（用于 DLL 调用）
3. Python → ctypes 类型（复用 core.types）
"""

import ctypes

# Python → C# 类型映射（用于生成 C# 函数签名）
PY_TO_CS_TYPE = {
    int: 'int',              # 或 'long' 根据范围
    float: 'double',
    bool: 'bool',
    str: 'string',           # C# string -> 传参用 StringBuilder 或 char*
    bytes: 'byte[]',
    list: 'int[]',           # 默认 int[]，可指定泛型
    dict: 'object',          # 复杂类型用 object
    type(None): 'void',
}

# C# → ctypes 类型映射（用于设置 DLL 函数签名）
CS_TO_CTYPES = {
    'int': ctypes.c_int,
    'long': ctypes.c_long,
    'double': ctypes.c_double,
    'float': ctypes.c_float,
    'bool': ctypes.c_bool,
    'byte': ctypes.c_uint8,
    'sbyte': ctypes.c_int8,
    'short': ctypes.c_int16,
    'ushort': ctypes.c_uint16,
    'char': ctypes.c_char,           # 单字符
    'string': ctypes.c_char_p,       # 字符串指针（需要特殊处理）
    'byte[]': ctypes.c_char_p,       # 字节数组指针
    'int[]': ctypes.POINTER(ctypes.c_int),
    'double[]': ctypes.POINTER(ctypes.c_double),
    'void': None,
    'void*': ctypes.c_void_p,
    'IntPtr': ctypes.c_void_p,
}


def get_cs_type(py_type, value=None):
    """
    根据 Python 类型获取 C# 类型名称

    参数：
        py_type: Python 类型或类型注解字符串
        value: 可选的参数值，用于推断更精确的类型

    返回：
        C# 类型名称字符串
    """
    if py_type is None or py_type is type(None):
        return 'void'

    if isinstance(py_type, str):
        # 处理字符串类型注解
        type_aliases = {
            'int': 'int',
            'float': 'double',
            'bool': 'bool',
            'str': 'string',
            'bytes': 'byte[]',
            'list': 'int[]',
            'None': 'void',
        }
        return type_aliases.get(py_type.lower(), 'int')

    if py_type in PY_TO_CS_TYPE:
        # 根据值范围推断更精确的类型
        if py_type is int and value is not None:
            if -2**31 <= value < 2**31:
                return 'int'
            else:
                return 'long'
        return PY_TO_CS_TYPE[py_type]

    return 'int'  # 默认


def get_cs_ctype(cs_type):
    """
    根据 C# 类型获取 ctypes 类型

    参数：
        cs_type: C# 类型名称字符串

    返回：
        ctypes 类型
    """
    return CS_TO_CTYPES.get(cs_type, ctypes.c_void_p)


def infer_cs_argtypes(args):
    """
    根据参数值推断 C# 参数类型列表

    参数：
        args: 参数值列表

    返回：
        (cs_types, ctypes_types) 元组
    """
    cs_types = []
    ctypes_types = []
    for arg in args:
        py_type = type(arg)
        cs_type = get_cs_type(py_type, arg)
        cs_types.append(cs_type)
        ctypes_types.append(get_cs_ctype(cs_type))
    return cs_types, ctypes_types