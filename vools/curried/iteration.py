"""
Iteration curried functions - 迭代操作柯里化函数

提供对可迭代对象进行操作的柯里化函数。
"""

from typing import TypeVar, Callable, Iterable, List, Optional, Any, Tuple, Union
from functools import reduce as functools_reduce, reduce
from itertools import chain, accumulate as itertools_accumulate
from builtins import map as builtin_map, filter as builtin_filter

from .core import identity, const
from ..decorators.curry_core import curry

A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
T = TypeVar('T')

__all__ = [
    'map',
    'imap',
    'filter',
    'ifilter',
    'reduce',
    'remove',
    'keep',
    'accumulate',
    'compose',
    'pipe',
    'complement',
    'juxt',
]


@curry
def map(func: Callable[[A], B], iterable: Iterable[A]) -> List[B]:
    """
    柯里化的 map 函数，将函数应用于可迭代对象的每个元素

    Args:
        func: 应用于每个元素的函数
        iterable: 可迭代对象

    Returns:
        应用函数后的结果列表

    Example:
        >>> double = lambda x: x * 2
        >>> map(double, [1, 2, 3])
        [2, 4, 6]
        >>> map(lambda x: x ** 2, range(5))
        [0, 1, 4, 9, 16]
    """
    return list(builtin_map(func, iterable))


@curry
def imap(func: Callable[[A], B], iterable: Iterable[A]) -> Iterable[B]:
    """
    惰性版本的 map 函数，返回迭代器而非列表

    Args:
        func: 应用于每个元素的函数
        iterable: 可迭代对象

    Returns:
        应用函数后的惰性迭代器

    Example:
        >>> double = lambda x: x * 2
        >>> result = imap(double, [1, 2, 3])
        >>> type(result)
        <class 'map'>
        >>> list(result)
        [2, 4, 6]
    """
    return builtin_map(func, iterable)


@curry
def filter(pred: Callable[[A], bool], iterable: Iterable[A]) -> List[A]:
    """
    柯里化的 filter 函数，根据谓词过滤元素

    Args:
        pred: 谓词函数，返回 True 保留元素
        iterable: 可迭代对象

    Returns:
        过滤后的结果列表

    Example:
        >>> is_even = lambda x: x % 2 == 0
        >>> filter(is_even, range(10))
        [0, 2, 4, 6, 8]
        >>> filter(lambda x: x > 0, [-1, 0, 1, 2, -3])
        [1, 2]
    """
    return list(builtin_filter(pred, iterable))


@curry
def ifilter(pred: Callable[[A], bool], iterable: Iterable[A]) -> Iterable[A]:
    """
    惰性版本的 filter 函数，返回迭代器而非列表

    Args:
        pred: 谓词函数，返回 True 保留元素
        iterable: 可迭代对象

    Returns:
        过滤后的惰性迭代器

    Example:
        >>> is_even = lambda x: x % 2 == 0
        >>> result = ifilter(is_even, range(10))
        >>> type(result)
        <class 'filter'>
        >>> list(result)
        [0, 2, 4, 6, 8]
    """
    return builtin_filter(pred, iterable)


@curry
def reduce(func: Callable[[B, A], B], iterable: Iterable[A], initializer: Optional[B] = None) -> B:
    """
    柯里化的 reduce 函数，累积归约元素

    Args:
        func: 累加函数，接受两个参数
        iterable: 可迭代对象
        initializer: 初始值（可选）

    Returns:
        归约后的结果，空迭代且无初始值时返回 None

    Example:
        >>> add = lambda x, y: x + y
        >>> reduce(add, [1, 2, 3])
        6
        >>> reduce(add, [1, 2, 3], 10)
        16
        >>> reduce(lambda x, y: x * y, [1, 2, 3, 4])
        24
    """
    if initializer is None:
        try:
            return functools_reduce(func, iterable)
        except TypeError:
            # 空迭代且无初始值时返回 None
            return None
    return functools_reduce(func, iterable, initializer)


@curry
def remove(pred: Callable[[A], bool], iterable: Iterable[A]) -> List[A]:
    """
    移除满足谓词的元素（filter 的反义）

    Args:
        pred: 谓词函数
        iterable: 可迭代对象

    Returns:
        移除元素后的结果

    Example:
        >>> is_even = lambda x: x % 2 == 0
        >>> remove(is_even, range(10))
        [1, 3, 5, 7, 9]
    """
    return filter(complement(pred), iterable)


@curry
def keep(iterable: Iterable[A]) -> List[A]:
    """
    移除 None 值

    Args:
        iterable: 可迭代对象

    Returns:
        移除了 None 值的列表

    Example:
        >>> keep([1, None, 2, None, 3])
        [1, 2, 3]
        >>> keep([None, None, None])
        []
    """
    return filter(identity, iterable)


@curry
def accumulate(func: Callable[[B, A], B], iterable: Iterable[A], initializer: Optional[B] = None) -> List[B]:
    """
    累积计算，返回每一步的结果列表

    Args:
        func: 累加函数
        iterable: 可迭代对象
        initializer: 初始值（可选）

    Returns:
        累积结果列表

    Example:
        >>> import operator
        >>> accumulate(operator.add, [1, 2, 3, 4, 5])
        [1, 3, 6, 10, 15]
        >>> accumulate(lambda x, y: x * y, [1, 2, 3, 4])
        [1, 2, 6, 24]
    """
    if initializer is None:
        return list(itertools_accumulate(iterable, func))
    return list(itertools_accumulate(iterable, func, initializer))


@curry
def compose(*funcs: Callable) -> Callable:
    """
    函数组合，从右到左应用

    Args:
        *funcs: 要组合的函数

    Returns:
        组合后的函数

    Example:
        >>> double = lambda x: x * 2
        >>> add_one = lambda x: x + 1
        >>> composed = compose(add_one, double)
        >>> composed(5)
        11
        >>> compose(str, lambda x: x * 2)(10)
        '20'
    """
    if not funcs:
        return identity

    def composed(*args, **kwargs):
        result = funcs[-1](*args, **kwargs)
        for func in reversed(funcs[:-1]):
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


def complement(func: Callable) -> Callable:
    """
    返回函数的补函数

    Args:
        func: 原始函数

    Returns:
        补函数

    Example:
        >>> is_even = lambda x: x % 2 == 0
        >>> is_odd = complement(is_even)
        >>> is_odd(3)
        True
        >>> is_odd(4)
        False
    """
    @curry
    def complement_func(*args, **kwargs):
        return not func(*args, **kwargs)
    return complement_func


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


__all__ = [
    'map',
    'filter',
    'reduce',
    'remove',
    'keep',
    'accumulate',
    'compose',
    'pipe',
    'complement',
    'juxt',
]
