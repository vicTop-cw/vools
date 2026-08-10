"""vools.bridge.vbscript.types - Python ↔ VBScript 类型映射"""
import ctypes

PY_TO_VBS_TYPE = {
    int: 'Integer',
    float: 'Double',
    str: 'String',
    bool: 'Boolean',
    list: 'Variant()',
    dict: 'Dictionary',
    type(None): 'Variant',
}

VBS_TO_CTYPES = {
    'Integer': ctypes.c_int,
    'Long': ctypes.c_long,
    'Double': ctypes.c_double,
    'Single': ctypes.c_float,
    'Boolean': ctypes.c_bool,
    'String': ctypes.c_char_p,
    'Variant': ctypes.c_void_p,
}

def get_vbs_type(py_type):
    return PY_TO_VBS_TYPE.get(py_type, 'Variant')

def get_vbs_ctype(vbs_type):
    return VBS_TO_CTYPES.get(vbs_type, ctypes.c_void_p)
