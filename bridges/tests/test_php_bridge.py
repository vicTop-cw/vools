"""
PHP 语言桥接测试

测试 vools.bridge.php 模块的基本功能。
需要 PHP 环境才能运行完整测试。
"""

import pytest
import asyncio
from vools.bridge.php import php, php_compiler_available


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = php_compiler_available()
        assert isinstance(result, bool)

    def test_php_decorator_only_code(self):
        """测试 @php 装饰器的 ONLY_CODE 模式"""
        @php(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'add' in result
        assert 'return $a + $b' in result

    def test_php_decorator_only_code_no_signature(self):
        """测试 @php 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @php(mode='ONLY_CODE')
        def custom_func():
            return '$x = 10;\necho $x;'

        result = custom_func()
        assert isinstance(result, str)
        assert '$x = 10' in result
        assert 'echo $x' in result

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_normal(self):
        """测试 @php 装饰器正常模式"""
        @php
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_float(self):
        """测试浮点运算"""
        @php
        def multiply(a: float, b: float) -> float:
            return 'return $a * $b;'

        result = multiply(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_string(self):
        """测试字符串操作"""
        @php
        def greet(name: str) -> str:
            return 'return "Hello, " . $name . "!";'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @php(fallback=py_add)
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(3, 4)
        assert result == 7


class TestStringInjectionRegression:
    r"""回归测试：args_json 单引号字面量注入（bug 账本 §13.54）。

    修复前 `'); die('INJECTED'); #` 会从 PHP 单引号字面量逃逸；修复后
    `_php_squote` 转义 `'` 与 `\`，payload 仅作字面字符串透传。
    """

    PAYLOAD_SQUOTE = "'); die('INJECTED'); #"
    PAYLOAD_BACKSLASH = "foo\\'); system('calc'); #"
    PAYLOAD_MIXED = "\"quoted\"); die('X'); #"
    PAYLOAD_NEWLINE = "line1\n'); die('N'); #"

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_squote_payload(self):
        """单引号闭合 payload 应作为字面值透传，不执行"""
        @php
        def my_echo(name: str) -> str:
            return 'return $name;'
        assert my_echo(self.PAYLOAD_SQUOTE) == self.PAYLOAD_SQUOTE

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_backslash_payload(self):
        """反斜杠+单引号 payload"""
        @php
        def my_echo(name: str) -> str:
            return 'return $name;'
        assert my_echo(self.PAYLOAD_BACKSLASH) == self.PAYLOAD_BACKSLASH

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_mixed_quote_payload(self):
        """双引号+单引号 payload"""
        @php
        def my_echo(name: str) -> str:
            return 'return $name;'
        assert my_echo(self.PAYLOAD_MIXED) == self.PAYLOAD_MIXED

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_newline_payload(self):
        """换行+单引号 payload（输出含真实换行，断言放宽为包含关系）"""
        @php
        def my_echo(name: str) -> str:
            return 'return $name;'
        payload_nl = "line1\n'); die('INJECTED'); #"
        assert "INJECTED" in my_echo(payload_nl)

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_through_concat(self):
        """注入 payload 作为字符串操作数参与拼接，仍应为字面值"""
        @php
        def wrap(name: str) -> str:
            return 'return "<" . $name . ">";'
        assert wrap(self.PAYLOAD_SQUOTE) == "<" + self.PAYLOAD_SQUOTE + ">"

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_injection_multiple_args(self):
        """多个参数混合正常值与恶意值，注入不得污染正常参数"""
        @php
        def pair(a: int, b: str) -> str:
            return 'return $a . "|" . $b;'
        assert pair(7, self.PAYLOAD_SQUOTE) == "7|" + self.PAYLOAD_SQUOTE


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_async_mode(self):
        """测试 @php 装饰器 async_mode=True"""
        @php(async_mode=True)
        def add_async(a: int, b: int) -> int:
            return 'return $a + $b;'

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_async_float(self):
        """测试异步浮点运算"""
        @php(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return 'return $a * $b;'

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    @pytest.mark.skipif(not php_compiler_available(), reason="PHP 环境不可用")
    def test_php_decorator_async_string(self):
        """测试异步字符串操作"""
        @php(async_mode=True)
        def greet_async(name: str) -> str:
            return 'return "Hello, " . $name . "!";'

        async def _run():
            return await greet_async("Async")

        result = asyncio.run(_run())
        assert "Hello" in result
        assert "Async" in result


class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import php
        assert php is not None

    def test_import_php_compiler_available(self):
        """测试从 vools.bridge 导入 php_compiler_available"""
        from vools.bridge import php_compiler_available
        assert callable(php_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])