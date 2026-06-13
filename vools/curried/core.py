"""
Core curried functions - 核心柯里化函数

提供函数式编程的基础工具函数。
"""

from typing import TypeVar, Callable, Any, Optional
from functools import lru_cache

from ..decorators.curry_core import curry

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
T = TypeVar('T')

__all__ = [
    'identity',
    'const',
    'flip',
    'apply',
    'curry',
    'memoize',
]


def identity(x: A) -> A:
    """
    返回输入值本身（恒等函数）

    Args:
        x: 任意值

    Returns:
        输入值 x

    Example:
        >>> identity(5)
        5
        >>> identity("hello")
        'hello'
        >>> identity([1, 2, 3])
        [1, 2, 3]
    """
    return x


@curry
def const(x: A, y: B) -> A:
    """
    常量函数，忽略第二个参数，总是返回第一个参数

    Args:
        x: 要返回的常量值
        y: 被忽略的参数

    Returns:
        常量值 x

    Example:
        >>> always_five = const(5)
        >>> always_five(10)
        5
        >>> always_five("anything")
        5
        >>> const("hello", "world")
        'hello'
    """
    return x


@curry
def flip(func: Callable[[A, B], C]) -> Callable[[B, A], C]:
    """
    翻转函数的参数顺序

    Args:
        func: 接受两个参数的函数

    Returns:
        参数顺序翻转后的函数

    Example:
        >>> divide = lambda a, b: a / b
        >>> flipped_divide = flip(divide)
        >>> flipped_divide(2, 6)
        3.0
        >>> flip(lambda a, b: a - b)(1, 5)
        4
    """
    @curry
    def flipped(a: B, b: A) -> C:
        return func(b, a)
    return flipped


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
        >>> apply(print, "hello", "world", sep="-")
        hello-world
    """
    return func(*args, **kwargs)


def _curry_func(func: Callable, *args, **kwargs):
    """通用柯里化函数"""
    if not args and not kwargs:
        @curry
        def curried_func(*a, **k):
            return func(*a, **k)
        return curried_func
    return func(*args, **kwargs)


# Alias for curry from curry_core
curry_func = curry


@lru_cache(maxsize=256)
def memoize(func: Callable) -> Callable:
    """
    缓存函数结果的记忆化装饰器

    对于相同输入，多次调用函数只计算一次。

    Args:
        func: 要记忆化的函数

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
    cache = {}

    @curry
    def memoized(*args, **kwargs):
        # 创建可哈希的键
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]

    return memoized
