"""
vools.bridge.cangjie - 仓颉语言桥接模块

提供仓颉动态编译与跨语言桥接能力,对齐 vools.bridge.nim 的 API 形态。

设计目标:免序列化(serialization-free)交互
- 通过 ctypes 直接调用 C ABI 兼容的仓颉函数
- 动态编译装饰器模式,函数体返回仓颉代码

前置条件:
- 安装仓颉 SDK,并将 cjc 加入 PATH
- 参考: https://cangjie-lang.cn/

使用示例:
    from vools.bridge.cangjie import cangjie, cjc_compiler_available

    if cjc_compiler_available():
        @cangjie
        def fib(n: int) -> int:
            return '''
            if n <= 1 {
                return 1
            } else {
                return fib(n - 1) + fib(n - 2)
            }
            '''

        print(fib(10))
"""

from .types import (
    PY_TO_CJ_TYPE,
    CJ_TO_CTYPES,
    get_cj_type,
    infer_cj_argtypes,
    is_array_type,
    get_ctype_for,
    resolve_cj_ret_type,
)
from .templates import (
    generate_cj_signature,
    generate_cj_code,
    generate_cj_exe_code,
    generate_cj_exe_with_args_code,
    generate_from_python_func,
    CangjieCodeGenerator,
)
from .loader import (
    load_cj_dll,
    get_cj_lib,
    is_cj_available,
    setup_cj_func,
    convert_args,
    convert_result,
    call_cj_func,
)
from .compiler import (
    cangjie,
    compile_and_run,
    compile_and_run_async,
    batch_compile_and_run_async,
    cjc_compiler_available,
    _compile_cj_code,
    _call_cj_func,
    _CJ_CACHE_DIR,
    CjFuture,
    _executor,
)

__all__ = [
    # 类型映射
    'PY_TO_CJ_TYPE',
    'CJ_TO_CTYPES',
    'get_cj_type',
    'infer_cj_argtypes',
    'is_array_type',
    'get_ctype_for',
    'resolve_cj_ret_type',

    # 代码生成
    'generate_cj_signature',
    'generate_cj_code',
    'generate_cj_exe_code',
    'generate_cj_exe_with_args_code',
    'generate_from_python_func',
    'CangjieCodeGenerator',

    # 库加载
    'load_cj_dll',
    'get_cj_lib',
    'is_cj_available',
    'setup_cj_func',
    'convert_args',
    'convert_result',
    'call_cj_func',

    # 编译器
    'cangjie',
    'compile_and_run',
    'compile_and_run_async',
    'batch_compile_and_run_async',
    'cjc_compiler_available',
    '_compile_cj_code',
    '_call_cj_func',
    '_CJ_CACHE_DIR',
    'CjFuture',
    '_executor',
]