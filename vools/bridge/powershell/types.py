"""vools.bridge.powershell.types - Python ↔ PowerShell 类型映射"""
import ctypes

PY_TO_PS_TYPE = {
    int: 'int',
    float: 'double',
    str: 'string',
    bool: 'bool',
    list: 'object[]',
    dict: 'hashtable',
    type(None): 'void',
}

PS_TO_CTYPES = {
    'int': ctypes.c_int,
    'long': ctypes.c_long,
    'double': ctypes.c_double,
    'float': ctypes.c_float,
    'bool': ctypes.c_bool,
    'string': ctypes.c_char_p,
    'void': None,
}

def get_ps_type(py_type):
    return PY_TO_PS_TYPE.get(py_type, 'string')

def get_ps_ctype(ps_type):
    return PS_TO_CTYPES.get(ps_type, ctypes.c_void_p)
