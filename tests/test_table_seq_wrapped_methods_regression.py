# -*- coding: utf-8 -*-
"""回归测试：Table 的 Seq 包装方法返回**可用**表格（BUG-374/375）。

`Table` 通过 `_seq_methods_to_wrap` 继承了一批 `Seq` 方法（take / skip /
reverse / sort_by / prepend / extend / ...），包装器只把列名与表名拷到结果上：

    def _with_attrs(self, result):
        result._columns = list(self._columns)
        result._name = self._name
        ...

但 `Seq._evaluate()` 在 Table 上产出的是 **dict 行**，于是 `_data` 里存的是
`[{'id': 1, 'name': 'a'}, ...]`，破坏「行必须是 list」的内部不变量：

    s = table.sort_by(lambda r: r['id'])
    s.get_cell(0, 'id')   # TypeError: '<' not supported between 'str' and 'int'
    s.row(0)              # {'id': 'id', 'name': 'name'}
    s.to_list()           # TypeError: unhashable type: 'slice'
    s.select('name')      # KeyError: 1
    s.where('id > 1')     # []（静默空表）

修复：`_with_attrs` 按列顺序把 dict 行还原为 list 行（tuple 行转 list、
标量包一层），并通过 `_data` property setter 赋值以重置 Seq 迭代状态。

【BUG-375】`get_cell(row, col)` 的 `col` 是 **int 索引**（按列名应用
`get_cell2`）。传列名时原先落入 `<` 比较抛 `'str' < 'int'` 的类型错误，
看不出是 API 用错；现在显式 TypeError 并指引 `get_cell2`。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([[3, 'c'], [1, 'a'], [2, 'b']],
                 columns=['id', 'name'], name='T')


class TestSortByReturnsUsableTable:
    def test_data_is_list_rows(self, table):
        s = table.sort_by(lambda r: r['id'])
        assert s._data == [[1, 'a'], [2, 'b'], [3, 'c']]
        assert all(isinstance(row, list) for row in s._data)

    def test_columns_and_name_preserved(self, table):
        s = table.sort_by(lambda r: r['id'])
        assert s._columns == ['id', 'name']
        assert s._name == 'T'

    def test_accessors_work(self, table):
        s = table.sort_by(lambda r: r['id'])
        assert s.get_cell(0, 0) == 1
        assert s.get_cell2(0, 'id') == 1
        assert s.row(0) == {'id': 1, 'name': 'a'}
        assert s.to_list() == [[1, 'a'], [2, 'b'], [3, 'c']]
        assert s.column('name') == ['a', 'b', 'c']

    def test_downstream_queries_work(self, table):
        s = table.sort_by(lambda r: r['id'])
        assert s.select('name')._data == [['a'], ['b'], ['c']]
        assert s.where('id > 1')._data == [[2, 'b'], [3, 'c']]

    def test_original_untouched(self, table):
        table.sort_by(lambda r: r['id'])
        assert table._data == [[3, 'c'], [1, 'a'], [2, 'b']]


class TestOtherWrappedMethods:
    def test_take(self, table):
        r = table.take(2)
        assert r._data == [[3, 'c'], [1, 'a']]
        assert isinstance(r._data[0], list)

    def test_skip(self, table):
        assert table.skip(1)._data == [[1, 'a'], [2, 'b']]

    def test_reverse(self, table):
        r = table.reverse()
        assert r._data == [[2, 'b'], [1, 'a'], [3, 'c']]
        assert r.get_cell2(0, 'id') == 2

    def test_reverse_keeps_columns(self, table):
        assert table.reverse()._columns == ['id', 'name']


class TestGetCellGuard:
    def test_column_name_rejected_with_hint(self, table):
        # 修复前：TypeError: '<' not supported between 'str' and 'int'
        with pytest.raises(TypeError) as ei:
            table.get_cell(0, 'id')
        msg = str(ei.value)
        assert 'int 列索引' in msg and 'get_cell2' in msg

    def test_bad_row_type(self, table):
        with pytest.raises(TypeError):
            table.get_cell('0', 0)

    def test_normal_usage_unchanged(self, table):
        assert table.get_cell(1, 1) == 'a'
        assert table.get_cell(9, 0, 'DEF') == 'DEF'
        assert table.get_cell2(0, 'id') == 3
        assert table.at(0, 'id') == 3