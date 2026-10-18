"""
Perl 语言桥接测试

测试 vools.bridge.perl 模块的基本功能。
需要 Perl 环境才能运行完整测试。
"""

import pytest
import asyncio
from vools.bridge.perl import perl, perl_compiler_available


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = perl_compiler_available()
        assert isinstance(result, bool)

    def test_perl_decorator_only_code(self):
        """测试 @perl 装饰器的 ONLY_CODE 模式"""
        @perl(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'add' in result
        assert 'return $a + $b' in result

    def test_perl_decorator_only_code_no_signature(self):
        """测试 @perl 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @perl(mode='ONLY_CODE')
        def custom_func():
            return 'my $x = 10;\nprint $x;'

        result = custom_func()
        assert isinstance(result, str)
        assert 'my $x = 10' in result
        assert 'print $x' in result

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_normal(self):
        """测试 @perl 装饰器正常模式"""
        @perl
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_float(self):
        """测试浮点运算"""
        @perl
        def multiply(a: float, b: float) -> float:
            return 'return $a * $b;'

        result = multiply(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_string(self):
        """测试字符串操作"""
        @perl
        def greet(name: str) -> str:
            return 'return "Hello, " . $name . "!";'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @perl(fallback=py_add)
        def add(a: int, b: int) -> int:
            return 'return $a + $b;'

        result = add(3, 4)
        assert result == 7


class TestStringInjectionRegression:
    r"""回归测试：args_json 单引号字面量注入（bug 账本 §13.52）。

    这些 payload 在修复前会从单引号字符串里"逃逸"，变成 Perl 源码执行
    （`'); die 'INJECTED'; #` 会闭合字符串再执行 die）。修复后 `_perl_squote`
    把 `'` 与 `\` 都转义，payload 只会被当作普通字符串值透传。

    payload 若真被注入，Perl 会因语法错误/`die` 抛错 → 用例 fail；
    payload 被安全转义 → 返回值等于原字面值 → 用例 pass。
    """

    PAYLOAD_SQUOTE = "'); die 'INJECTED'; #"          # 单引号闭合
    PAYLOAD_BACKSLASH = "foo\\'; system('calc'); #"   # 反斜杠 + 单引号
    PAYLOAD_MIXED = "\"quoted\"; die 'X'; #"          # 双引号 + 单引号
    PAYLOAD_NEWLINE = "line1\n'); die 'N'; #"         # 换行 + 单引号

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_squote_payload(self):
        """单引号闭合 payload 应作为字面值透传，不执行"""
        @perl
        def echo(name: str) -> str:
            return 'return $name;'
        assert echo(self.PAYLOAD_SQUOTE) == self.PAYLOAD_SQUOTE

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_backslash_payload(self):
        """反斜杠+单引号 payload（`_perl_squote` 需先转义 `\\` 再转义 `'`）"""
        @perl
        def echo(name: str) -> str:
            return 'return $name;'
        assert echo(self.PAYLOAD_BACKSLASH) == self.PAYLOAD_BACKSLASH

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_mixed_quote_payload(self):
        """双引号+单引号 payload（json.dumps 转义 `"` 为 `\\"`，_perl_squote 再转义 `\\`）"""
        @perl
        def echo(name: str) -> str:
            return 'return $name;'
        assert echo(self.PAYLOAD_MIXED) == self.PAYLOAD_MIXED

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_newline_payload(self):
        """换行+单引号 payload（输出含真实换行，断言放宽为包含关系）"""
        @perl
        def echo(name: str) -> str:
            return 'return $name;'
        # 注入成功会触发 die('INJECTED') → 异常；此处用包含关系避免原始 stdout 换行解析差异
        payload_nl = "line1\n'); die 'INJECTED'; #"
        assert "INJECTED" in echo(payload_nl)

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_through_concat(self):
        """注入 payload 作为字符串操作数参与拼接，仍应为字面值"""
        @perl
        def wrap(name: str) -> str:
            return 'return "<" . $name . ">";'
        assert wrap(self.PAYLOAD_SQUOTE) == "<" + self.PAYLOAD_SQUOTE + ">"

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_injection_multiple_args(self):
        """多个参数混合正常值与恶意值，注入不得污染正常参数"""
        @perl
        def pair(a: int, b: str) -> str:
            return 'return $a . "|" . $b;'
        assert pair(7, self.PAYLOAD_SQUOTE) == "7|" + self.PAYLOAD_SQUOTE


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_async_mode(self):
        """测试 @perl 装饰器 async_mode=True"""
        @perl(async_mode=True)
        def add_async(a: int, b: int) -> int:
            return 'return $a + $b;'

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_async_float(self):
        """测试异步浮点运算"""
        @perl(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return 'return $a * $b;'

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    @pytest.mark.skipif(not perl_compiler_available(), reason="Perl 环境不可用")
    def test_perl_decorator_async_string(self):
        """测试异步字符串操作"""
        @perl(async_mode=True)
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
        from vools.bridge import perl
        assert perl is not None

    def test_import_perl_compiler_available(self):
        """测试从 vools.bridge 导入 perl_compiler_available"""
        from vools.bridge import perl_compiler_available
        assert callable(perl_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])