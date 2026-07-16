"""
VB.NET 语言桥接测试

测试 vools.bridge.vbnet 模块的基本功能。
需要 .NET SDK (dotnet) 才能运行完整测试。

运行：python -m pytest tests/bridge/test_vbnet_bridge.py -v --tb=short
"""

import pytest
import asyncio
import ctypes
from vools.bridge.vbnet import (
    vbnet,
    vb,
    vbnet_compiler_available,
    VBNetBridge,
    vbnet_bridge,
    PY_TO_VB_TYPE,
    VB_TO_CTYPES,
    get_vb_type,
    get_vb_ctype,
)
from vools.bridge.vbnet.templates import (
    generate_vb_method,
    generate_vb_class,
    generate_vbproj,
)


# =============================================================================
# 编译器可用性检测
# =============================================================================

def test_vbnet_compiler_available():
    """测试 vbnet_compiler_available() 返回 bool"""
    available = vbnet_compiler_available()
    assert isinstance(available, bool), "返回值应为 bool 类型"


def test_vbnet_bridge_instance():
    """测试 VBNetBridge 实例"""
    bridge = vbnet_bridge
    assert bridge.name == 'vbnet'
    assert bridge.file_ext == '.vb'
    assert bridge.lib_ext == '.exe'
    assert isinstance(bridge.compiler_available(), bool)


# =============================================================================
# 类型映射测试（不需要编译器）
# =============================================================================

class TestVBNetTypeMapping:
    """测试 Python → VB.NET 类型映射"""

    def test_py_to_vb_type(self):
        """PY_TO_VB_TYPE 基本类型映射"""
        assert PY_TO_VB_TYPE[int] == 'Integer'
        assert PY_TO_VB_TYPE[float] == 'Double'
        assert PY_TO_VB_TYPE[str] == 'String'
        assert PY_TO_VB_TYPE[bool] == 'Boolean'
        assert PY_TO_VB_TYPE[bytes] == 'Byte()'
        assert PY_TO_VB_TYPE[list] == 'Integer()'
        assert PY_TO_VB_TYPE[type(None)] == 'Void'

    def test_vb_to_ctypes(self):
        """VB_TO_CTYPES 到 ctypes 映射"""
        assert VB_TO_CTYPES['Integer'] is ctypes.c_int
        assert VB_TO_CTYPES['Long'] is ctypes.c_long
        assert VB_TO_CTYPES['Double'] is ctypes.c_double
        assert VB_TO_CTYPES['Boolean'] is ctypes.c_bool
        assert VB_TO_CTYPES['String'] is ctypes.c_char_p
        assert VB_TO_CTYPES['Void'] is None

    def test_get_vb_type_python_types(self):
        """get_vb_type() 对 Python 类型的映射"""
        assert get_vb_type(int) == 'Integer'
        assert get_vb_type(float) == 'Double'
        assert get_vb_type(bool) == 'Boolean'
        assert get_vb_type(str) == 'String'
        assert get_vb_type(None) == 'Void'
        assert get_vb_type(type(None)) == 'Void'

    def test_get_vb_type_string_aliases(self):
        """get_vb_type() 对字符串别名的映射"""
        assert get_vb_type('int') == 'Integer'
        assert get_vb_type('float') == 'Double'
        assert get_vb_type('bool') == 'Boolean'
        assert get_vb_type('str') == 'String'
        assert get_vb_type('bytes') == 'Byte()'

    def test_get_vb_ctype(self):
        """get_vb_ctype() 映射"""
        assert get_vb_ctype('Integer') is ctypes.c_int
        assert get_vb_ctype('Double') is ctypes.c_double
        assert get_vb_ctype('Boolean') is ctypes.c_bool
        assert get_vb_ctype('String') is ctypes.c_char_p


# =============================================================================
# 模板生成测试（不需要编译器）
# =============================================================================

class TestVBNetTemplates:
    """测试 VB.NET 代码模板生成"""

    def test_generate_vb_method(self):
        """测试生成 VB.NET 方法代码"""
        method = generate_vb_method(
            func_name='Add',
            params=[('a', 'Integer'), ('b', 'Integer')],
            return_type='Integer',
            body='Return a + b',
        )
        assert 'Public Function Add(' in method
        assert '[a] As Integer' in method
        assert '[b] As Integer' in method
        assert 'As Integer' in method
        assert 'Return a + b' in method

    def test_generate_vb_sub(self):
        """测试生成 VB.NET 无返回值方法"""
        method = generate_vb_method(
            func_name='Hello',
            params=[('name', 'String')],
            return_type='Void',
            body='Console.WriteLine("Hello, " & name)',
        )
        assert 'Public Sub Hello(' in method
        assert '[name] As String' in method

    def test_generate_vb_class(self):
        """测试生成 VB.NET 类代码"""
        method = generate_vb_method(
            func_name='Add',
            params=[('a', 'Integer'), ('b', 'Integer')],
            return_type='Integer',
            body='Return a + b',
        )
        class_code = generate_vb_class([method])
        assert 'Public Module Bridge' in class_code
        assert 'Public Function Add(' in class_code

    def test_generate_vbproj(self):
        """测试生成 vbproj 文件"""
        proj = generate_vbproj()
        assert 'Microsoft.NET.Sdk' in proj
        assert 'TargetFramework' in proj
        assert 'OutputType' in proj


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestVBNetOnlyCode:
    """测试 @vbnet 装饰器的 ONLY_CODE 模式（无需 .NET SDK）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @vbnet(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "Return a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'Module Bridge' in result
        assert 'add' in result.lower()

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @vbnet(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "Return a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'multiply' in result.lower()

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @vbnet(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return 'Return "Hello, " & name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'greet' in result.lower()

    def test_only_code_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @vbnet(mode='ONLY_CODE', module_code="' Custom preamble")
        def add(a: int, b: int) -> int:
            return "Return a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert "' Custom preamble" in result


# =============================================================================
# 需要 .NET SDK 的测试
# =============================================================================

VBNET_AVAILABLE = vbnet_compiler_available()


@pytest.mark.skipif(not VBNET_AVAILABLE, reason="VB.NET compiler (dotnet) not available")
class TestVBNetDecorator:
    """测试 @vbnet 装饰器（需要 .NET SDK）"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @vbnet
        def add(a: int, b: int) -> int:
            return "Return a + b"

        result = add(2, 3)
        assert result == 5, "期望 5，实际 {0}".format(result)

    def test_subtract(self):
        """测试减法函数"""
        @vbnet
        def sub(a: int, b: int) -> int:
            return "Return a - b"

        result = sub(10, 3)
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_multiply(self):
        """测试乘法函数"""
        @vbnet
        def mul(a: int, b: int) -> int:
            return "Return a * b"

        result = mul(6, 7)
        assert result == 42, "期望 42，实际 {0}".format(result)

    def test_float_operation(self):
        """测试浮点运算"""
        @vbnet
        def multiply_float(a: float, b: float) -> float:
            return "Return a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001, "期望 7.0，实际 {0}".format(result)

    def test_boolean_operation(self):
        """测试布尔运算"""
        @vbnet
        def is_even(n: int) -> bool:
            return "Return n Mod 2 = 0"

        result = is_even(4)
        assert result is True
        result = is_even(5)
        assert result is False

    def test_large_input(self):
        """测试大整数"""
        @vbnet
        def double_it(x: int) -> int:
            return "Return x * 2"

        result = double_it(999999)
        assert result == 1999998, "期望 1999998，实际 {0}".format(result)


@pytest.mark.skipif(not VBNET_AVAILABLE, reason="VB.NET compiler (dotnet) not available")
class TestVBNetAsync:
    """测试 VB.NET 异步模式（需要 .NET SDK）"""

    def test_async_add(self):
        """测试异步加法"""
        @vbnet(async_mode=True)
        def async_add(a: int, b: int) -> int:
            return "Return a + b"

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        assert result == 7, "期望 7，实际 {0}".format(result)

    def test_async_concurrent(self):
        """测试并发异步调用"""
        @vbnet(async_mode=True)
        def async_mul(a: int, b: int) -> int:
            return "Return a * b"

        async def run():
            tasks = [async_mul(i, i) for i in range(1, 6)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert results == [1, 4, 9, 16, 25], "期望 [1,4,9,16,25]，实际 {0}".format(results)


@pytest.mark.skipif(not VBNET_AVAILABLE, reason="VB.NET compiler (dotnet) not available")
class TestVBNetFallback:
    """测试回退机制（需要 .NET SDK）"""

    def test_fallback_called(self):
        """测试编译失败时回退到 Python 函数"""
        def py_fallback(x: int) -> int:
            return x * 100

        @vbnet(fallback=py_fallback)
        def bad_func(x: int) -> int:
            return "this is not valid vb code !!!"

        result = bad_func(5)
        assert result == 500, "期望 500，实际 {0}".format(result)


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestVBNetBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import vbnet
        assert vbnet is not None

    def test_import_compiler_available(self):
        """测试导入 vbnet_compiler_available"""
        from vools.bridge import vbnet_compiler_available
        assert callable(vbnet_compiler_available)

    def test_vb_alias(self):
        """测试 vb 别名"""
        assert vb is vbnet

    def test_bridge_class(self):
        """测试 VBNetBridge 类"""
        bridge = VBNetBridge()
        assert bridge.name == 'vbnet'
        assert bridge.file_ext == '.vb'
        assert bridge.lib_ext == '.exe'
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])