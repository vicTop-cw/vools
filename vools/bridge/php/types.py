"""vools.bridge.php.types - Python ↔ PHP 类型映射"""
import ctypes

PY_TO_PHP_TYPE = {
    int: 'int',
    float: 'float',
    str: 'string',
    bool: 'bool',
    list: 'array',
    dict: 'array',
    type(None): 'NULL',
}

PHP_TO_CTYPES = {
    'int': ctypes.c_int,
    'integer': ctypes.c_int,
    'float': ctypes.c_double,
    'double': ctypes.c_double,
    'string': ctypes.c_char_p,
    'bool': ctypes.c_bool,
    'boolean': ctypes.c_bool,
    'array': ctypes.c_void_p,
    'NULL': None,
    'void': None,
}

def get_php_type(py_type):
    return PY_TO_PHP_TYPE.get(py_type, 'string')

def get_php_ctype(php_type):
    return PHP_TO_CTYPES.get(php_type, ctypes.c_void_p)