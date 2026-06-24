"""
Rust 桥接使用示例

演示如何使用 @rust 装饰器进行 Rust 动态编译。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.rust import rust, is_rust_available


# 示例 1：基本使用
@rust
def add(a: int, b: int) -> int:
    """
    简单的加法函数

    函数返回 Rust 代码字符串，装饰器自动编译并执行。
    """
    return "a + b"


# 示例 2：斐波那契数列
@rust
def fib(n: int) -> int:
    """
    斐波那契数列计算

    Rust 代码可以包含复杂的逻辑，如递归。
    """
    return """
    if n <= 1 {
        1
    } else {
        fib(n - 1) + fib(n - 2)
    }
    """


# 示例 3：带导入语句的函数
@rust
def complex_calc(x: int) -> int:
    """
    带导入语句的复杂计算

    Rust 代码可以包含 use 语句等预处理指令。
    """
    return """
    use std::os::raw::*;

    // 复杂计算
    x * x + x
    """


# 示例 4：不同模式
@rust(mode='ONLY_CODE')
def generate_code_only(x: int) -> int:
    """
    ONLY_CODE 模式：只生成 Rust 代码，不编译

    用于查看生成的代码或调试。
    """
    return "x + 100"


@rust(mode='DEBUG')
def debug_mode_func(x: int) -> int:
    """
    DEBUG 模式：强制重新编译

    每次调用都会重新编译，用于调试或测试。
    """
    return "x * 2"


# 示例 5：带回退机制
def python_fallback(x: int) -> int:
    """Python 回退实现"""
    return x * 10


@rust(fallback=python_fallback)
def with_fallback(x: int) -> int:
    """
    带回退机制的函数

    如果 Rust 编译失败或编译器不可用，自动回退到 Python 实现。
    """
    return "x + 1"


# 示例 6：多函数模块（使用 @rust_module）
from vools.bridge.rust import rust_module


@rust_module(name='math_ops')
class MathOps:
    """数学运算模块"""

    def add(a: int, b: int) -> int:
        return "a + b"

    def mul(a: int, b: int) -> int:
        return "a * b"

    def sub(a: int, b: int) -> int:
        return "a - b"


# 示例 8：异步模式
@rust(async_mode=True)
async def async_fib(n: int) -> int:
    """
    异步斐波那契数列计算

    编译和执行在后台线程中进行，不阻塞主线程。
    适合需要高性能但不想阻塞 UI 或其他异步操作的场景。
    """
    return """
    if n <= 1 {
        1
    } else {
        async_fib(n - 1) + async_fib(n - 2)
    }
    """


def main():
    """运行示例"""
    print("=" * 60)
    print("Rust 桥接使用示例")
    print("=" * 60)

    # 检查 Rust 编译器可用性
    if is_rust_available():
        print("✅ Rust 编译器可用")
    else:
        print("❌ Rust 编译器不可用，部分示例将无法运行")
        print("请安装 Rust 工具链：https://rustup.rs/")
        return

    print("\n" + "=" * 60)
    print("示例 8：异步模式 - async_fib 函数")
    print("=" * 60)

    # 异步调用示例
    import asyncio

    async def run_async_examples():
        """运行异步示例"""
        result = await async_fib(20)  # 在后台线程中编译和执行
        print(f"async_fib(20) = {result}")
        assert result == 10946, f"Expected 10946, got {result}"

        # 多个异步调用可以并行执行
        results = await asyncio.gather(
            async_fib(15),
            async_fib(18),
            async_fib(20)
        )
        print(f"异步并发调用结果: {results}")

    asyncio.run(run_async_examples())

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)

    result = add(5, 3)
    print(f"add(5, 3) = {result}")
    assert result == 8, f"Expected 8, got {result}"

    print("\n" + "=" * 60)
    print("示例 2：斐波那契数列 - fib 函数")
    print("=" * 60)

    result = fib(10)
    print(f"fib(10) = {result}")
    assert result == 89, f"Expected 89, got {result}"

    print("\n" + "=" * 60)
    print("示例 3：带导入语句 - complex_calc 函数")
    print("=" * 60)

    result = complex_calc(5)
    print(f"complex_calc(5) = {result}")
    assert result == 30, f"Expected 30, got {result}"

    print("\n" + "=" * 60)
    print("示例 4：ONLY_CODE 模式 - generate_code_only 函数")
    print("=" * 60)

    code = generate_code_only(5)
    print(f"生成的 Rust 代码：\n{code}")

    print("\n" + "=" * 60)
    print("示例 5：DEBUG 模式 - debug_mode_func 函数")
    print("=" * 60)

    result = debug_mode_func(3)
    print(f"debug_mode_func(3) = {result}")
    assert result == 6, f"Expected 6, got {result}"

    print("\n" + "=" * 60)
    print("示例 6：带回退机制 - with_fallback 函数")
    print("=" * 60)

    result = with_fallback(5)
    print(f"with_fallback(5) = {result}")
    # 如果 Rust 编译成功，应该是 6；如果回退到 Python，应该是 50

    print("\n" + "=" * 60)
    print("示例 7：多函数模块 - MathOps 类")
    print("=" * 60)

    # 注意：@rust_module 需要类实例化后才能调用方法
    # 这里暂时跳过，因为需要更复杂的实现
    print("（示例 7 需要类实例化，暂时跳过）")

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()