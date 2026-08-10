"""
测试 Scala 桥接功能

前置条件：
- 安装 scala-cli 或 scalac 并添加到 PATH
- 安装 Java 运行时 (java)
"""

import pytest
import sys
import os
import asyncio
try:
    from vools.bridge.scala import (
        scala,
        scala_compiler_available,
        is_scala_compiler_available,
        is_java_available,
    )
except ImportError as e:
    pytest.skip(f"无法导入 vools.bridge.scala: {e}", allow_module_level=True)


# ============================================================================
# 测试用例
# ============================================================================

def test_scala_compiler_available():
    """测试编译器可用性检查"""
    result = scala_compiler_available()
    assert isinstance(result, bool)
    print(f"Scala 编译器 (scalac/scala-cli) 可用: {result}")
    if not result:
        pytest.skip("Scala 编译器不可用，跳过后续编译执行测试")


def test_java_available_for_scala():
    """测试 Scala 所需 Java 运行时可用性"""
    result = is_java_available()
    assert isinstance(result, bool)
    print(f"Java 运行时 (java) 可用: {result}")


def test_type_mapping():
    """测试类型映射"""
    from vools.bridge.scala.compiler import _PY_TO_SCALA_TYPE, _get_scala_type

    # Python → Scala 类型
    assert _get_scala_type(int) == 'Int'
    assert _get_scala_type(float) == 'Double'
    assert _get_scala_type(str) == 'String'
    assert _get_scala_type(bool) == 'Boolean'
    assert _get_scala_type(type(None)) == 'Unit'


def test_mode_only_code():
    """测试 ONLY_CODE 模式（不依赖编译器）"""
    @scala(mode='ONLY_CODE')
    def add(a: int, b: int) -> int:
        return "a + b"

    code = add(5)  # 参数不重要，只生成代码
    assert isinstance(code, str)
    assert 'add' in code
    assert 'a + b' in code
    print(f"生成的 Scala 代码:\n{code}")


def test_simple_int_function():
    """测试简单整数函数"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala
    def add(a: int, b: int) -> int:
        return "a + b"

    result = add(2, 3)
    assert result == 5
    print(f"add(2, 3) = {result}")


def test_string_function():
    """测试字符串函数"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala
    def greet(name: str) -> str:
        return "s\"Hello, $name!\""

    result = greet("World")
    assert isinstance(result, str)
    print(f"greet('World') = {result}")


def test_float_function():
    """测试浮点数函数"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala
    def multiply(a: float, b: float) -> float:
        return "a * b"

    result = multiply(2.5, 4.0)
    assert float(result) == 10.0
    print(f"multiply(2.5, 4.0) = {result}")


def test_boolean_function():
    """测试布尔函数"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala
    def is_even(n: int) -> bool:
        return "n % 2 == 0"

    result = is_even(4)
    assert result is True
    result = is_even(7)
    assert result is False
    print(f"is_even(4) = {is_even(4)}, is_even(7) = {is_even(7)}")


def test_mode_force():
    """测试 FORCE 模式"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala(mode='FORCE')
    def dummy(x: int) -> int:
        return "x * 2"

    # FORCE 模式返回 JAR 路径
    jar_path = dummy(5)
    assert isinstance(jar_path, str)
    assert jar_path.endswith('.jar')
    print(f"FORCE 模式返回 JAR 路径: {jar_path}")


def test_async_mode_only_code():
    """测试异步模式 ONLY_CODE（不依赖编译器）"""
    @scala(mode='ONLY_CODE', async_mode=True)
    def async_add(a: int, b: int) -> int:
        return "a + b"

    code = asyncio.run(async_add(1, 2))
    assert isinstance(code, str)
    assert 'async_add' in code
    assert 'a + b' in code
    print(f"异步 ONLY_CODE 模式生成的代码:\n{code}")


def test_async_mode_execution():
    """测试异步模式实际执行"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala(async_mode=True)
    def async_compute(x: int) -> int:
        return "x * x"

    result = asyncio.run(async_compute(5))
    assert result == 25
    print(f"async_compute(5) = {result}")


def test_async_mode_concurrent():
    """测试异步模式并发执行"""
    if not scala_compiler_available():
        pytest.skip("Scala 编译器不可用")

    @scala(async_mode=True)
    def async_multiply(a: int, b: int) -> int:
        return "a * b"

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


if __name__ == '__main__':
    print("=" * 50)
    print("Scala 桥接测试")
    print("=" * 50)

    available = scala_compiler_available()
    print(f"Scala 编译器可用: {available}")

    if available:
        print("\n运行完整测试...")
        pytest.main([__file__, '-v'])
    else:
        print("\n编译器不可用，运行基础测试...")
        test_type_mapping()
        test_java_available_for_scala()
        test_mode_only_code()
        test_async_mode_only_code()
        print("\n基础测试通过!")