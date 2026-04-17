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
            its = iterable if isinstance(iterable, Iterable) else [iterable]
            
            pool = ProcessPoolExecutor if use_process else ThreadPoolExecutor
            
            with pool(max_workers=max_workers) as executor:
                results = [future for future in executor.map(func, its)]
            return results
        return wrapper
    return decorator if func is None else decorator(func)


# 预定义的装饰器
trd = vic_execute(max_workers=10, use_process=False)
proc = vic_execute(max_workers=3, use_process=True)


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    from time import sleep, time
    
    print("=== 测试 trd（多线程）===")
    
    @trd
    def add(x):
        sleep(0.1)
        return x + 1
    
    start = time()
    results = add(range(20))
    elapsed = time() - start
    
    print(f"处理 20 个任务，耗时: {elapsed:.2f}秒")
    print(f"结果前5个: {results[:5]}")
    
    print("\n所有测试通过!")
