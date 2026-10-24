"""
多线程装饰器

包含：
- trd: 多线程执行装饰器
- proc: 多进程执行装饰器
"""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections.abc import Iterable
from functools import wraps
import types
from typing import Callable, Any, Optional

__all__ = ['trd', 'proc', 'vic_execute']


def vic_execute(func: Optional[Callable] = None, max_workers: int = 3, use_process: bool = False):
    """
    多线程/多进程执行装饰器
    
    参数:
        func: 要装饰的函数
        max_workers: 最大工作线程/进程数
        use_process: 是否使用多进程（默认使用多线程）
    
    返回:
        装饰后的函数
    
    示例:
        >>> @vic_execute(max_workers=10)
        ... def process_data(x):
        ...     return x * 2
        >>> results = process_data(range(100))
    """
    def decorator(func):
        @wraps(func)
        def wrapper(iterable):
            # BUG-359: str/bytes/bytearray 也是 Iterable —— 原实现会把单个字符串
            # **逐字符**展开执行（up('abc') -> ['A','B','C']、bytes -> 整数列表），
            # 这是最容易踩的静默错值。按"单个值"处理，其余可迭代对象照旧逐元素。
            if isinstance(iterable, (str, bytes, bytearray)):
                its = [iterable]
            elif isinstance(iterable, Iterable):
                its = iterable
            else:
                its = [iterable]
            
            pool = ProcessPoolExecutor if use_process else ThreadPoolExecutor
            
            with pool(max_workers=max_workers) as executor:
                results = [future for future in executor.map(func, its)]
            return results
        # BUG-441: @wraps(func) 会把 builtins 的名字（如 print）复制到包装器上，
        # 于是调用参数个数错误时报 "print() takes 1 positional argument but 2
        # were given"，完全看不出是 vic_execute 包装器只接受单个 iterable。
        # 对 builtins 函数改用中性名称；Python 函数/方法仍保留原名。
        if isinstance(func, types.BuiltinFunctionType):
            wrapper.__name__ = "vic_execute_wrapper"
            wrapper.__qualname__ = "vic_execute_wrapper"
        return wrapper
    return decorator if func is None else decorator(func)


# 预定义的装饰器
trd = vic_execute(max_workers=10, use_process=False)
proc = vic_execute(max_workers=3, use_process=True)

