"""vools.bridge.perl.types - Python ↔ Perl 类型映射"""
import ctypes

PY_TO_PERL_TYPE = {
    int: 'int',
    float: 'num',
    str: 'str',
    bool: 'bool',
    list: 'array',
    dict: 'hash',
    type(None): 'undef',
}

PERL_TO_CTYPES = {
    'int': ctypes.c_int,
    'num': ctypes.c_double,
    'str': ctypes.c_char_p,
    'bool': ctypes.c_bool,
    'array': ctypes.POINTER(ctypes.c_int),
    'hash': ctypes.c_void_p,
    'undef': None,
}

def get_perl_type(py_type):
    return PY_TO_PERL_TYPE.get(py_type, 'str')

def get_perl_ctype(perl_type):
    return PERL_TO_CTYPES.get(perl_type, ctypes.c_char_p)