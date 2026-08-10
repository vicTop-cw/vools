"""
Haskell 语言桥接测试

测试 vools.bridge.haskell 模块的基本功能。
需要 GHC (>= 9.0) 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_haskell_bridge.py -v --tb=short
"""

import pytest
import asyncio
from vools.bridge.haskell import (
    haskell,
    haskell_compiler_available,
    is_haskell_available,
    PY_TO_HASKELL_TYPE,
    get_haskell_type,
    infer_haskell_argtypes,
    is_array_type,
    _generate_haskell_source,
    _HASKELL_CACHE_DIR,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_haskell_compiler_available():
    """测试 haskell_compiler_available() 返回 bool"""
    available = haskell_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_is_haskell_available():
    """测试 is_haskell_available() 与 haskell_compiler_available() 一致"""
    assert is_haskell_available() == haskell_compiler_available()


def test_cache_dir_exists():
    """测试缓存目录路径存在"""
    assert isinstance(_HASKELL_CACHE_DIR, str)
    assert len(_HASKELL_CACHE_DIR) > 0


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestHaskellTypeMapping:
    """测试 Python → Haskell 类型映射"""

    def test_py_to_haskell_type(self):
        """PY_TO_HASKELL_TYPE 基本类型映射"""
        assert PY_TO_HASKELL_TYPE[int] == 'Int'
        assert PY_TO_HASKELL_TYPE[float] == 'Double'
        assert PY_TO_HASKELL_TYPE[str] == 'String'
        assert PY_TO_HASKELL_TYPE[bool] == 'Bool'
        assert PY_TO_HASKELL_TYPE[bytes] == 'String'
        assert PY_TO_HASKELL_TYPE[type(None)] == '()'

    def test_get_haskell_type_python_types(self):
        """get_haskell_type() 对 Python 类型的映射"""
        assert get_haskell_type(int) == 'Int'
        assert get_haskell_type(float) == 'Double'
        assert get_haskell_type(bool) == 'Bool'
        assert get_haskell_type(str) == 'String'
        assert get_haskell_type(None) == '()'
        assert get_haskell_type(type(None)) == '()'

    def test_get_haskell_type_string_aliases(self):
        """get_haskell_type() 对字符串别名的映射"""
        assert get_haskell_type('int') == 'Int'
        assert get_haskell_type('integer') == 'Integer'
        assert get_haskell_type('float') == 'Double'
        assert get_haskell_type('double') == 'Double'
        assert get_haskell_type('bool') == 'Bool'
        assert get_haskell_type('boolean') == 'Bool'
        assert get_haskell_type('str') == 'String'
        assert get_haskell_type('string') == 'String'
        assert get_haskell_type('none') == '()'
        assert get_haskell_type('void') == '()'

    def test_get_haskell_type_unknown(self):
        """get_haskell_type() 对未知类型的回退"""
        assert get_haskell_type('unknown_type') == 'Int'

    def test_infer_haskell_argtypes(self):
        """infer_haskell_argtypes() 运行时类型推断"""
        assert infer_haskell_argtypes([1, 2, 3]) == ['Int', 'Int', 'Int']
        assert infer_haskell_argtypes([1.0, 2.0]) == ['Double', 'Double']
        assert infer_haskell_argtypes(['hello', 'world']) == ['String', 'String']
        assert infer_haskell_argtypes([True, False]) == ['Bool', 'Bool']
        assert infer_haskell_argtypes([b'bytes']) == ['String']

    def test_is_array_type(self):
        """is_array_type() 判断是否为数组类型"""
        assert is_array_type('[Int]') is True
        assert is_array_type('[String]') is True
        assert is_array_type('[a]') is True
        assert is_array_type('Int') is False
        assert is_array_type('Double') is False
        assert is_array_type('Bool') is False


# =============================================================================
# 代码生成测试（不需要编译器）
# =============================================================================

class TestHaskellCodeGeneration:
    """测试 Haskell 代码生成"""

    def test_generate_simple_function(self):
        """生成简单的 Haskell 函数代码"""
        code = _generate_haskell_source(
            func_name='add',
            params=[('a', 'Int', False), ('b', 'Int', False)],
            ret_haskell_type='Int',
            body='a + b',
        )
        assert 'module Main where' in code
        assert 'add a b =' in code
        assert 'a + b' in code
        assert 'main = do' in code
        assert 'print (add' in code

    def test_generate_no_params(self):
        """生成无参数的 Haskell 函数"""
        code = _generate_haskell_source(
            func_name='getValue',
            params=[],
            ret_haskell_type='Int',
            body='42',
        )
        assert 'module Main where' in code
        assert 'getValue' in code
        assert '42' in code
        assert 'main = print (getValue)' in code

    def test_generate_string_function(self):
        """生成字符串函数的代码"""
        code = _generate_haskell_source(
            func_name='greet',
            params=[('name', 'String', False)],
            ret_haskell_type='String',
            body='"Hello, " ++ name',
        )
        assert 'module Main where' in code
        assert 'greet name =' in code
        assert '"Hello, " ++ name' in code
        assert 'String' in code

    def test_generate_bool_function(self):
        """生成布尔函数的代码"""
        code = _generate_haskell_source(
            func_name='isEven',
            params=[('n', 'Int', False)],
            ret_haskell_type='Bool',
            body='n `mod` 2 == 0',
        )
        assert 'module Main where' in code
        assert 'isEven' in code
        assert 'n `mod` 2 == 0' in code

    def test_generate_double_function(self):
        """生成浮点函数的代码"""
        code = _generate_haskell_source(
            func_name='half',
            params=[('x', 'Double', False)],
            ret_haskell_type='Double',
            body='x / 2.0',
        )
        assert 'module Main where' in code
        assert 'half x =' in code
        assert 'Double' in code

    def test_generate_with_module_code(self):
        """生成带 module_code 的代码"""
        code = _generate_haskell_source(
            func_name='add',
            params=[('a', 'Int', False), ('b', 'Int', False)],
            ret_haskell_type='Int',
            body='a + b',
            module_code='-- Custom module header',
        )
        assert '-- Custom module header' in code


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestHaskellOnlyCode:
    """测试 @haskell 装饰器的 ONLY_CODE 模式（无需 Haskell 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @haskell(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'module Main where' in result
        assert 'add a b' in result
        assert 'a + b' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @haskell(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'multiply a b' in result
        assert 'a * b' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @haskell(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return '"Hello, " ++ name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'greet name' in result

    def test_only_code_mode_bool(self):
        """测试 ONLY_CODE 模式生成布尔函数代码"""
        @haskell(mode='ONLY_CODE')
        def is_positive(x: int) -> bool:
            return "x > 0"

        result = is_positive(5)
        assert isinstance(result, str)
        assert 'is_positive x' in result

    def test_only_code_mode_multiline(self):
        """测试 ONLY_CODE 模式生成多行函数体代码"""
        @haskell(mode='ONLY_CODE')
        def fib(n: int) -> int:
            return """
            if n <= 1 then 1
            else fib(n-1) + fib(n-2)
            """

        result = fib(10)
        assert isinstance(result, str)
        assert 'fib n' in result
        assert 'fib(n-1) + fib(n-2)' in result

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @haskell(mode='ONLY_CODE', module_code='-- Custom preamble')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '-- Custom preamble' in result


# =============================================================================
# 需要 GHC 编译器的测试
# =============================================================================

HASKELL_AVAILABLE = haskell_compiler_available()


@pytest.mark.skipif(not HASKELL_AVAILABLE, reason="GHC compiler not available")
class TestHaskellDecorator:
    """测试 @haskell 装饰器（需要 GHC 编译器）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @haskell
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(2, 3)
        assert result == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @haskell
        def sub(a: int, b: int) -> int:
            return "a - b"

        result = sub(10, 3)
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @haskell
        def mul(a: int, b: int) -> int:
            return "a * b"

        result = mul(6, 7)
        assert result == 42, "期望 42，实际 {0}".format(result)

    def test_fibonacci(self):
        """测试斐波那契函数"""
        @haskell
        def fib(n: int) -> int:
            return """
            if n <= 1 then 1
            else fib(n-1) + fib(n-2)
            """

        result = fib(10)
        assert result == 89, "期望 89，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @haskell
        def multiply_float(a: float, b: float) -> float:
            return "a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @haskell
        def is_even(n: int) -> bool:
            return "n `mod` 2 == 0"

        result = is_even(4)
        assert result is True
        result = is_even(5)
        assert result is False

    def test_large_input(self):
        """测试大整数"""
        @haskell
        def double_it(x: int) -> int:
            return "x * 2"

        result = double_it(999999)
        assert result == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not HASKELL_AVAILABLE, reason="GHC compiler not available")
class TestHaskellAsync:
    """测试 Haskell 异步模式（需要 GHC 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @haskell(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "a + b"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_async_fibonacci(self):
        """测试异步斐波那契"""
        @haskell(async_mode=True)
        def fib_async(n: int) -> int:
            return """
            if n <= 1 then 1
            else fib_async(n-1) + fib_async(n-2)
            """

        async def run():
            return await fib_async(10)

        result = asyncio.run(run())
        assert result == 89, "期望 89，实际 {0}".format(result)

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @haskell(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "a * b"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25], "期望 [1,4,9,16,25]，实际 {0}".format(results)


@pytest.mark.skipif(not HASKELL_AVAILABLE, reason="GHC compiler not available")
class TestHaskellModuleAndDeps:
    """测试 module_code 和 dependencies（需要 GHC 编译器）"""

    def test_module_code(self):
        """测试 module_code 参数"""
        @haskell(module_code='-- custom module')
        def with_module(x: int) -> int:
            return "x + 10"

        result = with_module(5)
        assert result == 15, "期望 15，实际 {0}".format(result)

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_fallback(x: int) -> int:
            return x * 100

        @haskell(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid haskell code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestHaskellBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import haskell
        assert haskell is not None

    def test_import_compiler_available(self):
        """测试导入 haskell_compiler_available"""
        from vools.bridge import haskell_compiler_available
        assert callable(haskell_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])