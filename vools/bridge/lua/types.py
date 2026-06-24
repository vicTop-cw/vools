"""vools.bridge.lua.types - Python ↔ Lua 类型映射"""
import ctypes

PY_TO_LUA_TYPE = {
    int: 'integer',
    float: 'number',
    str: 'string',
    bool: 'boolean',
    list: 'table',
    dict: 'table',
    type(None): 'nil',
}

LUA_TO_CTYPES = {
    'integer': ctypes.c_int,
    'number': ctypes.c_double,
    'string': ctypes.c_char_p,
    'boolean': ctypes.c_bool,
    'table': ctypes.c_void_p,
    'nil': None,
}

def get_lua_type(py_type):
    """根据 Python 类型获取 Lua 端类型字符串"""
    if py_type in PY_TO_LUA_TYPE:
        return PY_TO_LUA_TYPE[py_type]
    if isinstance(py_type, str):
        py_type_lower = py_type.strip().lower()
        if py_type_lower in ('int', 'integer'):
            return 'integer'
        elif py_type_lower in ('float', 'double', 'number'):
            return 'number'
        elif py_type_lower in ('str', 'string'):
            return 'string'
        elif py_type_lower in ('bool', 'boolean'):
            return 'boolean'
        elif py_type_lower in ('list', 'array', 'table'):
            return 'table'
        elif py_type_lower in ('none', 'nil', 'nonetype'):
            return 'nil'
    return 'string'


def get_lua_ctype(lua_type):
    """根据 Lua 类型获取 ctypes 类型"""
    if lua_type in LUA_TO_CTYPES:
        return LUA_TO_CTYPES[lua_type]
    return ctypes.c_char_p
