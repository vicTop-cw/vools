"""
Math curried functions - 数学运算柯里化函数

提供数学运算的柯里化版本。
"""

from typing import TypeVar, Union, Iterable
from functools import reduce as functools_reduce

from ..decorators.curry_core import curry

A = TypeVar('A')
T = TypeVar('T')

__all__ = [
    'add',
    'sub',
    'mul',
    'div',
    'mod',
    'pow',
    'floordiv',
    'truediv',
    'inc',
    'dec',
    'neg',
    'abs',
    'min',
    'max',
    'sum',
    'product',
    'mean',
    'median',
]


@curry
def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的加法函数

    Args:
        a: 第一个加数
        b: 第二个加数

    Returns:
        两数之和

    Example:
        >>> add(1, 2)
        3
        >>> add(1)(2)
        3
        >>> add('hello', ' world')
        'hello world'
    """
    return a + b


@curry
def sub(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的减法函数

    Args:
        a: 被减数
        b: 减数

    Returns:
        两数之差

    Example:
        >>> sub(5, 2)
        3
        >>> sub(5)(2)
        3
    """
    return a - b


@curry
def mul(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的乘法函数

    Args:
        a: 第一个乘数
        b: 第二个乘数

    Returns:
        两数之积

    Example:
        >>> mul(2, 3)
        6
        >>> mul(2)(3)
        6
    """
    return a * b


@curry
def div(a: Union[int, float], b: Union[int, float]) -> float:
    """
    柯里化的除法函数（返回浮点数）

    Args:
        a: 被除数
        b: 除数

    Returns:
        两数之商（浮点数）

    Example:
        >>> div(6, 2)
        3.0
        >>> div(6)(2)
        3.0
    """
    return a / b


@curry
def truediv(a: Union[int, float], b: Union[int, float]) -> float:
    """
    柯里化的真除法函数（返回浮点数）

    Args:
        a: 被除数
        b: 除数

    Returns:
        两数之商（浮点数）
    """
    return a / b


@curry
def floordiv(a: Union[int, float], b: Union[int, float]) -> int:
    """
    柯里化的整除函数

    Args:
        a: 被除数
        b: 除数

    Returns:
        整除结果

    Example:
        >>> floordiv(7, 2)
        3
        >>> floordiv(7)(2)
        3
    """
    return a // b


@curry
def mod(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的取模函数

    Args:
        a: 被除数
        b: 除数

    Returns:
        取模结果

    Example:
        >>> mod(7, 2)
        1
        >>> mod(7)(2)
        1
    """
    return a % b


@curry
def pow(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的幂函数

    Args:
        a: 底数
        b: 指数

    Returns:
        a 的 b 次方

    Example:
        >>> pow(2, 3)
        8
        >>> pow(2)(3)
        8
        >>> pow(9)(0.5)
        3.0
    """
    return a ** b


@curry
def inc(x: Union[int, float]) -> Union[int, float]:
    """
    加 1

    Args:
        x: 输入值

    Returns:
        x + 1

    Example:
        >>> inc(5)
        6
    """
    return x + 1


@curry
def dec(x: Union[int, float]) -> Union[int, float]:
    """
    减 1

    Args:
        x: 输入值

    Returns:
        x - 1

    Example:
        >>> dec(5)
        4
    """
    return x - 1


@curry
def neg(x: Union[int, float]) -> Union[int, float]:
    """
    取负

    Args:
        x: 输入值

    Returns:
        -x

    Example:
        >>> neg(5)
        -5
        >>> neg(-3)
        3
    """
    return -x


@curry
def abs(x: Union[int, float]) -> Union[int, float]:
    """
    绝对值

    Args:
        x: 输入值

    Returns:
        |x|

    Example:
        >>> abs(-5)
        5
        >>> abs(3)
        3
    """
    return x if x >= 0 else -x


@curry
def min(*args: Union[int, float]) -> Union[int, float]:
    """
    返回最小值

    Args:
        *args: 要比较的值，或单个可迭代对象

    Returns:
        最小值

    Example:
        >>> min(1, 2, 3)
        1
        >>> min([1, 2, 3])
        1
    """
    if len(args) == 1 and not isinstance(args[0], (int, float)):
        return functools_reduce(lambda a, b: a if a < b else b, args[0])
    return min(args)


@curry
def max(*args: Union[int, float]) -> Union[int, float]:
    """
    返回最大值

    Args:
        *args: 要比较的值，或单个可迭代对象

    Returns:
        最大值

    Example:
        >>> max(1, 2, 3)
        3
        >>> max([1, 2, 3])
        3
    """
    if len(args) == 1 and not isinstance(args[0], (int, float)):
        return functools_reduce(lambda a, b: a if a > b else b, args[0])
    return max(args)


@curry
def sum(iterable: Iterable[Union[int, float]]) -> Union[int, float]:
    """
    求和

    Args:
        iterable: 要求和的可迭代对象

    Returns:
        总和

    Example:
        >>> sum([1, 2, 3, 4, 5])
        15
    """
    return functools_reduce(lambda a, b: a + b, iterable, 0)


@curry
def product(iterable: Iterable[Union[int, float]]) -> Union[int, float]:
    """
    连乘

    Args:
        iterable: 要连乘的可迭代对象

    Returns:
        乘积

    Example:
        >>> product([1, 2, 3, 4])
        24
    """
    return functools_reduce(lambda a, b: a * b, iterable, 1)


@curry
def mean(iterable: Iterable[Union[int, float]]) -> float:
    """
    计算平均值

    Args:
        iterable: 要计算的可迭代对象

    Returns:
        平均值

    Example:
        >>> mean([1, 2, 3, 4, 5])
        3.0
    """
    items = list(iterable)
    if not items:
        raise ValueError("mean() requires at least one item")
    return sum(items) / len(items)


@curry
def median(iterable: Iterable[Union[int, float]]) -> float:
    """
    计算中位数

    Args:
        iterable: 要计算的可迭代对象

    Returns:
        中位数

    Example:
        >>> median([1, 2, 3, 4, 5])
        3
        >>> median([1, 2, 3, 4])
        2.5
    """
    items = sorted(iterable)
    n = len(items)
    if n == 0:
        raise ValueError("median() requires at least one item")
    if n % 2 == 1:
        return items[n // 2]
    return (items[n // 2 - 1] + items[n // 2]) / 2


__all__ = [
    'add',
    'sub',
    'mul',
    'div',
    'mod',
    'pow',
    'floordiv',
    'truediv',
    'inc',
    'dec',
    'neg',
    'abs',
    'min',
    'max',
    'sum',
    'product',
    'mean',
    'median',
]
