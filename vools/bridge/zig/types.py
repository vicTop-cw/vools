"""vools.bridge.zig.types - Python ↔ Zig 类型映射"""
import ctypes

PY_TO_ZIG_TYPE = {
    int: 'i64',
    float: 'f64',
    str: '[*:0]const u8',
    bool: 'bool',
    list: '[]i64',
    dict: 'std.StringHashMap(i64)',
    type(None): 'void',
}

ZIG_TO_CTYPES = {
    'i8': ctypes.c_int8,
    'i16': ctypes.c_int16,
    'i32': ctypes.c_int,
    'i64': ctypes.c_int64,
    'u8': ctypes.c_uint8,
    'u16': ctypes.c_uint16,
    'u32': ctypes.c_uint32,
    'u64': ctypes.c_uint64,
    'f32': ctypes.c_float,
    'f64': ctypes.c_double,
    'bool': ctypes.c_bool,
    '*:const u8': ctypes.c_char_p,
    'void': None,
}

def get_zig_type(py_type):
    return PY_TO_ZIG_TYPE.get(py_type, 'i64')

def get_zig_ctype(zig_type):
    return ZIG_TO_CTYPES.get(zig_type, ctypes.c_void_p)
