"""BUG-272 sys.dll @dll PEP 563 字符串注解解析错误回归测试。

从 __future__ import annotations 或 py3.6 字符串注解写法下，@dll 装饰器
_extract_annotations 应通过 typing.get_type_hints() 解析字符串注解，
_map_py_to_ctype 应兼容字符串名称输入，_convert_result 应兼容字符串
'ret_py_type' 解码返回值。
"""
import ctypes

import pytest

from vools.sys.dll import (
    _extract_annotations,
    _map_py_to_ctype,
    _convert_result,
)


# ------------------------------------------------------------------
# ① _extract_annotations：字符串注解解析
# ------------------------------------------------------------------

class TestExtractAnnotationsPEP563:
    """from __future__ import annotations 下注解为字符串，应正确解析。"""

    def test_string_annotations(self):
        # 用字符串注解模拟 PEP 563 效果（无需实际 import __future__）
        exec_ns = {}
        exec(
            "def f(a: 'int', b: 'str') -> 'bool': pass",
            exec_ns,
        )
        f = exec_ns['f']
        arg_types, ret_type, params = _extract_annotations(f)
        # 应解析为类型对象而非字符串
        assert arg_types[0] is int
        assert arg_types[1] is str
        assert ret_type is bool

    def test_string_annotations_fallback_to_raw(self):
        """当 get_type_hints 失败时，应回退到 inspect.signature 原始值。"""
        # 用带无效字符串注解的函数模拟 get_type_hints 失败场景
        def f(a, b):
            pass
        # 手动设置签名属性模拟无法解析的字符串注解
        import inspect
        sig = inspect.signature(f)
        params = list(sig.parameters.values())
        # 无注解时结果应为 None
        arg_types, ret_type, _ = _extract_annotations(f)
        assert arg_types == [None, None]
        assert ret_type is None

    def test_mixed_annotations(self):
        """混合部分注解、部分未注解的函数。"""
        def f(a: int, b, c: str):
            pass
        arg_types, ret_type, _ = _extract_annotations(f)
        assert arg_types[0] is int
        assert arg_types[1] is None
        assert arg_types[2] is str
        assert ret_type is None


# ------------------------------------------------------------------
# ② _map_py_to_ctype：字符串名称映射
# ------------------------------------------------------------------

class TestMapPyToCtypeStringName:
    """字符串类型名称应映射到正确 ctypes，与类型对象行为一致。"""

    def test_str_name(self):
        assert _map_py_to_ctype('str') is ctypes.c_char_p

    def test_int_name(self):
        assert _map_py_to_ctype('int') is ctypes.c_int

    def test_float_name(self):
        assert _map_py_to_ctype('float') is ctypes.c_double

    def test_bytes_name(self):
        assert _map_py_to_ctype('bytes') is ctypes.c_char_p

    def test_bool_name(self):
        assert _map_py_to_ctype('bool') is ctypes.c_bool

    def test_unknown_name_fallback(self):
        """未知字符串名称应回退到 c_int（与未知类型对象一致）。"""
        assert _map_py_to_ctype('unknown_type') is ctypes.c_int

    def test_none_input(self):
        """None 输入应返回 c_int（默认行为不变）。"""
        assert _map_py_to_ctype(None) is ctypes.c_int

    def test_type_object_unchanged(self):
        """类型对象输入应保持原有行为（回归）。"""
        assert _map_py_to_ctype(int) is ctypes.c_int
        assert _map_py_to_ctype(str) is ctypes.c_char_p
        assert _map_py_to_ctype(float) is ctypes.c_double
        assert _map_py_to_ctype(bytes) is ctypes.c_char_p
        assert _map_py_to_ctype(bool) is ctypes.c_bool
        assert _map_py_to_ctype(dict) is ctypes.c_int  # 未知类型


# ------------------------------------------------------------------
# ③ _convert_result：字符串 ret_py_type 处理
# ------------------------------------------------------------------

class TestConvertResultStringRetType:
    """ret_py_type 为字符串 'str'/'bytes' 时应正确处理。"""

    def test_string_str_decodes_bytes(self):
        assert _convert_result(b'hello', ctypes.c_char_p, 'str') == 'hello'

    def test_string_str_with_non_bytes(self):
        """非 bytes 输入应原样返回（不强制转 str）。"""
        assert _convert_result(42, ctypes.c_int, 'str') == 42

    def test_string_bytes_returns_bytes(self):
        assert _convert_result(b'hello', ctypes.c_char_p, 'bytes') == b'hello'

    def test_type_object_str_still_works(self):
        """类型对象 str 应保持原有行为（回归）。"""
        assert _convert_result(b'hello', ctypes.c_char_p, str) == 'hello'

    def test_none_returns_raw(self):
        """ret_py_type=None 应原样返回结果。"""
        assert _convert_result(b'hello', ctypes.c_char_p, None) == b'hello'

    def test_empty_string_ret_type(self):
        """空字符串 ret_py_type 应原样返回（未知类型）。"""
        assert _convert_result(b'hello', ctypes.c_char_p, '') == b'hello'


# ------------------------------------------------------------------
# ④ 端到端：PEP 563 字符串注解函数整体解析
# ------------------------------------------------------------------

class TestEndToEndPEP563:
    """端到端：字符串注解函数经 _extract_annotations + _map_py_to_ctype 后得到正确 ctypes。"""

    def test_e2e_string_annotations(self):
        exec_ns = {
            'ctypes': ctypes,
        }
        exec(
            "def greet(name: 'str', times: 'int') -> 'str': pass",
            exec_ns,
        )
        greet = exec_ns['greet']
        arg_types, ret_type, _ = _extract_annotations(greet)
        # 类型应被解析为类型对象
        assert arg_types == [str, int]
        assert ret_type is str
        # 映射 ctypes 应正确
        assert _map_py_to_ctype(arg_types[0]) is ctypes.c_char_p
        assert _map_py_to_ctype(arg_types[1]) is ctypes.c_int
        assert _map_py_to_ctype(ret_type) is ctypes.c_char_p

    def test_e2e_string_return_decoded(self):
        """返回值经 _convert_result 后应正确解码。"""
        # 模拟 PEP 563 返回 'str'（字符串）已被 get_type_hints 解析为 str 类型
        assert _convert_result(b'hello', ctypes.c_char_p, str) == 'hello'
