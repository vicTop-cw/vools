"""
Swift 语言桥接测试

测试 vools.bridge.swift 模块的基本功能。
需要 Swift 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_swift_bridge.py -v --tb=short
"""

import pytest
import asyncio
import ctypes
from vools.bridge.swift import (
    swift,
    swiftc,
    swift_compiler_available,
    SwiftBridge,
    swift_bridge,
    PY_TO_SWIFT_TYPE,
    SWIFT_TO_CTYPES,
    get_swift_type,
    get_swift_ctype,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_swift_compiler_available():
    """测试 swift_compiler_available() 返回 bool"""
    available = swift_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_swift_bridge_instance():
    """测试 SwiftBridge 实例"""
    bridge = swift_bridge
    assert bridge.name == 'swift'
    assert bridge.file_ext == '.swift'
    assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestSwiftTypeMapping:
    """测试 Python → Swift 类型映射"""

    def test_py_to_swift_type(self):
        """PY_TO_SWIFT_TYPE 基本类型映射"""
        assert PY_TO_SWIFT_TYPE[int] == 'Int'
        assert PY_TO_SWIFT_TYPE[float] == 'Double'
        assert PY_TO_SWIFT_TYPE[str] == 'String'
        assert PY_TO_SWIFT_TYPE[bool] == 'Bool'
        assert PY_TO_SWIFT_TYPE[list] == '[Int]'
        assert PY_TO_SWIFT_TYPE[dict] == '[String: Any]'
        assert PY_TO_SWIFT_TYPE[type(None)] == 'Void'

    def test_swift_to_ctypes(self):
        """SWIFT_TO_CTYPES 到 ctypes 映射"""
        assert SWIFT_TO_CTYPES['Int'] is ctypes.c_int
        assert SWIFT_TO_CTYPES['Int64'] is ctypes.c_int64
        assert SWIFT_TO_CTYPES['Double'] is ctypes.c_double
        assert SWIFT_TO_CTYPES['Bool'] is ctypes.c_bool
        assert SWIFT_TO_CTYPES['String'] is ctypes.c_char_p
        assert SWIFT_TO_CTYPES['Void'] is None

    def test_get_swift_type_python_types(self):
        """get_swift_type() 对 Python 类型的映射"""
        assert get_swift_type(int) == 'Int'
        assert get_swift_type(float) == 'Double'
        assert get_swift_type(bool) == 'Bool'
        assert get_swift_type(str) == 'String'

    def test_get_swift_type_unknown(self):
        """get_swift_type() 对未知类型的回退"""
        assert get_swift_type(bytes) == 'String'

    def test_get_swift_ctype(self):
        """get_swift_ctype() 映射"""
        assert get_swift_ctype('Int') is ctypes.c_int
        assert get_swift_ctype('Double') is ctypes.c_double
        assert get_swift_ctype('Bool') is ctypes.c_bool
        assert get_swift_ctype('String') is ctypes.c_char_p


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestSwiftOnlyCode:
    """测试 @swift 装饰器的 ONLY_CODE 模式（无需 Swift 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @swift(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'func add(' in result
        assert 'return a + b' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @swift(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "return a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'func multiply(' in result
        assert 'return a * b' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @swift(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return 'return "Hello, " + name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'func greet(' in result

    def test_only_code_mode_bool(self):
        """测试 ONLY_CODE 模式生成布尔函数代码"""
        @swift(mode='ONLY_CODE')
        def is_positive(x: int) -> bool:
            return "return x > 0"

        result = is_positive(5)
        assert isinstance(result, str)
        assert 'func is_positive(' in result

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @swift(mode='ONLY_CODE', module_code='// Custom preamble')
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '// Custom preamble' in result


# =============================================================================
# 需要 Swift 编译器的测试
# =============================================================================

SWIFT_AVAILABLE = swift_compiler_available()


@pytest.mark.skipif(not SWIFT_AVAILABLE, reason="Swift compiler not available")
class TestSwiftDecorator:
    """测试 @swift 装饰器（需要 Swift 编译器）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @swift
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(2, 3)
        assert result == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @swift
        def sub(a: int, b: int) -> int:
            return "return a - b"

        result = sub(10, 3)
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @swift
        def mul(a: int, b: int) -> int:
            return "return a * b"

        result = mul(6, 7)
        assert result == 42, "期望 42，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @swift
        def multiply_float(a: float, b: float) -> float:
            return "return a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @swift
        def is_even(n: int) -> bool:
            return "return n % 2 == 0"

        result = is_even(4)
        assert result is True
        result = is_even(5)
        assert result is False

    def test_large_input(self):
        """测试大整数"""
        @swift
        def double_it(x: int) -> int:
            return "return x * 2"

        result = double_it(999999)
        assert result == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not SWIFT_AVAILABLE, reason="Swift compiler not available")
class TestSwiftAsync:
    """测试 Swift 异步模式（需要 Swift 编译器）"""

    def test_async_add(self):
        """测试异步加法"""
        @swift(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "return a + b"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @swift(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "return a * b"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25], "期望 [1,4,9,16,25]，实际 {0}".format(results)


@pytest.mark.skipif(not SWIFT_AVAILABLE, reason="Swift compiler not available")
class TestSwiftFallback:
    """测试回退机制（需要 Swift 编译器）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @swift(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid swift code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestSwiftBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import swift
        assert swift is not None

    def test_import_compiler_available(self):
        """测试导入 swift_compiler_available"""
        from vools.bridge import swift_compiler_available
        assert callable(swift_compiler_available)

    def test_bridge_class(self):
        """测试 SwiftBridge 类"""
        bridge = SwiftBridge()
        assert bridge.name == 'swift'
        assert bridge.file_ext == '.swift'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])