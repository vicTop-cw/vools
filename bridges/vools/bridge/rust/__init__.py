"""
vools.bridge.rust - Rust 语言桥接模块

提供 Rust 动态编译和桥接能力，采用类似 fbc.py 的装饰器模式。
"""

from .decorator import rust, rust_module
from .compiler import (
    RustCompiler,
    get_compiler,
    compile_rust_code,
    is_rust_available,
)
from .types import (
    RustTypeMapper,
    get_rust_type,
    get_ctypes_type,
    infer_rust_types,
    infer_ctypes_types,
    infer_ret_type,
    convert_args,
)
from .templates import (
    RustCodeGenerator,
    generate_function_signature,
    generate_lib_code,
    generate_cargo_toml,
    generate_from_python_func,
)
from ._loader import (
    load_rust_dll,
    call_rust_function,
    is_rust_dll_available,
)

__all__ = [
    # 装饰器
    'rust',
    'rust_module',

    # 编译器
    'RustCompiler',
    'get_compiler',
    'compile_rust_code',
    'is_rust_available',

    # 类型映射
    'RustTypeMapper',
    'get_rust_type',
    'get_ctypes_type',
    'infer_rust_types',
    'infer_ctypes_types',
    'infer_ret_type',
    'convert_args',

    # 代码生成
    'RustCodeGenerator',
    'generate_function_signature',
    'generate_lib_code',
    'generate_cargo_toml',
    'generate_from_python_func',

    # 加载器
    'load_rust_dll',
    'call_rust_function',
    'is_rust_dll_available',
]