"""
提供 已经柯里化的函数 和类

按照 toolz 库的模式实现常用的柯里化函数和类，所有实现都使用内部的 curry_core.curry 函数，以确保一致的柯里化行为。

注意：共享函数从 vools.curried 子包导入，仅保留命名差异的函数。
"""

from typing import Any, Callable, Iterable, List, Optional, TypeVar, Union
from functools import reduce

from .curry_core import curry

# 类型定义
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')

# 从 vools.curried 导入共享函数（使用别名映射命名差异）
from vools.curried import (
    map as curried_map,
    filter as curried_filter,
    reduce as curried_reduce,
    compose,
    identity,
    const,
    flip,
    apply,
    add,
    mul,
    sub,
    div,
)

# pipe 从 vools.curried 导入（同名）
from vools.curried import pipe

# ============================================================================
# decorators 独有的 curried 函数
# ============================================================================

@curry
def curried_pipe(data: Any, *funcs: Callable) -> Any:
    """柯里化的管道函数"""
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


@curry
def and_(a: bool, b: bool) -> bool:
    """柯里化的逻辑与函数"""
    return a and b


@curry
def or_(a: bool, b: bool) -> bool:
    """柯里化的逻辑或函数"""
    return a or b


def not_(a: bool) -> bool:
    """逻辑非函数"""
    return not a


@curry
def curried_apply(func: Callable[..., A], *args: Any, **kwargs: Any) -> A:
    """柯里化的应用函数到参数"""
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