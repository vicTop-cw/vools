"""
Lua 语言桥接测试

测试 vools.bridge.lua 模块的基本功能。
需要 Lua 环境才能运行完整测试。
"""

import pytest
import asyncio
from vools.bridge.lua import lua, lua_compiler_available


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = lua_compiler_available()
        assert isinstance(result, bool)

    def test_lua_decorator_only_code(self):
        """测试 @lua 装饰器的 ONLY_CODE 模式"""
        @lua(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return 'return a + b'

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'add' in result
        assert 'return a + b' in result

    def test_lua_decorator_only_code_no_signature(self):
        """测试 @lua 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @lua(mode='ONLY_CODE')
        def custom_func():
            return 'x = 10\nprint(x)'

        result = custom_func()
        assert isinstance(result, str)
        assert 'x = 10' in result
        assert 'print(x)' in result

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_normal(self):
        """测试 @lua 装饰器正常模式"""
        @lua
        def add(a: int, b: int) -> int:
            return 'return a + b'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_float(self):
        """测试浮点运算"""
        @lua
        def multiply(a: float, b: float) -> float:
            return 'return a * b'

        result = multiply(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_string(self):
        """测试字符串操作"""
        @lua
        def greet(name: str) -> str:
            return 'return "Hello, " .. name .. "!"'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @lua(fallback=py_add)
        def add(a: int, b: int) -> int:
            return 'return a + b'

        result = add(3, 4)
        assert result == 7


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_async_mode(self):
        """测试 @lua 装饰器 async_mode=True"""
        @lua(async_mode=True)
        def add_async(a: int, b: int) -> int:
            return 'return a + b'

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_async_float(self):
        """测试异步浮点运算"""
        @lua(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return 'return a * b'

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    @pytest.mark.skipif(not lua_compiler_available(), reason="Lua 环境不可用")
    def test_lua_decorator_async_string(self):
        """测试异步字符串操作"""
        @lua(async_mode=True)
        def greet_async(name: str) -> str:
            return 'return "Hello, " .. name .. "!"'

        async def _run():
            return await greet_async("Async")

        result = asyncio.run(_run())
        assert "Hello" in result
        assert "Async" in result


class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import lua
        assert lua is not None

    def test_import_lua_compiler_available(self):
        """测试从 vools.bridge 导入 lua_compiler_available"""
        from vools.bridge import lua_compiler_available
        assert callable(lua_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])