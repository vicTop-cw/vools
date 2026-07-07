"""
测试 Rust 桥接装饰器

测试 @rust 装饰器的各种功能和模式。
"""

import pytest
from vools.bridge.rust import (
    rust,
    is_rust_available,
    RustTypeMapper,
    generate_from_python_func,
)


class TestRustTypeMapper:
    """测试 Rust 类型映射器"""

    def test_basic_types(self):
        """测试基本类型映射"""
        assert RustTypeMapper.get_rust_type(int) == 'c_long'
        assert RustTypeMapper.get_rust_type(float) == 'c_double'
        assert RustTypeMapper.get_rust_type(bool) == 'c_int'
        assert RustTypeMapper.get_rust_type(str) == '*const c_char'
        assert RustTypeMapper.get_rust_type(type(None)) == 'void'

    def test_ctypes_types(self):
        """测试 ctypes 类型映射"""
        import ctypes
        assert RustTypeMapper.get_ctypes_type('c_long') == ctypes.c_long
        assert RustTypeMapper.get_ctypes_type('c_double') == ctypes.c_double
        assert RustTypeMapper.get_ctypes_type('void') is None

    def test_infer_types(self):
        """测试类型推断"""
        rust_types = RustTypeMapper.infer_rust_types([1, 2.0, "hello"])
        assert rust_types == ['c_long', 'c_double', '*const c_char']

        ctypes_types = RustTypeMapper.infer_ctypes_types([1, 2.0, "hello"])
        import ctypes
        assert ctypes_types == [ctypes.c_long, ctypes.c_double, ctypes.c_char_p]


class TestRustCodeGenerator:
    """测试 Rust 代码生成器"""

    def test_function_signature_generation(self):
        """测试函数签名生成"""
        import inspect

        def fib(n: int) -> int:
            pass

        sig = inspect.signature(fib)
        code = generate_from_python_func(
            'fib',
            sig,
            int,
            'if n <= 1 { 1 } else { fib(n - 1) + fib(n - 2) }',
            auto_signature=True
        )

        # 验证生成的代码包含关键元素
        assert '#[no_mangle]' in code
        assert 'pub extern "C"' in code
        assert 'fn fib' in code
        assert 'n: c_long' in code
        assert '-> c_long' in code

    def test_code_with_imports(self):
        """测试带导入语句的代码"""
        import inspect

        def test_func(x: int) -> int:
            pass

        sig = inspect.signature(test_func)
        code = generate_from_python_func(
            'test_func',
            sig,
            int,
            'use std::collections::HashMap;\n\nx + 1',
            auto_signature=True
        )

        # 验证导入语句被保留
        assert 'use std::collections::HashMap;' in code


@pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
class TestRustDecorator:
    """测试 Rust 装饰器（需要 Rust 编译器）"""

    def test_simple_function(self):
        """测试简单函数编译和执行"""
        @rust
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(5, 3)
        assert result == 8

    def test_fibonacci(self):
        """测试斐波那契函数"""
        @rust
        def fib(n: int) -> int:
            return """
            if n <= 1 {
                1
            } else {
                fib(n - 1) + fib(n - 2)
            }
            """

        result = fib(10)
        assert result == 89  # fib(10) = 89

    def test_only_code_mode(self):
        """测试 ONLY_CODE 模式"""
        @rust(mode='ONLY_CODE')
        def test_func(x: int) -> int:
            return "x * 2"

        result = test_func(5)
        # ONLY_CODE 模式返回生成的代码字符串
        assert isinstance(result, str)
        assert '#[no_mangle]' in result

    def test_fallback_on_compilation_failure(self):
        """测试编译失败时的回退机制"""
        def py_fallback(x: int) -> int:
            return x * 10

        @rust(fallback=py_fallback)
        def bad_func(x: int) -> int:
            # 故意返回无效的 Rust 代码
            return "this is not valid rust code !!!"

        # 应该回退到 Python 实现
        result = bad_func(5)
        assert result == 50


class TestRustDecoratorModes:
    """测试装饰器的各种模式"""

    def test_normal_mode_description(self):
        """测试 NORMAL 模式的描述"""
        # NORMAL 模式：DLL 存在则用 DLL，不存在则编译
        @rust(mode='NORMAL')
        def normal_func(x: int) -> int:
            return "x + 1"

        # 如果 Rust 编译器可用，应该能执行
        if is_rust_available():
            result = normal_func(5)
            assert result == 6

    def test_debug_mode_description(self):
        """测试 DEBUG 模式的描述"""
        # DEBUG 模式：强制重新编译
        @rust(mode='DEBUG')
        def debug_func(x: int) -> int:
            return "x * 2"

        if is_rust_available():
            result = debug_func(3)
            assert result == 6


class TestRustCompiler:
    """测试 Rust 编译器"""

    def test_compiler_availability_check(self):
        """测试编译器可用性检查"""
        available = is_rust_available()
        # 根据环境判断
        assert isinstance(available, bool)

    def test_code_hash_generation(self):
        """测试代码哈希生成"""
        from vools.bridge.rust.compiler import get_compiler

        compiler = get_compiler()
        hash1 = compiler._get_code_hash("test code", "test_func")
        hash2 = compiler._get_code_hash("test code", "test_func")
        hash3 = compiler._get_code_hash("different code", "test_func")

        # 相同代码应该生成相同哈希
        assert hash1 == hash2
        # 不同代码应该生成不同哈希
        assert hash1 != hash3


# 集成测试
@pytest.mark.integration
@pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
class TestRustIntegration:
    """Rust 桥接集成测试"""

    def test_multiple_functions(self):
        """测试多个函数"""
        @rust
        def add(a: int, b: int) -> int:
            return "a + b"

        @rust
        def mul(a: int, b: int) -> int:
            return "a * b"

        @rust
        def sub(a: int, b: int) -> int:
            return "a - b"

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5

    def test_cache_mechanism(self):
        """测试缓存机制"""
        from vools.bridge.rust.compiler import get_compiler

        compiler = get_compiler()

        @rust(mode='DEBUG')
        def cached_func(x: int) -> int:
            return "x + 100"

        # 第一次调用（编译）
        result1 = cached_func(5)
        assert result1 == 105

        # 第二次调用（应该使用缓存）
        result2 = cached_func(10)
        assert result2 == 110


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '--tb=short'])
