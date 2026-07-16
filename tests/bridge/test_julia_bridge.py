"""
Julia 语言桥接测试

测试 vools.bridge.julia 模块的基本功能。
需要 Julia 编译器才能运行完整测试。
"""

import pytest
import sys
import os
import asyncio
from vools.bridge.julia import (
    julia,
    julia_compiler_available,
    is_julia_available,
    JuliaTypeMapper,
    get_julia_type,
    get_ctypes_type,
    infer_julia_argtypes,
    infer_ctypes_types,
    infer_ret_type,
    convert_args,
)
from vools.bridge.julia.templates import (
    generate_julia_function,
    generate_julia_c_wrapper,
    generate_compile_script,
)
from vools.bridge.julia.compiler import (
    JuliaBridge,
    JuliaCompiler,
    _JULIA_CACHE_DIR,
    _JULIA_PATH,
)


# =============================================================================
# 测试辅助
# =============================================================================

julia_available = julia_compiler_available()


# =============================================================================
# 类型映射测试
# =============================================================================

class TestJuliaTypeMapping:
    """测试 Python → Julia 类型映射"""

    def test_basic_type_mapping(self):
        """测试基本类型映射"""
        assert get_julia_type(int) == 'Int64'
        assert get_julia_type(float) == 'Float64'
        assert get_julia_type(str) == 'String'
        assert get_julia_type(bool) == 'Bool'
        assert get_julia_type(bytes) == 'Vector{UInt8}'
        assert get_julia_type(bytearray) == 'Vector{UInt8}'
        assert get_julia_type(list) == 'Vector{Any}'
        assert get_julia_type(tuple) == 'Tuple'
        assert get_julia_type(type(None)) == 'Nothing'
        assert get_julia_type(None) == 'Nothing'

    def test_string_aliases(self):
        """测试字符串形式的类型别名"""
        assert get_julia_type('int') == 'Int64'
        assert get_julia_type('int64') == 'Int64'
        assert get_julia_type('float') == 'Float64'
        assert get_julia_type('float64') == 'Float64'
        assert get_julia_type('double') == 'Float64'
        assert get_julia_type('bool') == 'Bool'
        assert get_julia_type('str') == 'String'
        assert get_julia_type('string') == 'String'
        assert get_julia_type('none') == 'Nothing'
        assert get_julia_type('nothing') == 'Nothing'
        assert get_julia_type('void') == 'Nothing'

    def test_ctypes_type_mapping(self):
        """测试 Julia 类型到 ctypes 的映射"""
        import ctypes
        assert get_ctypes_type('Int64') == ctypes.c_int64
        assert get_ctypes_type('Float64') == ctypes.c_double
        assert get_ctypes_type('Bool') == ctypes.c_bool
        assert get_ctypes_type('Cstring') == ctypes.c_char_p
        assert get_ctypes_type('Ptr{Cvoid}') == ctypes.c_void_p
        assert get_ctypes_type('Nothing') is None
        assert get_ctypes_type('Void') is None

    def test_infer_julia_argtypes(self):
        """测试根据值推断 Julia 类型"""
        assert infer_julia_argtypes([1]) == ['Int64']
        assert infer_julia_argtypes([1.5]) == ['Float64']
        assert infer_julia_argtypes([True]) == ['Bool']
        assert infer_julia_argtypes(['hello']) == ['Cstring']
        assert infer_julia_argtypes([1, 2.0, 'hi']) == ['Int64', 'Float64', 'Cstring']

    def test_infer_ctypes_types(self):
        """测试根据值推断 ctypes 类型"""
        import ctypes
        assert infer_ctypes_types([1]) == [ctypes.c_int64]
        assert infer_ctypes_types([1.5]) == [ctypes.c_double]
        assert infer_ctypes_types([True]) == [ctypes.c_bool]
        assert infer_ctypes_types(['hello']) == [ctypes.c_char_p]

    def test_infer_ret_type(self):
        """测试推断返回类型"""
        import ctypes
        jl_t, ct_t = infer_ret_type(int)
        assert jl_t == 'Int64'
        assert ct_t == ctypes.c_int64

        jl_t, ct_t = infer_ret_type(float)
        assert jl_t == 'Float64'
        assert ct_t == ctypes.c_double

        jl_t, ct_t = infer_ret_type(None)
        assert jl_t == 'Nothing'
        assert ct_t is None

    def test_convert_args_basic(self):
        """测试参数转换"""
        import ctypes
        converted = convert_args([1, 2.0, 'hi'], [ctypes.c_int64, ctypes.c_double, ctypes.c_char_p])
        assert converted[0] == 1
        assert converted[1] == 2.0
        assert converted[2] == b'hi'

    def test_convert_args_bool(self):
        """测试布尔参数转换"""
        import ctypes
        converted = convert_args([True, False], [ctypes.c_bool, ctypes.c_bool])
        assert converted[0] is True
        assert converted[1] is False

    def test_julia_type_mapper_class(self):
        """测试 JuliaTypeMapper 类"""
        assert JuliaTypeMapper.python_to_julia(int) == 'Int64'
        assert JuliaTypeMapper.python_to_julia(float) == 'Float64'
        assert JuliaTypeMapper.python_to_julia(str) == 'String'
        assert JuliaTypeMapper.python_to_julia(bool) == 'Bool'


# =============================================================================
# 代码生成测试
# =============================================================================

class TestJuliaCodeGeneration:
    """测试 Julia 代码生成"""

    def test_generate_julia_function_basic(self):
        """测试基本函数代码生成"""
        import inspect

        def add(a: int, b: int) -> int:
            return "return a + b"

        sig = inspect.signature(add)
        from vools.bridge.julia.types import get_julia_type
        code = generate_julia_function('add', sig, 'Int64', 'return a + b', auto_signature=True)

        assert 'function add(' in code
        assert 'a::Int64' in code
        assert 'b::Int64' in code
        assert '::Int64' in code
        assert 'return a + b' in code
        assert code.strip().endswith('end')

    def test_generate_julia_function_float(self):
        """测试浮点函数代码生成"""
        import inspect

        def multiply(a: float, b: float) -> float:
            return "return a * b"

        sig = inspect.signature(multiply)
        code = generate_julia_function('multiply', sig, 'Float64', 'return a * b', auto_signature=True)

        assert 'function multiply(' in code
        assert 'a::Float64' in code
        assert 'b::Float64' in code
        assert 'return a * b' in code

    def test_generate_julia_function_no_return(self):
        """测试无返回值函数的代码生成"""
        import inspect

        def greet(name: str):
            return 'println("Hello, ", name)'

        sig = inspect.signature(greet)
        code = generate_julia_function('greet', sig, 'Nothing', 'println("Hello, ", name)', auto_signature=True)

        assert 'function greet(' in code
        assert 'name::String' in code
        assert 'println("Hello, ", name)' in code

    def test_generate_julia_c_wrapper(self):
        """测试 C 包装器代码生成"""
        import inspect

        def add(a: int, b: int) -> int:
            return "return a + b"

        sig = inspect.signature(add)
        code = generate_julia_c_wrapper('add', sig, 'Int64', 'return a + b')

        assert 'function add(' in code
        assert 'a::Int64' in code
        assert 'b::Int64' in code
        assert 'return a + b' in code
        assert code.strip().endswith('end')

    def test_bridge_generate_code(self):
        """测试 JuliaBridge.generate_code 方法"""
        from vools.bridge._base import FunctionSpec

        bridge = JuliaBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='return a + b',
        )
        code = bridge.generate_code(spec)

        assert 'function add(' in code
        assert 'a::Int64' in code
        assert 'b::Int64' in code
        assert 'return a + b' in code

    def test_bridge_generate_code_with_module_code(self):
        """测试带 module_code 的代码生成"""
        from vools.bridge._base import FunctionSpec

        bridge = JuliaBridge()
        spec = FunctionSpec(
            name='add',
            annotations={'a': int, 'b': int, 'return': int},
            args=(),
            defaults={},
            body='return a + b',
            module_code='using LinearAlgebra',
        )
        code = bridge.generate_code(spec)

        assert 'using LinearAlgebra' in code
        assert 'function add(' in code

    def test_bridge_generate_code_with_dependencies(self):
        """测试带依赖函数的代码生成"""
        from vools.bridge._base import FunctionSpec

        bridge = JuliaBridge()
        dep_spec = FunctionSpec(
            name='helper',
            annotations={'x': int, 'return': int},
            args=(),
            defaults={},
            body='return x * 2',
        )
        spec = FunctionSpec(
            name='main_func',
            annotations={'a': int, 'return': int},
            args=(),
            defaults={},
            body='return helper(a) + 1',
            dependencies=[dep_spec],
        )
        code = bridge.generate_code(spec)

        assert 'function helper(' in code
        assert 'function main_func(' in code
        assert 'return x * 2' in code
        assert 'return helper(a) + 1' in code
        # helper 应该在 main_func 之前
        assert code.index('helper') < code.index('main_func')


# =============================================================================
# 编译器检测测试
# =============================================================================

class TestCompilerDetection:
    """测试编译器检测功能"""

    def test_julia_compiler_available_type(self):
        """测试 julia_compiler_available 返回类型"""
        result = julia_compiler_available()
        assert isinstance(result, bool)

    def test_is_julia_available_type(self):
        """测试 is_julia_available 返回类型"""
        result = is_julia_available()
        assert isinstance(result, bool)

    def test_julia_compiler_instance(self):
        """测试 JuliaCompiler 实例"""
        compiler = JuliaCompiler()
        assert isinstance(compiler.available, bool)
        version = compiler.version
        if version:
            assert isinstance(version, str)

    def test_cache_dir_exists(self):
        """测试缓存目录存在"""
        assert isinstance(_JULIA_CACHE_DIR, str)

    def test_julia_path_exists(self):
        """测试 julia 路径存在"""
        assert isinstance(_JULIA_PATH, str)
        assert len(_JULIA_PATH) > 0


# =============================================================================
# 装饰器 ONLY_CODE 模式测试（无需编译器）
# =============================================================================

class TestJuliaDecoratorOnlyCode:
    """测试 @julia 装饰器的 ONLY_CODE 模式（无需 Julia 编译器）"""

    def test_only_code_mode_basic(self):
        """测试 ONLY_CODE 模式生成基本代码"""
        @julia(mode='ONLY_CODE')
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(1, 2)
        assert isinstance(result, str)
        assert 'function add(' in result
        assert 'a::Int64' in result
        assert 'b::Int64' in result
        assert 'return a + b' in result

    def test_only_code_mode_float(self):
        """测试 ONLY_CODE 模式生成浮点函数代码"""
        @julia(mode='ONLY_CODE')
        def multiply(a: float, b: float) -> float:
            return "return a * b"

        result = multiply(1.0, 2.0)
        assert isinstance(result, str)
        assert 'function multiply(' in result
        assert 'a::Float64' in result
        assert 'b::Float64' in result
        assert 'return a * b' in result

    def test_only_code_mode_string(self):
        """测试 ONLY_CODE 模式生成字符串函数代码"""
        @julia(mode='ONLY_CODE')
        def greet(name: str) -> str:
            return 'return "Hello, " * name'

        result = greet("World")
        assert isinstance(result, str)
        assert 'function greet(' in result
        assert 'name::String' in result

    def test_only_code_mode_bool(self):
        """测试 ONLY_CODE 模式生成布尔函数代码"""
        @julia(mode='ONLY_CODE')
        def is_positive(x: int) -> bool:
            return "return x > 0"

        result = is_positive(5)
        assert isinstance(result, str)
        assert 'function is_positive(' in result
        assert 'x::Int64' in result
        assert 'Bool' in result

    def test_only_code_mode_multiline(self):
        """测试 ONLY_CODE 模式生成多行函数体代码"""
        @julia(mode='ONLY_CODE')
        def fib(n: int) -> int:
            return """
            if n <= 1
                return 1
            end
            return fib(n-1) + fib(n-2)
            """

        result = fib(10)
        assert isinstance(result, str)
        assert 'function fib(' in result
        assert 'if n <= 1' in result
        assert 'fib(n-1) + fib(n-2)' in result

    def test_only_code_mode_with_module_code(self):
        """测试 ONLY_CODE 模式带 module_code"""
        @julia(mode='ONLY_CODE', module_code='using LinearAlgebra')
        def matmul(a, b):
            return 'return a * b'

        result = matmul(1, 2)
        assert isinstance(result, str)
        assert 'using LinearAlgebra' in result

    def test_only_code_mode_with_deps(self):
        """测试 ONLY_CODE 模式带依赖函数"""
        def helper(x: int) -> int:
            return "return x * 2"

        @julia(mode='ONLY_CODE', deps=[helper])
        def main_func(a: int) -> int:
            return "return helper(a) + 1"

        result = main_func(5)
        assert isinstance(result, str)
        assert 'function helper(' in result
        assert 'function main_func(' in result
        assert 'return x * 2' in result
        assert 'return helper(a) + 1' in result
        # helper 应该在 main_func 之前
        assert result.index('helper') < result.index('main_func')


# =============================================================================
# 装饰器功能测试（需要 Julia 编译器）
# =============================================================================

@pytest.mark.skipif(not julia_available, reason="Julia compiler not available")
class TestJuliaDecorator:
    """测试 @julia 装饰器（需要 Julia 编译器）"""

    def test_simple_addition(self):
        """测试简单加法函数"""
        @julia
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(3, 4)
        assert result == 7

    def test_subtraction(self):
        """测试减法函数"""
        @julia
        def sub(a: int, b: int) -> int:
            return "return a - b"

        result = sub(10, 3)
        assert result == 7

    def test_multiplication(self):
        """测试乘法函数"""
        @julia
        def mul(a: int, b: int) -> int:
            return "return a * b"

        result = mul(6, 7)
        assert result == 42

    def test_fibonacci(self):
        """测试斐波那契函数"""
        @julia
        def fib(n: int) -> int:
            return """
            if n <= 1
                return 1
            end
            return fib(n-1) + fib(n-2)
            """

        result = fib(10)
        assert result == 89

    def test_float_operation(self):
        """测试浮点运算"""
        @julia
        def multiply_float(a: float, b: float) -> float:
            return "return a * b"

        result = multiply_float(3.5, 2.0)
        assert abs(result - 7.0) < 0.001

    def test_string_operation(self):
        """测试字符串操作"""
        @julia
        def greet(name: str) -> str:
            return 'return "Hello, " * name * "!"'

        result = greet("World")
        assert "Hello" in result
        assert "World" in result

    def test_boolean_operation(self):
        """测试布尔运算"""
        @julia
        def is_even(n: int) -> bool:
            return "return n % 2 == 0"

        result = is_even(4)
        assert result is True

        result = is_even(5)
        assert result is False

    def test_multiple_functions(self):
        """测试多个函数"""
        @julia
        def add(a: int, b: int) -> int:
            return "return a + b"

        @julia
        def mul(a: int, b: int) -> int:
            return "return a * b"

        @julia
        def sub(a: int, b: int) -> int:
            return "return a - b"

        assert add(10, 5) == 15
        assert mul(10, 5) == 50
        assert sub(10, 5) == 5

    def test_fallback(self):
        """测试 fallback 回退机制"""
        def py_add(a, b):
            return a + b

        @julia(fallback=py_add)
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(3, 4)
        assert result == 7


# =============================================================================
# 异步模式测试
# =============================================================================

@pytest.mark.skipif(not julia_available, reason="Julia compiler not available")
class TestJuliaAsyncMode:
    """测试 @julia 装饰器异步模式"""

    def test_async_mode_basic(self):
        """测试异步模式基本功能"""
        @julia(async_mode=True)
        def add_async(a: int, b: int) -> int:
            return "return a + b"

        async def _run():
            return await add_async(5, 7)

        result = asyncio.run(_run())
        assert result == 12

    def test_async_mode_fib(self):
        """测试异步模式斐波那契"""
        @julia(async_mode=True)
        def fib_async(n: int) -> int:
            return """
            if n <= 1
                return 1
            end
            return fib_async(n-1) + fib_async(n-2)
            """

        async def _run():
            return await fib_async(10)

        result = asyncio.run(_run())
        assert result == 89

    def test_async_mode_float(self):
        """测试异步模式浮点运算"""
        @julia(async_mode=True)
        def multiply_async(a: float, b: float) -> float:
            return "return a * b"

        async def _run():
            return await multiply_async(3.5, 4.0)

        result = asyncio.run(_run())
        assert abs(result - 14.0) < 0.001

    def test_async_mode_multiple(self):
        """测试多个异步任务并发执行"""
        @julia(async_mode=True)
        def add_concurrent(a: int, b: int) -> int:
            return "return a + b"

        async def _run():
            tasks = [add_concurrent(i, i * 2) for i in range(5)]
            results = await asyncio.gather(*tasks)
            return results

        results = asyncio.run(_run())
        assert results == [0, 3, 6, 9, 12]


# =============================================================================
# module_code 和 dependencies 测试
# =============================================================================

@pytest.mark.skipif(not julia_available, reason="Julia compiler not available")
class TestJuliaModuleCodeAndDeps:
    """测试 module_code 和 dependencies 功能"""

    def test_module_code_basic(self):
        """测试基本 module_code 功能"""
        @julia(module_code='# Module-level comment')
        def add(a: int, b: int) -> int:
            return "return a + b"

        result = add(3, 4)
        assert result == 7

    def test_dependencies_basic(self):
        """测试基本依赖函数"""
        def helper(x: int) -> int:
            return "return x * 2"

        @julia(deps=[helper])
        def main_func(a: int) -> int:
            return "return helper(a) + 1"

        result = main_func(5)
        assert result == 11  # helper(5) = 10, 10 + 1 = 11

    def test_module_code_and_deps_combined(self):
        """测试 module_code 和 dependencies 组合使用"""
        def square(x: int) -> int:
            return "return x * x"

        @julia(module_code='# Combined module code', deps=[square])
        def compute(a: int) -> int:
            return "return square(a) + a"

        result = compute(4)
        assert result == 20  # square(4) = 16, 16 + 4 = 20

    def test_only_code_with_module_and_deps(self):
        """测试 ONLY_CODE 模式带 module_code 和 dependencies"""
        def helper(x: int) -> int:
            return "return x * 3"

        @julia(mode='ONLY_CODE', module_code='# Module preamble', deps=[helper])
        def main_func(a: int) -> int:
            return "return helper(a) + 1"

        result = main_func(5)
        assert isinstance(result, str)
        assert '# Module preamble' in result
        assert 'function helper(' in result
        assert 'function main_func(' in result
        assert 'return x * 3' in result
        assert 'return helper(a) + 1' in result


# =============================================================================
# 桥接集成测试
# =============================================================================

class TestBridgeIntegration:
    """桥接框架集成测试"""

    def test_import_from_bridge(self):
        """测试从 vools.bridge 导入"""
        from vools.bridge import julia
        assert julia is not None

    def test_import_julia_compiler_available(self):
        """测试从 vools.bridge 导入 julia_compiler_available"""
        from vools.bridge import julia_compiler_available
        assert callable(julia_compiler_available)

    def test_JuliaBridge_instance(self):
        """测试 JuliaBridge 实例"""
        bridge = JuliaBridge()
        assert bridge.name == 'julia'
        assert bridge.file_ext == '.jl'
        assert bridge.is_compiled is False
        assert isinstance(bridge.compiler_available(), bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])