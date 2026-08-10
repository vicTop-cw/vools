"""
Shell/Bash 语言桥接测试

测试 vools.bridge.shell 模块的基本功能。
需要 bash 或 sh 环境才能运行完整测试。
"""

import pytest
import asyncio
from vools.bridge.shell import shell, shell_compiler_available


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = shell_compiler_available()
        assert isinstance(result, bool)

    def test_shell_decorator_only_code(self):
        """测试 @shell 装饰器的 ONLY_CODE 模式"""
        @shell(mode='ONLY_CODE')
        def add():
            return 'echo $(($1 + $2))'

        result = add()
        assert isinstance(result, str)
        assert 'add' in result
        assert 'echo $(($1 + $2))' in result

    def test_shell_decorator_only_code_no_signature(self):
        """测试 @shell 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @shell(mode='ONLY_CODE')
        def custom_func():
            return 'echo "hello world"'

        result = custom_func()
        assert isinstance(result, str)
        assert 'echo "hello world"' in result

    @pytest.mark.skipif(not shell_compiler_available(), reason="Shell 环境不可用")
    def test_shell_decorator_normal(self):
        """测试 @shell 装饰器正常模式"""
        @shell
        def add():
            return 'echo $(($1 + $2))'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not shell_compiler_available(), reason="Shell 环境不可用")
    def test_shell_decorator_string(self):
        """测试字符串操作"""
        @shell
        def greet():
            return 'echo "Hello, $1!"'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not shell_compiler_available(), reason="Shell 环境不可用")
    def test_shell_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @shell(fallback=py_add)
        def add():
            return 'echo $(($1 + $2))'

        result = add(3, 4)
        assert result == 7


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not shell_compiler_available(), reason="Shell 环境不可用")
    def test_shell_decorator_async_mode(self):
        """测试 @shell 装饰器 async_mode=True"""
        @shell(async_mode=True)
        def add_async():
            return 'echo $(($1 + $2))'

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not shell_compiler_available(), reason="Shell 环境不可用")
    def test_shell_decorator_async_string(self):
        """测试异步字符串操作"""
        @shell(async_mode=True)
        def greet_async():
            return 'echo "Hello, $1!"'

        async def _run():
            return await greet_async("Async")

        result = asyncio.run(_run())
        assert "Hello" in result
        assert "Async" in result


class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import shell
        assert shell is not None

    def test_import_shell_compiler_available(self):
        """测试从 vools.bridge 导入 shell_compiler_available"""
        from vools.bridge import shell_compiler_available
        assert callable(shell_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])