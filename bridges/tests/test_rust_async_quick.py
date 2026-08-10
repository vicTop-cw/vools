"""
快速测试异步编译模式

运行此脚本验证 @rust(async_mode=True) 功能。
"""

import sys
import os
import asyncio
from vools.bridge.rust import rust, is_rust_available


def main():
    """主函数"""
    print("=" * 70)
    print("Rust 异步编译模式快速测试")
    print("=" * 70)

    # 检查 Rust 编译器可用性
    if is_rust_available():
        print("✅ Rust 编译器可用")
    else:
        print("❌ Rust 编译器不可用")
        print("请安装 Rust 工具链：https://rustup.rs/")
        return False

    # 定义异步 Rust 函数
    @rust(async_mode=True)
    async def async_add(a: int, b: int) -> int:
        """异步加法函数"""
        return "a + b"

    @rust(async_mode=True)
    async def async_fib(n: int) -> int:
        """异步斐波那契函数"""
        return """
        if n <= 1 {
            1
        } else {
            async_fib(n - 1) + async_fib(n - 2)
        }
        """

    # 测试基本异步调用
    print("\n" + "=" * 70)
    print("测试 1: 基本异步调用")
    print("=" * 70)

    async def test_basic_async():
        result = await async_add(10, 5)
        print(f"async_add(10, 5) = {result}")
        assert result == 15, f"Expected 15, got {result}"
        print("✅ 基本异步调用测试通过")

    asyncio.run(test_basic_async())

    # 测试异步斐波那契
    print("\n" + "=" * 70)
    print("测试 2: 异步斐波那契数列")
    print("=" * 70)

    async def test_async_fib():
        result = await async_fib(15)
        print(f"async_fib(15) = {result}")
        assert result == 987, f"Expected 987, got {result}"
        print("✅ 异步斐波那契测试通过")

    asyncio.run(test_async_fib())

    # 测试并发异步调用
    print("\n" + "=" * 70)
    print("测试 3: 并发异步调用")
    print("=" * 70)

    async def test_concurrent_async():
        results = await asyncio.gather(
            async_add(100, 200),
            async_add(50, 50),
            async_add(10, 20)
        )
        print(f"并发调用结果: {results}")
        assert results == [300, 100, 30], f"Unexpected results: {results}"
        print("✅ 并发异步调用测试通过")

    asyncio.run(test_concurrent_async())

    # 测试混合同步和异步
    print("\n" + "=" * 70)
    print("测试 4: 混合同步和异步调用")
    print("=" * 70)

    @rust
    def sync_mul(a: int, b: int) -> int:
        """同步乘法函数"""
        return "a * b"

    async def test_mixed():
        # 同步调用
        sync_result = sync_mul(10, 5)
        print(f"sync_mul(10, 5) = {sync_result}")

        # 异步调用
        async_result = await async_add(10, 5)
        print(f"async_add(10, 5) = {async_result}")

        # 组合
        total = sync_result + async_result
        print(f"组合结果: {total}")
        assert total == 65, f"Expected 65, got {total}"
        print("✅ 混合调用测试通过")

    asyncio.run(test_mixed())

    print("\n" + "=" * 70)
    print("✅ 所有异步测试通过！")
    print("=" * 70)
    print("\n异步编译模式工作正常！")
    print("\n特点：")
    print("1. 编译和执行在后台线程中进行")
    print("2. 不阻塞主线程")
    print("3. 支持并发异步调用")
    print("4. 可以与 asyncio 其他异步操作配合使用")
    print("5. 使用 ThreadPoolExecutor（4 个工作线程）执行")

    return True


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
