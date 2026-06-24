"""
测试 Rust 异步编译模式

测试 @rust(async_mode=True) 异步功能。
"""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.rust import rust, is_rust_available


@pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
class TestRustAsyncMode:
    """测试 Rust 异步编译模式"""

    def test_basic_async_function(self):
        """测试基本的异步函数"""
        @rust(async_mode=True)
        async def async_add(a: int, b: int) -> int:
            return "a + b"

        # 调用异步函数
        result = asyncio.run(async_add(5, 3))
        assert result == 8

    def test_async_fibonacci(self):
        """测试异步斐波那契函数"""
        @rust(async_mode=True)
        async def async_fib(n: int) -> int:
            return """
            if n <= 1 {
                1
            } else {
                async_fib(n - 1) + async_fib(n - 2)
            }
            """

        result = asyncio.run(async_fib(15))
        assert result == 987  # fib(15) = 987

    def test_concurrent_async_calls(self):
        """测试并发异步调用"""
        @rust(async_mode=True)
        async def async_mul(a: int, b: int) -> int:
            return "a * b"

        # 并发调用
        results = asyncio.run(asyncio.gather(
            async_mul(5, 10),
            async_mul(3, 7),
            async_mul(2, 8)
        ))

        assert results == [50, 21, 16]

    def test_async_with_fallback(self):
        """测试异步函数带回退机制"""
        def python_fallback(x: int) -> int:
            return x * 10

        @rust(async_mode=True, fallback=python_fallback)
        async def async_with_fallback(x: int) -> int:
            return "x + 1"

        result = asyncio.run(async_with_fallback(5))
        # 如果编译成功，返回 6；否则返回 50
        assert result in [6, 50]


@pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
class TestRustAsyncWithAsyncio:
    """测试 Rust 异步与 asyncio 配合"""

    def test_mixed_async_operations(self):
        """测试混合异步操作"""
        @rust
        def sync_add(a: int, b: int) -> int:
            return "a + b"

        @rust(async_mode=True)
        async def async_mul(a: int, b: int) -> int:
            return "a * b"

        async def mixed_workflow():
            # 同步调用
            sync_result = sync_add(10, 5)

            # 异步调用
            async_result = await async_mul(10, 5)

            # 组合使用
            combined = sync_result + async_result

            return combined

        result = asyncio.run(mixed_workflow())
        assert result == 65  # 15 + 50

    def test_async_timeout_scenario(self):
        """测试异步超时场景"""
        @rust(async_mode=True)
        async def slow_compute(n: int) -> int:
            return """
            // 故意写一个需要编译的计算
            n + 1
            """

        # 异步调用应该能正常完成
        result = asyncio.run(slow_compute(100))
        assert result == 101


class TestRustAsyncModes:
    """测试异步模式的不同模式组合"""

    @pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
    def test_async_debug_mode(self):
        """测试异步 + DEBUG 模式"""
        @rust(mode='DEBUG', async_mode=True)
        async def async_debug_func(x: int) -> int:
            return "x * 2"

        result = asyncio.run(async_debug_func(5))
        assert result == 10

    @pytest.mark.skipif(not is_rust_available(), reason="Rust compiler not available")
    def test_async_only_code_mode(self):
        """测试异步 + ONLY_CODE 模式"""
        @rust(mode='ONLY_CODE', async_mode=True)
        async def async_code_gen(x: int) -> int:
            return "x + 100"

        result = asyncio.run(async_code_gen(5))
        # ONLY_CODE 模式返回生成的代码
        assert isinstance(result, str)
        assert '#[no_mangle]' in result


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '--tb=short'])