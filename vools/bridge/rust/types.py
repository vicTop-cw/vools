"""
vools.bridge.rust.types - Python ↔ Rust 类型映射系统

提供 Python 类型与 Rust C ABI 类型之间的自动转换和推断能力，
简化跨语言函数调用时的类型声明工作。
"""

import ctypes
from typing import Dict, Type, Any, List, Tuple

# Python 类型到 Rust C ABI 类型的映射表
# 注意：Rust 使用 C ABI (extern "C")，所以类型要对应 ctypes
PY_TO_RUST_TYPE_MAP: Dict[Type, str] = {
    int: 'c_long',              # i64 in Rust, c_long in ctypes
    float: 'c_double',          # f64 in Rust, c_double in ctypes
    bool: 'c_int',              # bool in Rust (0/1), c_int in ctypes
    str: '*const c_char',       # &CStr in Rust, c_char_p in ctypes
    bytes: '*const c_uchar',    # &[u8] in Rust, c_char_p in ctypes
    type(None): 'void',         # () in Rust, None in ctypes
}

# Rust C ABI 类型到 ctypes 类型的映射表
RUST_TO_CTYPES_MAP: Dict[str, Type] = {
    'c_long': ctypes.c_long,
    'c_double': ctypes.c_double,
    'c_int': ctypes.c_int,
    'c_char': ctypes.c_char,
    'c_uchar': ctypes.c_ubyte,
    '*const c_char': ctypes.c_char_p,
    '*const c_uchar': ctypes.c_char_p,
    'void': None,
    'c_longlong': ctypes.c_longlong,
    'c_ulong': ctypes.c_ulong,
    'c_ulonglong': ctypes.c_ulonglong,
    'c_float': ctypes.c_float,
    'c_short': ctypes.c_short,
    'c_ushort': ctypes.c_ushort,
    'c_int8': ctypes.c_int8,
    'c_uint8': ctypes.c_uint8,
    'c_int16': ctypes.c_int16,
    'c_uint16': ctypes.c_uint16,
    'c_int32': ctypes.c_int32,
    'c_uint32': ctypes.c_uint32,
    'c_int64': ctypes.c_int64,
    'c_uint64': ctypes.c_uint64,
    'c_size_t': ctypes.c_size_t,
    'c_ssize_t': ctypes.c_ssize_t,
}


class RustTypeMapper:
    """
    Rust 类型映射器

    提供 Python 类型与 Rust C ABI 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及自动转换参数格式。

    用法：
        rust_type = RustTypeMapper.get_rust_type(int)
        ctypes_type = RustTypeMapper.get_ctypes_type('c_long')
        argtypes = RustTypeMapper.infer_arg_types([1, 2.0, "hello"])
    """

    _py_to_rust = dict(PY_TO_RUST_TYPE_MAP)
    _rust_to_ctypes = dict(RUST_TO_CTYPES_MAP)

    @staticmethod
    def register_type(py_type: Type, rust_type: str, ctypes_type: Type = None):
        """
        注册自定义类型映射

        参数：
            py_type: Python 类型
            rust_type: 对应的 Rust C ABI 类型字符串
            ctypes_type: 对应的 ctypes 类型（可选，自动推导）
        """
        RustTypeMapper._py_to_rust[py_type] = rust_type
        if ctypes_type is not None:
            RustTypeMapper._rust_to_ctypes[rust_type] = ctypes_type

    @staticmethod
    def get_rust_type(py_type: Type) -> str:
        """
        获取 Python 类型对应的 Rust C ABI 类型字符串

        参数：
            py_type: Python 类型

        返回：
            Rust C ABI 类型字符串，如果未注册则返回 'c_long'
        """
        if py_type is None or py_type is type(None):
            return 'void'
        return RustTypeMapper._py_to_rust.get(py_type, 'c_long')

    @staticmethod
    def get_ctypes_type(rust_type: str) -> Type:
        """
        获取 Rust C ABI 类型对应的 ctypes 类型

        参数：
            rust_type: Rust C ABI 类型字符串

        返回：
            ctypes 类型，如果未注册则返回 ctypes.c_long
        """
        return RustTypeMapper._rust_to_ctypes.get(rust_type, ctypes.c_long)

    @staticmethod
    def infer_rust_types(args: List[Any]) -> List[str]:
        """
        根据参数值推断 Rust C ABI 类型列表

        遍历参数列表，根据每个参数的 Python 类型推断对应的 Rust 类型。
        对于未注册的类型，默认使用 'c_long'。

        参数：
            args: 参数值列表

        返回：
            Rust C ABI 类型字符串列表
        """
        result = []
        for arg in args:
            py_type = type(arg)
            rust_type = RustTypeMapper.get_rust_type(py_type)
            result.append(rust_type)
        return result

    @staticmethod
    def infer_ctypes_types(args: List[Any]) -> List[Type]:
        """
        根据参数值推断 ctypes 类型列表

        参数：
            args: 参数值列表

        返回：
            ctypes 类型列表
        """
        rust_types = RustTypeMapper.infer_rust_types(args)
        return [RustTypeMapper.get_ctypes_type(rt) for rt in rust_types]

    @staticmethod
    def infer_ret_type(ret_type: Type) -> Tuple[str, Type]:
        """
        根据返回类型注解推断 Rust 和 ctypes 返回类型

        参数：
            ret_type: Python 返回类型注解（如 int、str 等），
                     可以是 None 表示无返回值

        返回：
            (rust_type, ctypes_type) 元组
        """
        if ret_type is None or ret_type is type(None):
            return ('void', None)

        rust_type = RustTypeMapper.get_rust_type(ret_type)
        ctypes_type = RustTypeMapper.get_ctypes_type(rust_type)
        return (rust_type, ctypes_type)

    @staticmethod
    def convert_args(args: List[Any], ctypes_types: List[Type]) -> List[Any]:
        """
        转换参数以匹配 ctypes 类型要求

        目前支持的转换：
            - str -> bytes (utf-8 编码)，当对应类型为 c_char_p 时
            - bytes -> bytes，保持不变

        参数：
            args: 原始参数值列表
            ctypes_types: ctypes 参数类型列表

        返回：
            转换后的参数列表
        """
        result = []
        for arg, c_type in zip(args, ctypes_types):
            if c_type == ctypes.c_char_p:
                if isinstance(arg, str):
                    result.append(arg.encode('utf-8'))
                else:
                    result.append(arg)
            else:
                result.append(arg)
        return result


# 便捷函数
def get_rust_type(py_type: Type) -> str:
    """获取 Python 类型对应的 Rust C ABI 类型"""
    return RustTypeMapper.get_rust_type(py_type)


def get_ctypes_type(rust_type: str) -> Type:
    """获取 Rust C ABI 类型对应的 ctypes 类型"""
    return RustTypeMapper.get_ctypes_type(rust_type)


def infer_rust_types(args: List[Any]) -> List[str]:
    """根据参数值推断 Rust C ABI 类型列表"""
    return RustTypeMapper.infer_rust_types(args)


def infer_ctypes_types(args: List[Any]) -> List[Type]:
    """根据参数值推断 ctypes 类型列表"""
    return RustTypeMapper.infer_ctypes_types(args)


def infer_ret_type(ret_type: Type) -> Tuple[str, Type]:
    """根据返回类型注解推断 Rust 和 ctypes 返回类型"""
    return RustTypeMapper.infer_ret_type(ret_type)


def convert_args(args: List[Any], ctypes_types: List[Type]) -> List[Any]:
    """转换参数以匹配 ctypes 类型要求"""
    return RustTypeMapper.convert_args(args, ctypes_types)