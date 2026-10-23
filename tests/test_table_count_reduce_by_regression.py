# -*- coding: utf-8 -*-
"""回归测试：Table.count_by / reduce_by 支持列名且结果行规范（BUG-376）。

`count_by` / `reduce_by` 直接继承自 `Seq`，`key` 只接受 callable：

    table.count_by('city')   # TypeError: 'str' object is not callable

而同类的 `Table.group_by(col)` 明确接受**列名**，用户自然会写列名，报错信息
也看不出是接口不一致。此外二者通过 `self.__class__(gen())` 构造 Table，
**行是 tuple**（(key, count) / (key, value)），违反「行必须是 list」的不变量。

修复：
- Table 覆写这两个方法：`key` 支持列名（转成 `lambda r: r[col]`）或 callable，
  其它类型给出清晰 TypeError；`func` 也校验 callable；
- 新增 `_rows_as_lists` 助手，把 tuple/dict 行统一规范为 list 行。

`group_by(col)` 行为不变；callable 用法结果不变。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([[1, 'a'], [1, 'b'], [2, 'c']], columns=['k', 'v'], name='T')


class TestColumnNameSupport:
    def test_count_by_column(self, table):
        # 修复前：TypeError: 'str' object is not callable
        r = table.count_by('k')
        assert r._data == [[1, 2], [2, 1]]

    def test_reduce_by_column(self, table):
        r = table.reduce_by('k', lambda a, b: a)
        assert r.rows() == 2

    def test_count_by_callable_unchanged(self, table):
        assert table.count_by(lambda r: r['k'])._data == [[1, 2], [2, 1]]

    def test_reduce_by_callable_unchanged(self, table):
        assert table.reduce_by(lambda r: r['k'], lambda a, b: a).rows() == 2


class TestRowsAreLists:
    def test_count_by_rows(self, table):
        r = table.count_by('k')
        assert all(isinstance(row, list) for row in r._data)

    def test_reduce_by_rows(self, table):
        r = table.reduce_by('k', lambda a, b: a)
        assert all(isinstance(row, list) for row in r._data)

    def test_count_by_default_columns(self, table):
        r = table.count_by('k')
        assert r._columns == ['col_0', 'col_1']
        assert r.get_cell2(0, 'col_0') == 1


class TestTypeValidation:
    @pytest.mark.parametrize('bad', [123, 1.5, ['k']])
    def test_count_by_bad_key(self, table, bad):
        with pytest.raises(TypeError) as ei:
            table.count_by(bad)
        assert '列名(str)或 callable' in str(ei.value)

    @pytest.mark.parametrize('bad', [123, object()])
    def test_reduce_by_bad_key(self, table, bad):
        with pytest.raises(TypeError):
            table.reduce_by(bad)

    def test_reduce_by_bad_func(self, table):
        with pytest.raises(TypeError) as ei:
            table.reduce_by('k', 'add')
        assert 'func' in str(ei.value)


class TestGroupByUnchanged:
    def test_group_by_column(self, table):
        groups = table.group_by('k')
        assert len(groups) == 2
        assert groups[1]._data == [[1, 'a'], [1, 'b']]
        assert groups[1]._columns == ['k', 'v']

    def test_group_by_unknown_column_raises(self, table):
        with pytest.raises(ValueError):
            table.group_by('no_such_col')