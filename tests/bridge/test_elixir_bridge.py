"""
Elixir 语言桥接测试

测试 vools.bridge.elixir 模块的基本功能。
需要 Elixir 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_elixir_bridge.py -v --tb=short
"""

import pytest
import sys
import os
import asyncio
from vools.bridge.elixir import (
    elixir,
    elixir_compiler_available,
    is_elixir_available,
    ElixirBridge,
    PY_TO_ELIXIR_TYPE,
    ELIXIR_TO_CTYPES,
    get_elixir_type,
    infer_elixir_argtypes,
    is_array_type,
    get_ctype_for,
)


# =============================================================================
# 测试辅助
# =============================================================================

ELIXIR_AVAILABLE = elixir_compiler_available()


# =============================================================================
# 编译器检测测试
# =============================================================================

class TestCompilerDetection:
    """测试编译器检测功能"""

    def test_elixir_compiler_available_type(self):
        """测试 elixir_compiler_available 返回 bool"""
        result = elixir_compiler_available()
        assert isinstance(result, bool)

    def test_is_elixir_available(self):
        """测试 is_elixir_available 与 elixir_compiler_available 一致"""
        assert is_elixir_available() == elixir_compiler_available()

    def test_elixirbridge_instance(self):
        """测试 ElixirBridge 实例"""
        bridge = ElixirBridge()
        assert bridge.name == 'elixir'
        assert bridge.file_ext == '.ex'
        assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试
# =============================================================================

class TestTypeMapping:
    """测试 Python ↔ Elixir 类型映射"""

    def test_py_to_elixir_type(self):
        """PY_TO_ELIXIR_TYPE 基本类型映射"""
        assert PY_TO_ELIXIR_TYPE[int] == 'integer'
        assert PY_TO_ELIXIR_TYPE[float] == 'float'
        assert PY_TO_ELIXIR_TYPE[bool] == 'boolean'
        assert PY_TO_ELIXIR_TYPE[str] == 'binary'
        assert PY_TO_ELIXIR_TYPE[bytes] == 'binary'
        assert PY_TO_ELIXIR_TYPE[list] == 'list'
        assert PY_TO_ELIXIR_TYPE[type(None)] == 'none'

    def test_elixir_to_ctypes(self):
        """ELIXIR_TO_CTYPES 到 ctypes 映射"""
        import ctypes
        assert ELIXIR_TO_CTYPES['integer'] is ctypes.c_int64
        assert ELIXIR_TO_CTYPES['float'] is ctypes.c_double
        assert ELIXIR_TO_CTYPES['boolean'] is ctypes.c_bool
        assert ELIXIR_TO_CTYPES['binary'] is ctypes.c_char_p
        assert ELIXIR_TO_CTYPES['list'] is ctypes.c_void_p
        assert ELIXIR_TO_CTYPES['none'] is None

    def test_get_elixir_type_python_types(self):
        """get_elixir_type 对 Python 类型的映射"""
        assert get_elixir_type(int) == 'integer'
        assert get_elixir_type(float) == 'float'
        assert get_elixir_type(bool) == 'boolean'
        assert get_elixir_type(str) == 'binary'
        assert get_elixir_type(type(None)) == 'none'

    def test_get_elixir_type_string_aliases(self):
        """get_elixir_type 对字符串别名的映射"""
        assert get_elixir_type('int') == 'integer'
        assert get_elixir_type('double') == 'float'
        assert get_elixir_type('string') == 'binary'
        assert get_elixir_type('bool') == 'boolean'
        assert get_elixir_type('void') == 'none'
        assert get_elixir_type('none') == 'none'

    def test_infer_elixir_argtypes(self):
        """infer_elixir_argtypes 运行时类型推断"""
        assert infer_elixir_argtypes([1, 2, 3]) == ['integer', 'integer', 'integer']
        assert infer_elixir_argtypes([1.0, 2.0]) == ['float', 'float']
        assert infer_elixir_argtypes(['hello']) == ['binary']
        assert infer_elixir_argtypes([True, False]) == ['boolean', 'boolean']
        assert infer_elixir_argtypes([[1, 2, 3]]) == ['list']

    def test_is_array_type(self):
        """is_array_type 函数"""
        assert is_array_type('list') is True
        assert is_array_type('integer') is False
        assert is_array_type('binary') is False

    def test_get_ctype_for(self):
        """get_ctype_for 函数"""
        import ctypes
        assert get_ctype_for('integer') is ctypes.c_int64
        assert get_ctype_for('float') is ctypes.c_double
        assert get_ctype_for('boolean') is ctypes.c_bool
        assert get_ctype_for('binary') is ctypes.c_char_p


# =============================================================================
# 代码生成测试（不需要编译器）
# =============================================================================

class TestCodeGeneration:
    """测试 Elixir 代码生成"""

    def test_generate_simple_function(self):
        """生成简单函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ElixirBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='a + b',
        )
        code = bridge.generate_code(spec)
        assert 'defmodule' in code
        assert 'def add(' in code
        assert 'a + b' in code

    def test_generate_float_function(self):
        """生成浮点函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ElixirBridge()
        spec = FunctionSpec(
            name='multiply',
            annotations={'x': float, 'y': float, 'return': float},
            args=(),
            defaults={},
            body='x * y',
        )
        code = bridge.generate_code(spec)
        assert 'defmodule' in code
        assert 'def multiply(' in code
        assert 'x * y' in code

    def test_generate_string_function(self):
        """生成字符串函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ElixirBridge()
        spec = FunctionSpec(
            name='greet',
            annotations={'name': str, 'return': str},
            args=(),
            defaults={},
            body='"Hello, " <> name',
        )
        code = bridge.generate_code(spec)
        assert 'defmodule' in code
        assert 'def greet(' in code
        assert '"Hello, " <> name' in code

    def test_generate_with_module_code(self):
        """生成带 module_code 的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ElixirBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='a + b',
            module_code='# Module-level comment',
        )
        code = bridge.generate_code(spec)
        assert 'defmodule' in code
        assert '# Module-level comment' in code

    def test_generate_with_dependencies(self):
        """生成带依赖函数的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ElixirBridge()
        dep_spec = FunctionSpec(
            name='helper',
            annotations={'x': int, 'return': int},
            args=(),
            defaults={},
            body='x * 2',
        )
        spec = FunctionSpec(
            name='main_func',
            annotations={'a': int, 'return': int},
            args=(),
            defaults={},
            body='helper(a) + 1',
            dependencies=[dep_spec],
        )
        code = bridge.generate_code(spec)
        assert 'defmodule' in code
        assert 'def helper(' in code
        assert 'def main_func(' in code
        assert 'x * 2' in code
        assert 'helper(a) + 1' in code


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestDecoratorOnlyCode:
    """测试 @elixir 的 ONLY_CODE 模式（无需 Elixir 编译器）"""

    def test_only_code_basic(self):
        """ONLY_CODE 模式生成基本代码"""
        @elixir(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'defmodule' in result
        assert 'def add(' in result
        assert 'a + b' in result

    def test_only_code_float(self):
        """ONLY_CODE 模式生成浮点函数代码"""
        @elixir(mode='ONLY_CODE')
        def multiply(x: float, y: float) -> float:
            return "x * y"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'defmodule' in result
        assert 'def multiply(' in result
        assert 'x * y' in result

    def test_only_code_multiline(self):
        """ONLY_CODE 模式生成多行函数体"""
        @elixir(mode='ONLY_CODE')
        def fib(n: int) -> int:
            return """
            cond do
              n <= 1 -> 1
              true -> fib(n-1) + fib(n-2)
            end
            """

        result = fib(10)
        assert isinstance(result, str)
        assert 'defmodule' in result
        assert 'def fib(' in result
        assert 'cond do' in result

    def test_only_code_with_module_code(self):
        """ONLY_CODE 模式 + module_code"""
        @elixir(mode='ONLY_CODE', module_code='# custom module')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '# custom module' in result

    def test_only_code_with_deps(self):
        """ONLY_CODE 模式 + 依赖函数"""
        def helper(x: int) -> int:
            return "x * 2"

        @elixir(mode='ONLY_CODE', deps=[helper])
        def main_func(a: int) -> int:
            return "helper(a) + 1"

        result = main_func(5)
        assert isinstance(result, str)
        assert 'def helper(' in result
        assert 'def main_func(' in result
        assert 'x * 2' in result
        assert 'helper(a) + 1' in result


# =============================================================================
# 需要 Elixir 编译器的测试
# =============================================================================

@pytest.mark.skipif(not ELIXIR_AVAILABLE, reason="Elixir compiler not available")
class TestElixirDecorator:
    """测试 @elixir 装饰器（需要 Elixir 编译器）"""

    def test_simple_add(self):
        """测试简单加法"""
        @elixir
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(3, 4)
        assert result == 7

    def test_subtract(self):
        """测试减法"""
        @elixir
        def sub(a: int, b: int) -> int:
            return "a - b"

        result = sub(10, 3)
        assert result == 7

    def test_multiply(self):
        """测试乘法"""
        @elixir
        def mul(a: int, b: int) -> int:
            return "a * b"

        result = mul(6, 7)
        assert result == 42

    def test_float_operations(self):
        """测试浮点运算"""
        @elixir
        def add_float(a: float, b: float) -> float:
            return "a + b"

        result = add_float(2.5, 3.5)
        assert abs(result - 6.0) < 0.05

    def test_fibonacci(self):
        """测试递归斐波那契"""
        @elixir
        def fib(n: int) -> int:
            return """
            cond do
              n <= 1 -> 1
              true -> fib(n-1) + fib(n-2)
            end
            """

        result = fib(10)
        assert result == 89

    def test_boolean_return(self):
        """测试布尔返回值"""
        @elixir
        def is_positive(n: int) -> bool:
            return "n > 0"

        assert is_positive(5) is True
        assert is_positive(-1) is False

    def test_string_concat(self):
        """测试字符串拼接"""
        @elixir
        def greet(name: str) -> str:
            return '"Hello, " <> name'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @elixir(fallback=py_add)
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(3, 4)
        assert result == 7

    def test_multiple_functions(self):
        """测试多个函数"""
        @elixir
        def add(a: int, b: int) -> int:
            return "a + b"

        @elixir
        def mul(a: int, b: int) -> int:
            return "a * b"

        @elixir
        def sub(a: int, b: int) -> int:
            return "a - b"

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5


@pytest.mark.skipif(not ELIXIR_AVAILABLE, reason="Elixir compiler not available")
class TestElixirAsync:
    """测试 Elixir 异步模式（需要 Elixir 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @elixir(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "a + b"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7

    def test_async_fib(self):
        """测试异步斐波那契"""
        @elixir(async_mode=True)
        def fib_async(n: int) -> int:
            return """
            cond do
              n <= 1 -> 1
              true -> fib_async(n-1) + fib_async(n-2)
            end
            """

        async def run():
            return await fib_async(10)

        result = asyncio.run(run())
        assert result == 89

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @elixir(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "a * b"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25]


@pytest.mark.skipif(not ELIXIR_AVAILABLE, reason="Elixir compiler not available")
class TestElixirModuleAndDeps:
    """测试 module_code 和 dependencies（需要 Elixir 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        @elixir(module_code='# Module-level comment')
        def add_ten(x: int) -> int:
            return "x + 10"

        result = add_ten(5)
        assert result == 15

    def test_dependencies(self):
        """测试依赖函数"""
        def get_ten() -> int:
            return "10"

        @elixir(deps=[get_ten])
        def add_ten(x: int) -> int:
            return "x + get_ten()"

        result = add_ten(5)
        assert result == 15

    def test_module_and_deps(self):
        """测试 module_code + dependencies 组合"""
        def double(x: int) -> int:
            return "x * 2"

        def triple(x: int) -> int:
            return "x * 3"

        @elixir(module_code='# shared helpers', deps=[double, triple])
        def compute(x: int) -> int:
            return "double(x) + triple(x)"

        result = compute(5)
        assert result == 25


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import elixir as elixir_module
        assert elixir_module is not None

    def test_ElixirBridge_instance(self):
        """测试 ElixirBridge 实例属性"""
        bridge = ElixirBridge()
        assert bridge.name == 'elixir'
        assert bridge.file_ext == '.ex'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])