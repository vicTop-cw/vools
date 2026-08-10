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



# ============================================================================
# 编译模式枚举
# ============================================================================

class CompileMode:
    """编译模式枚举（兼容字符串比较）。

    定义所有编译执行模式，用于控制桥接装饰器的编译和执行行为。

    成员：
        NORMAL -- 正常模式，命中缓存跳过编译；未命中则编译
        DEBUG -- 调试模式，强制重新编译并执行
        FORCE -- 强制模式，强制重新编译但不执行
        ONLY_RUN -- 仅运行模式，只在有缓存时执行；没有则报错
        ONLY_CODE -- 仅代码模式，只生成源码不编译
        WHEN_CHANGE_JUST -- 变更编译模式，检测到代码变更时编译，不执行
        WHEN_CHANGE_AND_RUN -- 变更编译运行模式，检测到代码变更时编译并执行
    """

    NORMAL = 'NORMAL'
    DEBUG = 'DEBUG'
    FORCE = 'FORCE'
    ONLY_RUN = 'ONLY_RUN'
    ONLY_CODE = 'ONLY_CODE'
    WHEN_CHANGE_JUST = 'WHEN_CHANGE_JUST'
    WHEN_CHANGE_AND_RUN = 'WHEN_CHANGE_AND_RUN'

    _ALL = frozenset({NORMAL, DEBUG, FORCE, ONLY_RUN, ONLY_CODE,
                       WHEN_CHANGE_JUST, WHEN_CHANGE_AND_RUN})

    @classmethod
    def normalize(cls, mode):
        """将字符串或枚举值规范化为标准字符串。

        参数：
            mode: CompileMode 枚举成员 或 大小写不敏感的字符串。

        返回：
            str: 标准化的大写字符串。

        异常：
            ValueError: 无效的模式字符串。
        """
        if isinstance(mode, str):
            upper = mode.upper()
            if upper in cls._ALL:
                return upper
            raise ValueError(
                "Invalid compile mode: {!r}. "
                "Valid modes: {}".format(mode, sorted(cls._ALL))
            )
        # 假设是 CompileMode 枚举成员（通过字符串比较）
        mode_str = str(mode) if not isinstance(mode, str) else mode
        if mode_str in cls._ALL:
            return mode_str
        raise ValueError("Invalid compile mode: {!r}".format(mode))

    @classmethod
    def is_change_aware(cls, mode):
        """判断模式是否为代码变更感知模式。

        参数：
            mode: 编译模式字符串。

        返回：
            bool: True 如果是 WHEN_CHANGE_JUST 或 WHEN_CHANGE_AND_RUN。
        """
        m = cls.normalize(mode)
        return m in (cls.WHEN_CHANGE_JUST, cls.WHEN_CHANGE_AND_RUN)

    @classmethod
    def is_force_recompile(cls, mode):
        """判断模式是否需要强制重新编译。

        参数：
            mode: 编译模式字符串。

        返回：
            bool: True 如果需要强制重编译。
        """
        m = cls.normalize(mode)
        return m in (cls.DEBUG, cls.FORCE)

    @classmethod
    def should_execute(cls, mode):
        """判断模式是否需要在编译后执行。

        参数：
            mode: 编译模式字符串。

        返回：
            bool: True 如果需要执行函数。
        """
        m = cls.normalize(mode)
        return m not in (cls.FORCE, cls.ONLY_CODE, cls.WHEN_CHANGE_JUST)


# ============================================================================
# 语言类型枚举
# ============================================================================

class LangType:
    """语言类型枚举。

    用于分类语言，决定编译产物的处理方式。

    成员：
        COMPILED -- 编译型语言（Nim, Rust, C, C++, Go, Zig, FreeBASIC, Mojo, Cangjie, VBNet, MoonBit）
        INTERPRETED -- 解释型语言（Lua, Shell, Perl, PHP, Python, R, Ruby, VBScript, PowerShell）
        JVM -- JVM 语言（Java, Scala, Kotlin）
        DOTNET -- .NET 语言（C#）
        BEAM -- BEAM VM 语言（Erlang, Elixir）
    """

    COMPILED = 'compiled'
    INTERPRETED = 'interpreted'
    JVM = 'jvm'
    DOTNET = 'dotnet'
    BEAM = 'beam'

    _ALL = frozenset({COMPILED, INTERPRETED, JVM, DOTNET, BEAM})

    @classmethod
    def normalize(cls, lang_type):
        """规范化语言类型字符串。

        参数：
            lang_type: 字符串或 LangType 成员。

        返回：
            str: 标准化的小写字符串。
        """
        if isinstance(lang_type, str):
            lower = lang_type.lower()
            if lower in cls._ALL:
                return lower
            raise ValueError("Invalid lang type: {!r}".format(lang_type))
        return str(lang_type)
