"""
测试 vools.bridge.go 模块

测试 Go 桥接的编译器检测、类型映射、代码生成、简单函数调用、
异步模式和 module_code/dependencies 等功能。

运行：python -m pytest tests/bridge/test_go_bridge.py -v --tb=short
"""

import pytest
import asyncio
import ctypes
from vools.bridge.go import (
    go,
    go_compiler_available,
    is_go_available,
    PY_TO_GO_TYPE,
    GO_TO_CTYPES,
    get_go_type,
    infer_go_argtypes,
    _generate_go_source,
)


# ============================================================================
# 编译器可用性检测
# ============================================================================

def test_go_compiler_available():
    """测试 go_compiler_available() 返回 bool"""
    available = go_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_is_go_available():
    """测试 is_go_available() 与 go_compiler_available() 一致"""
    assert is_go_available() == go_compiler_available()


# ============================================================================
# 类型映射测试（不需要编译器）
# ============================================================================

class TestTypeMapping:
    """测试 Python ↔ Go 类型映射"""

    def test_py_to_go_type(self):
        """PY_TO_GO_TYPE 基本类型映射"""
        assert PY_TO_GO_TYPE[int] == 'C.longlong'
        assert PY_TO_GO_TYPE[float] == 'C.double'
        assert PY_TO_GO_TYPE[str] == '*C.char'
        assert PY_TO_GO_TYPE[bool] == 'C.bool'
        assert PY_TO_GO_TYPE[bytes] == 'unsafe.Pointer'
        assert PY_TO_GO_TYPE[list] == 'unsafe.Pointer'

    def test_go_to_ctypes(self):
        """GO_TO_CTYPES 到 ctypes 映射"""
        assert GO_TO_CTYPES['C.longlong'] is ctypes.c_int64
        assert GO_TO_CTYPES['C.double'] is ctypes.c_double
        assert GO_TO_CTYPES['C.bool'] is ctypes.c_bool
        assert GO_TO_CTYPES['*C.char'] is ctypes.c_char_p
        assert GO_TO_CTYPES['unsafe.Pointer'] is ctypes.c_void_p
        assert GO_TO_CTYPES['C.void'] is None
        assert GO_TO_CTYPES['C.int'] is ctypes.c_int32

    def test_get_go_type_python_types(self):
        """get_go_type() 对 Python 类型的映射"""
        assert get_go_type(int) == 'C.longlong'
        assert get_go_type(float) == 'C.double'
        assert get_go_type(bool) == 'C.bool'
        assert get_go_type(str) == '*C.char'
        assert get_go_type(type(None)) == 'C.void'

    def test_get_go_type_string_aliases(self):
        """get_go_type() 对字符串别名的映射"""
        assert get_go_type('int') == 'C.longlong'
        assert get_go_type('int64') == 'C.longlong'
        assert get_go_type('float') == 'C.double'
        assert get_go_type('float64') == 'C.double'
        assert get_go_type('string') == '*C.char'
        assert get_go_type('bool') == 'C.bool'
        assert get_go_type('void') == 'C.void'
        assert get_go_type('none') == 'C.void'

    def test_get_go_type_unknown(self):
        """get_go_type() 对未知类型的回退"""
        assert get_go_type('unknown_type') == 'C.longlong'

    def test_infer_go_argtypes(self):
        """infer_go_argtypes() 运行时类型推断"""
        assert infer_go_argtypes([1, 2, 3]) == ['C.longlong', 'C.longlong', 'C.longlong']
        assert infer_go_argtypes([1.0, 2.0]) == ['C.double', 'C.double']
        assert infer_go_argtypes(['hello', 'world']) == ['*C.char', '*C.char']
        assert infer_go_argtypes([True, False]) == ['C.bool', 'C.bool']
        assert infer_go_argtypes([b'bytes']) == ['unsafe.Pointer']
        assert infer_go_argtypes([[1, 2, 3]]) == ['unsafe.Pointer']


# ============================================================================
# 代码生成测试（不需要编译器）
# ============================================================================

class TestCodeGeneration:
    """测试 Go 代码生成"""

    def test_generate_simple_function(self):
        """生成简单的 Go 函数代码"""
        code = _generate_go_source(
            func_name='add',
            params=[('a', 'C.longlong', False), ('b', 'C.longlong', False)],
            ret_go_type='C.longlong',
            body='return int64(a) + int64(b)',
        )
        assert 'package main' in code
        assert 'import "C"' in code
        assert '//export add' in code
        assert 'func add(' in code
        assert 'C.longlong' in code
        assert 'return int64(a) + int64(b)' in code
        assert 'func main() {}' in code

    def test_generate_void_function(self):
        """生成无返回值的 Go 函数"""
        code = _generate_go_source(
            func_name='hello',
            params=[('name', '*C.char', False)],
            ret_go_type='C.void',
            body='// print nothing',
        )
        assert '//export hello' in code
        assert 'func hello(' in code
        assert 'func main() {}' in code

    def test_generate_array_function(self):
        """生成带数组参数的 Go 函数"""
        code = _generate_go_source(
            func_name='sum',
            params=[('arr', 'unsafe.Pointer', True)],
            ret_go_type='C.longlong',
            body='total := int64(0)\nfor i := int64(0); i < int64(arr_n); i++ { }\nreturn total',
        )
        assert '//export sum' in code
        assert 'arr unsafe.Pointer' in code
        assert 'arr_n C.longlong' in code
        assert 'func main() {}' in code

    def test_generate_no_params(self):
        """生成无参数的 Go 函数"""
        code = _generate_go_source(
            func_name='get_value',
            params=[],
            ret_go_type='C.longlong',
            body='return 42',
        )
        assert '//export get_value' in code
        assert 'func get_value()' in code
        assert 'return 42' in code


# ============================================================================
# 装饰器模式测试（部分不需要编译器）
# ============================================================================

class TestDecoratorModes:
    """测试装饰器的各种模式"""

    def test_only_code_mode(self):
        """ONLY_CODE 模式：只生成代码不编译"""
        @go(mode='ONLY_CODE')
        def example(x: int) -> int:
            return "return int64(x) * 2"

        code = example(5)
        assert isinstance(code, str)
        assert 'package main' in code
        assert '//export example' in code
        assert 'func example(' in code
        assert 'func main() {}' in code

    def test_only_code_with_module_code(self):
        """ONLY_CODE 模式 + module_code"""
        @go(mode='ONLY_CODE', module_code='// custom module header')
        def with_module(x: int) -> int:
            return "return int64(x) + 1"

        code = with_module(5)
        assert isinstance(code, str)
        assert '// custom module header' in code

    def test_only_code_with_dependencies(self):
        """ONLY_CODE 模式 + 依赖函数"""
        def helper() -> int:
            return "return 100"

        @go(mode='ONLY_CODE', deps=[helper])
        def main_func(x: int) -> int:
            return "return int64(x) + helper()"

        code = main_func(5)
        assert isinstance(code, str)
        assert '//export helper' in code
        assert '//export main_func' in code
        assert 'func helper(' in code
        assert 'func main_func(' in code

    def test_only_code_module_and_deps(self):
        """ONLY_CODE 模式：同时使用 module_code 和 dependencies"""
        def add_one(x: int) -> int:
            return "return int64(x) + 1"

        def mul_two(x: int) -> int:
            return "return int64(x) * 2"

        @go(mode='ONLY_CODE', module_code='// shared helpers', deps=[add_one, mul_two])
        def compute(x: int) -> int:
            return "return mul_two(add_one(int64(x)))"

        code = compute(5)
        assert isinstance(code, str)
        assert '// shared helpers' in code
        assert '//export add_one' in code
        assert '//export mul_two' in code
        assert '//export compute' in code


# ============================================================================
# 需要 Go 编译器的测试
# ============================================================================

GO_AVAILABLE = go_compiler_available()


@pytest.mark.skipif(not GO_AVAILABLE, reason="Go compiler not available")
class TestGoDecorator:
    """测试 Go 装饰器（需要 Go 编译器）"""

    def test_simple_add(self):
        """测试简单的加法函数"""
        @go
        def add(a: int, b: int) -> int:
            return "return C.longlong(int64(a) + int64(b))"

        result = add(2, 3)
        assert result == 5, f"期望 5，实际 {result}"

    def test_subtract(self):
        """测试减法函数"""
        @go
        def sub(a: int, b: int) -> int:
            return "return C.longlong(int64(a) - int64(b))"

        result = sub(10, 3)
        assert result == 7, f"期望 7，实际 {result}"

    def test_multiply(self):
        """测试乘法函数"""
        @go
        def mul(a: int, b: int) -> int:
            return "return C.longlong(int64(a) * int64(b))"

        result = mul(6, 7)
        assert result == 42, f"期望 42，实际 {result}"

    def test_float_operations(self):
        """测试浮点运算"""
        @go
        def add_float(a: float, b: float) -> float:
            return "return C.double(float64(a) + float64(b))"

        result = add_float(2.5, 3.5)
        assert abs(result - 6.0) < 0.001, f"期望 6.0，实际 {result}"

    def test_bool_return(self):
        """测试布尔返回值"""
        @go
        def is_positive(n: int) -> bool:
            return "return C.bool(int64(n) > 0)"

        assert is_positive(5) is True
        assert is_positive(-1) is False

    def test_large_input(self):
        """测试大整数"""
        @go
        def double_it(x: int) -> int:
            return "return C.longlong(int64(x) * 2)"

        result = double_it(999999)
        assert result == 1999998, f"期望 1999998，实际 {result}"


@pytest.mark.skipif(not GO_AVAILABLE, reason="Go compiler not available")
class TestGoAsync:
    """测试 Go 异步模式（需要 Go 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @go(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "return C.longlong(int64(a) + int64(b))"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7, f"期望 7，实际 {result}"

    def test_async_fibonacci(self):
        """测试异步斐波那契"""
        @go(async_mode=True)
        def fib(n: int) -> int:
            return """
            if int64(n) <= 1 {
                return C.longlong(1)
            }
            return C.longlong(fib(n-1) + fib(n-2))
            """

        async def run():
            return await fib(10)

        result = asyncio.run(run())
        assert result == 89, f"期望 89，实际 {result}"

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @go(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "return C.longlong(int64(a) * int64(b))"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25], f"期望 [1,4,9,16,25]，实际 {results}"


@pytest.mark.skipif(not GO_AVAILABLE, reason="Go compiler not available")
class TestGoModuleAndDeps:
    """测试 module_code 和 dependencies（需要 Go 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        @go(module_code='// custom module')
        def with_module(x: int) -> int:
            return "return C.longlong(int64(x) + 10)"

        result = with_module(5)
        assert result == 15, f"期望 15，实际 {result}"

    def test_dependencies(self):
        """测试依赖函数"""
        def get_ten() -> int:
            return "return C.longlong(10)"

        @go(deps=[get_ten])
        def add_ten(x: int) -> int:
            return "return C.longlong(int64(x) + int64(get_ten()))"

        result = add_ten(5)
        assert result == 15, f"期望 15，实际 {result}"

    def test_module_and_deps(self):
        """测试 module_code + dependencies 组合"""
        def double_it(x: int) -> int:
            return "return C.longlong(int64(x) * 2)"

        def triple_it(x: int) -> int:
            return "return C.longlong(int64(x) * 3)"

        @go(module_code='// combined helpers', deps=[double_it, triple_it])
        def compute(x: int) -> int:
            return "return C.longlong(double_it(x) + triple_it(x))"

        result = compute(5)
        assert result == 25, f"期望 25 (10+15)，实际 {result}"


@pytest.mark.skipif(not GO_AVAILABLE, reason="Go compiler not available")
class TestGoFallback:
    """测试回退机制（需要 Go 编译器）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @go(fallback=py_fallback)
        def bad_func(x: int) -> int:
            # 无效的 Go 代码
            return "this is not valid go code !!!"

        result = bad_func(5)
        assert result == 500, f"期望 500，实际 {result}"