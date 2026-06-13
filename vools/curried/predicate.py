"""
Predicate curried functions - 谓词和比较函数

提供谓词逻辑和比较操作的柯里化函数。
"""

from typing import TypeVar, Callable, Any, Iterable, List, Union
from inspect import isclass

from ..decorators.curry_core import curry

A = TypeVar('A')
B = TypeVar('B')
T = TypeVar('T')

__all__ = [
    'is_none',
    'is_not_none',
    'is_eq',
    'is_ne',
    'is_lt',
    'is_gt',
    'is_le',
    'is_ge',
    'is_in',
    'is_not_in',
    'isinstance_',
    'issubclass_',
    'call',
    'methodcaller',
    'attrgetter',
    'itemgetter',
]


@curry
def is_none(x: Any) -> bool:
    """
    检查值是否为 None

    Args:
        x: 要检查的值

    Returns:
        如果 x 是 None 返回 True

    Example:
        >>> is_none(None)
        True
        >>> is_none(0)
        False
        >>> is_none('')
        False
    """
    return x is None


@curry
def is_not_none(x: Any) -> bool:
    """
    检查值是否不为 None

    Args:
        x: 要检查的值

    Returns:
        如果 x 不是 None 返回 True

    Example:
        >>> is_not_none(None)
        False
        >>> is_not_none(0)
        True
    """
    return x is not None


@curry
def is_eq(val: Any, other: Any) -> bool:
    """
    检查值是否等于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val == other 返回 True

    Example:
        >>> is_eq(5)(5)
        True
        >>> is_eq(5)(3)
        False
    """
    return val == other


@curry
def is_ne(val: Any, other: Any) -> bool:
    """
    检查值是否不等于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val != other 返回 True

    Example:
        >>> is_ne(5)(3)
        True
        >>> is_ne(5)(5)
        False
    """
    return val != other


@curry
def is_lt(val: Any, other: Any) -> bool:
    """
    检查值是否小于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val < other 返回 True

    Example:
        >>> is_lt(3)(5)
        True
        >>> is_lt(5)(3)
        False
    """
    return val < other


@curry
def is_gt(val: Any, other: Any) -> bool:
    """
    检查值是否大于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val > other 返回 True

    Example:
        >>> is_gt(5)(3)
        True
        >>> is_gt(3)(5)
        False
    """
    return val > other


@curry
def is_le(val: Any, other: Any) -> bool:
    """
    检查值是否小于或等于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val <= other 返回 True

    Example:
        >>> is_le(3)(5)
        True
        >>> is_le(5)(3)
        False
        >>> is_le(5)(5)
        True
    """
    return val <= other


@curry
def is_ge(val: Any, other: Any) -> bool:
    """
    检查值是否大于或等于指定值

    Args:
        val: 要比较的值
        other: 指定的值

    Returns:
        如果 val >= other 返回 True

    Example:
        >>> is_ge(5)(3)
        True
        >>> is_ge(3)(5)
        False
        >>> is_ge(5)(5)
        True
    """
    return val >= other


@curry
def is_in(iterable: Iterable) -> Callable[[Any], bool]:
    """
    检查值是否在可迭代对象中

    Args:
        iterable: 可迭代对象

    Returns:
        检查函数

    Example:
        >>> is_in([1, 2, 3])(2)
        True
        >>> is_in([1, 2, 3])(5)
        False
    """
    @curry
    def _is_in(val: Any) -> bool:
        return val in iterable
    return _is_in


@curry
def is_not_in(iterable: Iterable) -> Callable[[Any], bool]:
    """
    检查值是否不在可迭代对象中

    Args:
        iterable: 可迭代对象

    Returns:
        检查函数

    Example:
        >>> is_not_in([1, 2, 3])(5)
        True
        >>> is_not_in([1, 2, 3])(2)
        False
    """
    @curry
    def _is_not_in(val: Any) -> bool:
        return val not in iterable
    return _is_not_in


@curry
def isinstance_(class_or_tuple: Union[type, tuple], obj: Any) -> bool:
    """
    检查对象是否是指定类的实例

    Args:
        class_or_tuple: 类或类元组
        obj: 要检查的对象

    Returns:
        如果 obj 是实例返回 True

    Example:
        >>> isinstance_(int)(5)
        True
        >>> isinstance_(str)(5)
        False
        >>> isinstance_((int, float))(5)
        True
    """
    return isinstance(obj, class_or_tuple)


@curry
def issubclass_(class_or_tuple: Union[type, tuple], cls: type) -> bool:
    """
    检查类是否是指定类的子类

    Args:
        class_or_tuple: 类或类元组
        cls: 父类

    Returns:
        如果 class_or_tuple 是 cls 的子类返回 True

    Example:
        >>> issubclass_(int)(object)
        True
        >>> issubclass_(object)(int)
        False
    """
    if not isclass(class_or_tuple):
        return False
    return issubclass(class_or_tuple, cls)


@curry
def call(func: Callable, *args, **kwargs) -> Any:
    """
    调用函数

    Args:
        func: 要调用的函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数调用结果

    Example:
        >>> call(print, 'hello')
        hello
        >>> call(len, [1, 2, 3])
        3
    """
    return func(*args, **kwargs)


def methodcaller(name: str, *args, **kwargs) -> Callable:
    """
    返回调用指定方法的可调用对象

    Args:
        name: 方法名
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        调用方法的可调用对象

    Example:
        >>> upper_caller = methodcaller('upper')
        >>> upper_caller('hello')
        'HELLO'
        >>> split_caller = methodcaller('split', '-')
        >>> split_caller('a-b-c')
        ['a', 'b', 'c']
    """
    @curry
    def caller(obj):
        return getattr(obj, name)(*args, **kwargs)
    return caller


def attrgetter(name: str) -> Callable:
    """
    返回获取指定属性的可调用对象

    Args:
        name: 属性名（支持点号分隔的多层属性）

    Returns:
        获取属性的可调用对象

    Example:
        >>> from collections import namedtuple
        >>> Person = namedtuple('Person', ['name', 'age'])
        >>> p = Person('Alice', 30)
        >>> name_getter = attrgetter('name')
        >>> name_getter(p)
        'Alice'
    """
    if '.' in name:
        names = name.split('.')
        def getter(obj):
            for n in names:
                obj = getattr(obj, n)
            return obj
        return getter
    return lambda obj: getattr(obj, name)


def itemgetter(key: Any) -> Callable:
    """
    返回获取指定项的可调用对象

    Args:
        key: 键（支持多个键）

    Returns:
        获取项的可调用对象

    Example:
        >>> from operator import itemgetter
        >>> data = ['a', 'b', 'c', 'd']
        >>> itemgetter(0)(data)
        'a'
        >>> itemgetter(0, -1)(data)
        ('a', 'd')
    """
    @curry
    def getter(obj):
        return obj[key]
    return getter


__all__ = [
    'is_none',
    'is_not_none',
    'is_eq',
    'is_ne',
    'is_lt',
    'is_gt',
    'is_le',
    'is_ge',
    'is_in',
    'is_not_in',
    'isinstance_',
    'issubclass_',
    'call',
    'methodcaller',
    'attrgetter',
    'itemgetter',
]
