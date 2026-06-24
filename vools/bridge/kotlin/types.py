"""vools.bridge.kotlin.types - Python ↔ Kotlin 类型映射"""
import ctypes

PY_TO_KOTLIN_TYPE = {
    int: 'Int',
    float: 'Double',
    str: 'String',
    bool: 'Boolean',
    list: 'List<Int>',
    dict: 'Map<String, Any>',
    type(None): 'Unit',
}

KOTLIN_TO_CTYPES = {
    'Int': ctypes.c_int,
    'Long': ctypes.c_long,
    'Double': ctypes.c_double,
    'Float': ctypes.c_float,
    'Boolean': ctypes.c_bool,
    'String': ctypes.c_char_p,
    'Unit': None,
}

def get_kotlin_type(py_type):
    return PY_TO_KOTLIN_TYPE.get(py_type, 'String')

def get_kotlin_ctype(kotlin_type):
    return KOTLIN_TO_CTYPES.get(kotlin_type, ctypes.c_void_p)
