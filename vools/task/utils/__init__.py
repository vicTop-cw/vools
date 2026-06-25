"""
vools.task.utils - 任务队列工具模块

提供任务处理常用的辅助函数和工具类。
"""

from typing import Any, Callable, Optional, TypeVar, Union, List, Dict
from functools import wraps
import asyncio
import time

__all__ = [
    # 函数式工具
    'identity', 'const', 'compose', 'pipe', 'partial',
    # 任务辅助
    'retry', 'timeout', 'catch', 'finally_fn',
    # 异步工具
    'async_retry', 'async_timeout',
    # 装饰器
    'with_timeout', 'with_retry', 'with_logging',
    # 工具类
    'Result',
]

T = TypeVar('T')
F = TypeVar('F', bound=Callable)


# ============================================================================
# 函数式工具
# ============================================================================

def identity(x: T) -> T:
    """恒等函数，原样返回输入值。
    
    Args:
        x: 任意输入值
        
    Returns:
        原样返回输入值
        
    Example:
        >>> identity(42)
        42
    """
    return x


def const(x: T) -> Callable[..., T]:
    """常量函数，返回始终产生相同值的函数。
    
    Args:
        x: 要返回的常量值
        
    Returns:
        忽略所有参数并返回常量的函数
        
    Example:
        >>> f = const(5)
        >>> f(1, 2, 3)
        5
    """
    return lambda *args, **kwargs: x


def compose(*funcs: Callable) -> Callable:
    """函数组合，从右到左执行。
    
    Args:
        *funcs: 要组合的函数列表
        
    Returns:
        组合后的函数
        
    Example:
        >>> f = compose(lambda x: x + 1, lambda x: x * 2)
        >>> f(3)
        7  # (3 * 2) + 1
    """
    if not funcs:
        return identity
    
    def _compose(x):
        result = x
        for func in reversed(funcs):
            result = func(result)
        return result
    return _compose


def pipe(*funcs: Callable) -> Callable:
    """函数管道，从左到右执行。
    
    Args:
        *funcs: 要执行的函数列表
        
    Returns:
        管道函数
        
    Example:
        >>> f = pipe(lambda x: x * 2, lambda x: x + 1)
        >>> f(3)
        7  # (3 * 2) + 1
    """
    if not funcs:
        return identity
    
    def _pipe(x):
        result = x
        for func in funcs:
            result = func(result)
        return result
    return _pipe


def partial(func: Callable, *args, **kwargs) -> Callable:
    """偏函数，预先绑定部分参数。
    
    Args:
        func: 要偏置的函数
        *args: 预绑定的位置参数
        **kwargs: 预绑定的关键字参数
        
    Returns:
        偏函数
        
    Example:
        >>> add = partial(lambda a, b: a + b, 1)
        >>> add(2)
        3
    """
    @wraps(func)
    def _partial(*more_args, **more_kwargs):
        return func(*args, *more_args, **kwargs, **more_kwargs)
    return _partial


# ============================================================================
# 任务辅助函数
# ============================================================================

def retry(func: Callable[[], T], times: int = 3, delay: float = 1.0, 
          exceptions: tuple = (Exception,)) -> T:
    """重试函数执行。
    
    Args:
        func: 要执行的函数
        times: 最大重试次数
        delay: 重试间隔（秒）
        exceptions: 需要重试的异常类型元组
        
    Returns:
        函数执行结果
        
    Raises:
        最后一次重试的异常
        
    Example:
        >>> result = retry(lambda: fetch_data(), times=3, delay=1.0)
    """
    last_exception = None
    for attempt in range(times):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt < times - 1:
                time.sleep(delay)
    raise last_exception


def timeout(func: Callable, seconds: float) -> Callable:
    """为函数添加超时限制。
    
    Args:
        func: 要包装的函数
        seconds: 超时时间（秒）
        
    Returns:
        带超时限制的函数
        
    Note:
        仅支持类 Unix 系统，使用 signal 实现
    """
    import signal
    
    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Function timed out after {seconds} seconds")
    
    @wraps(func)
    def _timeout(*args, **kwargs):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(seconds))
        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    return _timeout


def catch(func: Callable[[], T], default: T = None, 
          exceptions: tuple = (Exception,)) -> T:
    """捕获异常，返回默认值。
    
    Args:
        func: 要执行的函数
        default: 异常时返回的默认值
        exceptions: 要捕获的异常类型元组
        
    Returns:
        函数执行结果或默认值
        
    Example:
        >>> result = catch(lambda: int("not a number"), default=0)
        0
    """
    try:
        return func()
    except exceptions:
        return default


def finally_fn(func: Callable, finally_func: Callable) -> Callable:
    """确保 finally_func 始终执行。
    
    Args:
        func: 主函数
        finally_func: 最终执行的清理函数
        
    Returns:
        包装后的函数
    """
    @wraps(func)
    def _finally(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            finally_func()
    return _finally


# ============================================================================
# 异步工具
# ============================================================================

async def async_retry(func: Callable, times: int = 3, delay: float = 1.0,
                     exceptions: tuple = (Exception,)) -> T:
    """异步重试。
    
    Args:
        func: 异步函数
        times: 最大重试次数
        delay: 重试间隔（秒）
        exceptions: 需要重试的异常类型元组
        
    Returns:
        函数执行结果
    """
    last_exception = None
    for attempt in range(times):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < times - 1:
                await asyncio.sleep(delay)
    raise last_exception


async def async_timeout(coro, seconds: float):
    """异步超时。
    
    Args:
        coro: 协程对象
        seconds: 超时时间
        
    Returns:
        协程执行结果
        
    Raises:
        asyncio.TimeoutError: 超时时抛出
    """
    return await asyncio.wait_for(coro, timeout=seconds)


# ============================================================================
# 装饰器
# ============================================================================

def with_timeout(seconds: float):
    """超时装饰器。
    
    Args:
        seconds: 超时时间（秒）
        
    Example:
        >>> @with_timeout(5.0)
        ... def long_running_task():
        ...     pass
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return timeout(func, seconds)(*args, **kwargs)
        return wrapper
    return decorator


def with_retry(times: int = 3, delay: float = 1.0):
    """重试装饰器。
    
    Args:
        times: 最大重试次数
        delay: 重试间隔（秒）
        
    Example:
        >>> @with_retry(times=3, delay=1.0)
        ... def fetch_data():
        ...     pass
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry(lambda: func(*args, **kwargs), times=times, delay=delay)
        return wrapper
    return decorator


def with_logging(logger=None):
    """日志装饰器。
    
    Args:
        logger: 日志记录器，默认使用 print
        
    Example:
        >>> @with_logging()
        ... def my_task():
        ...     pass
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            log = logger.info if logger else print
            log(f"[START] {func.__name__}")
            try:
                result = func(*args, **kwargs)
                log(f"[END] {func.__name__} - Success")
                return result
            except Exception as e:
                log(f"[ERROR] {func.__name__} - {e}")
                raise
        return wrapper
    return decorator


# ============================================================================
# Result 类型
# ============================================================================

from ...functional.result import Result
