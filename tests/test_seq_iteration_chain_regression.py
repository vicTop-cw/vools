# -*- coding: utf-8 -*-
"""回归测试：Seq 直接迭代应用链式操作 + accum(initial) 修复（BUG-412）。

**问题 1（严重，静默错值）**：`Seq` 继承 `SeqBase.__iter__`（直接产出原始
`_collection` 元素），而 `sorted()/take()/reduce()` 等走 `_evaluate()`（应用
操作管道）——同一个对象两种口径：

    list(Seq([1, 2]).map(lambda x: x * 2))     # 修复前 -> [1, 2]（map 被忽略！）
    list(Seq([1, 2]).map(lambda x: x * 2).sorted())  # -> [2, 4]（又生效了）

`for x in seq.filter(...)` 同样拿到**未过滤**的元素。VList 因自定义 `__iter__`
不受影响，更显不一致。

**问题 2**：`accum(func, initial)` 把 `initial` 按位置传给
`itertools.accumulate`，而它是**关键字专用**参数：

    Seq([1, 2]).accum(add, 10)
    # TypeError: accumulate() takes at most 2 positional arguments (3 given)

修复：`Seq.__iter__` 统一走 `_evaluate()`；`_evaluate` 通过 `_raw_iter()` 钩子
取原始元素（`_SeqIterator` 补 `__iter__` 使其成为合法迭代器）；`Table` 覆盖
`_raw_iter` 保持「元素是 dict 行」的既有口径（sort_by / count_by 的列名回调
依赖它）；`accum` 用 `initial=` 传参。
"""

import itertools

import pytest

from vools.data.seq import Seq
from vools.data.table import Table
from vools.data.vlist import VList


class TestIterationAppliesOps:
    def test_map_via_list(self):
        assert list(Seq([1, 2]).map(lambda x: x * 2)) == [2, 4]

    def test_filter_via_list(self):
        assert list(Seq([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]

    def test_chained_maps(self):
        assert list(Seq([1, 2]).map(lambda x: x * 2).map(lambda x: x + 1)) == [3, 5]

    def test_for_loop(self):
        assert [x for x in Seq([1, 2, 3]).map(lambda x: x * 10)] == [10, 20, 30]

    def test_consistency_with_sorted(self):
        seq = Seq([3, 1]).map(lambda x: x * 2)
        assert list(seq.sorted()) == [2, 6]
        # 同一实例再迭代，口径一致
        assert list(Seq([3, 1]).map(lambda x: x * 2)) == [6, 2]

    def test_take_consistency(self):
        assert list(Seq([1, 2, 3]).map(lambda x: x * 10).take(2)) == [10, 20]

    def test_reduce_consistency(self):
        assert Seq([1, 2, 3]).map(lambda x: x * 2).reduce(lambda a, b: a + b) == 12

    def test_empty(self):
        assert list(Seq([])) == []
        assert list(Seq([]).map(lambda x: x)) == []

    def test_plain_iteration_unchanged(self):
        assert list(Seq([1, 2, 3])) == [1, 2, 3]

    def test_iterator_is_a_proper_iterator(self):
        it = iter(Seq([1, 2]))
        assert iter(it) is it
        assert next(it) == 1


class TestAccumInitial:
    def test_accum_with_initial(self):
        # 修复前：TypeError: accumulate() takes at most 2 positional arguments
        expected = list(itertools.accumulate([1, 2], lambda a, b: a + b, initial=10))
        assert list(Seq([1, 2]).accum(lambda a, b: a + b, 10)) == expected
        assert expected == [10, 11, 13]

    def test_accum_without_initial(self):
        assert list(Seq([1, 2, 3]).accum(lambda a, b: a + b)) == [1, 3, 6]

    def test_accum_initial_zero(self):
        assert list(Seq([1, 2]).accum(lambda a, b: a + b, 0)) == [0, 1, 3]


class TestTableSemanticsPreserved:
    """Table 的元素视图是 dict 行，sort_by/count_by 的列名回调依赖它。"""

    @pytest.fixture()
    def table(self):
        return Table([[3, 'c'], [1, 'a'], [2, 'b']],
                     columns=['id', 'name'], name='T')

    def test_sort_by(self, table):
        s = table.sort_by(lambda r: r['id'])
        assert s._data == [[1, 'a'], [2, 'b'], [3, 'c']]
        assert s._columns == ['id', 'name']

    def test_count_by(self):
        t = Table([['a', 1], ['b', 2], ['a', 3]], columns=['k', 'v'])
        r = t.count_by('k')
        assert r._data == [['a', 2], ['b', 1]]
        assert r._columns == ['col_0', 'col_1']

    def test_iteration_yields_dict_rows(self, table):
        assert list(iter(table)) == [
            {'id': 3, 'name': 'c'},
            {'id': 1, 'name': 'a'},
            {'id': 2, 'name': 'b'},
        ]

    def test_map_rows_unchanged(self, table):
        assert list(table.map(lambda r: r)) == [
            {'id': 3, 'name': 'c'}, {'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]


class TestVListUnchanged:
    def test_map(self):
        assert list(VList([1, 2]).map(lambda x: x * 2)) == [2, 4]

    def test_filter(self):
        assert list(VList([1, 2, 3]).filter(lambda x: x > 1)) == [2, 3]