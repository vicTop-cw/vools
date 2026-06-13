"""
Collection curried functions - 集合操作柯里化函数

提供对集合、序列等数据结构进行操作的柯里化函数。
"""

from typing import TypeVar, Callable, Iterable, List, Optional, Any, Tuple, Dict, Iterator, Union
from itertools import chain, islice, groupby as itertools_groupby
from collections import OrderedDict

from ..decorators.curry_core import curry

A = TypeVar('A')
B = TypeVar('B')
K = TypeVar('K')
T = TypeVar('T')

__all__ = [
    'unique',
    'iunique',
    'groupby',
    'group_by',
    'partition',
    'partition_all',
    'concat',
    'cat',
    'flatten',
    'first',
    'second',
    'last',
    'nth',
    'get',
    'take',
    'drop',
    'head',
    'tail',
    'cons',
    'singleton',
    'interleave',
    'interpose',
    'distinct',
]


@curry
def unique(iterable: Iterable[A], key: Optional[Callable[[A], K]] = None) -> List[A]:
    """
    返回可迭代对象中的唯一元素，保持顺序

    Args:
        iterable: 可迭代对象
        key: 可选的键函数，用于确定唯一性

    Returns:
        唯一元素列表

    Example:
        >>> unique([1, 2, 2, 3, 1, 4])
        [1, 2, 3, 4]
        >>> unique(['a', 'A', 'b'], key=str.lower)
        ['a', 'b']
    """
    if key is None:
        seen = set()
        result = []
        for item in iterable:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
    else:
        seen = set()
        result = []
        for item in iterable:
            k = key(item)
            if k not in seen:
                seen.add(k)
                result.append(item)
        return result


@curry
def iunique(iterable: Iterable[A], key: Optional[Callable[[A], K]] = None) -> Iterator[A]:
    """
    惰性版本的 unique，返回生成器而非列表

    Args:
        iterable: 可迭代对象
        key: 可选的键函数，用于确定唯一性

    Returns:
        唯一元素的惰性生成器

    Example:
        >>> result = iunique([1, 2, 2, 3, 1, 4])
        >>> type(result)
        <class 'generator'>
        >>> list(result)
        [1, 2, 3, 4]
    """
    if key is None:
        seen = set()
        for item in iterable:
            if item not in seen:
                seen.add(item)
                yield item
    else:
        seen = set()
        for item in iterable:
            k = key(item)
            if k not in seen:
                seen.add(k)
                yield item


distinct = unique


@curry
def groupby(func: Callable[[A], K], iterable: Iterable[A]) -> Dict[K, List[A]]:
    """
    按键函数对元素分组

    Args:
        func: 分组键函数
        iterable: 可迭代对象

    Returns:
        字典，键是分组键，值是属于该组的元素列表

    Example:
        >>> groupby(lambda x: x % 2, range(5))
        {0: [0, 2, 4], 1: [1, 3]}
        >>> groupby(str.lower, ['A', 'b', 'C', 'a', 'B'])
        {'A': ['A', 'a'], 'b': ['b', 'B'], 'C': ['C']}
    """
    result = OrderedDict()
    for item in iterable:
        key = func(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return dict(result)


group_by = groupby


@curry
def partition(n: int, iterable: Iterable[A]) -> List[List[A]]:
    """
    将可迭代对象按固定大小分组，最后一组可能更小

    Args:
        n: 每组大小
        iterable: 可迭代对象

    Returns:
        分组列表

    Example:
        >>> partition(3, range(10))
        [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
        >>> partition(2, ['a', 'b', 'c', 'd', 'e'])
        [['a', 'b'], ['c', 'd'], ['e']]
    """
    return list(_partition(n, iterable))


def _partition(n, iterable):
    """partition 的生成器实现"""
    it = iter(iterable)
    while True:
        batch = list(islice(it, n))
        if not batch:
            break
        yield batch


@curry
def partition_all(n: int, iterable: Iterable[A]) -> List[List[A]]:
    """
    将可迭代对象按固定大小分组，所有组都有相同大小

    Args:
        n: 每组大小
        iterable: 可迭代对象

    Returns:
        分组列表

    Example:
        >>> partition_all(3, range(10))
        [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
        >>> partition_all(2, ['a', 'b', 'c'])
        [['a', 'b'], ['c']]
    """
    return list(_partition_all(n, iterable))


def _partition_all(n, iterable):
    """partition_all 的生成器实现"""
    it = iter(iterable)
    while True:
        batch = list(islice(it, n))
        if not batch:
            break
        yield batch


@curry
def concat(*iterables: Iterable) -> chain:
    """
    连接多个可迭代对象

    Args:
        *iterables: 要连接的可迭代对象

    Returns:
        chain 对象

    Example:
        >>> list(concat([1, 2], [3, 4], [5]))
        [1, 2, 3, 4, 5]
        >>> list(concat('abc', 'def'))
        ['a', 'b', 'c', 'd', 'e', 'f']
    """
    return chain(*iterables)


cat = concat


@curry
def flatten(iterable: Iterable, depth: int = None) -> List:
    """
    展平嵌套的可迭代对象

    Args:
        iterable: 要展平的可迭代对象
        depth: 展平深度，None 表示完全展平

    Returns:
        展平后的列表

    Example:
        >>> flatten([[1, 2], [3, 4]])
        [1, 2, 3, 4]
        >>> flatten([[1, [2, 3]], [4, [5, [6]]]])
        [1, 2, 3, 4, 5, 6]
        >>> flatten([[1, [2, 3]], [4, [5, [6]]]], depth=1)
        [1, [2, 3], 4, [5, [6]]]
    """
    if depth == 0:
        return list(iterable)

    result = []
    for item in iterable:
        if isinstance(item, (list, tuple, set)):
            result.extend(flatten(item, depth - 1 if depth is not None else None))
        else:
            result.append(item)
    return result


@curry
def first(iterable: Iterable[A], default: A = None) -> A:
    """
    返回可迭代对象的第一个元素

    Args:
        iterable: 可迭代对象
        default: 如果为空可迭代对象返回的默认值

    Returns:
        第一个元素或默认值

    Example:
        >>> first(range(10))
        0
        >>> first([])
        None
        >>> first([], default=-1)
        -1
    """
    try:
        return next(iter(iterable))
    except StopIteration:
        return default


@curry
def second(iterable: Iterable[A], default: A = None) -> A:
    """
    返回可迭代对象的第二个元素

    Args:
        iterable: 可迭代对象
        default: 如果不存在返回的默认值

    Returns:
        第二个元素或默认值
    """
    return nth(1, iterable, default)


@curry
def last(iterable: Iterable[A], default: A = None) -> A:
    """
    返回可迭代对象的最后一个元素

    Args:
        iterable: 可迭代对象
        default: 如果为空可迭代对象返回的默认值

    Returns:
        最后一个元素或默认值

    Example:
        >>> last(range(10))
        9
        >>> last([])
        None
    """
    item = default
    for item in iterable:
        pass
    return item


@curry
def nth(n: int, iterable: Iterable[A], default: A = None) -> A:
    """
    返回可迭代对象的第 n 个元素（从 0 开始）

    Args:
        n: 元素索引（支持负索引）
        iterable: 可迭代对象
        default: 如果不存在返回的默认值

    Returns:
        第 n 个元素或默认值

    Example:
        >>> nth(0, range(10))
        0
        >>> nth(5, range(10))
        5
        >>> nth(10, range(5), default=-1)
        -1
        >>> nth(-1, range(10))
        9
    """
    if n < 0:
        # 负索引：转换为正索引
        items = list(iterable)
        n = len(items) + n
        if n < 0:
            return default
        return items[n] if n < len(items) else default
    return next(islice(iter(iterable), n, n + 1), default)


@curry
def get(iterable: Iterable, index: int, default: Any = None) -> Any:
    """
    获取可迭代对象指定索引处的元素

    Args:
        iterable: 可迭代对象
        index: 索引
        default: 如果不存在返回的默认值

    Returns:
        指定索引处的元素或默认值
    """
    return nth(index, iterable, default)


@curry
def take(n: int, iterable: Iterable[A]) -> List[A]:
    """
    从可迭代对象中取前 n 个元素

    Args:
        n: 要取的元素数量
        iterable: 可迭代对象

    Returns:
        前 n 个元素的列表

    Example:
        >>> take(5, range(100))
        [0, 1, 2, 3, 4]
    """
    return list(islice(iter(iterable), n))


@curry
def drop(n: int, iterable: Iterable[A]) -> List[A]:
    """
    从可迭代对象中丢弃前 n 个元素

    Args:
        n: 要丢弃的元素数量
        iterable: 可迭代对象

    Returns:
        剩余元素的列表

    Example:
        >>> drop(5, range(10))
        [5, 6, 7, 8, 9]
    """
    return list(islice(iter(iterable), n, None))


head = take
tail = drop


@curry
def cons(x: A, iterable: Iterable[A]) -> List[A]:
    """
    将元素添加到列表开头

    Args:
        x: 要添加的元素
        iterable: 原有可迭代对象

    Returns:
        新列表

    Example:
        >>> cons(0, [1, 2, 3])
        [0, 1, 2, 3]
    """
    return [x] + list(iterable)


@curry
def singleton(x: A) -> List[A]:
    """
    创建只包含一个元素的列表

    Args:
        x: 元素

    Returns:
        只包含该元素的列表
    """
    return [x]


@curry
def interleave(iterables: List[Iterable]) -> List:
    """
    交替合并多个可迭代对象

    Args:
        iterables: 可迭代对象列表

    Returns:
        交替合并后的列表

    Example:
        >>> interleave([[1, 2], [3, 4], [5, 6]])
        [1, 3, 5, 2, 4, 6]
    """
    result = []
    iterators = [iter(it) for it in iterables]
    while iterators:
        new_iterators = []
        for it in iterators:
            try:
                result.append(next(it))
                new_iterators.append(it)
            except StopIteration:
                pass
        iterators = new_iterators
        if not iterators:
            break
    return result


@curry
def interpose(x: A, iterable: Iterable[A]) -> List[A]:
    """
    在可迭代对象的元素之间插入分隔符

    Args:
        x: 分隔符
        iterable: 可迭代对象

    Returns:
        带分隔符的列表

    Example:
        >>> interpose('-', 'abc')
        ['a', '-', 'b', '-', 'c']
        >>> interpose(0, [1, 2, 3])
        [1, 0, 2, 0, 3]
    """
    result = []
    for i, item in enumerate(iterable):
        if i > 0:
            result.append(x)
        result.append(item)
    return result


@curry
def pluck(key: K, iterable: Iterable[Dict[K, Any]]) -> List[Any]:
    """
    从字典序列中提取指定键的值

    Args:
        key: 要提取的键
        iterable: 字典序列

    Returns:
        值的列表

    Example:
        >>> pluck('name', [{'name': 'Alice', 'age': 25}, {'name': 'Bob', 'age': 30}])
        ['Alice', 'Bob']
    """
    return [d[key] for d in iterable]


@curry
def pluck_attr(attr: str, iterable: Iterable) -> List:
    """
    从对象序列中提取指定属性的值

    Args:
        attr: 要提取的属性名
        iterable: 对象序列

    Returns:
        属性值的列表

    Example:
        >>> class Person:
        ...     def __init__(self, name):
        ...         self.name = name
        >>> pluck_attr('name', [Person('Alice'), Person('Bob')])
        ['Alice', 'Bob']
    """
    return [getattr(obj, attr) for obj in iterable]


@curry
def walk(fn: Callable[[A], Any], iterable: Iterable[A]) -> None:
    """
    对序列中每个元素应用函数（仅副作用）

    Args:
        fn: 要应用的函数
        iterable: 可迭代对象

    Example:
        >>> result = []
        >>> walk(lambda x: result.append(x * 2), [1, 2, 3])
        >>> result
        [2, 4, 6]
    """
    for item in iterable:
        fn(item)


@curry
def mapcat(fn: Callable[[A], Iterable[B]], iterable: Iterable[A]) -> List[B]:
    """
    对序列中的每个元素应用函数，然后展平结果

    Args:
        fn: 返回可迭代对象的函数
        iterable: 可迭代对象

    Returns:
        展平后的列表

    Example:
        >>> mapcat(lambda x: [x, x * 2], [1, 2, 3])
        [1, 2, 2, 4, 3, 6]
    """
    return flatten([fn(item) for item in iterable])


@curry
def compact(iterable: Iterable[A]) -> List[A]:
    """
    移除序列中的 falsy 值

    Args:
        iterable: 可迭代对象

    Returns:
        移除 falsy 值后的列表

    Example:
        >>> compact([1, None, 2, False, 3, '', 4])
        [1, 2, 3, 4]
    """
    return [item for item in iterable if item]


@curry
def merge(*dicts: Dict) -> Dict:
    """
    合并多个字典，后面的字典会覆盖前面的

    Args:
        *dicts: 要合并的字典

    Returns:
        合并后的字典

    Example:
        >>> merge({'a': 1, 'b': 2}, {'b': 3, 'c': 4})
        {'a': 1, 'b': 3, 'c': 4}
    """
    result = {}
    for d in dicts:
        result.update(d)
    return result


def merge_with(fn: Callable) -> Callable:
    """
    使用函数合并多个字典的值（柯里化版本）

    Args:
        fn: 合并函数，接收多个值返回合并结果

    Returns:
        接收字典列表并返回合并后字典的函数

    Example:
        >>> merge_with(sum)({'a': 1, 'b': 2}, {'a': 3, 'b': 4}, {'a': 5})
        {'a': 9, 'b': 6}
    """
    def _merge_with(*dicts: Dict) -> Dict:
        result = {}
        keys = set().union(*dicts)
        for key in keys:
            values = [d[key] for d in dicts if key in d]
            result[key] = fn(*values) if len(values) > 1 else values[0]
        return result
    return _merge_with


@curry
def get_in(keys: List[Any], d: Dict, default: Any = None) -> Any:
    """
    获取嵌套字典中的值

    Args:
        keys: 键的路径列表
        d: 字典
        default: 如果路径不存在返回的默认值

    Returns:
        嵌套字典中的值或默认值

    Example:
        >>> get_in(['a', 'b', 'c'], {'a': {'b': {'c': 42}}})
        42
        >>> get_in(['a', 'x'], {'a': {'b': 1}}, default='not found')
        'not found'
    """
    result = d
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
    return result


@curry
def set_in(keys: List[Any], value: Any, d: Dict) -> Dict:
    """
    设置嵌套字典中的值（不修改原字典）

    Args:
        keys: 键的路径列表
        value: 要设置的值
        d: 原始字典

    Returns:
        新的嵌套字典

    Example:
        >>> set_in(['a', 'b', 'c'], 42, {'a': {'b': {'c': 0}}})
        {'a': {'b': {'c': 42}}}
    """
    result = dict(d)
    current = result
    for i, key in enumerate(keys[:-1]):
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return result


@curry
def update_in(keys: List[Any], fn: Callable[[Any], Any], d: Dict) -> Dict:
    """
    更新嵌套字典中的值（不修改原字典）

    Args:
        keys: 键的路径列表
        fn: 更新函数，接收旧值返回新值
        d: 原始字典

    Returns:
        新的嵌套字典

    Example:
        >>> update_in(['a', 'b'], lambda x: x * 2, {'a': {'b': 10}})
        {'a': {'b': 20}}
    """
    result = dict(d)
    current = result
    for i, key in enumerate(keys[:-1]):
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    if keys[-1] in current:
        current[keys[-1]] = fn(current[keys[-1]])
    return result


@curry
def split_at(n: int, iterable: Iterable[A]) -> Tuple[List[A], List[A]]:
    """
    在指定位置分割序列

    Args:
        n: 分割位置
        iterable: 可迭代对象

    Returns:
        包含两个列表的元组

    Example:
        >>> split_at(3, [1, 2, 3, 4, 5])
        ([1, 2, 3], [4, 5])
    """
    items = list(iterable)
    return items[:n], items[n:]


@curry
def butlast(iterable: Iterable[A]) -> List[A]:
    """
    返回除最后一个元素外的所有元素

    Args:
        iterable: 可迭代对象

    Returns:
        去掉最后一个元素的列表

    Example:
        >>> butlast([1, 2, 3, 4])
        [1, 2, 3]
        >>> butlast([1])
        []
    """
    items = list(iterable)
    return items[:-1] if items else []


@curry
def dissoc(d: Dict, *keys) -> Dict:
    """
    创建一个不包含指定键的新字典

    Args:
        d: 原始字典
        *keys: 要移除的键

    Returns:
        新字典

    Example:
        >>> dissoc({'a': 1, 'b': 2, 'c': 3}, 'a', 'c')
        {'b': 2}
    """
    return {k: v for k, v in d.items() if k not in keys}


@curry
def assoc(d: Dict, **kwargs) -> Dict:
    """
    创建一个包含新键值对的新字典

    Args:
        d: 原始字典
        **kwargs: 要添加的键值对

    Returns:
        新字典

    Example:
        >>> assoc({'a': 1, 'b': 2}, b=20, c=3)
        {'a': 1, 'b': 20, 'c': 3}
    """
    result = dict(d)
    result.update(kwargs)
    return result


@curry
def assoc_in(d: Dict, keys: List[Any], value: Any) -> Dict:
    """
    在嵌套字典中设置值（类似 set_in，但使用 kwargs 风格）

    Args:
        d: 原始字典
        keys: 键的路径列表
        value: 要设置的值

    Returns:
        新字典

    Example:
        >>> assoc_in({'a': {'b': 1}}, ['a', 'b'], 2)
        {'a': {'b': 2}}
    """
    return set_in(keys, value, d)


@curry
def constantly(value: A) -> Callable[..., A]:
    """
    创建一个始终返回常量值的函数

    Args:
        value: 要返回的常量值

    Returns:
        返回常量值的函数

    Example:
        >>> always_42 = constantly(42)
        >>> always_42(1, 2, 3)
        42
    """
    def constant_fn(*args, **kwargs):
        return value
    return constant_fn


__all__ = [
    'unique',
    'groupby',
    'group_by',
    'partition',
    'partition_all',
    'concat',
    'cat',
    'flatten',
    'first',
    'second',
    'last',
    'nth',
    'get',
    'take',
    'drop',
    'head',
    'tail',
    'cons',
    'singleton',
    'interleave',
    'interpose',
    'distinct',
    'pluck',
    'pluck_attr',
    'walk',
    'mapcat',
    'compact',
    'merge',
    'merge_with',
    'get_in',
    'set_in',
    'update_in',
    'split_at',
    'butlast',
    'dissoc',
    'assoc',
    'assoc_in',
    'constantly',
]
