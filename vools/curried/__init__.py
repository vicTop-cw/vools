"""
vools.curried - 完整的 Curried 函数库

基于 toolz.curried 模块设计的函数式编程工具集，
提供全面柯里化的高阶函数支持。

功能分类:
- core: 核心工具函数 (identity, const, flip, etc.)
- iteration: 迭代操作函数 (map, filter, reduce, etc.)
- collection: 集合操作函数 (groupby, partition, unique, etc.)
- composition: 函数组合 (compose, pipe, juxt, etc.)
- math: 数学运算 (add, sub, mul, div, etc.)
- string: 字符串操作 (join, split, strip, etc.)
- predicate: 谓词和比较 (is_none, is_eq, etc.)

示例:
    >>> from vools.curried import map, filter, reduce, add
    >>> filter(add(1), range(10))  # 柯里化使用
    [1, 3, 5, 7, 9]
"""

from typing import TypeVar, Callable, Iterable, List, Optional, Any, Union
from functools import reduce as functools_reduce

# 导入基础柯里化装饰器
from ..decorators.curry_core import curry

# 类型变量
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')
T = TypeVar('T')

__version__ = '1.0.0'

__all__ = [
    # 版本
    '__version__',
]

# 导入各模块
from .core import (
    identity,
    const,
    flip,
    apply,
    curry,
)
from .iteration import (
    map,
    imap,
    filter,
    ifilter,
    reduce,
    remove,
    keep,
    accumulate,
    compose,
    pipe,
)
from .collection import (
    unique,
    iunique,
    groupby,
    groupby as group_by,
    partition,
    partition_all,
    concat,
    cat,
    flatten,
    first,
    second,
    last,
    nth,
    get,
    pluck,
    pluck_attr,
    walk,
    mapcat,
    compact,
    merge,
    merge_with,
    get_in,
    set_in,
    update_in,
    interleave,
    interpose,
    split_at,
    butlast,
    dissoc,
    assoc,
    assoc_in,
    constantly,
)
from .composition import (
    juxt,
    memoize,
    do,
    tap,
    compose_left,
)
from .math import (
    add,
    sub,
    mul,
    div,
    mod,
    pow,
    floordiv,
    truediv,
    inc,
    dec,
    neg,
    abs,
    min,
    max,
    sum,
    product,
    mean,
    median,
)
from .string import (
    join,
    split,
    strip,
    lstrip,
    rstrip,
    lower,
    upper,
    capitalize,
    title,
    replace,
)
from .predicate import (
    is_none,
    is_not_none,
    is_eq,
    is_ne,
    is_lt,
    is_gt,
    is_le,
    is_ge,
    is_in,
    is_not_in,
    isinstance_,
    issubclass_,
)
from ..decorators.control import (
    excepts,
    silent,
    suppress,
    ignore,
)

# 扩展导出列表
__all__.extend([
    # core
    'identity', 'const', 'flip', 'apply', 'curry',
    # iteration
    'map', 'imap', 'filter', 'ifilter', 'reduce', 'remove', 'keep', 'accumulate', 'compose', 'pipe',
    # collection
    'unique', 'iunique', 'groupby', 'partition', 'partition_all', 'concat', 'cat', 'flatten',
    'first', 'second', 'last', 'nth', 'get',
    'pluck', 'pluck_attr', 'walk', 'mapcat', 'compact',
    'merge', 'merge_with', 'get_in', 'set_in', 'update_in',
    'split_at', 'butlast', 'dissoc', 'assoc', 'assoc_in', 'constantly',
    'interleave', 'interpose',
    # composition
    'juxt', 'memoize', 'do', 'tap', 'compose_left',
    # math
    'add', 'sub', 'mul', 'div', 'mod', 'pow', 'floordiv', 'truediv', 'inc', 'dec', 'neg', 'abs',
    'min', 'max', 'sum', 'product', 'mean', 'median',
    # string
    'join', 'split', 'strip', 'lstrip', 'rstrip', 'lower', 'upper', 'capitalize', 'title', 'replace',
    # predicate
    'is_none', 'is_not_none', 'is_eq', 'is_ne', 'is_lt', 'is_gt', 'is_le', 'is_ge',
    'is_in', 'is_not_in', 'isinstance_', 'issubclass_',
    # decorators
    'excepts', 'silent', 'suppress', 'ignore',
])
