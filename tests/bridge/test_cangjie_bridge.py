"""
测试仓颉语言桥接功能

测试内容:
- 编译器可用性检测
- 简单函数调用(整数运算)
- 异步调用测试
- 多种模式测试
"""

import pytest
import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.cangjie import (
    cjc_compiler_available,
    cangjie,
    compile_and_run,
    compile_and_run_async,
    batch_compile_and_run_async,
    get_cj_type,
    generate_cj_code,
)


class TestCangjieCompiler:
    """测试仓颉编译器可用性"""

    def test_compiler_available(self):
        """测试编译器是否可用"""
        available = cjc_compiler_available()
        # 如果编译器不可用,跳过后续测试
        if not available:
            pytest.skip("仓颉编译器(cjc)不可用,跳过测试")
        assert available is True


class TestCangjieTypes:
    """测试类型映射"""

    def test_py_to_cj_int(self):
        """测试 int 类型映射"""
        assert get_cj_type(int) == 'Int64'

    def test_py_to_cj_float(self):
        """测试 float 类型映射"""
        assert get_cj_type(float) == 'Float64'

    def test_py_to_cj_bool(self):
        """测试 bool 类型映射"""
        assert get_cj_type(bool) == 'Bool'

    def test_py_to_cj_none(self):
        """测试 None 类型映射"""
        assert get_cj_type(type(None)) == 'Unit'

    def test_py_to_cj_str(self):
        """测试 str 类型映射"""
        assert get_cj_type(str) == 'String'


class TestCangjieCodeGenerator:
    """测试代码生成"""

    def test_generate_simple_function(self):
        """测试生成简单函数"""
        code = generate_cj_code(
            'add',
            ['a', 'b'],
            ['Int64', 'Int64'],
            'Int64',
            'return a + b'
        )
        assert '@C' in code
        assert 'func add' in code
        assert 'a: Int64' in code
        assert 'b: Int64' in code
        assert 'return a + b' in code

    def test_generate_function_with_unit_return(self):
        """测试生成 Unit 返回类型函数"""
        code = generate_cj_code(
            'hello',
            [],
            [],
            'Unit',
            'println("Hello")'
        )
        assert '@C' in code
        assert 'func hello' in code
        assert ': Unit' in code


@pytest.mark.skipif(not cjc_compiler_available(), reason="仓颉编译器不可用")
@pytest.mark.skip(reason="仓颉运行时初始化问题待解决")
class TestCangjieDecorator:
    """测试仓颉装饰器"""

    def test_simple_add(self):
        """测试简单加法函数"""
        @cangjie
        def add(a: int, b: int) -> int:
            return 'return a + b'

        result = add(10, 20)
        assert result == 30

    def test_only_code_mode(self):
        """测试 ONLY_CODE 模式"""
        @cangjie(mode='ONLY_CODE')
        def multiply(a: int, b: int) -> int:
            return 'return a * b'

        code = multiply(5, 6)
        assert '@C' in code
        assert 'func multiply' in code

    def test_force_mode(self):
        """测试 FORCE 模式"""
        @cangjie(mode='FORCE')
        def subtract(a: int, b: int) -> int:
            return 'return a - b'

        dll_path = subtract(10, 5)
        assert dll_path.endswith('.dll') or dll_path.endswith('.so')
        assert os.path.exists(dll_path)


@pytest.mark.skipif(not cjc_compiler_available(), reason="仓颉编译器不可用")
@pytest.mark.skip(reason="仓颉运行时初始化问题待解决")
class TestCangjieCompileAndRun:
    """测试直接编译运行"""

    def test_compile_and_run_simple(self):
        """测试编译运行简单代码"""
        result = compile_and_run(
            'return 42',
            func_name='get_value',
            args=(),
            ret_type='Int64'
        )
        assert result == 42


@pytest.mark.skipif(not cjc_compiler_available(), reason="仓颉编译器不可用")
@pytest.mark.skip(reason="仓颉运行时初始化问题待解决")
class TestCangjieAsync:
    """测试异步调用"""

    def test_async_decorator_only_code(self):
        """测试异步装饰器 ONLY_CODE 模式"""
        @cangjie(async_mode=True)
        def multiply_async(a: int, b: int) -> int:
            return 'return a * b'

        # 异步模式只生成代码
        code = multiply_async(5, 6)
        assert '@C' in code
        assert 'func multiply_async' in code

    @pytest.mark.asyncio
    async def test_async_compile_and_run(self):
        """测试异步编译运行"""
        code = await compile_and_run_async(
            'return 100',
            func_name='get_hundred',
            args=(),
            ret_type='Int64'
        )
        # 异步模式返回代码
        assert '@C' in code or code == 100

    @pytest.mark.asyncio
    async def test_batch_async(self):
        """测试批量异步编译"""
        funcs = [
            ('return 1', 'func1', (), 'Int64'),
            ('return 2', 'func2', (), 'Int64'),
            ('return 3', 'func3', (), 'Int64'),
        ]
        results = await batch_compile_and_run_async(funcs)
        assert len(results) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])