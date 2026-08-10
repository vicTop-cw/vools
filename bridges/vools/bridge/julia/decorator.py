"""
vools.bridge.julia.decorator - Julia 动态编译装饰器

提供 @julia 装饰器，用于将 Python 函数转换为 Julia 代码并编译为共享库。
支持同步和异步两种模式。
"""

import os
import functools
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from .compiler import (
    _julia_bridge,
    julia_compiler_available,
    compile_julia_code,
    _JULIA_CACHE_DIR,
)
from .types import (
    JuliaTypeMapper,
    get_julia_type,
    get_ctypes_type,
    infer_julia_argtypes,
    infer_ctypes_types,
    infer_ret_type,
    convert_args,
    is_array_type,
)
from ._loader import load_julia_dll, call_julia_function

julia = _julia_bridge.decorator


# =============================================================================
# 异步执行
# =============================================================================

_executor = ThreadPoolExecutor(max_workers=4)


class JuliaFuture:
    """
    Julia 异步执行 Future

    仿 go.GoFuture，对 ThreadPoolExecutor.Future 做薄包装。
    支持 .result() / .done() / .add_done_callback() / .cancel() / __await__。
    """

    def __init__(self, fn, *args, **kwargs):
        self._future = _executor.submit(fn, *args, **kwargs)

    def result(self, timeout=None):
        return self._future.result(timeout=timeout)

    def done(self):
        return self._future.done()

    def add_done_callback(self, fn):
        self._future.add_done_callback(fn)

    def cancel(self):
        return self._future.cancel()

    def __getattr__(self, name):
        return getattr(self._future, name)

    def __await__(self):
        return self._future.__await__()


# =============================================================================
# 便捷函数
# =============================================================================

def compile_and_run(
    julia_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'Int64',
    cache_dir: str = None,
):
    """
    直接编译并运行一段 Julia 源码（无装饰器）

    参数：
        julia_code: 完整 Julia 源码
        func_name: 要调用的导出函数名
        args: Python 位置参数
        ret_type: 返回类型（Julia 端类型字符串）
        cache_dir: 缓存目录（可选）

    返回：
        函数调用结果
    """
    actual_cache_dir = cache_dir or _JULIA_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    # 运行时推断入参类型
    param_julia_types = infer_julia_argtypes(args)

    so_path = compile_julia_code(julia_code, func_name, actual_cache_dir)
    return call_julia_function(so_path, func_name, args, param_julia_types, ret_type)


def is_julia_available() -> bool:
    """
    检查 Julia 桥接是否可用（编译器或预编译库二选一）

    返回：
        bool: True 表示至少有一种使用方式可用
    """
    return julia_compiler_available()


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
    # 类型映射
    'JuliaTypeMapper',
    'get_julia_type',
    'get_ctypes_type',
    'infer_julia_argtypes',
    'infer_ctypes_types',
    'infer_ret_type',
    'convert_args',
    # 内部（暴露用于测试 / 高级用法）
    '_JULIA_CACHE_DIR',
]
