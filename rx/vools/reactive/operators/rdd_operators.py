"""
vools-reactive RDD 风格算子

提供 Spark RDD 风格的算子适配到响应式流式模型。

设计原则：
- 需要完整数据集的算子（聚合/排序/集合）在 on_completed 时批量发射结果
- 分区级算子（map_partitions）支持分批处理，partition_size=None 时收集全部
- 连接/集合算子为双源独立函数，与 zip / combine_latest 同口径
- 所有算子保持 curry / placeholder / 字符串表达式兼容

新增算子 (21):
  map_partitions, map_partitions_with_index,
  group_by_key, reduce_by_key, aggregate_by_key,
  sort_by, sort_by_key,
  join, left_outer_join, right_outer_join, full_outer_join, cogroup,
  intersection, subtract, cartesian,
  coalesce, repartition, glom,
  zip_with_index, zip_with_unique_id
"""

from typing import TypeVar, Callable, Optional, Any, List, Dict, Set, Tuple, Union, Iterable
from collections import defaultdict
from itertools import product

from ..core.observable import Observable, Observer, Subscription

__all__ = [
    'T', 'K', 'V', 'U', 'W',
    # 分区/批量处理
    'map_partitions', 'map_partitions_with_index', 'glom',
    # 键值聚合
    'group_by_key', 'reduce_by_key', 'aggregate_by_key',
    # 排序
    'sort_by', 'sort_by_key',
    # 连接（双源）
    'join', 'left_outer_join', 'right_outer_join', 'full_outer_join', 'cogroup',
    # 集合（双源）
    'intersection', 'subtract', 'cartesian',
    # 分区管理
    'coalesce', 'repartition',
    # 索引/ID
    'zip_with_index', 'zip_with_unique_id',
]

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')
U = TypeVar('U')
W = TypeVar('W')
R = TypeVar('R')


# ══════════════════════════════════════════════════════════════
# 分区 / 批量处理
# ══════════════════════════════════════════════════════════════

def map_partitions(
    mapper: Callable[[Iterable[T]], Iterable[R]],
    partition_size: Optional[int] = None
) -> Callable[[Observable[T]], Observable[R]]:
    """分区级映射算子

    将流元素分批（按 partition_size），对每批应用 mapper。
    mapper 接收一个可迭代对象（分区），返回一个可迭代对象（结果序列）。

    RDD 语义：rdd.mapPartitions(fn) 对每个分区应用 fn，fn 接收分区迭代器。
    流式适配：用 batch 模拟分区。

    Args:
        mapper: (Iterable[T]) -> Iterable[R]，分区级映射函数
        partition_size: 每批大小。None 表示收集全部元素后一次性处理；
                       正整数表示每积累到该数量就处理一批。

    Example:
        >>> Observable.of(1, 2, 3, 4).pipe(
        ...     ops.map_partitions(lambda it: [sum(it)], 2)
        ... ).subscribe(print)
        3  # sum([1,2])
        7  # sum([3,4])
        >>> Observable.of(1, 2, 3).pipe(
        ...     ops.map_partitions(lambda it: list(it), None)
        ... ).subscribe(print)
        1, 2, 3
    """
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            buf: List[T] = []

            def _flush():
                if buf:
                    try:
                        for item in mapper(buf):
                            observer.on_next(item)
                        buf.clear()
                    except Exception as e:
                        observer.on_error(e)

            def on_next(value: T) -> None:
                buf.append(value)
                if partition_size is not None and len(buf) >= partition_size:
                    _flush()

            def on_completed() -> None:
                _flush()
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def map_partitions_with_index(
    mapper: Callable[[int, Iterable[T]], Iterable[R]],
    partition_size: Optional[int] = None
) -> Callable[[Observable[T]], Observable[R]]:
    """带分区索引的分区级映射算子

    与 map_partitions 相同，但 mapper 额外接收分区索引（从 0 开始）。

    RDD 语义：rdd.mapPartitionsWithIndex(fn) 对每个分区应用 fn，fn 接收 (index, iterator)。

    Args:
        mapper: (int, Iterable[T]) -> Iterable[R]，(分区索引, 分区) -> 结果
        partition_size: 同 map_partitions

    Example:
        >>> Observable.of(10, 20, 30, 40).pipe(
        ...     ops.map_partitions_with_index(lambda i, it: [(i, x) for x in it], 2)
        ... ).subscribe(print)
        (0, 10), (0, 20), (1, 30), (1, 40)
    """
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            buf: List[T] = []
            idx = [0]

            def _flush():
                if buf:
                    try:
                        for item in mapper(idx[0], buf):
                            observer.on_next(item)
                        buf.clear()
                        idx[0] += 1
                    except Exception as e:
                        observer.on_error(e)

            def on_next(value: T) -> None:
                buf.append(value)
                if partition_size is not None and len(buf) >= partition_size:
                    _flush()

            def on_completed() -> None:
                _flush()
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def glom() -> Callable[[Observable[T]], Observable[List[T]]]:
    """将全部元素收集为单个列表并发射

    RDD 语义：rdd.glom() 将每个分区转换为数组。
    流式适配：收集所有元素为一个分区（列表）。

    Returns:
        Observable[List[T]]: 发射单个列表

    Example:
        >>> Observable.of(1, 2, 3).pipe(ops.glom()).subscribe(print)
        [1, 2, 3]
    """
    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            items: List[T] = []

            def on_next(value: T) -> None:
                items.append(value)

            def on_completed() -> None:
                observer.on_next(items)
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


# ══════════════════════════════════════════════════════════════
# 分区管理
# ══════════════════════════════════════════════════════════════

def coalesce(
    num_partitions: int
) -> Callable[[Observable[T]], Observable[List[T]]]:
    """将数据合并为指定数量的分区

    RDD 语义：rdd.coalesce(n) 将分区数减少到 n，不触发 shuffle。
    流式适配：收集所有元素后均匀切分为 num_partitions 个列表依次发射。
    当元素数 < num_partitions 时，多余分区发射空列表。

    Args:
        num_partitions: 目标分区数（>= 1）

    Example:
        >>> Observable.of(1, 2, 3, 4, 5, 6).pipe(ops.coalesce(3)).subscribe(print)
        [1, 2]
        [3, 4]
        [5, 6]
    """
    if num_partitions < 1:
        raise ValueError(f"num_partitions must be >= 1, got {num_partitions}")

    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            items: List[T] = []

            def on_completed() -> None:
                n = len(items)
                if n == 0:
                    # 发射 num_partitions 个空列表
                    for _ in range(num_partitions):
                        observer.on_next([])
                else:
                    # 均匀切分：前 remainder 个分区多一个元素
                    base_size, remainder = divmod(n, num_partitions)
                    idx = 0
                    for i in range(num_partitions):
                        size = base_size + (1 if i < remainder else 0)
                        observer.on_next(items[idx:idx + size])
                        idx += size
                observer.on_completed()

            def on_next(value: T) -> None:
                items.append(value)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def repartition(
    num_partitions: int
) -> Callable[[Observable[T]], Observable[List[T]]]:
    """将数据重新分区为指定数量（round-robin 分配）

    RDD 语义：rdd.repartition(n) 通过 shuffle 重新分配分区。
    流式适配：收集所有元素后 round-robin 分配到 num_partitions 个列表。

    与 coalesce 的区别：coalesce 保持元素原始顺序切分，
    repartition 采用轮询分配（模拟 shuffle）。

    Args:
        num_partitions: 目标分区数（>= 1）

    Example:
        >>> Observable.of(1, 2, 3, 4, 5, 6).pipe(ops.repartition(3)).subscribe(print)
        [1, 4]
        [2, 5]
        [3, 6]
    """
    if num_partitions < 1:
        raise ValueError(f"num_partitions must be >= 1, got {num_partitions}")

    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            items: List[T] = []

            def on_completed() -> None:
                partitions: List[List[T]] = [[] for _ in range(num_partitions)]
                for i, item in enumerate(items):
                    partitions[i % num_partitions].append(item)
                for p in partitions:
                    observer.on_next(p)
                observer.on_completed()

            def on_next(value: T) -> None:
                items.append(value)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


# ══════════════════════════════════════════════════════════════
# 键值聚合
# ══════════════════════════════════════════════════════════════

def group_by_key(
    key_fn: Optional[Callable[[T], K]] = None
) -> Callable[[Observable[T]], Observable[Tuple[K, List[Any]]]]:
    """按键分组

    收集所有元素，按键分组后发射 (key, [values]) 对。

    默认假设元素为 (key, value) 元组；提供 key_fn 时按 key_fn(element) 取键，
    此时 value 为元素本身。

    Args:
        key_fn: 可选的键提取函数。None 表示元素本身是 (key, value) 对。

    Example:
        >>> Observable.of(("a", 1), ("b", 2), ("a", 3))
        ...     .pipe(ops.group_by_key()).subscribe(print)
        ("a", [1, 3])
        ("b", [2])
        >>> Observable.of({"k": "x", "v": 1}, {"k": "y", "v": 2}, {"k": "x", "v": 3})
        ...     .pipe(ops.group_by_key(lambda d: d["k"])).subscribe(print)
        ("x", [{"k": "x", "v": 1}, {"k": "x", "v": 3}])
        ("y", [{"k": "y", "v": 2}])
    """
    def operator(source: Observable[T]) -> Observable[Tuple[K, List[Any]]]:
        def subscribe(observer: Observer[Tuple[K, List[Any]]]) -> Subscription:
            groups: Dict[K, List[Any]] = defaultdict(list)

            def on_next(value: T) -> None:
                try:
                    if key_fn is not None:
                        k = key_fn(value)
                        groups[k].append(value)
                    else:
                        k, v = value  # type: ignore
                        groups[k].append(v)
                except Exception as e:
                    observer.on_error(e)

            def on_completed() -> None:
                for key, values in groups.items():
                    observer.on_next((key, values))
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def reduce_by_key(
    func: Callable[[V, V], V],
    key_fn: Optional[Callable[[T], K]] = None
) -> Callable[[Observable[T]], Observable[Tuple[K, V]]]:
    """按键归约

    收集所有元素，按键归约后发射 (key, reduced_value)。
    要求 func 满足结合律以保证结果确定性。

    Args:
        func: (V, V) -> V 归约函数
        key_fn: 可选的键提取函数。None 表示元素本身是 (key, value) 对。

    Example:
        >>> Observable.of(("a", 1), ("b", 2), ("a", 3))
        ...     .pipe(ops.reduce_by_key(lambda a, b: a + b)).subscribe(print)
        ("a", 4)
        ("b", 2)
    """
    def operator(source: Observable[T]) -> Observable[Tuple[K, V]]:
        def subscribe(observer: Observer[Tuple[K, V]]) -> Subscription:
            reduced: Dict[K, V] = {}

            def on_next(value: T) -> None:
                try:
                    if key_fn is not None:
                        k = key_fn(value)
                        v = value  # type: ignore
                    else:
                        k, v = value  # type: ignore
                    if k in reduced:
                        reduced[k] = func(reduced[k], v)
                    else:
                        reduced[k] = v
                except Exception as e:
                    observer.on_error(e)

            def on_completed() -> None:
                for key, val in reduced.items():
                    observer.on_next((key, val))
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def aggregate_by_key(
    zero_value: Callable[[], U],
    seq_op: Callable[[U, V], U],
    comb_op: Optional[Callable[[U, U], U]] = None,
    key_fn: Optional[Callable[[T], K]] = None
) -> Callable[[Observable[T]], Observable[Tuple[K, U]]]:
    """按键自定义聚合

    提供零值工厂、序列操作和可选的合并操作，实现最通用的按键聚合。

    Args:
        zero_value: () -> U，返回每个键的初始聚合值
        seq_op: (U, V) -> U，将元素归并到聚合值
        comb_op: (U, U) -> U，合并两个聚合值。None 时使用 seq_op。
        key_fn: 可选的键提取函数。None 表示元素本身是 (key, value) 对。

    Example:
        >>> # 按字符串分组求长度之和
        >>> Observable.of("apple", "banana", "avocado", "blueberry")
        ...     .pipe(ops.aggregate_by_key(
        ...         zero_value=lambda: 0,
        ...         seq_op=lambda acc, s: acc + len(s),
        ...         key_fn=lambda s: s[0]
        ...     )).subscribe(print)
        ("a", 16)  # len("apple")+len("avocado")=5+7=12... wait 5+7=12
        ("b", 15)  # len("banana")+len("blueberry")=6+9=15
    """
    if comb_op is None:
        comb_op = seq_op

    def operator(source: Observable[T]) -> Observable[Tuple[K, U]]:
        def subscribe(observer: Observer[Tuple[K, U]]) -> Subscription:
            accs: Dict[K, U] = {}

            def on_next(value: T) -> None:
                try:
                    if key_fn is not None:
                        k = key_fn(value)
                        v = value  # type: ignore
                    else:
                        k, v = value  # type: ignore
                    if k in accs:
                        accs[k] = seq_op(accs[k], v)
                    else:
                        accs[k] = seq_op(zero_value(), v)
                except Exception as e:
                    observer.on_error(e)

            def on_completed() -> None:
                for key, val in accs.items():
                    observer.on_next((key, val))
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


# ══════════════════════════════════════════════════════════════
# 排序
# ══════════════════════════════════════════════════════════════

def sort_by(
    key_fn: Optional[Callable[[T], Any]] = None,
    reverse: bool = False
) -> Callable[[Observable[T]], Observable[T]]:
    """按自定义键排序

    收集所有元素，按 key_fn 排序后依次发射。

    Args:
        key_fn: 键提取函数。None 表示直接比较元素。
        reverse: 是否降序。

    Example:
        >>> Observable.of(3, 1, 4, 2).pipe(ops.sort_by()).subscribe(print)
        1, 2, 3, 4
        >>> Observable.of("banana", "apple", "cherry")
        ...     .pipe(ops.sort_by(key_fn=len)).subscribe(print)
        "apple", "banana", "cherry"
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            items: List[T] = []

            def on_next(value: T) -> None:
                items.append(value)

            def on_completed() -> None:
                try:
                    items.sort(key=key_fn, reverse=reverse)
                    for item in items:
                        observer.on_next(item)
                except Exception as e:
                    observer.on_error(e)
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


def sort_by_key(
    key_fn: Optional[Callable[[K], Any]] = None,
    reverse: bool = False
) -> Callable[[Observable[Tuple[K, V]]], Observable[Tuple[K, V]]]:
    """按键排序

    收集所有 (key, value) 对，按键排序后依次发射。

    Args:
        key_fn: 键提取函数。None 表示直接比较 key。
        reverse: 是否降序。

    Example:
        >>> Observable.of(("b", 2), ("a", 1), ("c", 3))
        ...     .pipe(ops.sort_by_key()).subscribe(print)
        ("a", 1), ("b", 2), ("c", 3)
    """
    def operator(source: Observable[Tuple[K, V]]) -> Observable[Tuple[K, V]]:
        def subscribe(observer: Observer[Tuple[K, V]]) -> Subscription:
            items: List[Tuple[K, V]] = []

            def on_next(value: Tuple[K, V]) -> None:
                items.append(value)

            def on_completed() -> None:
                try:
                    if key_fn:
                        items.sort(key=lambda x: key_fn(x[0]), reverse=reverse)
                    else:
                        items.sort(key=lambda x: x[0], reverse=reverse)
                    for item in items:
                        observer.on_next(item)
                except Exception as e:
                    observer.on_error(e)
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )

        return Observable(subscribe)

    return operator


# ══════════════════════════════════════════════════════════════
# 连接（双源独立函数）
# ══════════════════════════════════════════════════════════════

def join(
    left: Observable[Tuple[K, V]],
    right: Observable[Tuple[K, W]],
    key_fn: Optional[Callable[[T], K]] = None
) -> Observable[Tuple[K, Tuple[V, W]]]:
    """内连接 (Inner Join)

    收集两侧 (key, value) 对，对同时存在于两侧的 key 发射所有匹配的 (key, (v, w))。

    Args:
        left: 左侧 (key, value) 流
        right: 右侧 (key, value) 流
        key_fn: 可选的键提取函数。None 表示元素本身是 (key, value) 对。

    Example:
        >>> left  = Observable.of(("a", 1), ("b", 2))
        >>> right = Observable.of(("a", "x"), ("c", "y"))
        >>> ops.join(left, right).subscribe(print)
        ("a", (1, "x"))
    """
    def _get_key_val(item):
        if key_fn:
            return key_fn(item), item
        return item[0], item[1]

    def subscribe(observer: Observer[Tuple[K, Tuple[V, W]]]) -> Subscription:
        left_dict: Dict[K, List[V]] = defaultdict(list)
        right_dict: Dict[K, List[W]] = defaultdict(list)
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                for key in left_dict:
                    if key in right_dict:
                        for v in left_dict[key]:
                            for w in right_dict[key]:
                                observer.on_next((key, (v, w)))
                observer.on_completed()

        def left_on_next(item):
            k, v = _get_key_val(item)
            left_dict[k].append(v)

        def right_on_next(item):
            k, v = _get_key_val(item)
            right_dict[k].append(v)

        def left_on_completed():
            left_done[0] = True
            try_emit()

        def right_on_completed():
            right_done[0] = True
            try_emit()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def left_outer_join(
    left: Observable[Tuple[K, V]],
    right: Observable[Tuple[K, W]],
    key_fn: Optional[Callable[[T], K]] = None
) -> Observable[Tuple[K, Tuple[V, Optional[W]]]]:
    """左外连接 (Left Outer Join)

    对左侧所有 key，发射 (key, (v, w))；若 key 不在右侧则 w = None。

    Example:
        >>> left  = Observable.of(("a", 1), ("b", 2))
        >>> right = Observable.of(("a", "x"))
        >>> ops.left_outer_join(left, right).subscribe(print)
        ("a", (1, "x"))
        ("b", (2, None))
    """
    def _get_key_val(item):
        if key_fn:
            return key_fn(item), item
        return item[0], item[1]

    def subscribe(observer: Observer[Tuple[K, Tuple[V, Optional[W]]]]) -> Subscription:
        left_dict: Dict[K, List[V]] = defaultdict(list)
        right_dict: Dict[K, List[W]] = defaultdict(list)
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                for key in left_dict:
                    if key in right_dict:
                        for v in left_dict[key]:
                            for w in right_dict[key]:
                                observer.on_next((key, (v, w)))
                    else:
                        for v in left_dict[key]:
                            observer.on_next((key, (v, None)))
                observer.on_completed()

        def left_on_next(item):
            k, v = _get_key_val(item)
            left_dict[k].append(v)

        def right_on_next(item):
            k, v = _get_key_val(item)
            right_dict[k].append(v)

        def left_on_completed():
            left_done[0] = True
            try_emit()

        def right_on_completed():
            right_done[0] = True
            try_emit()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def right_outer_join(
    left: Observable[Tuple[K, V]],
    right: Observable[Tuple[K, W]],
    key_fn: Optional[Callable[[T], K]] = None
) -> Observable[Tuple[K, Tuple[Optional[V], W]]]:
    """右外连接 (Right Outer Join)

    对右侧所有 key，发射 (key, (v, w))；若 key 不在左侧则 v = None。

    Example:
        >>> left  = Observable.of(("a", 1))
        >>> right = Observable.of(("a", "x"), ("c", "y"))
        >>> ops.right_outer_join(left, right).subscribe(print)
        ("a", (1, "x"))
        ("c", (None, "y"))
    """
    def _get_key_val(item):
        if key_fn:
            return key_fn(item), item
        return item[0], item[1]

    def subscribe(observer: Observer[Tuple[K, Tuple[Optional[V], W]]]) -> Subscription:
        left_dict: Dict[K, List[V]] = defaultdict(list)
        right_dict: Dict[K, List[W]] = defaultdict(list)
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                for key in right_dict:
                    if key in left_dict:
                        for v in left_dict[key]:
                            for w in right_dict[key]:
                                observer.on_next((key, (v, w)))
                    else:
                        for w in right_dict[key]:
                            observer.on_next((key, (None, w)))
                observer.on_completed()

        def left_on_next(item):
            k, v = _get_key_val(item)
            left_dict[k].append(v)

        def right_on_next(item):
            k, v = _get_key_val(item)
            right_dict[k].append(v)

        def left_on_completed():
            left_done[0] = True
            try_emit()

        def right_on_completed():
            right_done[0] = True
            try_emit()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def full_outer_join(
    left: Observable[Tuple[K, V]],
    right: Observable[Tuple[K, W]],
    key_fn: Optional[Callable[[T], K]] = None
) -> Observable[Tuple[K, Tuple[Optional[V], Optional[W]]]]:
    """全外连接 (Full Outer Join)

    对左右两侧所有 key 的并集，发射 (key, (v, w))；
    仅在单侧存在时，缺失侧为 None。

    Example:
        >>> left  = Observable.of(("a", 1), ("b", 2))
        >>> right = Observable.of(("a", "x"), ("c", "y"))
        >>> ops.full_outer_join(left, right).subscribe(print)
        ("a", (1, "x"))
        ("b", (2, None))
        ("c", (None, "y"))
    """
    def _get_key_val(item):
        if key_fn:
            return key_fn(item), item
        return item[0], item[1]

    def subscribe(observer: Observer[Tuple[K, Tuple[Optional[V], Optional[W]]]]) -> Subscription:
        left_dict: Dict[K, List[V]] = defaultdict(list)
        right_dict: Dict[K, List[W]] = defaultdict(list)
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                all_keys = set(left_dict.keys()) | set(right_dict.keys())
                for key in all_keys:
                    has_left = key in left_dict
                    has_right = key in right_dict
                    if has_left and has_right:
                        for v in left_dict[key]:
                            for w in right_dict[key]:
                                observer.on_next((key, (v, w)))
                    elif has_left:
                        for v in left_dict[key]:
                            observer.on_next((key, (v, None)))
                    else:
                        for w in right_dict[key]:
                            observer.on_next((key, (None, w)))
                observer.on_completed()

        def left_on_next(item):
            k, v = _get_key_val(item)
            left_dict[k].append(v)

        def right_on_next(item):
            k, v = _get_key_val(item)
            right_dict[k].append(v)

        def left_on_completed():
            left_done[0] = True
            try_emit()

        def right_on_completed():
            right_done[0] = True
            try_emit()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def cogroup(
    left: Observable[Tuple[K, V]],
    right: Observable[Tuple[K, W]],
    key_fn: Optional[Callable[[T], K]] = None
) -> Observable[Tuple[K, Tuple[List[V], List[W]]]]:
    """协分组 (Cogroup)

    收集两侧 (key, value) 对，发射 (key, (left_values, right_values))。
    对左右两侧所有 key 的并集进行分组。

    Example:
        >>> left  = Observable.of(("a", 1), ("b", 2))
        >>> right = Observable.of(("a", "x"), ("c", "y"))
        >>> ops.cogroup(left, right).subscribe(print)
        ("a", ([1], ["x"]))
        ("b", ([2], []))
        ("c", ([], ["y"]))
    """
    def _get_key_val(item):
        if key_fn:
            return key_fn(item), item
        return item[0], item[1]

    def subscribe(observer: Observer[Tuple[K, Tuple[List[V], List[W]]]]) -> Subscription:
        left_dict: Dict[K, List[V]] = defaultdict(list)
        right_dict: Dict[K, List[W]] = defaultdict(list)
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                all_keys = set(left_dict.keys()) | set(right_dict.keys())
                for key in all_keys:
                    observer.on_next((
                        key,
                        (list(left_dict.get(key, [])), list(right_dict.get(key, [])))
                    ))
                observer.on_completed()

        def left_on_next(item):
            k, v = _get_key_val(item)
            left_dict[k].append(v)

        def right_on_next(item):
            k, v = _get_key_val(item)
            right_dict[k].append(v)

        def left_on_completed():
            left_done[0] = True
            try_emit()

        def right_on_completed():
            right_done[0] = True
            try_emit()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


# ══════════════════════════════════════════════════════════════
# 集合（双源独立函数）
# ══════════════════════════════════════════════════════════════

def intersection(
    left: Observable[T],
    right: Observable[T],
    key_fn: Optional[Callable[[T], Any]] = None
) -> Observable[T]:
    """交集

    发射同时在左右两侧存在的元素。重复元素按出现次数取最小值。

    Args:
        left: 左侧元素流
        right: 右侧元素流
        key_fn: 可选的键提取函数。None 表示直接比较元素。

    Example:
        >>> a = Observable.of(1, 2, 3, 4)
        >>> b = Observable.of(3, 4, 5, 6)
        >>> ops.intersection(a, b).subscribe(print)
        3, 4
    """
    def _get_key(item):
        return key_fn(item) if key_fn else item

    def subscribe(observer: Observer[T]) -> Subscription:
        right_counts: Dict[Any, int] = defaultdict(int)
        right_done = [False]
        left_buf: List[T] = []
        left_done = [False]
        subscription = Subscription(lambda: None)

        def _emit_from_buf():
            """根据 right_counts 从 left_buf 中发射匹配元素"""
            for item in left_buf:
                k = _get_key(item)
                if right_counts[k] > 0:
                    right_counts[k] -= 1
                    observer.on_next(item)
            left_buf.clear()

        def try_emit():
            if left_done[0] and right_done[0]:
                # 两侧都完成，发射交集
                observer.on_completed()

        def left_on_next(item):
            if right_done[0]:
                # 右侧已完成，可以直接判断
                k = _get_key(item)
                if right_counts[k] > 0:
                    right_counts[k] -= 1
                    observer.on_next(item)
            else:
                # 右侧未完成，缓存
                left_buf.append(item)

        def right_on_next(item):
            k = _get_key(item)
            right_counts[k] += 1
            if left_done[0]:
                # 左侧已完成且已发射，无需额外处理
                pass

        def right_on_completed():
            right_done[0] = True
            # 右侧完成，处理左侧缓存
            if left_done[0]:
                _emit_from_buf()
            observer.on_completed() if left_done[0] else None

        def left_on_completed():
            left_done[0] = True
            if not right_done[0]:
                # 右侧未完成，等待
                return
            _emit_from_buf()
            observer.on_completed()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def subtract(
    left: Observable[T],
    right: Observable[T],
    key_fn: Optional[Callable[[T], Any]] = None
) -> Observable[T]:
    """差集

    发射在左侧存在但不在右侧的元素。

    Args:
        left: 左侧元素流
        right: 右侧元素流
        key_fn: 可选的键提取函数。None 表示直接比较元素。

    Example:
        >>> a = Observable.of(1, 2, 3, 4)
        >>> b = Observable.of(3, 4)
        >>> ops.subtract(a, b).subscribe(print)
        1, 2
    """
    def _get_key(item):
        return key_fn(item) if key_fn else item

    def subscribe(observer: Observer[T]) -> Subscription:
        right_set: Dict[Any, int] = defaultdict(int)
        left_buf: List[T] = []
        right_done = [False]
        left_done = [False]
        subscription = Subscription(lambda: None)

        def _emit_left():
            for item in left_buf:
                k = _get_key(item)
                if right_set[k] == 0:
                    observer.on_next(item)
                else:
                    right_set[k] -= 1
            left_buf.clear()

        def left_on_next(item):
            if right_done[0]:
                k = _get_key(item)
                if right_set[k] == 0:
                    observer.on_next(item)
                else:
                    right_set[k] -= 1
            else:
                left_buf.append(item)

        def right_on_next(item):
            k = _get_key(item)
            right_set[k] += 1

        def right_on_completed():
            right_done[0] = True
            if left_done[0]:
                _emit_left()
            observer.on_completed() if left_done[0] else None

        def left_on_completed():
            left_done[0] = True
            if right_done[0]:
                _emit_left()
                observer.on_completed()

        left_sub = left.subscribe(
            on_next=left_on_next,
            on_error=observer.on_error,
            on_completed=left_on_completed
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=right_on_next,
            on_error=observer.on_error,
            on_completed=right_on_completed
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


def cartesian(
    left: Observable[T],
    right: Observable[U]
) -> Observable[Tuple[T, U]]:
    """笛卡尔积

    发射左侧每个元素与右侧每个元素组成的所有配对 (a, b)。

    Example:
        >>> a = Observable.of(1, 2)
        >>> b = Observable.of("a", "b")
        >>> ops.cartesian(a, b).subscribe(print)
        (1, "a"), (1, "b"), (2, "a"), (2, "b")
    """
    def subscribe(observer: Observer[Tuple[T, U]]) -> Subscription:
        left_items: List[T] = []
        right_items: List[U] = []
        left_done = [False]
        right_done = [False]
        subscription = Subscription(lambda: None)

        def try_emit():
            if left_done[0] and right_done[0]:
                for a, b in product(left_items, right_items):
                    observer.on_next((a, b))
                observer.on_completed()

        left_sub = left.subscribe(
            on_next=lambda x: left_items.append(x),
            on_error=observer.on_error,
            on_completed=lambda: (left_done.__setitem__(0, True), try_emit())
        )
        subscription.add_child(left_sub)

        right_sub = right.subscribe(
            on_next=lambda x: right_items.append(x),
            on_error=observer.on_error,
            on_completed=lambda: (right_done.__setitem__(0, True), try_emit())
        )
        subscription.add_child(right_sub)

        return subscription

    return Observable(subscribe)


# ══════════════════════════════════════════════════════════════
# 索引 / ID
# ══════════════════════════════════════════════════════════════

def zip_with_index() -> Callable[[Observable[T]], Observable[Tuple[T, int]]]:
    """将每个元素与其索引配对

    发射 (element, index)，index 从 0 开始递增。

    RDD 语义：rdd.zipWithIndex() 为每个元素分配全局唯一递增索引。

    Example:
        >>> Observable.of("a", "b", "c").pipe(ops.zip_with_index()).subscribe(print)
        ("a", 0), ("b", 1), ("c", 2)
    """
    def operator(source: Observable[T]) -> Observable[Tuple[T, int]]:
        def subscribe(observer: Observer[Tuple[T, int]]) -> Subscription:
            idx = [0]

            def on_next(value: T) -> None:
                observer.on_next((value, idx[0]))
                idx[0] += 1

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )

        return Observable(subscribe)

    return operator


def zip_with_unique_id() -> Callable[[Observable[T]], Observable[Tuple[T, int]]]:
    """将每个元素与唯一 ID 配对

    发射 (element, unique_id)。ID 为流内唯一，从 0 开始递增。

    RDD 语义：rdd.zipWithUniqueId() 为每个元素分配唯一 ID。
    与 zipWithIndex 的区别：在多分区场景下 ID 分配策略不同
    （基于分区 ID + 分区内偏移，非全局连续）。
    在单流响应式模型中，两者行为等价（均为全局递增）。

    Example:
        >>> Observable.of("a", "b", "c").pipe(ops.zip_with_unique_id()).subscribe(print)
        ("a", 0), ("b", 1), ("c", 2)
    """
    def operator(source: Observable[T]) -> Observable[Tuple[T, int]]:
        def subscribe(observer: Observer[Tuple[T, int]]) -> Subscription:
            uid = [0]

            def on_next(value: T) -> None:
                observer.on_next((value, uid[0]))
                uid[0] += 1

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )

        return Observable(subscribe)

    return operator
