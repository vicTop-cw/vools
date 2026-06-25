"""
测试 LangBridge 的 only_code 模式功能

运行：python tests/test_only_code_mode.py
"""

import sys
import os
import asyncio
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.freebasic import FbcBridge
from vools.core.asyncio_compat import run as asyncio_run


def test_overwrite_mode():
    """测试 overwrite 写入模式"""
    print("=" * 60)
    print("测试 1: overwrite 写入模式")
    print("=" * 60)

    bridge = FbcBridge()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False, encoding='utf-8') as f:
        f.write("' original content line 1\n")
        f.write("' original content line 2\n")
        f.write("' original content line 3\n")
        temp_path = f.name

    try:
        @bridge.decorator(only_code=True, output_file=temp_path, write_mode='overwrite')
        def test_func(x: int) -> int:
            return "Return x * 2"

        result = test_func(5)
        print(f"返回值: {result}")
        assert result == temp_path, "应该返回文件路径"

        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"文件内容（前 200 字符）:\n{content[:200]}")
        assert 'Function test_func' in content, "应该包含生成的函数"
        assert 'original content' not in content, "原内容应该被覆盖"

        print("✓ overwrite 模式测试通过\n")
    finally:
        os.unlink(temp_path)


def test_append_mode():
    """测试 append 写入模式"""
    print("=" * 60)
    print("测试 2: append 写入模式")
    print("=" * 60)

    bridge = FbcBridge()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False, encoding='utf-8') as f:
        f.write("' header line 1\n")
        f.write("' header line 2\n")
        temp_path = f.name

    try:
        @bridge.decorator(only_code=True, output_file=temp_path, write_mode='append')
        def append_func(a: int, b: int) -> int:
            return "Return a + b"

        result = append_func(1, 2)
        assert result == temp_path

        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"文件内容:\n{content}")
        assert "' header line 1" in content, "原内容应该保留"
        assert "' header line 2" in content, "原内容应该保留"
        assert 'Function append_func' in content, "新内容应该被追加"

        print("✓ append 模式测试通过\n")
    finally:
        os.unlink(temp_path)


def test_insert_mode():
    """测试 insert 写入模式"""
    print("=" * 60)
    print("测试 3: insert:NN 写入模式")
    print("=" * 60)

    bridge = FbcBridge()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False, encoding='utf-8') as f:
        f.write("Line 1\n")
        f.write("Line 2\n")
        f.write("Line 3\n")
        f.write("Line 4\n")
        f.write("Line 5\n")
        temp_path = f.name

    try:
        @bridge.decorator(only_code=True, output_file=temp_path, write_mode='insert:3')
        def insert_func(x: int) -> int:
            return "Return x + 1"

        result = insert_func(10)
        assert result == temp_path

        with open(temp_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"文件行数: {len(lines)}")
        for i, line in enumerate(lines, 1):
            print(f"  {i}: {line.rstrip()}")

        assert lines[0].strip() == 'Line 1', "第 1 行应该不变"
        assert lines[1].strip() == 'Line 2', "第 2 行应该不变"
        assert lines[2].strip() == 'Line 3', "第 3 行应该不变"
        assert 'Function insert_func' in lines[3], "第 4 行应该是插入的函数（在第 3 行之后）"
        assert lines[-2].strip() == 'Line 4', "倒数第二行应该是 Line 4"
        assert lines[-1].strip() == 'Line 5', "最后一行应该是 Line 5"

        print("✓ insert 模式测试通过\n")
    finally:
        os.unlink(temp_path)


def test_replace_mode():
    """测试 replace 写入模式"""
    print("=" * 60)
    print("测试 4: replace:MM-NN 写入模式")
    print("=" * 60)

    bridge = FbcBridge()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False, encoding='utf-8') as f:
        f.write("Line 1\n")
        f.write("Line 2\n")
        f.write("Line 3\n")
        f.write("Line 4\n")
        f.write("Line 5\n")
        temp_path = f.name

    try:
        @bridge.decorator(only_code=True, output_file=temp_path, write_mode='replace:2-4')
        def replace_func(x: int) -> int:
            return "Return x * 3"

        result = replace_func(7)
        assert result == temp_path

        with open(temp_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"文件行数: {len(lines)}")
        for i, line in enumerate(lines, 1):
            print(f"  {i}: {line.rstrip()}")

        assert lines[0].strip() == 'Line 1', "第 1 行应该保留"
        assert 'Function replace_func' in lines[1], "第 2 行应该是替换的函数"
        assert lines[-1].strip() == 'Line 5', "最后一行应该是 Line 5"
        assert 'Line 2' not in ''.join(lines), "Line 2 应该被替换"
        assert 'Line 3' not in ''.join(lines), "Line 3 应该被替换"
        assert 'Line 4' not in ''.join(lines), "Line 4 应该被替换"

        print("✓ replace 模式测试通过\n")
    finally:
        os.unlink(temp_path)


def test_prefix_suffix():
    """测试 prefix 和 suffix 参数"""
    print("=" * 60)
    print("测试 5: prefix 和 suffix 参数")
    print("=" * 60)

    bridge = FbcBridge()

    @bridge.decorator(only_code=True, prefix="' PREFIX HEADER\n", suffix="' SUFFIX FOOTER\n")
    def prefix_suffix_func(x: int) -> int:
        return "Return x + 10"

    code = prefix_suffix_func(5)
    print(f"生成的代码:\n{code}")

    assert code.startswith("' PREFIX HEADER"), "代码应该以 prefix 开头"
    assert code.endswith("' SUFFIX FOOTER\n"), "代码应该以 suffix 结尾"
    assert 'Function prefix_suffix_func' in code, "应该包含函数"

    print("✓ prefix/suffix 测试通过\n")


def test_deps_included():
    """测试 deps 依赖函数会被包含在生成的代码中"""
    print("=" * 60)
    print("测试 6: deps 依赖函数包含")
    print("=" * 60)

    bridge = FbcBridge()

    def helper(x: int) -> int:
        return "Return x * 2"

    @bridge.decorator(only_code=True, deps=[helper])
    def main_func(x: int) -> int:
        return "Return helper(x) + 1"

    code = main_func(5)
    print(f"生成的代码:\n{code}")

    assert 'Function helper' in code, "应该包含依赖函数 helper"
    assert 'Function main_func' in code, "应该包含主函数 main_func"
    # 检查顺序：依赖函数应该在主函数之前
    helper_pos = code.index('Function helper')
    main_pos = code.index('Function main_func')
    assert helper_pos < main_pos, "依赖函数应该在主函数之前生成"

    print("✓ deps 测试通过\n")


def test_module_code_included():
    """测试 module_code 会被包含在生成的代码中"""
    print("=" * 60)
    print("测试 7: module_code 包含")
    print("=" * 60)

    bridge = FbcBridge()

    @bridge.decorator(only_code=True, module_code="' Module level code\nConst MY_CONST = 42\n")
    def func_with_module(x: int) -> int:
        return "Return x + MY_CONST"

    code = func_with_module(5)
    print(f"生成的代码:\n{code}")

    assert "' Module level code" in code, "应该包含模块级代码"
    assert "Const MY_CONST = 42" in code, "应该包含模块常量"
    assert 'Function func_with_module' in code, "应该包含函数"

    print("✓ module_code 测试通过\n")


def test_no_only_code_backward_compat():
    """测试不传 only_code 时行为完全不变（向后兼容）"""
    print("=" * 60)
    print("测试 8: 向后兼容（不传 only_code）")
    print("=" * 60)

    bridge = FbcBridge()

    if not bridge.compiler_available():
        print("⚠  编译器不可用，跳过编译相关测试")
        print("✓ 向后兼容测试跳过（无编译器）\n")
        return

    @bridge.decorator
    def add_backward(a: int, b: int) -> int:
        return "Return a + b"

    result = add_backward(3, 4)
    print(f"add_backward(3, 4) = {result}")
    assert result == 7, "常规模式应该正常工作"

    print("✓ 向后兼容测试通过\n")


def test_only_code_no_output_file_returns_code():
    """测试 only_code 模式下不传 output_file 时返回代码字符串"""
    print("=" * 60)
    print("测试 9: 仅代码模式返回代码字符串")
    print("=" * 60)

    bridge = FbcBridge()

    @bridge.decorator(only_code=True)
    def simple_func(x: int) -> int:
        return "Return x * 5"

    code = simple_func(10)
    print(f"返回类型: {type(code)}")
    print(f"代码内容（前 200 字符）:\n{code[:200]}")

    assert isinstance(code, str), "应该返回字符串"
    assert 'Function simple_func' in code, "应该包含函数定义"
    assert 'cdecl' in code, "应该包含 cdecl 调用约定"

    print("✓ 仅代码返回字符串测试通过\n")


def test_async_only_code():
    """测试异步模式下的 only_code"""
    print("=" * 60)
    print("测试 10: 异步 only_code 模式")
    print("=" * 60)

    bridge = FbcBridge()

    @bridge.decorator(only_code=True, async_mode=True)
    async def async_func(x: int) -> int:
        return "Return x + 100"

    async def run_test():
        code = await async_func(42)
        return code

    code = asyncio_run(run_test())
    print(f"异步返回代码（前 200 字符）:\n{code[:200]}")

    assert isinstance(code, str), "应该返回字符串"
    assert 'Function async_func' in code, "应该包含函数定义"

    print("✓ 异步 only_code 测试通过\n")


def test_async_only_code_with_file():
    """测试异步模式下 only_code + output_file"""
    print("=" * 60)
    print("测试 11: 异步 only_code + output_file")
    print("=" * 60)

    bridge = FbcBridge()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False, encoding='utf-8') as f:
        temp_path = f.name

    try:
        @bridge.decorator(only_code=True, async_mode=True, output_file=temp_path)
        async def async_file_func(x: int) -> int:
            return "Return x * 7"

        async def run_test():
            result = await async_file_func(6)
            return result

        result = asyncio_run(run_test())
        print(f"返回值: {result}")
        assert result == temp_path, "应该返回文件路径"

        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()

        assert 'Function async_file_func' in content, "文件应该包含生成的函数"

        print("✓ 异步 only_code + 文件测试通过\n")
    finally:
        os.unlink(temp_path)


def test_write_code_to_file_static():
    """测试 _write_code_to_file 静态方法"""
    print("=" * 60)
    print("测试 12: _write_code_to_file 静态方法")
    print("=" * 60)

    from vools.bridge._base import LangBridge

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("A\nB\nC\nD\nE\n")
        temp_path = f.name

    try:
        # 测试 overwrite
        LangBridge._write_code_to_file("NEW\n", temp_path, 'overwrite')
        with open(temp_path, 'r', encoding='utf-8') as f:
            assert f.read() == "NEW\n"
        print("  ✓ overwrite")

        # 重置
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write("A\nB\nC\nD\nE\n")

        # 测试 append
        LangBridge._write_code_to_file("F\n", temp_path, 'append')
        with open(temp_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert lines[-1] == "F\n"
        assert len(lines) == 6
        print("  ✓ append")

        # 重置
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write("A\nB\nC\nD\nE\n")

        # 测试 insert
        LangBridge._write_code_to_file("X\n", temp_path, 'insert:2')
        with open(temp_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert lines[2] == "X\n"
        assert len(lines) == 6
        print("  ✓ insert")

        # 重置
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write("A\nB\nC\nD\nE\n")

        # 测试 replace
        LangBridge._write_code_to_file("X\nY\n", temp_path, 'replace:2-4')
        with open(temp_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert lines[0] == "A\n"
        assert lines[1] == "X\n"
        assert lines[2] == "Y\n"
        assert lines[3] == "E\n"
        assert len(lines) == 4
        print("  ✓ replace")

        # 测试无效模式
        try:
            LangBridge._write_code_to_file("test", temp_path, 'invalid_mode')
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert 'Unknown write_mode' in str(e)
            print("  ✓ 无效模式报错")

        print("✓ _write_code_to_file 静态方法测试通过\n")
    finally:
        os.unlink(temp_path)


def main():
    print("\n" + "=" * 60)
    print("LangBridge only_code 模式测试")
    print("=" * 60 + "\n")

    try:
        test_overwrite_mode()
        test_append_mode()
        test_insert_mode()
        test_replace_mode()
        test_prefix_suffix()
        test_deps_included()
        test_module_code_included()
        test_no_only_code_backward_compat()
        test_only_code_no_output_file_returns_code()
        test_async_only_code()
        test_async_only_code_with_file()
        test_write_code_to_file_static()

        print("=" * 60)
        print("所有测试通过！✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
