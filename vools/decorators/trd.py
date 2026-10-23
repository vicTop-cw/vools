"""
多线程装饰器

包含：
- trd: 多线程执行装饰器
- proc: 多进程执行装饰器
"""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections.abc import Iterable
from functools import wraps
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
        return wrapper
    return decorator if func is None else decorator(func)


# 预定义的装饰器
trd = vic_execute(max_workers=10, use_process=False)
proc = vic_execute(max_workers=3, use_process=True)

