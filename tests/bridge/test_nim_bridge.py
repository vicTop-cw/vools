"""
Nim 语言桥接测试

测试 vools.bridge.nim 模块的基本功能。
需要 Nim 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_nim_bridge.py -v --tb=short
"""

import pytest
import asyncio
import ctypes
from vools.bridge.nim import (
    nim,
    nim_compiler_available,
    is_nim_available,
    compile_and_run,
)
from vools.bridge.nim.compiler import (
    PY_TO_NIM_TYPE,
    NIM_TO_CTYPES,
    _generate_nim_wrapper,
    NimBridge,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_nim_compiler_available():
    """测试 nim_compiler_available() 返回 bool"""
    available = nim_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_is_nim_available():
    """测试 is_nim_available() 返回 bool"""
    result = is_nim_available()
    assert isinstance(result, bool)


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestNimTypeMapping:
    """测试 Python → Nim 类型映射"""

    def test_py_to_nim_type(self):
        """PY_TO_NIM_TYPE 基本类型映射"""
        assert PY_TO_NIM_TYPE[int] == 'cint'
        assert PY_TO_NIM_TYPE[float] == 'cdouble'
        assert PY_TO_NIM_TYPE[bool] == 'bool'
        assert PY_TO_NIM_TYPE[str] == 'cstring'
        assert PY_TO_NIM_TYPE[bytes] == 'cstring'

    def test_nim_to_ctypes(self):
        """NIM_TO_CTYPES 到 ctypes 映射"""
        assert NIM_TO_CTYPES['cint'] is ctypes.c_int
        assert NIM_TO_CTYPES['cdouble'] is ctypes.c_double
        assert NIM_TO_CTYPES['bool'] is ctypes.c_bool
        assert NIM_TO_CTYPES['cstring'] is ctypes.c_char_p
        assert NIM_TO_CTYPES['string'] is ctypes.c_char_p


# =============================================================================
# 代码生成测试（不需要编译器）
# =============================================================================

class TestNimCodeGeneration:
    """测试 Nim 代码生成"""

    def test_generate_simple_function(self):
        """生成简单的 Nim 函数代码"""
        code = _generate_nim_wrapper(
            func_name='add',
            args=(1, 2),
            nim_body='result = a + b',
            ret_type='cint',
            arg_names=['a', 'b'],
        )
        assert 'proc add*' in code
        assert 'a: cint' in code
        assert 'b: cint' in code
        assert 'result = a + b' in code
        assert 'exportc' in code

    def test_generate_void_function(self):
        """生成无返回值的 Nim 函数"""
        code = _generate_nim_wrapper(
            func_name='hello',
            args=(1,),
            nim_body='echo "hello"',
            ret_type='void',
            arg_names=None,
        )
        assert 'proc hello*' in code
        assert 'echo "hello"' in code
        assert 'exportc' in code

    def test_generate_float_function(self):
        """生成浮点函数的 Nim 代码"""
        code = _generate_nim_wrapper(
            func_name='half',
            args=(1.0,),
            nim_body='result = x / 2.0',
            ret_type='cdouble',
            arg_names=['x'],
        )
        assert 'proc half*' in code
        assert 'x: cdouble' in code
        assert 'result = x / 2.0' in code

    def test_bridge_instance(self):
        """测试 NimBridge 实例"""
        bridge = NimBridge()
        assert bridge.name == 'nim'
        assert bridge.file_ext == '.nim'
        assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestNimOnlyCode:
    """测试 @nim 装饰器的 ONLY_CODE 模式（无需 Nim 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @nim(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "result = a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'proc add*' in result
        assert 'result = a + b' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @nim(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "result = a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'proc multiply*' in result
        assert 'result = a * b' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @nim(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return 'result = "Hello, " & name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'proc greet*' in result

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @nim(mode='ONLY_CODE', module_code='# Custom preamble')
        def add(a: int, b: int) -> int:
            return "result = a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '# Custom preamble' in result


# =============================================================================
# 需要 Nim 编译器的测试
# =============================================================================

NIM_AVAILABLE = nim_compiler_available()


@pytest.mark.skipif(not NIM_AVAILABLE, reason="Nim compiler not available")
class TestNimDecorator:
    """测试 @nim 装饰器（需要 Nim 编译器）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @nim
        def add(a: int, b: int) -> int:
            return "result = a + b"

        result = add(2, 3)
        assert result == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @nim
        def sub(a: int, b: int) -> int:
            return "result = a - b"

        result = sub(10, 3)
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @nim
        def mul(a: int, b: int) -> int:
            return "result = a * b"

        result = mul(6, 7)
        assert result == 42, "期望 42，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @nim
        def multiply_float(a: float, b: float) -> float:
            return "result = a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @nim
        def is_even(n: int) -> bool:
            return "result = n mod 2 == 0"

        result = is_even(4)
        assert result is True
        result = is_even(5)
        assert result is False

    def test_large_input(self):
        """测试大整数"""
        @nim
        def double_it(x: int) -> int:
            return "result = x * 2"

        result = double_it(999999)
        assert result == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not NIM_AVAILABLE, reason="Nim compiler not available")
class TestNimAsync:
    """测试 Nim 异步模式（需要 Nim 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @nim(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "result = a + b"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @nim(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "result = a * b"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25], "期望 [1,4,9,16,25]，实际 {0}".format(results)


@pytest.mark.skipif(not NIM_AVAILABLE, reason="Nim compiler not available")
class TestNimFallback:
    """测试回退机制（需要 Nim 编译器）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @nim(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid nim code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestNimBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import nim
        assert nim is not None

    def test_import_compiler_available(self):
        """测试导入 nim_compiler_available"""
        from vools.bridge import nim_compiler_available
        assert callable(nim_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])