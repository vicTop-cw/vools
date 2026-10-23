# -*- coding: utf-8 -*-
"""回归测试：唯一化崩溃 + to_date 紧凑格式（BUG-356/357）。

【BUG-356】`Seq.unique` / `Seq.distinct()` 用 `set` 去重：

    s = set(); if i not in s: ...

元素不可哈希时（dict/list）抛 `TypeError: unhashable type: 'dict'`。
`Table` 的 `_evaluate()` 产出的是 **dict 行**，所以 `Table().unique`
**必然崩溃**（`unique` 是 Seq 的 property）。修复：不可哈希时退化为
顺序保持的线性去重；可哈希路径行为不变。

【BUG-357】`Table.to_date` 的格式列表缺本库自己的主格式 `%Y%m%d`
（from_file / get_date_seq / VDate 都用它），遇到 '20260115' 时**静默保持字符串**
（列类型悄悄没转）。修复：补 `%Y%m%d`、`%Y%m%d%H%M%S`、`%Y.%m.%d`，
无法解析的值保持原样（既有语义）。
"""

import datetime

import pytest

from vools.data.seq import Seq
from vools.data.table import Table


class TestUniqueUnhashable:
    def test_table_unique(self):
        # 修复前：TypeError unhashable type: 'dict'
        t = Table([[1, 2], [1, 2], [3, 4]], columns=['a', 'b'])
        assert t.unique == [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]

    def test_seq_dict_unique(self):
        s = Seq([{'a': 1}, {'a': 1}, {'a': 2}])
        assert s.unique == [{'a': 1}, {'a': 2}]

    def test_seq_list_unique(self):
        assert Seq([[1], [1], [2]]).unique == [[1], [2]]

    def test_hashable_unchanged(self):
        assert Seq([1, 1, 2, 3, 2]).unique == [1, 2, 3]
        assert Seq(['a', 'a', 'b']).unique == ['a', 'b']

    def test_empty(self):
        assert Seq([]).unique == []


class TestDistinctUnhashable:
    def test_default_key_with_dicts(self):
        # 修复前：distinct() 默认恒等 key -> dict 不可哈希 -> TypeError
        assert list(Seq([{'a': 1}, {'a': 1}, {'a': 2}]).distinct()) == [
            {'a': 1}, {'a': 2}]

    def test_custom_key(self):
        assert list(Seq([1, '1', 2]).distinct(key=str)) == [1, 2]

    def test_hashable_unchanged(self):
        assert list(Seq([1, 1, 2]).distinct()) == [1, 2]

    def test_table_distinct_own_impl(self):
        # Table.distinct 是独立实现（支持 unhashable 单元格），不受影响
        t = Table([[{'x': 1}], [{'x': 1}]], columns=['a'])
        assert t.distinct().rows() == 1


class TestToDateFormats:
    @pytest.mark.parametrize('value,expected', [
        ('20260115', datetime.datetime(2026, 1, 15)),
        ('2026-01-15', datetime.datetime(2026, 1, 15)),
        ('2026/01/15', datetime.datetime(2026, 1, 15)),
        ('2026.01.15', datetime.datetime(2026, 1, 15)),
        ('2026-01-15 10:30:00', datetime.datetime(2026, 1, 15, 10, 30)),
        ('20260115103000', datetime.datetime(2026, 1, 15, 10, 30)),
    ])
    def test_formats(self, value, expected):
        # 修复前：'20260115' / '20260115103000' / '2026.01.15' 保持字符串
        t = Table([[value]], columns=['d']).to_date('d')
        assert t._data[0][0] == expected

    def test_unparsable_kept(self):
        t = Table([['not-a-date']], columns=['d']).to_date('d')
        assert t._data[0][0] == 'not-a-date'

    def test_non_string_kept(self):
        t = Table([[20260115], [None]], columns=['d']).to_date('d')
        assert t._data == [[20260115], [None]]

    def test_by_index(self):
        t = Table([['20260115']], columns=['d']).to_date(0)
        assert isinstance(t._data[0][0], datetime.datetime)