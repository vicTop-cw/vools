"""
测试 Rust 类型映射系统

测试 Python ↔ Rust ↔ ctypes 类型转换。
"""

import pytest
import ctypes
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.rust.types import (
    RustTypeMapper,
    get_rust_type,
    get_ctypes_type,
    infer_rust_types,
    infer_ctypes_types,
    infer_ret_type,
    convert_args,
)


class TestRustTypeMapperBasic:
    """测试基本类型映射"""

    def test_int_type(self):
        """测试 int 类型映射"""
        rust_type = get_rust_type(int)
        assert rust_type == 'c_long'

        ctypes_type = get_ctypes_type('c_long')
        assert ctypes_type == ctypes.c_long

    def test_float_type(self):
        """测试 float 类型映射"""
        rust_type = get_rust_type(float)
        assert rust_type == 'c_double'

        ctypes_type = get_ctypes_type('c_double')
        assert ctypes_type == ctypes.c_double

    def test_bool_type(self):
        """测试 bool 类型映射"""
        rust_type = get_rust_type(bool)
        assert rust_type == 'c_int'  # C ABI 中 bool 用 int 表示

        ctypes_type = get_ctypes_type('c_int')
        assert ctypes_type == ctypes.c_int

    def test_str_type(self):
        """测试 str 类型映射"""
        rust_type = get_rust_type(str)
        assert rust_type == '*const c_char'

        ctypes_type = get_ctypes_type('*const c_char')
        assert ctypes_type == ctypes.c_char_p

    def test_none_type(self):
        """测试 None 类型映射"""
        rust_type = get_rust_type(type(None))
        assert rust_type == 'void'

        ctypes_type = get_ctypes_type('void')
        assert ctypes_type is None


class TestRustTypeMapperInference:
    """测试类型推断"""

    def test_infer_single_types(self):
        """测试单个类型推断"""
        assert infer_rust_types([42]) == ['c_long']
        assert infer_rust_types([3.14]) == ['c_double']
        assert infer_rust_types([True]) == ['c_int']
        assert infer_rust_types(["hello"]) == ['*const c_char']

    def test_infer_multiple_types(self):
        """测试多个类型推断"""
        args = [1, 2.5, True, "test"]
        rust_types = infer_rust_types(args)
        assert rust_types == ['c_long', 'c_double', 'c_int', '*const c_char']

        ctypes_types = infer_ctypes_types(args)
        assert ctypes_types == [ctypes.c_long, ctypes.c_double, ctypes.c_int, ctypes.c_char_p]

    def test_infer_return_type(self):
        """测试返回类型推断"""
        rust_type, ctypes_type = infer_ret_type(int)
        assert rust_type == 'c_long'
        assert ctypes_type == ctypes.c_long

        rust_type, ctypes_type = infer_ret_type(None)
        assert rust_type == 'void'
        assert ctypes_type is None

    def test_infer_unknown_type(self):
        """测试未知类型推断"""
        # 未注册的类型应该默认为 c_long
        rust_type = get_rust_type(list)
        assert rust_type == 'c_long'


class TestRustTypeMapperConversion:
    """测试参数转换"""

    def test_str_to_bytes_conversion(self):
        """测试字符串到字节转换"""
        args = ["hello", "world"]
        ctypes_types = [ctypes.c_char_p, ctypes.c_char_p]
        converted = convert_args(args, ctypes_types)

        assert converted == ["hello".encode('utf-8'), "world".encode('utf-8')]
        assert isinstance(converted[0], bytes)
        assert isinstance(converted[1], bytes)

    def test_int_no_conversion(self):
        """测试整数不转换"""
        args = [42, 100]
        ctypes_types = [ctypes.c_long, ctypes.c_long]
        converted = convert_args(args, ctypes_types)

        assert converted == [42, 100]
        assert isinstance(converted[0], int)
        assert isinstance(converted[1], int)

    def test_mixed_conversion(self):
        """测试混合类型转换"""
        args = [42, "hello", 3.14]
        ctypes_types = [ctypes.c_long, ctypes.c_char_p, ctypes.c_double]
        converted = convert_args(args, ctypes_types)

        assert converted[0] == 42
        assert converted[1] == "hello".encode('utf-8')
        assert converted[2] == 3.14


class TestRustTypeMapperRegistration:
    """测试自定义类型注册"""

    def test_register_custom_type(self):
        """测试注册自定义类型"""
        # 注册自定义类型
        RustTypeMapper.register_type(dict, '*mut c_void', ctypes.c_void_p)

        # 验证注册成功
        rust_type = get_rust_type(dict)
        assert rust_type == '*mut c_void'

        ctypes_type = get_ctypes_type('*mut c_void')
        assert ctypes_type == ctypes.c_void_p

    def test_register_overwrite(self):
        """测试覆盖已有类型"""
        # 注册覆盖 int 类型（仅用于测试）
        original_type = get_rust_type(int)

        RustTypeMapper.register_type(int, 'c_longlong', ctypes.c_longlong)
        new_type = get_rust_type(int)

        assert new_type == 'c_longlong'

        # 恢复原始类型
        RustTypeMapper.register_type(int, original_type, ctypes.c_long)


class TestRustTypeMapperEdgeCases:
    """测试边界情况"""

    def test_empty_args(self):
        """测试空参数列表"""
        rust_types = infer_rust_types([])
        assert rust_types == []

        ctypes_types = infer_ctypes_types([])
        assert ctypes_types == []

    def test_none_return_type(self):
        """测试 None 返回类型"""
        rust_type, ctypes_type = infer_ret_type(type(None))
        assert rust_type == 'void'
        assert ctypes_type is None

    def test_bytes_arg(self):
        """测试 bytes 参数"""
        args = [b"hello"]
        ctypes_types = [ctypes.c_char_p]
        converted = convert_args(args, ctypes_types)

        # bytes 不需要转换
        assert converted == [b"hello"]


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])