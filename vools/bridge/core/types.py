"""
vools.bridge.core.types - Python ↔ ctypes 类型映射系统

提供 Python 类型与 ctypes 类型之间的自动转换和推断能力，
简化跨语言函数调用时的类型声明工作。
"""

import ctypes
import sys


PY_TO_CTYPES = {
    int: ctypes.c_long,
    float: ctypes.c_double,
    bool: ctypes.c_int,
    str: ctypes.c_char_p,
    bytes: ctypes.c_char_p,
}


class CTypeMapper:
    """
    ctypes 类型映射器

    提供 Python 类型与 ctypes 类型之间的转换和推断功能，
    支持根据参数值自动推断类型，以及自动转换参数格式。

    用法：
        argtypes = CTypeMapper.infer_arg_types([1, 2.0, "hello"])
        converted = CTypeMapper.convert_args([1, "hello"], argtypes)
    """

    _py_to_ctypes = dict(PY_TO_CTYPES)

    @staticmethod
    def register_type(py_type, c_type):
        """
        注册自定义类型映射

        参数：
            py_type: Python 类型
            c_type: 对应的 ctypes 类型
        """
        CTypeMapper._py_to_ctypes[py_type] = c_type

    @staticmethod
    def get_ctype(py_type):
        """
        获取 Python 类型对应的 ctypes 类型

        参数：
            py_type: Python 类型

        返回：
            ctypes 类型，如果未注册则返回 None
        """
        return CTypeMapper._py_to_ctypes.get(py_type)

    @staticmethod
    def get_py_type(value):
        """
        根据值获取 Python 类型名称

        参数：
            value: 参数值

        返回：
            Python 类型（int, float, bool, str, bytes 等）
        """
        return type(value)

    @staticmethod
    def infer_arg_types(args):
        """
        根据参数值推断 ctypes 参数类型列表

        遍历参数列表，根据每个参数的 Python 类型推断对应的 ctypes 类型。
        对于未注册的类型，默认使用 ctypes.c_void_p。

        参数：
            args: 参数值列表

        返回：
            ctypes 类型列表
        """
        result = []
        for arg in args:
            py_type = type(arg)
            c_type = CTypeMapper._py_to_ctypes.get(py_type)
            if c_type is None:
                c_type = ctypes.c_void_p
            result.append(c_type)
        return result

    @staticmethod
    def infer_ret_type(ret_type):
        """
        根据返回类型注解推断 ctypes 返回类型

        参数：
            ret_type: Python 返回类型注解（如 int、str 等），
                     可以是 None 表示无返回值

        返回：
            对应的 ctypes 类型，如果无法推断则返回 ctypes.c_int
        """
        if ret_type is None or ret_type is type(None):
            return None
        if isinstance(ret_type, type):
            c_type = CTypeMapper._py_to_ctypes.get(ret_type)
            if c_type is not None:
                return c_type
        return ctypes.c_int

    @staticmethod
    def convert_args(args, argtypes):
        """
        转换参数以匹配 ctypes 类型要求

        目前支持的转换：
            - str -> bytes (utf-8 编码)，当对应类型为 c_char_p 时

        参数：
            args: 原始参数值列表
            argtypes: ctypes 参数类型列表

        返回：
            转换后的参数列表
        """
        result = []
        for arg, c_type in zip(args, argtypes):
            if c_type is ctypes.c_char_p:
                if isinstance(arg, str):
                    result.append(arg.encode('utf-8'))
                else:
                    result.append(arg)
            else:
                result.append(arg)
        return result


_default_mapper = None


def get_default_mapper():
    """
    获取默认的 CTypeMapper（保持向后兼容）

    返回：
        CTypeMapper 类本身（因为所有方法都是静态方法）
    """
    return CTypeMapper


def infer_arg_types(args):
    """
    根据参数值推断 ctypes 参数类型列表（便捷函数）

    参数：
        args: 参数值列表

    返回：
        ctypes 类型列表
    """
    return CTypeMapper.infer_arg_types(args)


def infer_ret_type(ret_type):
    """
    根据返回类型注解推断 ctypes 返回类型（便捷函数）

    参数：
        ret_type: Python 返回类型注解

    返回：
        对应的 ctypes 类型
    """
    return CTypeMapper.infer_ret_type(ret_type)


def convert_args(args, argtypes):
    """
    转换参数以匹配 ctypes 类型要求（便捷函数）

    参数：
        args: 原始参数值列表
        argtypes: ctypes 参数类型列表

    返回：
        转换后的参数列表
    """
    return CTypeMapper.convert_args(args, argtypes)
