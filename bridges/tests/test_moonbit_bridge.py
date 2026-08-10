"""
MoonBit 语言桥接测试

测试 vools.bridge.moonbit 模块的基本功能。
需要 moon 命令行工具才能运行完整测试。

运行：python -m pytest tests/bridge/test_moonbit_bridge.py -v --tb=short
"""

import pytest
import asyncio
from vools.bridge.moonbit import (
    moonbit,
    moonbit_compiler_available,
    MoonBitBridge,
    moonbit_bridge,
)
from vools.bridge.moonbit.types import (
    PY_TO_MOONBIT_TYPE,
    get_moonbit_type,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_moonbit_compiler_available():
    """测试 moonbit_compiler_available() 返回 bool"""
    available = moonbit_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_moonbit_bridge_instance():
    """测试 MoonBitBridge 实例"""
    bridge = moonbit_bridge
    assert bridge.name == 'moonbit'
    assert bridge.file_ext == '.mbt'
    assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestMoonBitTypeMapping:
    """测试 Python → MoonBit 类型映射"""

    def test_py_to_moonbit_type(self):
        """PY_TO_MOONBIT_TYPE 基本类型映射"""
        assert PY_TO_MOONBIT_TYPE[int] == 'Int'
        assert PY_TO_MOONBIT_TYPE[float] == 'Double'
        assert PY_TO_MOONBIT_TYPE[str] == 'String'
        assert PY_TO_MOONBIT_TYPE[bool] == 'Bool'

    def test_get_moonbit_type_python_types(self):
        """get_moonbit_type() 对 Python 类型的映射"""
        assert get_moonbit_type(int) == 'Int'
        assert get_moonbit_type(float) == 'Double'
        assert get_moonbit_type(bool) == 'Bool'
        assert get_moonbit_type(str) == 'String'
        assert get_moonbit_type(bytes) == 'Bytes'

    def test_get_moonbit_type_unknown(self):
        """get_moonbit_type() 对未知类型的回退"""
        assert get_moonbit_type(list) == 'String'
        assert get_moonbit_type(dict) == 'String'


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestMoonBitOnlyCode:
    """测试 @moonbit 装饰器的 ONLY_CODE 模式（无需 MoonBit 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @moonbit(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'fn add(' in result
        assert 'a + b' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @moonbit(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'fn multiply(' in result
        assert 'a * b' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @moonbit(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return '"Hello, " + name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'fn greet(' in result

    def test_only_code_mode_bool(self):
        """测试 ONLY_CODE 模式生成布尔函数代码"""
        @moonbit(mode='ONLY_CODE')
        def is_positive(x: int) -> bool:
            return "x > 0"

        result = is_positive(5)
        assert isinstance(result, str)
        assert 'fn is_positive(' in result

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @moonbit(mode='ONLY_CODE', module_code='// Custom preamble')
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert '// Custom preamble' in result


# =============================================================================
# 需要 MoonBit 编译器的测试
# =============================================================================

MOONBIT_AVAILABLE = moonbit_compiler_available()


@pytest.mark.skipif(not MOONBIT_AVAILABLE, reason="MoonBit compiler not available")
class TestMoonBitDecorator:
    """测试 @moonbit 装饰器（需要 MoonBit 编译器）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @moonbit
        def add(a: int, b: int) -> int:
            return "a + b"

        result = add(2, 3)
        assert int(result) == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @moonbit
        def sub(a: int, b: int) -> int:
            return "a - b"

        result = sub(10, 3)
        assert int(result) == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @moonbit
        def mul(a: int, b: int) -> int:
            return "a * b"

        result = mul(6, 7)
        assert int(result) == 42, "期望 42，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @moonbit
        def multiply_float(a: float, b: float) -> float:
            return "a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(float(result) - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @moonbit
        def is_even(n: int) -> bool:
            return "n % 2 == 0"

        result = is_even(4)
        assert result in ('true', True), "期望 True，实际 {0}".format(result)
        result = is_even(5)
        assert result in ('false', False), "期望 False，实际 {0}".format(result)

    def test_large_input(self):
        """测试大整数"""
        @moonbit
        def double_it(x: int) -> int:
            return "x * 2"

        result = double_it(999999)
        assert int(result) == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not MOONBIT_AVAILABLE, reason="MoonBit compiler not available")
class TestMoonBitFallback:
    """测试回退机制（需要 MoonBit 编译器）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @moonbit(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid moonbit code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestMoonBitBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import moonbit
        assert moonbit is not None

    def test_bridge_class(self):
        """测试 MoonBitBridge 类"""
        bridge = MoonBitBridge()
        assert bridge.name == 'moonbit'
        assert bridge.file_ext == '.mbt'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])