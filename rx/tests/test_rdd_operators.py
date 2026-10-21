"""
测试 RDD 风格算子

覆盖全部 21 个新增算子：
  map_partitions, map_partitions_with_index, glom,
  coalesce, repartition,
  group_by_key, reduce_by_key, aggregate_by_key,
  sort_by, sort_by_key,
  join, left_outer_join, right_outer_join, full_outer_join, cogroup,
  intersection, rdd_subtract, cartesian,
  zip_with_index, zip_with_unique_id
"""

import pytest
from vools.reactive import Observable, ops


# ══════════════════════════════════════════════════════════════
# map_partitions / map_partitions_with_index / glom
# ══════════════════════════════════════════════════════════════

class TestMapPartitions:
    """map_partitions / map_partitions_with_index / glom 测试"""

    def test_map_partitions_with_size(self):
        """按指定分区大小分批处理"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6).pipe(
            ops.map_partitions(lambda it: [sum(it)], 2)
        ).subscribe(on_next=result.append)
        assert result == [3, 7, 11]

    def test_map_partitions_collect_all(self):
        """partition_size=None 时收集全部"""
        result = []
        Observable.of(1, 2, 3).pipe(
            ops.map_partitions(lambda it: [sum(it)], None)
        ).subscribe(on_next=result.append)
        assert result == [6]

    def test_map_partitions_empty(self):
        """空流不发射"""
        result = []
        Observable.of().pipe(
            ops.map_partitions(lambda it: [sum(it)], 2)
        ).subscribe(on_next=result.append)
        assert result == []

    def test_map_partitions_flat_mapper(self):
        """mapper 返回多个元素"""
        result = []
        Observable.of(1, 2, 3, 4).pipe(
            ops.map_partitions(lambda it: list(it), 2)
        ).subscribe(on_next=result.append)
        assert result == [1, 2, 3, 4]

    def test_map_partitions_with_index(self):
        """带分区索引"""
        result = []
        Observable.of(10, 20, 30, 40).pipe(
            ops.map_partitions_with_index(lambda i, it: [(i, x) for x in it], 2)
        ).subscribe(on_next=result.append)
        assert result == [(0, 10), (0, 20), (1, 30), (1, 40)]

    def test_map_partitions_with_index_none(self):
        """带索引 + 收集全部"""
        result = []
        Observable.of("a", "b", "c").pipe(
            ops.map_partitions_with_index(lambda i, it: [(i, x) for x in it], None)
        ).subscribe(on_next=result.append)
        assert result == [(0, "a"), (0, "b"), (0, "c")]

    def test_glom(self):
        """收集全部为单个列表"""
        result = []
        Observable.of(1, 2, 3, 4).pipe(ops.glom()).subscribe(on_next=result.append)
        assert result == [[1, 2, 3, 4]]

    def test_glom_empty(self):
        """glom 空流"""
        result = []
        Observable.of().pipe(ops.glom()).subscribe(on_next=result.append)
        assert result == [[]]

    def test_glom_single(self):
        """glom 单元素"""
        result = []
        Observable.of(42).pipe(ops.glom()).subscribe(on_next=result.append)
        assert result == [[42]]


# ══════════════════════════════════════════════════════════════
# coalesce / repartition
# ══════════════════════════════════════════════════════════════

class TestCoalesceRepartition:
    """coalesce / repartition 测试"""

    def test_coalesce_even(self):
        """均匀切分"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6).pipe(ops.coalesce(3)).subscribe(on_next=result.append)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_coalesce_uneven(self):
        """不均匀切分：前 remainder 个分区多一个元素"""
        result = []
        Observable.of(1, 2, 3, 4, 5).pipe(ops.coalesce(3)).subscribe(on_next=result.append)
        assert result == [[1, 2], [3, 4], [5]]

    def test_coalesce_single_partition(self):
        """合并为 1 个分区"""
        result = []
        Observable.of(1, 2, 3).pipe(ops.coalesce(1)).subscribe(on_next=result.append)
        assert result == [[1, 2, 3]]

    def test_coalesce_empty(self):
        """空流产生 num_partitions 个空列表"""
        result = []
        Observable.of().pipe(ops.coalesce(3)).subscribe(on_next=result.append)
        assert result == [[], [], []]

    def test_coalesce_more_partitions_than_elements(self):
        """分区数 > 元素数"""
        result = []
        Observable.of(1, 2).pipe(ops.coalesce(5)).subscribe(on_next=result.append)
        # 2 个元素分 5 个分区：前 2 个各 1 个，后 3 个空
        assert result == [[1], [2], [], [], []]

    def test_repartition_round_robin(self):
        """round-robin 分配"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6).pipe(ops.repartition(3)).subscribe(on_next=result.append)
        assert result == [[1, 4], [2, 5], [3, 6]]

    def test_repartition_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.repartition(2)).subscribe(on_next=result.append)
        assert result == [[], []]

    def test_repartition_single(self):
        """单分区"""
        result = []
        Observable.of(1, 2, 3).pipe(ops.repartition(1)).subscribe(on_next=result.append)
        assert result == [[1, 2, 3]]


# ══════════════════════════════════════════════════════════════
# group_by_key / reduce_by_key / aggregate_by_key
# ══════════════════════════════════════════════════════════════

class TestKeyValueAggregation:
    """group_by_key / reduce_by_key / aggregate_by_key 测试"""

    def test_group_by_key_basic(self):
        """基本分组"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 3)).pipe(
            ops.group_by_key()
        ).subscribe(on_next=result.append)
        # 转换为 dict 便于比较
        d = dict(result)
        assert d["a"] == [1, 3]
        assert d["b"] == [2]

    def test_group_by_key_with_key_fn(self):
        """自定义 key_fn — 分组值为原始元素"""
        result = []
        Observable.of({"k": "x", "v": 1}, {"k": "y", "v": 2}, {"k": "x", "v": 3}).pipe(
            ops.group_by_key(lambda d: d["k"])
        ).subscribe(on_next=result.append)
        d = dict(result)
        # key_fn 模式下，分组值为原始元素
        assert d["x"] == [{"k": "x", "v": 1}, {"k": "x", "v": 3}]
        assert d["y"] == [{"k": "y", "v": 2}]

    def test_group_by_key_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.group_by_key()).subscribe(on_next=result.append)
        assert result == []

    def test_group_by_key_single(self):
        """单元素"""
        result = []
        Observable.of(("a", 1)).pipe(ops.group_by_key()).subscribe(on_next=result.append)
        assert result == [("a", [1])]

    def test_reduce_by_key_sum(self):
        """按键求和"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 3), ("b", 4), ("a", 5)).pipe(
            ops.reduce_by_key(lambda x, y: x + y)
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 9  # 1+3+5
        assert d["b"] == 6  # 2+4

    def test_reduce_by_key_max(self):
        """按键取最大值"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 5), ("a", 3)).pipe(
            ops.reduce_by_key(max)
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 5
        assert d["b"] == 2

    def test_reduce_by_key_with_key_fn(self):
        """自定义 key_fn 的 reduce_by_key — 对长度相同的字符串按首字母分组求连接"""
        result = []
        Observable.of("apple", "apricot", "banana", "blueberry", "cherry").pipe(
            ops.reduce_by_key(lambda a, b: a + "|" + b, key_fn=lambda s: s[0])
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == "apple|apricot"
        assert d["b"] == "banana|blueberry"
        assert d["c"] == "cherry"

    def test_reduce_by_key_single(self):
        """单元素"""
        result = []
        Observable.of(("a", 42)).pipe(ops.reduce_by_key(lambda x, y: x + y)).subscribe(on_next=result.append)
        assert result == [("a", 42)]

    def test_reduce_by_key_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.reduce_by_key(lambda x, y: x + y)).subscribe(on_next=result.append)
        assert result == []

    def test_aggregate_by_key_sum(self):
        """aggregate_by_key 求和"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 3)).pipe(
            ops.aggregate_by_key(
                zero_value=lambda: 0,
                seq_op=lambda acc, v: acc + v
            )
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 4
        assert d["b"] == 2

    def test_aggregate_by_key_max(self):
        """aggregate_by_key 取最大值"""
        result = []
        Observable.of(("x", 5), ("y", 3), ("x", 8), ("y", 1)).pipe(
            ops.aggregate_by_key(
                zero_value=lambda: float("-inf"),
                seq_op=max
            )
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["x"] == 8
        assert d["y"] == 3

    def test_aggregate_by_key_with_comb_op(self):
        """aggregate_by_key 使用 comb_op"""
        result = []
        Observable.of(("a", 10), ("b", 20), ("a", 30)).pipe(
            ops.aggregate_by_key(
                zero_value=lambda: 0,
                seq_op=lambda acc, v: acc + v,
                comb_op=lambda a, b: a + b
            )
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 40
        assert d["b"] == 20

    def test_aggregate_by_key_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(
            ops.aggregate_by_key(zero_value=lambda: 0, seq_op=lambda a, b: a + b)
        ).subscribe(on_next=result.append)
        assert result == []


# ══════════════════════════════════════════════════════════════
# sort_by / sort_by_key
# ══════════════════════════════════════════════════════════════

class TestSortOperators:
    """sort_by / sort_by_key 测试"""

    def test_sort_by_basic(self):
        """基本排序"""
        result = []
        Observable.of(3, 1, 4, 1, 5, 9, 2, 6).pipe(ops.sort_by()).subscribe(on_next=result.append)
        assert result == [1, 1, 2, 3, 4, 5, 6, 9]

    def test_sort_by_reverse(self):
        """降序"""
        result = []
        Observable.of(3, 1, 4, 2).pipe(ops.sort_by(reverse=True)).subscribe(on_next=result.append)
        assert result == [4, 3, 2, 1]

    def test_sort_by_key_fn(self):
        """自定义键"""
        result = []
        Observable.of("banana", "apple", "cherry").pipe(
            ops.sort_by(key_fn=len)
        ).subscribe(on_next=result.append)
        assert result == ["apple", "banana", "cherry"]

    def test_sort_by_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.sort_by()).subscribe(on_next=result.append)
        assert result == []

    def test_sort_by_single(self):
        """单元素"""
        result = []
        Observable.of(42).pipe(ops.sort_by()).subscribe(on_next=result.append)
        assert result == [42]

    def test_sort_by_key_basic(self):
        """按键排序 (key, value) 对"""
        result = []
        Observable.of(("b", 2), ("a", 1), ("c", 3)).pipe(
            ops.sort_by_key()
        ).subscribe(on_next=result.append)
        assert result == [("a", 1), ("b", 2), ("c", 3)]

    def test_sort_by_key_reverse(self):
        """按键降序"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("c", 3)).pipe(
            ops.sort_by_key(reverse=True)
        ).subscribe(on_next=result.append)
        assert result == [("c", 3), ("b", 2), ("a", 1)]

    def test_sort_by_key_with_fn(self):
        """按键自定义函数排序"""
        result = []
        Observable.of(("apple", 1), ("pie", 2), ("banana", 3)).pipe(
            ops.sort_by_key(key_fn=lambda k: len(k))
        ).subscribe(on_next=result.append)
        # "pie" len=3, "apple" len=5, "banana" len=6
        assert result == [("pie", 2), ("apple", 1), ("banana", 3)]

    def test_sort_by_key_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.sort_by_key()).subscribe(on_next=result.append)
        assert result == []


# ══════════════════════════════════════════════════════════════
# join / left_outer_join / right_outer_join / full_outer_join / cogroup
# ══════════════════════════════════════════════════════════════

class TestJoinOperators:
    """join 系列算子测试"""

    def test_join_inner(self):
        """内连接"""
        result = []
        left = Observable.of(("a", 1), ("b", 2), ("c", 3))
        right = Observable.of(("a", "x"), ("b", "y"), ("d", "z"))
        ops.join(left, right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (1, "x")), ("b", (2, "y"))]

    def test_join_empty_left(self):
        """左空"""
        result = []
        ops.join(Observable.of(), Observable.of(("a", 1))).subscribe(on_next=result.append)
        assert result == []

    def test_join_empty_right(self):
        """右空"""
        result = []
        ops.join(Observable.of(("a", 1)), Observable.of()).subscribe(on_next=result.append)
        assert result == []

    def test_left_outer_join(self):
        """左外连接"""
        result = []
        left = Observable.of(("a", 1), ("b", 2), ("c", 3))
        right = Observable.of(("a", "x"))
        ops.left_outer_join(left, right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (1, "x")), ("b", (2, None)), ("c", (3, None))]

    def test_left_outer_join_empty_right(self):
        """右空 → 全部 v=None"""
        result = []
        left = Observable.of(("a", 1), ("b", 2))
        ops.left_outer_join(left, Observable.of()).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (1, None)), ("b", (2, None))]

    def test_right_outer_join(self):
        """右外连接"""
        result = []
        left = Observable.of(("a", 1))
        right = Observable.of(("a", "x"), ("c", "y"))
        ops.right_outer_join(left, right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (1, "x")), ("c", (None, "y"))]

    def test_right_outer_join_empty_left(self):
        """左空 → 全部 v=None"""
        result = []
        right = Observable.of(("a", "x"), ("b", "y"))
        ops.right_outer_join(Observable.of(), right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (None, "x")), ("b", (None, "y"))]

    def test_full_outer_join(self):
        """全外连接"""
        result = []
        left = Observable.of(("a", 1), ("b", 2))
        right = Observable.of(("a", "x"), ("c", "y"))
        ops.full_outer_join(left, right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", (1, "x")), ("b", (2, None)), ("c", (None, "y"))]

    def test_full_outer_join_empty_left(self):
        """左空"""
        result = []
        right = Observable.of(("a", "x"))
        ops.full_outer_join(Observable.of(), right).subscribe(on_next=result.append)
        assert result == [("a", (None, "x"))]

    def test_full_outer_join_empty_right(self):
        """右空"""
        result = []
        left = Observable.of(("a", 1))
        ops.full_outer_join(left, Observable.of()).subscribe(on_next=result.append)
        assert result == [("a", (1, None))]

    def test_cogroup(self):
        """协分组"""
        result = []
        left = Observable.of(("a", 1), ("b", 2), ("c", 3))
        right = Observable.of(("a", "x"), ("c", "y"), ("c", "z"))
        ops.cogroup(left, right).subscribe(on_next=result.append)
        result.sort()
        assert result == [("a", ([1], ["x"])), ("b", ([2], [])), ("c", ([3], ["y", "z"]))]

    def test_cogroup_empty_right(self):
        """右空"""
        result = []
        left = Observable.of(("a", 1))
        ops.cogroup(left, Observable.of()).subscribe(on_next=result.append)
        assert result == [("a", ([1], []))]

    def test_join_multiple_values_per_key(self):
        """多值 key 的 join（笛卡尔积展开）"""
        result = []
        left = Observable.of(("a", 1), ("a", 2))
        right = Observable.of(("a", "x"), ("a", "y"))
        ops.join(left, right).subscribe(on_next=result.append)
        assert len(result) == 4  # 2 * 2
        assert all(r[0] == "a" for r in result)
        pairs = {r[1] for r in result}
        assert pairs == {(1, "x"), (1, "y"), (2, "x"), (2, "y")}


# ══════════════════════════════════════════════════════════════
# intersection / rdd_subtract / cartesian
# ══════════════════════════════════════════════════════════════

class TestSetOperators:
    """intersection / rdd_subtract / cartesian 测试"""

    def test_intersection_basic(self):
        """基本交集"""
        result = []
        a = Observable.of(1, 2, 3, 4)
        b = Observable.of(3, 4, 5, 6)
        ops.intersection(a, b).subscribe(on_next=result.append)
        result.sort()
        assert result == [3, 4]

    def test_intersection_empty_left(self):
        """左空"""
        result = []
        ops.intersection(Observable.of(), Observable.of(1, 2)).subscribe(on_next=result.append)
        assert result == []

    def test_intersection_empty_right(self):
        """右空"""
        result = []
        ops.intersection(Observable.of(1, 2), Observable.of()).subscribe(on_next=result.append)
        assert result == []

    def test_intersection_duplicates(self):
        """交集保留重复计数（取最小值）"""
        result = []
        a = Observable.of(1, 1, 2, 2, 3)
        b = Observable.of(1, 2, 2, 4)
        ops.intersection(a, b).subscribe(on_next=result.append)
        result.sort()
        # 1 在左 2 次右 1 次 → 1 个；2 在左 2 次右 2 次 → 2 个
        assert result == [1, 2, 2]

    def test_rdd_subtract_basic(self):
        """基本差集"""
        result = []
        a = Observable.of(1, 2, 3, 4)
        b = Observable.of(3, 4)
        ops.rdd_subtract(a, b).subscribe(on_next=result.append)
        result.sort()
        assert result == [1, 2]

    def test_rdd_subtract_empty_right(self):
        """右空"""
        result = []
        a = Observable.of(1, 2, 3)
        ops.rdd_subtract(a, Observable.of()).subscribe(on_next=result.append)
        result.sort()
        assert result == [1, 2, 3]

    def test_rdd_subtract_empty_left(self):
        """左空"""
        result = []
        ops.rdd_subtract(Observable.of(), Observable.of(1, 2)).subscribe(on_next=result.append)
        assert result == []

    def test_rdd_subtract_with_key_fn(self):
        """带 key_fn 的差集"""
        result = []
        a = Observable.of({"k": "a"}, {"k": "b"}, {"k": "c"})
        b = Observable.of({"k": "b"})
        ops.rdd_subtract(a, b, key_fn=lambda x: x["k"]).subscribe(on_next=result.append)
        assert len(result) == 2
        assert {"k": "a"} in result
        assert {"k": "c"} in result

    def test_cartesian_basic(self):
        """基本笛卡尔积"""
        result = []
        a = Observable.of(1, 2)
        b = Observable.of("a", "b")
        ops.cartesian(a, b).subscribe(on_next=result.append)
        assert len(result) == 4
        assert (1, "a") in result
        assert (1, "b") in result
        assert (2, "a") in result
        assert (2, "b") in result

    def test_cartesian_empty_left(self):
        """左空"""
        result = []
        ops.cartesian(Observable.of(), Observable.of(1, 2)).subscribe(on_next=result.append)
        assert result == []

    def test_cartesian_empty_right(self):
        """右空"""
        result = []
        ops.cartesian(Observable.of(1, 2), Observable.of()).subscribe(on_next=result.append)
        assert result == []

    def test_cartesian_single(self):
        """单元素"""
        result = []
        ops.cartesian(Observable.of(1), Observable.of("a")).subscribe(on_next=result.append)
        assert result == [(1, "a")]


# ══════════════════════════════════════════════════════════════
# zip_with_index / zip_with_unique_id
# ══════════════════════════════════════════════════════════════

class TestZipIndex:
    """zip_with_index / zip_with_unique_id 测试"""

    def test_zip_with_index(self):
        """基本索引配对"""
        result = []
        Observable.of("a", "b", "c").pipe(ops.zip_with_index()).subscribe(on_next=result.append)
        assert result == [("a", 0), ("b", 1), ("c", 2)]

    def test_zip_with_index_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.zip_with_index()).subscribe(on_next=result.append)
        assert result == []

    def test_zip_with_index_single(self):
        """单元素"""
        result = []
        Observable.of(42).pipe(ops.zip_with_index()).subscribe(on_next=result.append)
        assert result == [(42, 0)]

    def test_zip_with_index_numbers(self):
        """数值流"""
        result = []
        Observable.of(10, 20, 30, 40).pipe(ops.zip_with_index()).subscribe(on_next=result.append)
        assert result == [(10, 0), (20, 1), (30, 2), (40, 3)]

    def test_zip_with_unique_id(self):
        """基本唯一 ID 配对"""
        result = []
        Observable.of("x", "y", "z").pipe(ops.zip_with_unique_id()).subscribe(on_next=result.append)
        assert result == [("x", 0), ("y", 1), ("z", 2)]

    def test_zip_with_unique_id_empty(self):
        """空流"""
        result = []
        Observable.of().pipe(ops.zip_with_unique_id()).subscribe(on_next=result.append)
        assert result == []

    def test_zip_with_unique_id_large(self):
        """大量元素"""
        result = []
        Observable.from_range(100).pipe(ops.zip_with_unique_id()).subscribe(on_next=result.append)
        assert len(result) == 100
        assert result[0] == (0, 0)
        assert result[99] == (99, 99)


# ══════════════════════════════════════════════════════════════
# pipe 链式调用测试（验证代理方法）
# ══════════════════════════════════════════════════════════════

class TestPipeIntegration:
    """通过 pipe() 链式调用 RDD 算子"""

    def test_pipe_map_partitions(self):
        """pipe + map_partitions"""
        result = []
        Observable.of(1, 2, 3, 4).p().map_partitions(lambda it: [sum(it)], 2).subscribe(on_next=result.append)
        assert result == [3, 7]

    def test_pipe_glom(self):
        """pipe + glom"""
        result = []
        Observable.of(1, 2, 3).p().glom().subscribe(on_next=result.append)
        assert result == [[1, 2, 3]]

    def test_pipe_group_by_key(self):
        """pipe + group_by_key"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 3)).p().group_by_key().subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == [1, 3]
        assert d["b"] == [2]

    def test_pipe_reduce_by_key(self):
        """pipe + reduce_by_key"""
        result = []
        Observable.of(("a", 1), ("b", 2), ("a", 3)).p().reduce_by_key(lambda x, y: x + y).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 4
        assert d["b"] == 2

    def test_pipe_sort_by(self):
        """pipe + sort_by"""
        result = []
        Observable.of(3, 1, 4, 2).p().sort_by().subscribe(on_next=result.append)
        assert result == [1, 2, 3, 4]

    def test_pipe_sort_by_key(self):
        """pipe + sort_by_key"""
        result = []
        Observable.of(("b", 2), ("a", 1)).p().sort_by_key().subscribe(on_next=result.append)
        assert result == [("a", 1), ("b", 2)]

    def test_pipe_zip_with_index(self):
        """pipe + zip_with_index"""
        result = []
        Observable.of("a", "b", "c").p().zip_with_index().subscribe(on_next=result.append)
        assert result == [("a", 0), ("b", 1), ("c", 2)]

    def test_pipe_zip_with_unique_id(self):
        """pipe + zip_with_unique_id"""
        result = []
        Observable.of("x", "y").p().zip_with_unique_id().subscribe(on_next=result.append)
        assert result == [("x", 0), ("y", 1)]

    def test_pipe_coalesce(self):
        """pipe + coalesce"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6).p().coalesce(3).subscribe(on_next=result.append)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_pipe_repartition(self):
        """pipe + repartition"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6).p().repartition(3).subscribe(on_next=result.append)
        assert result == [[1, 4], [2, 5], [3, 6]]

    def test_pipe_chained(self):
        """链式调用多个 RDD 算子"""
        result = []
        Observable.of(("b", 2), ("a", 1), ("c", 3), ("a", 4)).p() \
            .group_by_key() \
            .subscribe(on_next=lambda kv: result.append((kv[0], kv[1][0])))  # 取每组第一个
        # group_by 会按组发射；这里验证链式调用不崩溃
        assert len(result) > 0

    def test_pipe_aggregate_by_key(self):
        """pipe + aggregate_by_key"""
        result = []
        Observable.of(("a", 10), ("b", 20), ("a", 30)).p().aggregate_by_key(
            zero_value=lambda: 0,
            seq_op=lambda acc, v: acc + v
        ).subscribe(on_next=result.append)
        d = dict(result)
        assert d["a"] == 40
        assert d["b"] == 20


# ══════════════════════════════════════════════════════════════
# 边界条件 / 错误传播
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界条件测试"""

    def test_map_partitions_error_propagation(self):
        """mapper 异常传播"""
        err = [None]
        def failing_mapper(it):
            raise ValueError("mapper failed")
        Observable.of(1, 2, 3).pipe(
            ops.map_partitions(failing_mapper, 2)
        ).subscribe(
            on_next=lambda x: None,
            on_error=lambda e: err.__setitem__(0, e)
        )
        assert isinstance(err[0], ValueError)

    def test_sort_by_error_propagation(self):
        """key_fn 异常传播"""
        err = [None]
        Observable.of(1, 2, 3).pipe(
            ops.sort_by(key_fn=lambda x: 1 / 0)
        ).subscribe(
            on_next=lambda x: None,
            on_error=lambda e: err.__setitem__(0, e)
        )
        assert isinstance(err[0], ZeroDivisionError)

    def test_group_by_key_error_propagation(self):
        """key_fn 异常传播"""
        err = [None]
        Observable.of(1, 2, 3).pipe(
            ops.group_by_key(key_fn=lambda x: 1 / 0)
        ).subscribe(
            on_next=lambda x: None,
            on_error=lambda e: err.__setitem__(0, e)
        )
        assert isinstance(err[0], ZeroDivisionError)

    def test_reduce_by_key_error_propagation(self):
        """func 异常传播"""
        err = [None]
        Observable.of(("a", 1), ("a", 2)).pipe(
            ops.reduce_by_key(lambda a, b: a / (b - b))
        ).subscribe(
            on_next=lambda x: None,
            on_error=lambda e: err.__setitem__(0, e)
        )
        assert isinstance(err[0], ZeroDivisionError)

    def test_zip_with_index_preserves_order(self):
        """索引严格递增"""
        result = []
        Observable.of("first", "second", "third", "fourth", "fifth").pipe(
            ops.zip_with_index()
        ).subscribe(on_next=result.append)
        assert [r[1] for r in result] == [0, 1, 2, 3, 4]

    def test_coalesce_preserves_order(self):
        """coalesce 保持元素原始顺序"""
        result = []
        Observable.of(1, 2, 3, 4, 5, 6, 7).pipe(ops.coalesce(3)).subscribe(on_next=result.append)
        # 7 个元素分 3 个分区：前 1 个多一个
        # base_size=2, remainder=1: [1,2,3], [4,5], [6,7]
        assert result == [[1, 2, 3], [4, 5], [6, 7]]

    def test_repartition_round_robin_distribution(self):
        """repartition 均匀分布"""
        result = []
        Observable.from_range(9).pipe(ops.repartition(3)).subscribe(on_next=result.append)
        assert result == [[0, 3, 6], [1, 4, 7], [2, 5, 8]]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
