"""
vools.bridge.freebasic.types - Python ↔ FreeBASIC 类型映射

提供 Python 类型与 FreeBASIC 类型之间的双向映射，以及 ctypes 端桥接表。

设计目标：免序列化（serialization-free）交互。
- list[int] / list[float] 不再走 CSV/JSON 中转，而是直接拆为 (Long Ptr, n) 两个 FB 参数。
- str / bytes 走 ZString Ptr（utf-8 c_char_p），不通过 BSTR。
"""

import ctypes


# ----------------------------------------------------------------------------
# Python 类型 → FreeBASIC 类型
# ----------------------------------------------------------------------------

PY_TO_FB_TYPE = {
    int: 'Long',
    float: 'Double',
    bool: 'Boolean',
    str: 'ZString Ptr',
    bytes: 'ZString Ptr',
    list: 'Long Ptr',  # 默认 int 列表（最常见）
    dict: 'Any Ptr',
    tuple: 'Any Ptr',
    type(None): 'Void',
}


# 字符串别名到 FB 类型的回退（用于 typing 或 str 形式注解）
_TYPE_ALIASES = {
    'int': 'Long',
    'long': 'Long',
    'float': 'Double',
    'double': 'Double',
    'bool': 'Boolean',
    'boolean': 'Boolean',
    'str': 'ZString Ptr',
    'string': 'ZString Ptr',
    'bytes': 'ZString Ptr',
    'byteptr': 'ZString Ptr',
    'list': 'Long Ptr',  # 默认 int 列表
    'list[int]': 'Long Ptr',
    'list[float]': 'Double Ptr',
    'list[double]': 'Double Ptr',
    'dict': 'Any Ptr',
    'tuple': 'Any Ptr',
    'none': 'Void',
    'nonetype': 'Void',
    'void': 'Void',
}


def get_fb_type(py_type):
    """
    根据 Python 类型获取 FreeBASIC 类型

    参数：
        py_type: Python 类型 / 类型注解（可为字符串形式）

    返回：
        FB 类型字符串，未知则返回 'Long'
    """
    # 处理 None 类型
    if py_type is None or py_type is type(None):
        return 'Void'

    # 直接匹配
    if py_type in PY_TO_FB_TYPE:
        return PY_TO_FB_TYPE[py_type]

    # 处理泛型别名（如 list[int]、list[float]），get_type_hints 会解析字符串注解
    import typing as _typing
    origin = _typing.get_origin(py_type)
    if origin is not None:
        if origin is list:
            args = _typing.get_args(py_type)
            if args and args[0] is float:
                return 'Double Ptr'
            return 'Long Ptr'
        if origin is dict:
            return 'Any Ptr'

    # 字符串形式注解（来自 typing 或 forward reference）
    if isinstance(py_type, str):
        normalized = py_type.strip().lower()
        if normalized in _TYPE_ALIASES:
            return _TYPE_ALIASES[normalized]
        # 处理带模块前缀的，例如 'builtins.int' -> 'int'
        short = normalized.split('.')[-1]
        if short in _TYPE_ALIASES:
            return _TYPE_ALIASES[short]
        # 未知字符串类型默认 Long
        return 'Long'

    # 其他未知类型
    return 'Long'


def infer_fb_argtypes(args):
    """
    根据运行时值推断 FB 参数类型

    与 fbc.py 区别：list 不再用 POINTER + CSV，而是按元素类型分类。
    - 元素全为 int → 'Long Ptr'
    - 元素全为 float → 'Double Ptr'
    - 其他 list → 'Any Ptr'

    返回：
        FB 类型字符串列表
    """
    result = []
    for arg in args:
        if isinstance(arg, bool):
            result.append('Boolean')
        elif isinstance(arg, int):
            result.append('Long')
        elif isinstance(arg, float):
            result.append('Double')
        elif isinstance(arg, str):
            result.append('ZString Ptr')
        elif isinstance(arg, bytes):
            result.append('ZString Ptr')
        elif isinstance(arg, list):
            if arg and all(isinstance(x, int) and not isinstance(x, bool) for x in arg):
                result.append('Long Ptr')
            elif arg and all(isinstance(x, float) for x in arg):
                result.append('Double Ptr')
            else:
                result.append('Any Ptr')
            # 长度作为额外参数返回（由 compiler 拼接）
        elif isinstance(arg, tuple):
            result.append('Any Ptr')
        elif isinstance(arg, dict):
            result.append('Any Ptr')
        else:
            result.append('Any Ptr')
    return result


def is_array_type(fb_type):
    """判断 FB 类型是否为数组（POINTER 形式需要附加长度参数）"""
    return fb_type in ('Long Ptr', 'Double Ptr')


# ----------------------------------------------------------------------------
# FreeBASIC 类型 → ctypes 类型（用于 ctypes 端 cdecl 边界）
# ----------------------------------------------------------------------------

FB_TO_CTYPES = {
    'Long': ctypes.c_long,
    'Double': ctypes.c_double,
    'Boolean': ctypes.c_bool,
    'ZString Ptr': ctypes.c_char_p,
    'Byte Ptr': ctypes.c_char_p,
    'Long Ptr': ctypes.POINTER(ctypes.c_long),
    'Double Ptr': ctypes.POINTER(ctypes.c_double),
    'Any Ptr': ctypes.c_void_p,
    'Void': None,
}


def get_ctype_for(fb_type):
    """
    根据 FB 类型获取 ctypes 类型

    返回：
        ctypes 类型，'Void' 返回 None
    """
    return FB_TO_CTYPES.get(fb_type, ctypes.c_long)
