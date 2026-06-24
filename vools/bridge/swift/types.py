"""vools.bridge.swift.types - Python ↔ Swift 类型映射"""
import ctypes

PY_TO_SWIFT_TYPE = {
    int: 'Int',
    float: 'Double',
    str: 'String',
    bool: 'Bool',
    list: '[Int]',
    dict: '[String: Any]',
    type(None): 'Void',
}

SWIFT_TO_CTYPES = {
    'Int': ctypes.c_int,
    'Int32': ctypes.c_int32,
    'Int64': ctypes.c_int64,
    'UInt': ctypes.c_uint,
    'Double': ctypes.c_double,
    'Float': ctypes.c_float,
    'Bool': ctypes.c_bool,
    'String': ctypes.c_char_p,
    'Void': None,
}

def get_swift_type(py_type):
    return PY_TO_SWIFT_TYPE.get(py_type, 'String')

def get_swift_ctype(swift_type):
    return SWIFT_TO_CTYPES.get(swift_type, ctypes.c_void_p)