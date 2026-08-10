"""
Ruby 语言桥接测试

测试 vools.bridge.ruby 模块的基本功能。
需要 Ruby 环境才能运行完整测试。
"""

import pytest
import asyncio
from vools.bridge.ruby import ruby, ruby_compiler_available


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = ruby_compiler_available()
        assert isinstance(result, bool)

    def test_ruby_decorator_only_code(self):
        """测试 @ruby 装饰器的 ONLY_CODE 模式"""
        @ruby(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return 'a + b'

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'add' in result
        assert 'a + b' in result

    def test_ruby_decorator_only_code_no_signature(self):
        """测试 @ruby 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @ruby(mode='ONLY_CODE')
        def custom_func():
            return 'x = 10\nputs x'

        result = custom_func()
        assert isinstance(result, str)
        assert 'x = 10' in result
        assert 'puts x' in result

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_normal(self):
        """测试 @ruby 装饰器正常模式"""
        @ruby
        def add(a: int, b: int) -> int:
            return 'a + b'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_float(self):
        """测试浮点运算"""
        @ruby
        def multiply(a: float, b: float) -> float:
            return 'a * b'

        result = multiply(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_string(self):
        """测试字符串操作"""
        @ruby
        def greet(name: str) -> str:
            return '"Hello, " + name + "!"'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @ruby(fallback=py_add)
        def add(a: int, b: int) -> int:
            return 'a + b'

        result = add(3, 4)
        assert result == 7


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_async_mode(self):
        """测试 @ruby 装饰器 async_mode=True"""
        @ruby(async_mode=True)
        def add_async(a: int, b: int) -> int:
            return 'a + b'

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_async_float(self):
        """测试异步浮点运算"""
        @ruby(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return 'a * b'

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    @pytest.mark.skipif(not ruby_compiler_available(), reason="Ruby 环境不可用")
    def test_ruby_decorator_async_string(self):
        """测试异步字符串操作"""
        @ruby(async_mode=True)
        def greet_async(name: str) -> str:
            return '"Hello, " + name + "!"'

        async def _run():
            return await greet_async("Async")

        result = asyncio.run(_run())
        assert "Hello" in result
        assert "Async" in result


class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import ruby
        assert ruby is not None

    def test_import_ruby_compiler_available(self):
        """测试从 vools.bridge 导入 ruby_compiler_available"""
        from vools.bridge import ruby_compiler_available
        assert callable(ruby_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])