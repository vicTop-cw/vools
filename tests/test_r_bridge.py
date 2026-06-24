"""
R 语言桥接测试

测试 vools.bridge.r 模块的基本功能。
需要 WSL + R 环境才能运行完整测试。
"""

import pytest
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.r.types import (
    RTypeMapper,
    get_r_type,
    infer_r_types,
    serialize_args,
    deserialize_result,
    PY_TO_R_TYPE,
)
from vools.bridge.r.templates import (
    RCodeGenerator,
    generate_function_signature,
    generate_script_code,
    generate_from_python_func,
)
from vools.bridge.r.loader import (
    is_r_available,
    get_r_version,
    is_jsonlite_available,
)
from vools.bridge.r.compiler import (
    r_compiler_available,
    compile_and_run,
    compile_and_run_async,
    r,
    r_module,
)


class TestTypes:
    """类型映射测试"""

    def test_py_to_r_type_map(self):
        """测试 Python 类型到 R 类型的映射"""
        assert get_r_type(int) == 'integer'
        assert get_r_type(float) == 'numeric'
        assert get_r_type(bool) == 'logical'
        assert get_r_type(str) == 'character'
        assert get_r_type(bytes) == 'character'
        assert get_r_type(list) == 'vector'
        assert get_r_type(dict) == 'list'
        assert get_r_type(None) == 'NULL'
        assert get_r_type(type(None)) == 'NULL'

    def test_r_type_aliases(self):
        """测试字符串形式的类型别名"""
        assert get_r_type('int') == 'integer'
        assert get_r_type('float') == 'numeric'
        assert get_r_type('double') == 'numeric'
        assert get_r_type('bool') == 'logical'
        assert get_r_type('str') == 'character'
        assert get_r_type('string') == 'character'
        assert get_r_type('none') == 'NULL'
        assert get_r_type('void') == 'NULL'

    def test_infer_r_types(self):
        """测试根据值推断 R 类型"""
        assert infer_r_types([1]) == ['integer']
        assert infer_r_types([1.5]) == ['numeric']
        assert infer_r_types([True]) == ['logical']
        assert infer_r_types(['hello']) == ['character']
        assert infer_r_types([[1, 2, 3]]) == ['integer']
        assert infer_r_types([[1.0, 2.0]]) == ['numeric']
        assert infer_r_types([None]) == ['NULL']
        assert infer_r_types([1, 'hi', 3.14]) == ['integer', 'character', 'numeric']

    def test_serialize_args(self):
        """测试参数序列化"""
        json_str = serialize_args([1, 'hello', 3.14])
        assert '"args"' in json_str
        assert '1' in json_str
        assert 'hello' in json_str
        assert '3.14' in json_str

    def test_deserialize_result(self):
        """测试结果反序列化"""
        assert deserialize_result('42', int) == 42
        assert deserialize_result('3.14', float) == 3.14
        assert deserialize_result('"hello"', str) == 'hello'
        assert deserialize_result('true', bool) is True
        assert deserialize_result('[1,2,3]', list) == [1, 2, 3]
        assert deserialize_result('', None) is None
        assert deserialize_result(None, None) is None


class TestTemplates:
    """代码模板生成测试"""

    def test_generate_function_signature(self):
        """测试生成 R 函数签名"""
        params = [('n', 'integer'), ('x', 'numeric')]
        code = 'return(n + x)'
        result = generate_function_signature('add', params, 'numeric', code)
        assert 'add <- function(n, x)' in result
        assert 'return(n + x)' in result

    def test_generate_script_code(self):
        """测试生成完整 R 脚本"""
        func_code = 'add <- function(a, b) { return(a + b) }'
        script = generate_script_code(func_code, 'add')
        assert 'library(jsonlite)' in script
        assert 'readLines("stdin"' in script
        assert 'do.call(add' in script
        assert 'toJSON(result' in script

    def test_generate_from_python_func(self):
        """测试从 Python 函数生成 R 代码"""
        def add(a: int, b: int) -> int:
            return 'return(a + b)'

        import inspect
        sig = inspect.signature(add)
        result = generate_from_python_func(
            'add', sig, int, 'return(a + b)', True
        )
        assert 'add <- function(a, b)' in result
        assert 'return(a + b)' in result

    def test_extract_preamble(self):
        """测试提取前置语句"""
        code = '''library(dplyr)
# comment
result <- x + y
return(result)'''
        preamble, body = RCodeGenerator.extract_preamble(code)
        assert any('library(dplyr)' in p for p in preamble)
        assert any('# comment' in p for p in preamble)
        assert 'result <- x + y' in body
        assert 'return(result)' in body


class TestLoader:
    """加载器测试（环境检测）"""

    def test_is_r_available_type(self):
        """测试 is_r_available 返回类型"""
        result = is_r_available()
        assert isinstance(result, bool)

    def test_r_compiler_available_type(self):
        """测试 r_compiler_available 返回类型"""
        result = r_compiler_available()
        assert isinstance(result, bool)

    def test_get_r_version(self):
        """测试获取 R 版本"""
        version = get_r_version()
        if version is not None:
            assert isinstance(version, str)

    def test_is_jsonlite_available_type(self):
        """测试 jsonlite 可用性检查返回类型"""
        result = is_jsonlite_available()
        assert isinstance(result, bool)


class TestCompiler:
    """编译器/执行器测试"""

    def test_compiler_available_type(self):
        """测试编译器可用性返回类型"""
        result = r_compiler_available()
        assert isinstance(result, bool)

    def test_r_decorator_only_code(self):
        """测试 @r 装饰器的 ONLY_CODE 模式"""
        @r(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return 'return(a + b)'

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'add <- function(a, b)' in result
        assert 'return(a + b)' in result

    def test_r_decorator_only_code_no_signature(self):
        """测试 @r 装饰器 ONLY_CODE 模式（不自动生成签名）"""
        @r(mode='ONLY_CODE', auto_signature=False)
        def custom_func():
            return 'x <- 1:10\nmean(x)'

        result = custom_func()
        assert isinstance(result, str)
        assert 'x <- 1:10' in result
        assert 'mean(x)' in result

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_compile_and_run_basic(self):
        """测试基本的编译运行"""
        result = compile_and_run(
            'return(arg0 + arg1)',
            func_name='add',
            args=(3, 4),
            ret_type='integer'
        )
        assert result == 7

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_normal(self):
        """测试 @r 装饰器正常模式"""
        @r
        def fib(n: int) -> int:
            return '''
            if (n <= 1) {
                return(1)
            } else {
                return(fib(n - 1) + fib(n - 2))
            }
            '''

        result = fib(10)
        assert result == 89

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_float(self):
        """测试浮点运算"""
        @r
        def multiply(a: float, b: float) -> float:
            return 'return(a * b)'

        result = multiply(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_string(self):
        """测试字符串操作"""
        @r
        def greet(name: str) -> str:
            return 'return(paste0("Hello, ", name, "!"))'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @r(fallback=py_add)
        def add(a: int, b: int) -> int:
            return 'return(a + b)'

        result = add(3, 4)
        assert result == 7

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_compile_and_run_vector_sum(self):
        """测试向量求和"""
        result = compile_and_run(
            'return(sum(arg0))',
            func_name='vec_sum',
            args=([1, 2, 3, 4, 5],),
            ret_type='integer'
        )
        assert result == 15

    def test_r_module_decorator_structure(self):
        """测试 r_module 装饰器的结构（不实际执行）"""
        @r_module(name='test_math')
        class TestMath:
            def add(self, a: int, b: int) -> int:
                return 'return(a + b)'

            def multiply(self, a: float, b: float) -> float:
                return 'return(a * b)'

        assert hasattr(TestMath, 'add')
        assert hasattr(TestMath, 'multiply')


class TestAsync:
    """异步执行测试"""

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_compile_and_run_async_basic(self):
        """测试异步编译运行基本功能"""
        async def _run():
            result = await compile_and_run_async(
                'return(arg0 + arg1)',
                func_name='add_async',
                args=(5, 7),
                ret_type='integer'
            )
            return result

        result = asyncio.run(_run())
        assert result == 12

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_compile_and_run_async_vector(self):
        """测试异步向量运算"""
        async def _run():
            result = await compile_and_run_async(
                'return(sum(arg0))',
                func_name='vec_sum_async',
                args=([10, 20, 30, 40],),
                ret_type='integer'
            )
            return result

        result = asyncio.run(_run())
        assert result == 100

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_async_mode(self):
        """测试 @r 装饰器 async_mode=True"""
        @r(async_mode=True)
        def fib_async(n: int) -> int:
            return '''
            if (n <= 1) {
                return(1)
            } else {
                return(fib_async(n - 1) + fib_async(n - 2))
            }
            '''

        async def _run():
            return await fib_async(10)

        result = asyncio.run(_run())
        assert result == 89

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_async_float(self):
        """测试异步浮点运算"""
        @r(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return 'return(a * b)'

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_r_decorator_async_string(self):
        """测试异步字符串操作"""
        @r(async_mode=True)
        def greet_async(name: str) -> str:
            return 'return(paste0("Hello, ", name, "!"))'

        async def _run():
            return await greet_async("Async")

        result = asyncio.run(_run())
        assert "Hello" in result
        assert "Async" in result

    @pytest.mark.skipif(not r_compiler_available(), reason="R 环境不可用")
    def test_async_concurrent(self):
        """测试多个异步任务并发执行"""
        @r(async_mode=True)
        def slow_add(a: int, b: int) -> int:
            return '''
            Sys.sleep(0.1)
            return(a + b)
            '''

        async def _run():
            tasks = [slow_add(i, i * 2) for i in range(5)]
            results = await asyncio.gather(*tasks)
            return results

        results = asyncio.run(_run())
        assert results == [0, 3, 6, 9, 12]


class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import r
        assert r is not None

    def test_import_r_compiler_available(self):
        """测试从 vools.bridge 导入 r_compiler_available"""
        from vools.bridge import r_compiler_available
        assert callable(r_compiler_available)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-x'])
