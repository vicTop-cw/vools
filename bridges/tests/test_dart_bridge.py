"""
Dart 语言桥接测试

测试 vools.bridge.dart 模块的基本功能。
需要 Dart 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_dart_bridge.py -v --tb=short
"""

import pytest
import sys
import os
import asyncio
from vools.bridge.dart import (
    dart,
    dartexe,
    dart_compiler_available,
    DartBridge,
    PY_TO_DART_TYPE,
    DART_TO_CTYPES,
    get_dart_type,
    get_dart_ctype,
)


# =============================================================================
# 测试辅助
# =============================================================================

DART_AVAILABLE = dart_compiler_available()


# =============================================================================
# 编译器检测测试
# =============================================================================

class TestCompilerDetection:
    """测试编译器检测功能"""

    def test_dart_compiler_available_type(self):
        """测试 dart_compiler_available 返回 bool"""
        result = dart_compiler_available()
        assert isinstance(result, bool)

    def test_dartbridge_instance(self):
        """测试 DartBridge 实例"""
        bridge = DartBridge()
        assert bridge.name == 'dart'
        assert bridge.file_ext == '.dart'
        assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试
# =============================================================================

class TestTypeMapping:
    """测试 Python ↔ Dart 类型映射"""

    def test_py_to_dart_type(self):
        """PY_TO_DART_TYPE 基本类型映射"""
        assert PY_TO_DART_TYPE[int] == 'int'
        assert PY_TO_DART_TYPE[float] == 'double'
        assert PY_TO_DART_TYPE[str] == 'String'
        assert PY_TO_DART_TYPE[bool] == 'bool'
        assert PY_TO_DART_TYPE[type(None)] == 'void'

    def test_dart_to_ctypes(self):
        """DART_TO_CTYPES 到 ctypes 映射"""
        import ctypes
        assert DART_TO_CTYPES['int'] is ctypes.c_int
        assert DART_TO_CTYPES['int64'] is ctypes.c_int64
        assert DART_TO_CTYPES['double'] is ctypes.c_double
        assert DART_TO_CTYPES['bool'] is ctypes.c_bool
        assert DART_TO_CTYPES['String'] is ctypes.c_char_p
        assert DART_TO_CTYPES['void'] is None

    def test_get_dart_type(self):
        """get_dart_type 函数"""
        assert get_dart_type(int) == 'int'
        assert get_dart_type(float) == 'double'
        assert get_dart_type(str) == 'String'
        assert get_dart_type(bool) == 'bool'
        assert get_dart_type(type(None)) == 'void'

    def test_get_dart_ctype(self):
        """get_dart_ctype 函数"""
        import ctypes
        assert get_dart_ctype('int') is ctypes.c_int
        assert get_dart_ctype('double') is ctypes.c_double
        assert get_dart_ctype('bool') is ctypes.c_bool
        assert get_dart_ctype('String') is ctypes.c_char_p


# =============================================================================
# 代码生成测试（不需要编译器）
# =============================================================================

class TestCodeGeneration:
    """测试 Dart 代码生成"""

    def test_generate_simple_function(self):
        """生成简单函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = DartBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='return a + b;',
        )
        code = bridge.generate_code(spec)
        assert "import 'dart:convert';" in code
        assert "import 'dart:io';" in code
        assert 'int add(' in code
        assert 'return a + b;' in code
        assert 'void main()' in code

    def test_generate_float_function(self):
        """生成浮点函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = DartBridge()
        spec = FunctionSpec(
            name='multiply',
            annotations={'x': float, 'y': float, 'return': float},
            args=(),
            defaults={},
            body='return x * y;',
        )
        code = bridge.generate_code(spec)
        assert 'double multiply(' in code
        assert 'return x * y;' in code

    def test_generate_string_function(self):
        """生成字符串函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = DartBridge()
        spec = FunctionSpec(
            name='greet',
            annotations={'name': str, 'return': str},
            args=(),
            defaults={},
            body="return 'Hello ' + name;",
        )
        code = bridge.generate_code(spec)
        assert 'String greet(' in code
        assert "return 'Hello ' + name;" in code

    def test_generate_with_module_code(self):
        """生成带 module_code 的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = DartBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='return a + b;',
            module_code='// custom module header',
        )
        code = bridge.generate_code(spec)
        assert '// custom module header' in code

    def test_generate_with_dependencies(self):
        """生成带依赖函数的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = DartBridge()
        dep_spec = FunctionSpec(
            name='helper',
            annotations={'x': int, 'return': int},
            args=(),
            defaults={},
            body='return x * 2;',
        )
        spec = FunctionSpec(
            name='main_func',
            annotations={'a': int, 'return': int},
            args=(),
            defaults={},
            body='return helper(a) + 1;',
            dependencies=[dep_spec],
        )
        code = bridge.generate_code(spec)
        assert 'String helper(' in code
        assert 'int main_func(' in code
        assert 'return x * 2;' in code
        assert 'return helper(a) + 1;' in code


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestDecoratorOnlyCode:
    """测试 @dart 的 ONLY_CODE 模式（无需 Dart 编译器）"""

    def test_only_code_basic(self):
        """ONLY_CODE 模式生成基本代码"""
        @dart(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(1, 2)
        assert isinstance(result, str)
        assert "import 'dart:convert';" in result
        assert 'int add(' in result
        assert 'return a + b;' in result

    def test_only_code_float(self):
        """ONLY_CODE 模式生成浮点函数代码"""
        @dart(mode='ONLY_CODE')
        def multiply(x: float, y: float) -> float:
            return "return x * y;"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'double multiply(' in result
        assert 'return x * y;' in result

    def test_only_code_string(self):
        """ONLY_CODE 模式生成字符串函数代码"""
        @dart(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return "return 'Hello ' + name;"

        result = greet("World")
        assert isinstance(result, str)
        assert 'String greet(' in result
        assert "return 'Hello ' + name;" in result

    def test_only_code_multiline(self):
        """ONLY_CODE 模式生成多行函数体"""
        @dart(mode='ONLY_CODE')
        def fib(n: int) -> int:
            return """
            if (n <= 1) return 1;
            return fib(n-1) + fib(n-2);
            """

        result = fib(10)
        assert isinstance(result, str)
        assert 'int fib(' in result
        assert 'if (n <= 1)' in result

    def test_only_code_with_module_code(self):
        """ONLY_CODE 模式 + module_code"""
        @dart(mode='ONLY_CODE', module_code='// custom module')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '// custom module' in result

    def test_only_code_with_deps(self):
        """ONLY_CODE 模式 + 依赖函数"""
        def helper(x: int) -> int:
            return "return x * 2;"

        @dart(mode='ONLY_CODE', deps=[helper])
        def main_func(a: int) -> int:
            return "return helper(a) + 1;"

        result = main_func(5)
        assert isinstance(result, str)
        assert 'String helper(' in result
        assert 'int main_func(' in result
        assert 'return x * 2;' in result
        assert 'return helper(a) + 1;' in result


# =============================================================================
# 需要 Dart 编译器的测试
# =============================================================================

@pytest.mark.skipif(not DART_AVAILABLE, reason="Dart compiler not available")
class TestDartDecorator:
    """测试 @dart 装饰器（需要 Dart 编译器）"""

    def test_simple_add(self):
        """测试简单加法"""
        @dart
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(3, 4)
        assert result == 7

    def test_subtract(self):
        """测试减法"""
        @dart
        def sub(a: int, b: int) -> int:
            return "return a - b;"

        result = sub(10, 3)
        assert result == 7

    def test_multiply(self):
        """测试乘法"""
        @dart
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        result = mul(6, 7)
        assert result == 42

    def test_float_operations(self):
        """测试浮点运算"""
        @dart
        def add_float(a: float, b: float) -> float:
            return "return a + b;"

        result = add_float(2.5, 3.5)
        assert abs(result - 6.0) < 0.001

    def test_fibonacci(self):
        """测试递归斐波那契"""
        @dart
        def fib(n: int) -> int:
            return """
            if (n <= 1) return 1;
            return fib(n-1) + fib(n-2);
            """

        result = fib(10)
        assert result == 89

    def test_bool_return(self):
        """测试布尔返回值"""
        @dart
        def is_positive(n: int) -> bool:
            return "return n > 0;"

        assert is_positive(5) is True
        assert is_positive(-1) is False

    def test_string_concat(self):
        """测试字符串拼接"""
        @dart
        def greet(name: str) -> str:
            return "return 'Hello ' + name;"

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @dart(fallback=py_add)
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(3, 4)
        assert result == 7

    def test_multiple_functions(self):
        """测试多个函数"""
        @dart
        def add(a: int, b: int) -> int:
            return "return a + b;"

        @dart
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        @dart
        def sub(a: int, b: int) -> int:
            return "return a - b;"

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5


@pytest.mark.skipif(not DART_AVAILABLE, reason="Dart compiler not available")
class TestDartAsync:
    """测试 Dart 异步模式（需要 Dart 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @dart(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "return a + b;"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7

    def test_async_fib(self):
        """测试异步斐波那契"""
        @dart(async_mode=True)
        def fib_async(n: int) -> int:
            return """
            if (n <= 1) return 1;
            return fib_async(n-1) + fib_async(n-2);
            """

        async def run():
            return await fib_async(10)

        result = asyncio.run(run())
        assert result == 89

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @dart(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "return a * b;"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25]


@pytest.mark.skipif(not DART_AVAILABLE, reason="Dart compiler not available")
class TestDartModuleAndDeps:
    """测试 module_code 和 dependencies（需要 Dart 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        @dart(module_code='// custom module')
        def add_ten(x: int) -> int:
            return "return x + 10;"

        result = add_ten(5)
        assert result == 15

    def test_module_code_string(self):
        """测试 module_code 参数 + 字符串函数"""
        @dart(module_code='// string helpers')
        def hello(name: str) -> str:
            return "return 'Hello ' + name;"

        result = hello("World")
        assert "Hello" in result

    def test_module_code_multiple(self):
        """测试 module_code 参数 + 多个函数"""
        @dart(module_code='// math module')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        @dart(module_code='// math module')
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        assert add(3, 4) == 7
        assert mul(3, 4) == 12


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import dart as dart_module
        assert dart_module is not None

    def test_DartBridge_instance(self):
        """测试 DartBridge 实例属性"""
        bridge = DartBridge()
        assert bridge.name == 'dart'
        assert bridge.file_ext == '.dart'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])