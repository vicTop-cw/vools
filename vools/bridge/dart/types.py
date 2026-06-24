"""vools.bridge.dart.types - Python ↔ Dart 类型映射"""
import ctypes

PY_TO_DART_TYPE = {
    int: 'int',
    float: 'double',
    str: 'String',
    bool: 'bool',
    list: 'List<int>',
    dict: 'Map<String, dynamic>',
    type(None): 'void',
}

DART_TO_CTYPES = {
    'int': ctypes.c_int,
    'int32': ctypes.c_int32,
    'int64': ctypes.c_int64,
    'double': ctypes.c_double,
    'float': ctypes.c_float,
    'bool': ctypes.c_bool,
    'String': ctypes.c_char_p,
    'void': None,
}

def get_dart_type(py_type):
    return PY_TO_DART_TYPE.get(py_type, 'String')

def get_dart_ctype(dart_type):
    return DART_TO_CTYPES.get(dart_type, ctypes.c_void_p)
