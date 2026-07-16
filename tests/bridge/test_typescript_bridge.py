"""
测试 TypeScript 桥接功能

前置条件：
- 安装 Node.js (node) 并添加到 PATH
- 可选：安装 TypeScript (tsc)
"""

import pytest
import sys
import os
import asyncio

try:
    from vools.bridge.typescript import (
        typescript,
        ts,
        ts_compiler_available,
        is_typescript_available,
        is_node_available,
        get_node_version,
        get_ts_type,
        PY_TO_TS_TYPE,
        compile_and_run,
        TSFuture,
    )
except ImportError as e:
    pytest.skip(f"无法导入 vools.bridge.typescript: {e}", allow_module_level=True)


# ============================================================================
# 测试用例
# ============================================================================

def test_compiler_availability():
    """测试编译器/运行时可用性检查"""
    # node 可用性
    node_available = is_node_available()
    assert isinstance(node_available, bool)
    print(f"Node.js 可用: {node_available}")

    # tsc 可用性
    tsc_available = is_typescript_available()
    assert isinstance(tsc_available, bool)
    print(f"TypeScript 编译器可用: {tsc_available}")

    # 桥接完全可用性（只需 node）
    result = ts_compiler_available()
    assert isinstance(result, bool)
    print(f"TypeScript 桥接可用: {result}")

    if not result:
        pytest.skip("Node.js 不可用，跳过后续需要编译器的测试")

    # 获取版本
    node_ver = get_node_version()
    if node_ver:
        print(f"Node.js 版本: {node_ver}")


def test_type_mapping():
    """测试类型映射"""
    # Python → TypeScript 类型
    assert get_ts_type(int) == 'number'
    assert get_ts_type(float) == 'number'
    assert get_ts_type(str) == 'string'
    assert get_ts_type(bool) == 'boolean'
    assert get_ts_type(list) == 'any[]'
    assert get_ts_type(dict) == 'Record<string, any>'
    assert get_ts_type(type(None)) == 'null'

    # 未知类型返回 'any'
    assert get_ts_type(bytes) == 'any'

    # 验证 PY_TO_TS_TYPE 字典
    assert PY_TO_TS_TYPE[int] == 'number'
    assert PY_TO_TS_TYPE[float] == 'number'
    assert PY_TO_TS_TYPE[str] == 'string'
    assert PY_TO_TS_TYPE[bool] == 'boolean'

    print("类型映射测试通过")


def test_mode_only_code():
    """测试 ONLY_CODE 模式（不依赖编译器）"""
    @typescript(mode='ONLY_CODE')
    def add(a: int, b: int) -> int:
        return "return a + b;"

    code = add(5, 3)  # 参数不重要，只生成代码
    assert isinstance(code, str)
    assert 'add' in code
    assert 'return a + b' in code
    assert 'function' in code.lower() or '=>' in code
    print(f"生成的 TypeScript 代码:\n{code}")


def test_module_code():
    """测试 module_code 支持"""
    @typescript(mode='ONLY_CODE', module_code='import * as fs from "fs";')
    def read_file(path: str) -> str:
        return "return fs.readFileSync(path, 'utf-8');"

    code = read_file("test.txt")
    assert isinstance(code, str)
    assert 'import * as fs from "fs"' in code
    assert 'read_file' in code
    assert "readFileSync" in code
    print(f"带 module_code 生成的代码:\n{code}")


def test_dependencies():
    """测试依赖函数代码在主函数之前生成"""
    def helper(x: int) -> int:
        return "return x * 2;"

    @typescript(mode='ONLY_CODE', deps=[helper])
    def compute(a: int) -> int:
        return "return helper(a) + 1;"

    code = compute(5)
    assert isinstance(code, str)
    assert 'compute' in code
    assert 'return helper(a) + 1' in code
    # 依赖函数 helper 的代码应出现在生成代码中
    assert 'helper' in code
    assert 'return x * 2' in code  # helper 的函数体
    print(f"带依赖函数生成的代码:\n{code}")


def test_simple_int_function():
    """测试简单整数函数编译运行"""
    if not ts_compiler_available():
        pytest.skip("Node.js 不可用")

    @typescript
    def add(a: int, b: int) -> int:
        return "return a + b;"

    result = add(2, 3)
    assert result == 5
    print(f"add(2, 3) = {result}")


def test_string_function():
    """测试字符串函数"""
    if not ts_compiler_available():
        pytest.skip("Node.js 不可用")

    @typescript
    def greet(name: str) -> str:
        return "return 'Hello, ' + name + '!';"

    result = greet("World")
    assert isinstance(result, str)
    assert "Hello" in result
    print(f"greet('World') = {result}")


def test_compile_and_run():
    """测试便捷函数"""
    if not ts_compiler_available():
        pytest.skip("Node.js 不可用")

    result = compile_and_run(
        "return 42;",
        func_name='main',
        param_names=[],
        args=[]
    )
    assert result == 42
    print(f"compile_and_run('return 42;') = {result}")


def test_async_mode_only_code():
    """测试异步模式 ONLY_CODE（不依赖编译器）"""
    @typescript(mode='ONLY_CODE', async_mode=True)
    def async_add(a: int, b: int) -> int:
        return "return a + b;"

    code = asyncio.run(async_add(1, 2))
    assert isinstance(code, str)
    assert 'async_add' in code
    assert 'return a + b' in code
    print(f"异步 ONLY_CODE 模式生成的代码:\n{code}")


def test_async_mode_execution():
    """测试异步模式实际执行"""
    if not ts_compiler_available():
        pytest.skip("Node.js 不可用")

    @typescript(async_mode=True)
    def async_compute(x: int) -> int:
        return "return x * x;"

    result = asyncio.run(async_compute(5))
    assert result == 25
    print(f"async_compute(5) = {result}")


def test_async_mode_concurrent():
    """测试异步模式并发执行"""
    if not ts_compiler_available():
        pytest.skip("Node.js 不可用")

    @typescript(async_mode=True)
    def async_multiply(a: int, b: int) -> int:
        return "return a * b;"

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


def test_ts_future():
    """测试 TSFuture 类"""
    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(lambda: 42)

    ts_future = TSFuture(executor, "dummy.js", [])

    # 注意：TSFuture 通过 executor 执行 _call_ts_function，
    # 这里用假文件路径，主要测试 Future 包装结构
    with pytest.raises(Exception):
        ts_future.result(timeout=5)


def test_ts_alias():
    """测试 ts 别名的装饰器"""
    @ts(mode='ONLY_CODE')
    def multiply(a: int, b: int) -> int:
        return "return a * b;"

    code = multiply(3, 4)
    assert isinstance(code, str)
    assert 'multiply' in code
    assert 'return a * b' in code
    print(f"ts 别名生成的代码:\n{code}")


if __name__ == '__main__':
    print("=" * 50)
    print("TypeScript 桥接测试")
    print("=" * 50)

    available = ts_compiler_available()
    print(f"TypeScript 桥接可用: {available}")

    if available:
        print("\n运行完整测试...")
        pytest.main([__file__, '-v'])
    else:
        print("\nNode.js 不可用，运行基础测试...")
        test_type_mapping()
        test_mode_only_code()
        test_module_code()
        test_dependencies()
        test_async_mode_only_code()
        test_ts_alias()
        print("\n基础测试通过!")