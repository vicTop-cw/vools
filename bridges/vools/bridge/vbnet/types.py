"""
vools.bridge.vbnet.types - Python ↔ VB.NET ↔ ctypes 类型映射

提供三层类型映射：
1. Python → VB.NET 类型（用于生成 VB.NET 代码）
2. VB.NET → ctypes 类型（用于 DLL 调用）
3. Python → ctypes 类型（复用 core.types）
"""

import ctypes

PY_TO_VB_TYPE = {
    int: 'Integer',
    float: 'Double',
    bool: 'Boolean',
    str: 'String',
    bytes: 'Byte()',
    list: 'Integer()',
    dict: 'Object',
    type(None): 'Void',
}

VB_TO_CTYPES = {
    'Integer': ctypes.c_int,
    'Long': ctypes.c_long,
    'Double': ctypes.c_double,
    'Single': ctypes.c_float,
    'Boolean': ctypes.c_bool,
    'Byte': ctypes.c_uint8,
    'SByte': ctypes.c_int8,
    'Short': ctypes.c_int16,
    'UShort': ctypes.c_uint16,
    'Char': ctypes.c_char,
    'String': ctypes.c_char_p,
    'Byte()': ctypes.c_char_p,
    'Integer()': ctypes.POINTER(ctypes.c_int),
    'Double()': ctypes.POINTER(ctypes.c_double),
    'Void': None,
    'Void*': ctypes.c_void_p,
    'IntPtr': ctypes.c_void_p,
}


def get_vb_type(py_type, value=None):
    """根据 Python 类型获取 VB.NET 类型名称

    Args:
        py_type: Python 类型或类型注解字符串
        value: 可选的参数值，用于推断更精确的类型

    Returns:
        VB.NET 类型名称字符串
    """
    if py_type is None or py_type is type(None):
        return 'Void'

    if isinstance(py_type, str):
        type_aliases = {
            'int': 'Integer',
            'float': 'Double',
            'bool': 'Boolean',
            'str': 'String',
            'bytes': 'Byte()',
            'list': 'Integer()',
            'None': 'Void',
        }
        return type_aliases.get(py_type.lower(), 'Integer')

    if py_type in PY_TO_VB_TYPE:
        if py_type is int and value is not None:
            if -2**31 <= value < 2**31:
                return 'Integer'
            else:
                return 'Long'
        return PY_TO_VB_TYPE[py_type]

    return 'Integer'


def get_vb_ctype(vb_type):
    """根据 VB.NET 类型获取 ctypes 类型

    Args:
        vb_type: VB.NET 类型名称字符串

    Returns:
        ctypes 类型
    """
    return VB_TO_CTYPES.get(vb_type, ctypes.c_void_p)


def infer_vb_argtypes(args):
    """根据参数值推断 VB.NET 参数类型列表

    Args:
        args: 参数值列表

    Returns:
        (vb_types, ctypes_types) 元组
    """
    vb_types = []
    ctypes_types = []
    for arg in args:
        py_type = type(arg)
        vb_type = get_vb_type(py_type, arg)
        vb_types.append(vb_type)
        ctypes_types.append(get_vb_ctype(vb_type))
    return vb_types, ctypes_types
