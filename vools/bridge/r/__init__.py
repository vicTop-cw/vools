"""
vools.bridge.r - R 语言桥接模块

提供 R 动态执行与跨语言桥接能力，对齐 vools.bridge.freebasic 的 API 形态。

设计特点：
- 通过 WSL 调用 Rscript 执行 R 代码（Windows）
- 基于 JSON 的进程间数据交换
- 装饰器模式：@r 装饰器，函数体返回 R 代码字符串

前置条件（Windows）：
- 安装 WSL 2
- WSL 中安装 R 和 Rscript
- 推荐安装 jsonlite 包：install.packages("jsonlite")

前置条件（Linux）：
- 系统安装 R 和 Rscript

使用示例：
    from vools.bridge.r import r, compile_and_run, r_compiler_available

    if r_compiler_available():
        @r
        def fib(n: int) -> int:
            return '''
            if (n <= 1) {
                return(1)
            } else {
                return(fib(n - 1) + fib(n - 2))
            }
            '''

        print(fib(10))
"""

from .types import (
    PY_TO_R_TYPE,
    RTypeMapper,
    get_r_type,
    infer_r_types,
    serialize_args,
    deserialize_result,
)
from .templates import (
    RCodeGenerator,
    generate_function_signature,
    generate_script_code,
    generate_from_python_func,
)
from .loader import (
    is_r_available,
    get_r_version,
    is_jsonlite_available,
)
from .compiler import (
    r,
    r_module,
    compile_and_run,
    compile_and_run_async,
    r_compiler_available,
    RBridge,
    _r_bridge,
)

__all__ = [
    # 类型映射
    'PY_TO_R_TYPE',
    'RTypeMapper',
    'get_r_type',
    'infer_r_types',
    'serialize_args',
    'deserialize_result',
    # 代码生成
    'RCodeGenerator',
    'generate_function_signature',
    'generate_script_code',
    'generate_from_python_func',
    # 加载器
    'is_r_available',
    'get_r_version',
    'is_jsonlite_available',
    # 装饰器与执行
    'r',
    'r_module',
    'compile_and_run',
    'compile_and_run_async',
    'r_compiler_available',
    # LangBridge 实现
    'RBridge',
    '_r_bridge',
]
