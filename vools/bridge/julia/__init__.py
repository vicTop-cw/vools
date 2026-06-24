"""
vools.bridge.julia - Julia 语言桥接模块

提供 Julia 动态编译和跨语言桥接能力，对齐 vools.bridge.go 的 API 形态。

设计目标：免序列化（serialization-free）交互
- 列表/切片参数走 unsafe.Pointer + 长度，不走 CSV/JSON
- 字符串参数走 Cstring，Julia 端由 C.call 包装层做转换
- 通过 pyjulia 风格的 ctypes 模式：编译为 c-shared，ctypes 加载

使用示例::

    from vools.bridge.julia import julia, compile_and_run, julia_compiler_available

    if julia_compiler_available():
        @julia
        def add(a: int, b: int) -> int:
            return "return a + b"

        print(add(2, 3))   # -> 5

        @julia(mode='DEBUG')
        def fib(n: int) -> int:
            return \'\'\'
            if n <= 1
                return 1
            end
            return fib(n-1) + fib(n-2)
            \'\'\'

        print(fib(10))   # -> 89

前置条件:
- 安装 Julia (>= 1.6)，并将 julia 加入 PATH
- Linux/WSL: 推荐使用 JuliaJLL 或 StaticCompiler
- Windows: 需将 Julia\\bin 目录加入 PATH
- 参考: https://julialang.org/
"""

from .decorator import (
    julia,
    julia_compiler_available,
    is_julia_available,
    compile_and_run,
    JuliaFuture,
)
from .compiler import (
    JuliaCompiler,
    compile_julia_code,
    get_compiler,
    JuliaBridge,
    _julia_bridge,
)
from .types import (
    JuliaTypeMapper,
    get_julia_type,
    get_ctypes_type,
    infer_julia_argtypes,
    infer_ctypes_types,
    infer_ret_type,
    convert_args,
)
from .templates import (
    generate_julia_function,
    generate_julia_c_wrapper,
    generate_compile_script,
)
from ._loader import (
    load_julia_dll,
    call_julia_function,
    is_julia_dll_available,
)

julia_bridge = _julia_bridge

__all__ = [
    # 装饰器
    'julia',

    # 编译器检测
    'julia_compiler_available',
    'is_julia_available',

    # 便捷入口
    'compile_and_run',

    # 异步 Future
    'JuliaFuture',

    # 编译器
    'JuliaCompiler',
    'compile_julia_code',
    'get_compiler',

    # 类型映射
    'JuliaTypeMapper',
    'get_julia_type',
    'get_ctypes_type',
    'infer_julia_argtypes',
    'infer_ctypes_types',
    'infer_ret_type',
    'convert_args',

    # 代码生成
    'generate_julia_function',
    'generate_julia_c_wrapper',
    'generate_compile_script',

    # 加载器
    'load_julia_dll',
    'call_julia_function',
    'is_julia_dll_available',

    # LangBridge 实现
    'JuliaBridge',
    'julia_bridge',
]
