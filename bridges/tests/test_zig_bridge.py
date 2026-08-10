"""
Zig 语言桥接测试

测试 vools.bridge.zig 模块的基本功能。
需要 Zig 编译器才能运行完整测试。

运行：python -m pytest tests/bridge/test_zig_bridge.py -v --tb=short
"""

import pytest
import asyncio
import ctypes
from vools.bridge.zig import (
    zig,
    zigc,
    zig_compiler_available,
    ZigBridge,
    zig_bridge,
    PY_TO_ZIG_TYPE,
    ZIG_TO_CTYPES,
    get_zig_type,
    get_zig_ctype,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_zig_compiler_available():
    """测试 zig_compiler_available() 返回 bool"""
    available = zig_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_zig_bridge_instance():
    """测试 ZigBridge 实例"""
    bridge = zig_bridge
    assert bridge.name == 'zig'
    assert bridge.file_ext == '.zig'
    assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestZigTypeMapping:
    """测试 Python → Zig 类型映射"""

    def test_py_to_zig_type(self):
        """PY_TO_ZIG_TYPE 基本类型映射"""
        assert PY_TO_ZIG_TYPE[int] == 'i64'
        assert PY_TO_ZIG_TYPE[float] == 'f64'
        assert PY_TO_ZIG_TYPE[str] == '[*:0]const u8'
        assert PY_TO_ZIG_TYPE[bool] == 'bool'
        assert PY_TO_ZIG_TYPE[list] == '[]i64'
        assert PY_TO_ZIG_TYPE[type(None)] == 'void'

    def test_zig_to_ctypes(self):
        """ZIG_TO_CTYPES 到 ctypes 映射"""
        assert ZIG_TO_CTYPES['i8'] is ctypes.c_int8
        assert ZIG_TO_CTYPES['i16'] is ctypes.c_int16
        assert ZIG_TO_CTYPES['i32'] is ctypes.c_int
        assert ZIG_TO_CTYPES['i64'] is ctypes.c_int64
        assert ZIG_TO_CTYPES['f32'] is ctypes.c_float
        assert ZIG_TO_CTYPES['f64'] is ctypes.c_double
        assert ZIG_TO_CTYPES['bool'] is ctypes.c_bool
        assert ZIG_TO_CTYPES['void'] is None

    def test_get_zig_type_python_types(self):
        """get_zig_type() 对 Python 类型的映射"""
        assert get_zig_type(int) == 'i64'
        assert get_zig_type(float) == 'f64'
        assert get_zig_type(bool) == 'bool'
        assert get_zig_type(str) == '[*:0]const u8'
        assert get_zig_type(type(None)) == 'void'

    def test_get_zig_type_unknown(self):
        """get_zig_type() 对未知类型的回退"""
        assert get_zig_type(bytes) == 'i64'

    def test_get_zig_ctype(self):
        """get_zig_ctype() 映射"""
        assert get_zig_ctype('i64') is ctypes.c_int64
        assert get_zig_ctype('f64') is ctypes.c_double
        assert get_zig_ctype('bool') is ctypes.c_bool
        assert get_zig_ctype('void') is None


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestZigOnlyCode:
    """测试 @zig 装饰器的 ONLY_CODE 模式（无需 Zig 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @zig(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'export fn vools_add' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @zig(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "return a * b;"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'export fn vools_multiply' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @zig(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return "return name;"

        result = greet("World")
        assert isinstance(result, str)
        assert 'export fn vools_greet' in result

    def test_only_code_mode_bool(self):
        """测试 ONLY_CODE 模式生成布尔函数代码"""
        @zig(mode='ONLY_CODE')
        def is_positive(x: int) -> bool:
            return "return x > 0;"

        result = is_positive(5)
        assert isinstance(result, str)
        assert 'export fn vools_is_positive' in result

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @zig(mode='ONLY_CODE', module_code='// Custom preamble')
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '// Custom preamble' in result


# =============================================================================
# 需要 Zig 编译器的测试
# =============================================================================

ZIG_AVAILABLE = zig_compiler_available()


@pytest.mark.skipif(not ZIG_AVAILABLE, reason="Zig compiler not available")
class TestZigDecorator:
    """测试 @zig 装饰器（需要 Zig 编译器）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @zig
        def add(a: int, b: int) -> int:
            return "return a + b;"

        result = add(2, 3)
        assert result == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @zig
        def sub(a: int, b: int) -> int:
            return "return a - b;"

        result = sub(10, 3)
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @zig
        def mul(a: int, b: int) -> int:
            return "return a * b;"

        result = mul(6, 7)
        assert result == 42, "期望 42，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @zig
        def multiply_float(a: float, b: float) -> float:
            return "return a * b;"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @zig
        def is_even(n: int) -> bool:
            return "return @rem(n, 2) == 0;"

        result = is_even(4)
        assert result is True
        result = is_even(5)
        assert result is False

    def test_large_input(self):
        """测试大整数"""
        @zig
        def double_it(x: int) -> int:
            return "return x * 2;"

        result = double_it(999999)
        assert result == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not ZIG_AVAILABLE, reason="Zig compiler not available")
class TestZigFallback:
    """测试回退机制（需要 Zig 编译器）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @zig(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid zig code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestZigBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import zig
        assert zig is not None

    def test_import_compiler_available(self):
        """测试导入 zig_compiler_available"""
        from vools.bridge import zig_compiler_available
        assert callable(zig_compiler_available)

    def test_zigc_alias(self):
        """测试 zigc 别名"""
        assert zigc is zig

    def test_bridge_class(self):
        """测试 ZigBridge 类"""
        bridge = ZigBridge()
        assert bridge.name == 'zig'
        assert bridge.file_ext == '.zig'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])