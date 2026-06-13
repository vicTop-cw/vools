"""
Function composition curried functions - 函数组合柯里化函数

提供函数组合和高级函数式编程工具。
"""

from typing import TypeVar, Callable, List, Any, Optional
from functools import lru_cache, wraps

from ..decorators.curry_core import curry

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
T = TypeVar('T')

__all__ = [
    'juxt',
    'memoize',
    'do',
    'tap',
    'compose_left',
    'pipe',
    'apply',
]


@curry
def juxt(*funcs: Callable) -> Callable[[Any], List]:
    """
    并行应用多个函数到同一个值

    Args:
        *funcs: 要应用的函数列表

    Returns:
        返回各函数结果组成的列表

    Example:
        >>> double = lambda x: x * 2
        >>> triple = lambda x: x * 3
        >>> juxt(double, triple, lambda x: x + 1)(5)
        [10, 15, 6]
    """
    @curry
    def juxt_func(val):
        return [f(val) for f in funcs]
    return juxt_func


def memoize(func: Callable = None, *, maxsize: int = 128) -> Callable:
    """
    缓存函数结果的记忆化装饰器

    对于相同输入，多次调用函数只计算一次。

    Args:
        func: 要记忆化的函数
        maxsize: 缓存最大容量

    Returns:
        记忆化后的函数

    Example:
        >>> @memoize
        ... def expensive_computation(x):
        ...     print(f"Computing {x}")
        ...     return x * 2
        >>> expensive_computation(5)
        Computing 5
        10
        >>> expensive_computation(5)  # 不再打印，直接返回缓存结果
        10
    """
    if func is None:
        def decorator(f):
            return _memoize_impl(f, maxsize)
        return decorator
    return _memoize_impl(func, maxsize)


def _memoize_impl(func: Callable, maxsize: int) -> Callable:
    """memoize 的实现"""
    cache = {}
    sentinel = object()

    @wraps(func)
    def memoized(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        result = cache.get(key, sentinel)
        if result is not sentinel:
            return result
        result = func(*args, **kwargs)
        if len(cache) >= maxsize:
            # 简单的 FIFO 策略
            oldest = next(iter(cache))
            del cache[oldest]
        cache[key] = result
        return result

    memoized.cache = cache
    memoized.cache_clear = lambda: cache.clear()
    return memoized


@curry
def do(func: Callable, x: Any) -> Any:
    """
    先执行函数，返回原始值（用于副作用）

    Args:
        func: 要执行的函数
        x: 原始值

    Returns:
        原始值 x

    Example:
        >>> result = []
        >>> do(lambda x: result.append(x) or x, 5)
        5
        >>> result
        [5]
    """
    func(x)
    return x


tap = do


@curry
def compose_left(*funcs: Callable) -> Callable:
    """
    函数组合，从左到右应用（与 compose 相反）

    Args:
        *funcs: 要组合的函数

    Returns:
        组合后的函数

    Example:
        >>> double = lambda x: x * 2
        >>> add_one = lambda x: x + 1
        >>> composed = compose_left(double, add_one)
        >>> composed(5)  # (5 * 2) + 1 = 11
        11
    """
    if not funcs:
        return identity

    def composed(*args, **kwargs):
        result = funcs[0](*args, **kwargs)
        for func in funcs[1:]:
            result = func(result)
        return result

    return composed


@curry
def pipe(data: Any, *funcs: Callable) -> Any:
    """
    管道函数，从左到右应用函数

    Args:
        data: 初始数据
        *funcs: 要应用的函数序列

    Returns:
        管道处理后的结果

    Example:
        >>> double = lambda x: x * 2
        >>> add_one = lambda x: x + 1
        >>> pipe(5, double, add_one)
        11
    """
    result = data
    for func in funcs:
        result = func(result)
    return result


@curry
def apply(func: Callable[..., A], *args, **kwargs) -> A:
    """
    将函数应用到给定的参数

    Args:
        func: 要应用的函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数执行结果

    Example:
        >>> add = lambda a, b: a + b
        >>> apply(add, 1, 2)
        3
    """
    return func(*args, **kwargs)


@curry
def flip(fn: Callable) -> Callable:
    """
    翻转函数参数顺序

    Args:
        fn: 要翻转参数的函数

    Returns:
        参数顺序翻转后的函数

    Example:
        >>> from operator import sub
        >>> flipped_sub = flip(sub)
        >>> flipped_sub(3, 5)  # 等同于 sub(5, 3)
        2
    """
    def flipped(*args, **kwargs):
        if args:
            return fn(*reversed(args), **kwargs)
        return fn(**kwargs)
    return flipped


__all__ = [
    'juxt',
    'memoize',
    'do',
    'tap',
    'compose_left',
    'pipe',
    'apply',
    'flip',
]
