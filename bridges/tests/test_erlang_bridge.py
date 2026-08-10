"""
Erlang 语言桥接测试

测试 vools.bridge.erlang 模块的基本功能。
需要 Erlang 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_erlang_bridge.py -v --tb=short
"""

import pytest
import sys
import os
import asyncio
from vools.bridge.erlang import (
    erlang,
    erlang_compiler_available,
    is_erlang_available,
    ErlangBridge,
    PY_TO_ERLANG_TYPE,
    ERLANG_TO_CTYPES,
    get_erlang_type,
    infer_erlang_argtypes,
    is_array_type,
    get_ctype_for,
)


# =============================================================================
# 测试辅助
# =============================================================================

ERLANG_AVAILABLE = erlang_compiler_available()


# =============================================================================
# 编译器检测测试
# =============================================================================

class TestCompilerDetection:
    """测试编译器检测功能"""

    def test_erlang_compiler_available_type(self):
        """测试 erlang_compiler_available 返回 bool"""
        result = erlang_compiler_available()
        assert isinstance(result, bool)

    def test_is_erlang_available(self):
        """测试 is_erlang_available 与 erlang_compiler_available 一致"""
        assert is_erlang_available() == erlang_compiler_available()

    def test_erlangbridge_instance(self):
        """测试 ErlangBridge 实例"""
        bridge = ErlangBridge()
        assert bridge.name == 'erlang'
        assert bridge.file_ext == '.erl'
        assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试
# =============================================================================

class TestTypeMapping:
    """测试 Python ↔ Erlang 类型映射"""

    def test_py_to_erlang_type(self):
        """PY_TO_ERLANG_TYPE 基本类型映射"""
        assert PY_TO_ERLANG_TYPE[int] == 'integer'
        assert PY_TO_ERLANG_TYPE[float] == 'float'
        assert PY_TO_ERLANG_TYPE[bool] == 'boolean'
        assert PY_TO_ERLANG_TYPE[str] == 'binary'
        assert PY_TO_ERLANG_TYPE[bytes] == 'binary'
        assert PY_TO_ERLANG_TYPE[list] == 'list'
        assert PY_TO_ERLANG_TYPE[type(None)] == 'none'

    def test_erlang_to_ctypes(self):
        """ERLANG_TO_CTYPES 到 ctypes 映射"""
        import ctypes
        assert ERLANG_TO_CTYPES['integer'] is ctypes.c_int64
        assert ERLANG_TO_CTYPES['float'] is ctypes.c_double
        assert ERLANG_TO_CTYPES['boolean'] is ctypes.c_bool
        assert ERLANG_TO_CTYPES['binary'] is ctypes.c_char_p
        assert ERLANG_TO_CTYPES['list'] is ctypes.c_void_p
        assert ERLANG_TO_CTYPES['none'] is None

    def test_get_erlang_type_python_types(self):
        """get_erlang_type 对 Python 类型的映射"""
        assert get_erlang_type(int) == 'integer'
        assert get_erlang_type(float) == 'float'
        assert get_erlang_type(bool) == 'boolean'
        assert get_erlang_type(str) == 'binary'
        assert get_erlang_type(type(None)) == 'none'

    def test_get_erlang_type_string_aliases(self):
        """get_erlang_type 对字符串别名的映射"""
        assert get_erlang_type('int') == 'integer'
        assert get_erlang_type('double') == 'float'
        assert get_erlang_type('string') == 'binary'
        assert get_erlang_type('bool') == 'boolean'
        assert get_erlang_type('void') == 'none'
        assert get_erlang_type('none') == 'none'

    def test_infer_erlang_argtypes(self):
        """infer_erlang_argtypes 运行时类型推断"""
        assert infer_erlang_argtypes([1, 2, 3]) == ['integer', 'integer', 'integer']
        assert infer_erlang_argtypes([1.0, 2.0]) == ['float', 'float']
        assert infer_erlang_argtypes(['hello']) == ['binary']
        assert infer_erlang_argtypes([True, False]) == ['boolean', 'boolean']
        assert infer_erlang_argtypes([[1, 2, 3]]) == ['list']

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
    """测试 Erlang 代码生成"""

    def test_generate_simple_function(self):
        """生成简单函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ErlangBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='A + B.',
        )
        code = bridge.generate_code(spec)
        assert '-module(' in code
        assert '-export([' in code
        assert 'add(' in code
        assert 'A + B' in code

    def test_generate_float_function(self):
        """生成浮点函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ErlangBridge()
        spec = FunctionSpec(
            name='multiply',
            annotations={'x': float, 'y': float, 'return': float},
            args=(),
            defaults={},
            body='X * Y.',
        )
        code = bridge.generate_code(spec)
        assert '-module(' in code
        assert '-export([' in code
        assert 'multiply(' in code
        assert 'X * Y' in code

    def test_generate_bool_function(self):
        """生成布尔函数代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ErlangBridge()
        spec = FunctionSpec(
            name='is_positive',
            annotations={'n': int, 'return': bool},
            args=(),
            defaults={},
            body='N > 0.',
        )
        code = bridge.generate_code(spec)
        assert '-module(' in code
        assert '-export([' in code
        assert 'is_positive(' in code
        assert 'N > 0' in code

    def test_generate_with_module_code(self):
        """生成带 module_code 的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ErlangBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='A + B.',
            module_code='% Module-level comment',
        )
        code = bridge.generate_code(spec)
        assert '-module(' in code
        assert '% Module-level comment' in code

    def test_generate_with_dependencies(self):
        """生成带依赖函数的代码"""
        from vools.bridge._base import FunctionSpec

        bridge = ErlangBridge()
        dep_spec = FunctionSpec(
            name='helper',
            annotations={'x': int, 'return': int},
            args=(),
            defaults={},
            body='X * 2.',
        )
        spec = FunctionSpec(
            name='main_func',
            annotations={'a': int, 'return': int},
            args=(),
            defaults={},
            body='helper(A) + 1.',
            dependencies=[dep_spec],
        )
        code = bridge.generate_code(spec)
        assert '-module(' in code
        assert '-export([' in code
        assert 'helper(' in code
        assert 'main_func(' in code
        assert 'X * 2' in code
        assert 'helper(A) + 1' in code


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestDecoratorOnlyCode:
    """测试 @erlang 的 ONLY_CODE 模式（无需 Erlang 编译器）"""

    def test_only_code_basic(self):
        """ONLY_CODE 模式生成基本代码"""
        @erlang(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "A + B."

        result = add(1, 2)
        assert isinstance(result, str)
        assert '-module(' in result
        assert '-export([' in result
        assert 'add(' in result
        assert 'A + B' in result

    def test_only_code_float(self):
        """ONLY_CODE 模式生成浮点函数代码"""
        @erlang(mode='ONLY_CODE')
        def multiply(x: float, y: float) -> float:
            return "X * Y."

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert '-module(' in result
        assert '-export([' in result
        assert 'multiply(' in result
        assert 'X * Y' in result

    def test_only_code_multiline(self):
        """ONLY_CODE 模式生成多行函数体"""
        @erlang(mode='ONLY_CODE')
        def fib(n: int) -> int:
            return """
            if N =< 1 -> 1;
               true -> fib(N-1) + fib(N-2)
            end.
            """

        result = fib(10)
        assert isinstance(result, str)
        assert '-module(' in result
        assert 'fib(' in result
        assert 'if N =< 1' in result

    def test_only_code_with_module_code(self):
        """ONLY_CODE 模式 + module_code"""
        @erlang(mode='ONLY_CODE', module_code='% custom module')
        def add(a: int, b: int) -> int:
            return "A + B."

        result = add(1, 2)
        assert isinstance(result, str)
        assert '% custom module' in result

    def test_only_code_with_deps(self):
        """ONLY_CODE 模式 + 依赖函数"""
        def helper(x: int) -> int:
            return "X * 2."

        @erlang(mode='ONLY_CODE', deps=[helper])
        def main_func(a: int) -> int:
            return "helper(A) + 1."

        result = main_func(5)
        assert isinstance(result, str)
        assert 'helper(' in result
        assert 'main_func(' in result
        assert 'X * 2' in result
        assert 'helper(A) + 1' in result


# =============================================================================
# 需要 Erlang 编译器的测试
# =============================================================================

@pytest.mark.skipif(not ERLANG_AVAILABLE, reason="Erlang compiler not available")
class TestErlangDecorator:
    """测试 @erlang 装饰器（需要 Erlang 编译器）"""

    def test_simple_add(self):
        """测试简单加法"""
        @erlang
        def add(a: int, b: int) -> int:
            return "A + B."

        result = add(3, 4)
        assert result == 7

    def test_subtract(self):
        """测试减法"""
        @erlang
        def sub(a: int, b: int) -> int:
            return "A - B."

        result = sub(10, 3)
        assert result == 7

    def test_multiply(self):
        """测试乘法"""
        @erlang
        def mul(a: int, b: int) -> int:
            return "A * B."

        result = mul(6, 7)
        assert result == 42

    def test_float_operations(self):
        """测试浮点运算"""
        @erlang
        def add_float(a: float, b: float) -> float:
            return "A + B."

        result = add_float(2.5, 3.5)
        assert abs(result - 6.0) < 0.05

    def test_fibonacci(self):
        """测试递归斐波那契"""
        @erlang
        def fib(n: int) -> int:
            return """
            if N =< 1 -> 1;
               true -> fib(N-1) + fib(N-2)
            end.
            """

        result = fib(10)
        assert result == 89

    def test_boolean_return(self):
        """测试布尔返回值"""
        @erlang
        def is_positive(n: int) -> bool:
            return "N > 0."

        assert is_positive(5) is True
        assert is_positive(-1) is False

    def test_string_return(self):
        """测试字符串返回值"""
        @erlang
        def hello() -> str:
            return '"Hello, World".'

        result = hello()
        assert "Hello" in str(result)

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @erlang(fallback=py_add)
        def add(a: int, b: int) -> int:
            return "A + B."

        result = add(3, 4)
        assert result == 7

    def test_multiple_functions(self):
        """测试多个函数"""
        @erlang
        def add(a: int, b: int) -> int:
            return "A + B."

        @erlang
        def mul(a: int, b: int) -> int:
            return "A * B."

        @erlang
        def sub(a: int, b: int) -> int:
            return "A - B."

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5


@pytest.mark.skipif(not ERLANG_AVAILABLE, reason="Erlang compiler not available")
class TestErlangAsync:
    """测试 Erlang 异步模式（需要 Erlang 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @erlang(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "A + B."

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7

    def test_async_fib(self):
        """测试异步斐波那契"""
        @erlang(async_mode=True)
        def fib_async(n: int) -> int:
            return """
            if N =< 1 -> 1;
               true -> fib_async(N-1) + fib_async(N-2)
            end.
            """

        async def run():
            return await fib_async(10)

        result = asyncio.run(run())
        assert result == 89

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @erlang(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "A * B."

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25]


@pytest.mark.skipif(not ERLANG_AVAILABLE, reason="Erlang compiler not available")
class TestErlangModuleAndDeps:
    """测试 module_code 和 dependencies（需要 Erlang 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        @erlang(module_code='% Module-level comment')
        def add_ten(x: int) -> int:
            return "X + 10."

        result = add_ten(5)
        assert result == 15

    def test_dependencies(self):
        """测试依赖函数"""
        def get_ten() -> int:
            return "10."

        @erlang(deps=[get_ten])
        def add_ten(x: int) -> int:
            return "X + get_ten()."

        result = add_ten(5)
        assert result == 15

    def test_module_and_deps(self):
        """测试 module_code + dependencies 组合"""
        def double(x: int) -> int:
            return "X * 2."

        def triple(x: int) -> int:
            return "X * 3."

        @erlang(module_code='% shared helpers', deps=[double, triple])
        def compute(x: int) -> int:
            return "double(X) + triple(X)."

        result = compute(5)
        assert result == 25


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import erlang as erlang_module
        assert erlang_module is not None

    def test_ErlangBridge_instance(self):
        """测试 ErlangBridge 实例属性"""
        bridge = ErlangBridge()
        assert bridge.name == 'erlang'
        assert bridge.file_ext == '.erl'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])