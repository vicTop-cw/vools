"""vools.bridge.shell.types - Python ↔ Shell 类型映射"""
import ctypes

PY_TO_SHELL_TYPE = {
    int: 'int',
    float: 'float',
    str: 'string',
    bool: 'bool',
    list: 'array',
    dict: 'assoc_array',
    type(None): 'void',
}

SHELL_TO_CTYPES = {
    'int': ctypes.c_int,
    'float': ctypes.c_double,
    'string': ctypes.c_char_p,
    'bool': ctypes.c_bool,
    'void': None,
}

def get_shell_type(py_type):
    return PY_TO_SHELL_TYPE.get(py_type, 'string')

def get_shell_ctype(shell_type):
    return SHELL_TO_CTYPES.get(shell_type, ctypes.c_void_p)
