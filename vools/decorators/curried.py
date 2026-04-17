"""
提供 已经柯里化的函数 和类

按照 toolz 库的模式实现常用的柯里化函数和类，所有实现都使用内部的 curry_core.curry 函数，以确保一致的柯里化行为。

包含以下功能：
- 常用的高阶函数：map, filter, reduce, compose, pipe 等
- 数学函数：add, mul, sub, div 等
- 逻辑函数：and_, or_, not_ 等
- 工具函数：identity, const, flip 等
"""

from typing import Any, Callable, Iterable, List, Optional, TypeVar, Union
from functools import reduce

from .curry_core import curry


# 类型定义
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')


# ============================================================================
# 高阶函数
# ============================================================================

@curry
def curried_map(func: Callable[[A], B], iterable: Iterable[A]) -> List[B]:
    """
    柯里化的 map 函数
    
    Args:
        func: 应用于每个元素的函数
        iterable: 可迭代对象
    
    Returns:
        应用函数后的结果列表
    
    Example:
        >>> double = lambda x: x * 2
        >>> curried_map(double, [1, 2, 3])
        [2, 4, 6]
        >>> curried_map(double)([1, 2, 3])
        [2, 4, 6]
    """
    return list(map(func, iterable))


@curry
def curried_filter(func: Callable[[A], bool], iterable: Iterable[A]) -> List[A]:
    """
    柯里化的 filter 函数
    
    Args:
        func: 用于过滤的谓词函数
        iterable: 可迭代对象
    
    Returns:
        过滤后的结果列表
    
    Example:
        >>> is_even = lambda x: x % 2 == 0
        >>> curried_filter(is_even, [1, 2, 3, 4])
        [2, 4]
        >>> curried_filter(is_even)([1, 2, 3, 4])
        [2, 4]
    """
    return list(filter(func, iterable))


@curry
def curried_reduce(func: Callable[[B, A], B], iterable: Iterable[A], initializer: Optional[B] = None) -> B:
    """
    柯里化的 reduce 函数
    
    Args:
        func: 累加函数，接受两个参数
        iterable: 可迭代对象
        initializer: 初始值（可选）
    
    Returns:
        归约后的结果
    
    Example:
        >>> add = lambda x, y: x + y
        >>> curried_reduce(add, [1, 2, 3])
        6
        >>> curried_reduce(add)([1, 2, 3])
        6
        >>> curried_reduce(add, [1, 2, 3], 10)
        16
    """
    from functools import reduce
    if initializer is None:
        return reduce(func, iterable)
    return reduce(func, iterable, initializer)


@curry
def compose(*funcs: Callable) -> Callable:
    """
    柯里化的函数组合
    
    Args:
        *funcs: 要组合的函数
    
    Returns:
        组合后的函数，从右到左应用
    
    Example:
        >>> double = lambda x: x * 2
        >>> add_one = lambda x: x + 1
        >>> composed = compose(add_one, double)
        >>> composed(5)
        11
    """
    def composed_func(*args, **kwargs):
        result = funcs[-1](*args, **kwargs)
        for func in reversed(funcs[:-1]):
            result = func(result)
        return result
    return composed_func


def pipe(data: Any, *funcs: Callable) -> Any:
    """
    管道函数
    
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
def curried_pipe(data: Any, *funcs: Callable) -> Any:
    """
    柯里化的管道函数
    
    Args:
        data: 初始数据
        *funcs: 要应用的函数序列
    
    Returns:
        管道处理后的结果
    
    Example:
        >>> double = lambda x: x * 2
        >>> add_one = lambda x: x + 1
        >>> curried_pipe(5, double, add_one)
        11
        >>> curried_pipe(5)(double, add_one)
        11
    """
    if not funcs:
        def partial_pipe(*more_funcs: Callable) -> Any:
            result = data
            for func in more_funcs:
                result = func(result)
            return result
        return partial_pipe
    
    result = data
    for func in funcs:
        result = func(result)
    return result


# ============================================================================
# 数学函数
# ============================================================================

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
    """
    return a + b


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
def div(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    柯里化的除法函数
    
    Args:
        a: 被除数
        b: 除数
    
    Returns:
        两数之商
    
    Example:
        >>> div(6, 2)
        3.0
        >>> div(6)(2)
        3.0
    """
    return a / b


# ============================================================================
# 逻辑函数
# ============================================================================

@curry
def and_(a: bool, b: bool) -> bool:
    """
    柯里化的逻辑与函数
    
    Args:
        a: 第一个布尔值
        b: 第二个布尔值
    
    Returns:
        逻辑与的结果
    
    Example:
        >>> and_(True, False)
        False
        >>> and_(True)(True)
        True
    """
    return a and b


@curry
def or_(a: bool, b: bool) -> bool:
    """
    柯里化的逻辑或函数
    
    Args:
        a: 第一个布尔值
        b: 第二个布尔值
    
    Returns:
        逻辑或的结果
    
    Example:
        >>> or_(True, False)
        True
        >>> or_(False)(False)
        False
    """
    return a or b


def not_(a: bool) -> bool:
    """
    逻辑非函数
    
    Args:
        a: 布尔值
    
    Returns:
        逻辑非的结果
    
    Example:
        >>> not_(True)
        False
        >>> not_(False)
        True
    """
    return not a


# ============================================================================
# 工具函数
# ============================================================================

def identity(a: A) -> A:
    """
    恒等函数，返回输入值本身
    
    Args:
        a: 任意值
    
    Returns:
        输入值本身
    
    Example:
        >>> identity(5)
        5
        >>> identity("hello")
        "hello"
    """
    return a


@curry
def const(a: A, b: Any) -> A:
    """
    常量函数，忽略第二个参数，返回第一个参数
    
    Args:
        a: 要返回的常量值
        b: 被忽略的参数
    
    Returns:
        常量值 a
    
    Example:
        >>> always_five = const(5)
        >>> always_five(10)
        5
        >>> const("hello", "world")
        "hello"
    """
    return a


@curry
def flip(func: Callable[[A, B], C]) -> Callable[[B, A], C]:
    """
    翻转函数的参数顺序
    
    Args:
        func: 接受两个参数的函数
    
    Returns:
        参数顺序翻转后的函数
    
    Example:
        >>> subtract = lambda a, b: a - b
        >>> flipped_subtract = flip(subtract)
        >>> flipped_subtract(2, 5)
        3  # 相当于 subtract(5, 2)
    """
    def flipped_func(b: B, a: A) -> C:
        return func(a, b)
    return flipped_func


def apply(func: Callable[..., A], *args: Any, **kwargs: Any) -> A:
    """
    应用函数到参数
    
    Args:
        func: 要应用的函数
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        函数应用的结果
    
    Example:
        >>> add = lambda a, b: a + b
        >>> apply(add, 1, 2)
        3
    """
    return func(*args, **kwargs)


@curry
def curried_apply(func: Callable[..., A], *args: Any, **kwargs: Any) -> A:
    """
    柯里化的应用函数到参数
    
    Args:
        func: 要应用的函数
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        函数应用的结果
    
    Example:
        >>> add = lambda a, b: a + b
        >>> curried_apply(add, 1, 2)
        3
        >>> curried_apply(add)(1, 2)
        3
    """
    if not args and not kwargs:
        def partial_apply(*more_args: Any, **more_kwargs: Any) -> A:
            return func(*more_args, **more_kwargs)
        return partial_apply
    return func(*args, **kwargs)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 高阶函数
    'curried_map',
    'curried_filter',
    'curried_reduce',
    'compose',
    'pipe',
    'curried_pipe',
    
    # 数学函数
    'add',
    'mul',
    'sub',
    'div',
    
    # 逻辑函数
    'and_',
    'or_',
    'not_',
    
    # 工具函数
    'identity',
    'const',
    'flip',
    'apply',
    'curried_apply',
]


