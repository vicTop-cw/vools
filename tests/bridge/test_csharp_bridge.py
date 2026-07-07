"""
测试 C# 桥接功能

前置条件：
- 安装 .NET SDK (dotnet) 并添加到 PATH
"""

import pytest
import sys
import os
import asyncio
try:
    from vools.bridge.csharp import (
        csharp,
        csharp_compiler_available,
        compile_and_run,
        is_csharp_available,
        get_cs_type,
        get_cs_ctype,
        PY_TO_CS_TYPE,
        CS_TO_CTYPES,
        CsharpFuture,
    )
except ImportError as e:
    pytest.skip(f"无法导入 vools.bridge.csharp: {e}", allow_module_level=True)


def test_csharp_compiler_available():
    """测试编译器可用性检查"""
    result = csharp_compiler_available()
    assert isinstance(result, bool)
    print(f"C# 编译器可用: {result}")
    if not result:
        pytest.skip("C# 编译器不可用，跳过后续测试")


def test_type_mapping():
    """测试类型映射"""
    # Python → C# 类型
    assert get_cs_type(int) == 'int'
    assert get_cs_type(float) == 'double'
    assert get_cs_type(bool) == 'bool'
    assert get_cs_type(str) == 'string'
    assert get_cs_type(type(None)) == 'void'

    # C# → ctypes 类型
    import ctypes
    assert get_cs_ctype('int') == ctypes.c_int
    assert get_cs_ctype('double') == ctypes.c_double
    assert get_cs_ctype('bool') == ctypes.c_bool
    assert get_cs_ctype('string') == ctypes.c_char_p


def test_is_csharp_available():
    """测试桥接可用性检查"""
    result = is_csharp_available()
    assert isinstance(result, bool)
    print(f"C# 桥接可用: {result}")


def test_mode_only_code():
    """测试 ONLY_CODE 模式（不依赖编译器）"""
    @csharp(mode='ONLY_CODE')
    def add(a: int, b: int) -> int:
        return "return a + b;"

    code = add(5)  # 参数不重要，只生成代码
    assert isinstance(code, str)
    assert 'DllExport' in code
    assert 'add' in code
    assert 'return a + b' in code
    print(f"生成的 C# 代码:\n{code}")


def test_simple_int_function():
    """测试简单整数函数"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    @csharp
    def add(a: int, b: int) -> int:
        return "return a + b;"

    result = add(2, 3)
    assert result == 5
    print(f"add(2, 3) = {result}")


def test_string_function():
    """测试字符串函数"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    # 注意：C# 字符串插值需要特殊处理
    @csharp
    def greet(name: str) -> str:
        return "return \"Hello, \" + name + \"!\";"

    result = greet("World")
    assert isinstance(result, str)
    assert "Hello" in result
    print(f"greet('World') = {result}")


def test_recursive_function():
    """测试递归函数"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    @csharp
    def fib(n: int) -> int:
        return """
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
        """

    # 注意：递归函数在 C# DLL 中需要特殊处理（函数名匹配）
    # 这里简化测试，只测试小数值
    result = fib(5)
    assert result == 5  # fib(5) = 5
    print(f"fib(5) = {result}")


def test_compile_and_run():
    """测试便捷函数"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    # 简单返回常量
    result = compile_and_run("return 42;", func_name='main', args=(), ret_type=int)
    assert result == 42
    print(f"compile_and_run('return 42;') = {result}")


def test_mode_force():
    """测试 FORCE 模式"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    @csharp(mode='FORCE')
    def dummy(x: int) -> int:
        return "return x * 2;"

    # FORCE 模式返回 DLL 路径
    dll_path = dummy(5)
    assert isinstance(dll_path, str)
    assert dll_path.endswith('.dll')
    print(f"FORCE 模式返回 DLL 路径: {dll_path}")


def test_async_mode_only_code():
    """测试异步模式 ONLY_CODE（不依赖编译器）"""
    # 注意：async_mode=True 时，被装饰的函数仍然是普通函数（返回代码字符串）
    # async_wrapper 会返回一个 async 函数
    @csharp(mode='ONLY_CODE', async_mode=True)
    def async_add(a: int, b: int) -> int:
        return "return a + b;"

    # async_add 是一个 async 函数，调用它返回 coroutine
    code = asyncio.run(async_add(1, 2))
    assert isinstance(code, str)
    assert 'DllExport' in code
    assert 'async_add' in code
    print(f"异步 ONLY_CODE 模式生成的代码:\n{code}")


def test_async_mode_execution():
    """测试异步模式实际执行"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    # async_mode=True 时，被装饰的函数仍然是普通函数
    @csharp(async_mode=True)
    def async_compute(x: int) -> int:
        return "return x * x;"

    # 异步执行
    result = asyncio.run(async_compute(5))
    assert result == 25
    print(f"async_compute(5) = {result}")


def test_async_mode_concurrent():
    """测试异步模式并发执行"""
    if not csharp_compiler_available():
        pytest.skip("C# 编译器不可用")

    # async_mode=True 时，被装饰的函数仍然是普通函数
    @csharp(async_mode=True)
    def async_multiply(a: int, b: int) -> int:
        return "return a * b;"

    # 并发执行多个任务
    async def run_concurrent():
        results = await asyncio.gather(
            async_multiply(2, 3),
            async_multiply(4, 5),
            async_multiply(6, 7),
        )
        return results

    results = asyncio.run(run_concurrent())
    assert results == [6, 20, 42]
    print(f"并发执行结果: {results}")


def test_csharp_future():
    """测试 CsharpFuture 类"""
    from concurrent.futures import ThreadPoolExecutor, Future

    # 创建一个简单的 Future
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(lambda: 42)

    # 创建 CsharpFuture
    cs_future = CsharpFuture(future, "dummy.dll", "test_func", int)

    # 测试 result 方法
    assert cs_future.result(timeout=5) == 42

    # 测试 __await__
    async def test_await():
        result = await cs_future
        return result

    result = asyncio.run(test_await())
    assert result == 42
    print(f"CsharpFuture 测试通过")


if __name__ == '__main__':
    # 直接运行测试
    print("=" * 50)
    print("C# 桥接测试")
    print("=" * 50)

    # 检查编译器可用性
    available = csharp_compiler_available()
    print(f"C# 编译器可用: {available}")

    if available:
        print("\n运行完整测试...")
        pytest.main([__file__, '-v'])
    else:
        print("\n编译器不可用，运行基础测试...")
        test_type_mapping()
        test_is_csharp_available()
        test_mode_only_code()
        test_async_mode_only_code()
        test_csharp_future()
        print("\n基础测试通过!")
