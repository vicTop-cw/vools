"""
C 语言桥接测试

测试 vools.bridge.c 模块的基本功能。
需要 C 编译器（gcc）才能运行完整测试。

运行：python -m pytest tests/bridge/test_c_bridge.py -v --tb=short
"""

import pytest
import sys
import os
import asyncio
from vools.bridge.c import (
    CBridge,
    c_compiler_available,
    PY_TO_C_TYPE,
    C_TO_CTYPES,
    load_dll,
    CDLLWrapper,
)


# =============================================================================
# 测试辅助
# =============================================================================

C_AVAILABLE = c_compiler_available()


# =============================================================================
# 编译器检测测试
# =============================================================================

class TestCompilerDetection:
    """测试编译器检测功能"""

    def test_c_compiler_available_type(self):
        """测试 c_compiler_available 返回 bool"""
        result = c_compiler_available()
        assert isinstance(result, bool)

    def test_cbridge_instance(self):
        """测试 CBridge 实例"""
        bridge = CBridge()
        assert bridge.name == 'c'
        assert bridge.file_ext == '.c'
        assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试
# =============================================================================

class TestTypeMapping:
    """测试 Python ↔ C 类型映射"""

    def test_py_to_c_type(self):
        """PY_TO_C_TYPE 基本类型映射"""
        assert PY_TO_C_TYPE[int] == 'int'
        assert PY_TO_C_TYPE[float] == 'double'
        assert PY_TO_C_TYPE[bool] == 'int'
        assert PY_TO_C_TYPE[str] == 'const char*'
        assert PY_TO_C_TYPE[bytes] == 'const char*'

    def test_c_to_ctypes(self):
        """C_TO_CTYPES 到 ctypes 映射"""
        import ctypes
        assert C_TO_CTYPES['int'] is ctypes.c_int
        assert C_TO_CTYPES['double'] is ctypes.c_double
        assert C_TO_CTYPES['float'] is ctypes.c_float
        assert C_TO_CTYPES['const char*'] is ctypes.c_char_p
        assert C_TO_CTYPES['char*'] is ctypes.c_char_p
        assert C_TO_CTYPES['void'] is None


# =============================================================================
# 代码生成测试（不需要编译器）
# =============================================================================

class TestCodeGeneration:
    """测试 C 代码生成"""

    def test_generate_simple_function(self):
        """生成简单函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = CBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='return a + b;',
        )
        code = bridge.generate_code(spec)
        assert 'int add(' in code
        assert 'int a' in code
        assert 'int b' in code
        assert 'return a + b;' in code

    def test_generate_float_function(self):
        """生成浮点函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = CBridge()
        spec = FunctionSpec(
            name='multiply',
            annotations={'x': float, 'y': float, 'return': float},
            args=(),
            defaults={},
            body='return x * y;',
        )
        code = bridge.generate_code(spec)
        assert 'double multiply(' in code
        assert 'double x' in code
        assert 'double y' in code

    def test_generate_void_function(self):
        """生成无返回值函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = CBridge()
        spec = FunctionSpec(
            name='hello',
            annotations={'return': type(None)},
            args=(),
            defaults={},
            body=';',
        )
        code = bridge.generate_code(spec)
        assert 'void hello(' in code

    def test_generate_with_module_code(self):
        """生成带 module_code 的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = CBridge()
        bridge.set_includes(['<stdio.h>', '<string.h>'])
        spec = FunctionSpec(
            name='strlen_test',
            annotations={'s': str, 'return': int},
            args=(),
            defaults={},
            body='return (int)strlen(s);',
            module_code='#include <string.h>',
        )
        code = bridge.generate_code(spec)
        assert '#include <stdio.h>' in code
        assert '#include <string.h>' in code

    def test_generate_with_dependencies(self):
        """生成带依赖函数的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = CBridge()
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
        assert 'int helper(' in code
        assert 'int main_func(' in code
        assert 'return x * 2;' in code
        assert 'return helper(a) + 1;' in code
        assert code.index('helper') < code.index('main_func')


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestDecoratorOnlyCode:
    """测试 @decorator 的 ONLY_CODE 模式（无需 C 编译器）"""

    def test_only_code_basic(self):
        """ONLY_CODE 模式生成基本代码"""
        bridge = CBridge()

        @bridge.decorator(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'int add(' in result
        assert 'return a + b;' in result

    def test_only_code_float(self):
        """ONLY_CODE 模式生成浮点函数代码"""
        bridge = CBridge()

        @bridge.decorator(mode='ONLY_CODE')
        def multiply(x: float, y: float) -> float:
            return "return x * y;"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'double multiply(' in result
        assert 'return x * y;' in result

    def test_only_code_multiline(self):
        """ONLY_CODE 模式生成多行函数体"""
        bridge = CBridge()

        @bridge.decorator(mode='ONLY_CODE')
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
        bridge = CBridge()

        @bridge.decorator(mode='ONLY_CODE', module_code='#include <string.h>')
        def str_len(s: str) -> int:
            return "return (int)strlen(s);"

        result = str_len("hello")
        assert isinstance(result, str)
        assert '#include <string.h>' in result

    def test_only_code_with_deps(self):
        """ONLY_CODE 模式 + 依赖函数"""
        bridge = CBridge()

        def helper(x: int) -> int:
            return "return x * 2;"

        @bridge.decorator(mode='ONLY_CODE', deps=[helper])
        def main_func(a: int) -> int:
            return "return helper(a) + 1;"

        result = main_func(5)
        assert isinstance(result, str)
        assert 'int helper(' in result
        assert 'int main_func(' in result
        assert 'return x * 2;' in result
        assert 'return helper(a) + 1;' in result


# =============================================================================
# 需要 C 编译器的测试
# =============================================================================

@pytest.mark.skipif(not C_AVAILABLE, reason="C compiler not available")
class TestCDecorator:
    """测试 CBridge.decorator（需要 C 编译器）"""

    def test_simple_add(self):
        """测试简单加法"""
        bridge = CBridge()

        @bridge.decorator
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(3, 4)
        assert result == 7

    def test_subtract(self):
        """测试减法"""
        bridge = CBridge()

        @bridge.decorator
        def sub(a: int, b: int) -> int:
            return "return a - b;"

        result = sub(10, 3)
        assert result == 7

    def test_multiply(self):
        """测试乘法"""
        bridge = CBridge()

        @bridge.decorator
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        result = mul(6, 7)
        assert result == 42

    def test_float_operations(self):
        """测试浮点运算"""
        bridge = CBridge()

        @bridge.decorator
        def add_float(a: float, b: float) -> float:
            return "return a + b;"

        result = add_float(2.5, 3.5)
        assert abs(result - 6.0) < 0.001

    def test_fibonacci(self):
        """测试递归斐波那契"""
        bridge = CBridge()

        @bridge.decorator
        def fib(n: int) -> int:
            return """
            if (n <= 1) return 1;
            return fib(n-1) + fib(n-2);
            """

        result = fib(10)
        assert result == 89

    def test_boolean_result(self):
        """测试布尔返回值"""
        bridge = CBridge()

        @bridge.decorator
        def is_positive(n: int) -> int:
            return "return n > 0;"

        result = is_positive(5)
        assert result == 1
        result = is_positive(-1)
        assert result == 0

    def test_string_length(self):
        """测试字符串操作"""
        bridge = CBridge()

        @bridge.decorator(module_code='#include <string.h>')
        def str_len(s: str) -> int:
            return "return (int)strlen(s);"

        result = str_len("hello")
        assert result == 5

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        bridge = CBridge()

        @bridge.decorator(fallback=py_add)
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(3, 4)
        assert result == 7

    def test_multiple_functions(self):
        """测试多个函数"""
        bridge = CBridge()

        @bridge.decorator
        def add(a: int, b: int) -> int:
            return "return a + b;"

        @bridge.decorator
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        @bridge.decorator
        def sub(a: int, b: int) -> int:
            return "return a - b;"

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5


@pytest.mark.skipif(not C_AVAILABLE, reason="C compiler not available")
class TestCAsync:
    """测试 C 异步模式（需要 C 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        bridge = CBridge()

        @bridge.decorator(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "return a + b;"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7

    def test_async_fib(self):
        """测试异步斐波那契"""
        bridge = CBridge()

        @bridge.decorator(async_mode=True)
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
        bridge = CBridge()

        @bridge.decorator(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "return a * b;"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25]


@pytest.mark.skipif(not C_AVAILABLE, reason="C compiler not available")
class TestCModuleAndDeps:
    """测试 module_code 和 dependencies（需要 C 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        bridge = CBridge()

        @bridge.decorator(module_code='#include <string.h>')
        def str_len(s: str) -> int:
            return "return (int)strlen(s);"

        result = str_len("hello")
        assert result == 5

    def test_dependencies(self):
        """测试依赖函数"""
        bridge = CBridge()

        def get_ten(x: int) -> int:
            return "return 10;"

        @bridge.decorator(deps=[get_ten])
        def add_ten(x: int) -> int:
            return "return x + get_ten(x);"

        result = add_ten(5)
        assert result == 15

    def test_module_and_deps(self):
        """测试 module_code + dependencies 组合"""
        bridge = CBridge()

        def doubler(x: int) -> int:
            return "return x * 2;"

        def tripler(x: int) -> int:
            return "return x * 3;"

        @bridge.decorator(module_code='// shared helpers', deps=[doubler, tripler])
        def compute(x: int) -> int:
            return "return doubler(x) + tripler(x);"

        result = compute(5)
        assert result == 25


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import c as c_module
        assert c_module is not None

    def test_CBridge_instance(self):
        """测试 CBridge 实例属性"""
        bridge = CBridge()
        assert bridge.name == 'c'
        assert bridge.file_ext == '.c'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])