# -*- coding: utf-8 -*-
"""回归测试：新增/插入/改名时拒绝重复列名（BUG-326）。

列名是表格按名操作的主键（`GetCol`/`DelCol`/`SetColName`/`QAXColTo*`/
`to_num`/`get_cell2` 等大量 API 按名定位）。原实现允许重名：

    q = Qax([[1,'a'],[2,'b']], columns=['id','name'])
    q.InsertCol(2, 'id', 99)      # -> 列 ['id','id','name']
    q.GetCol('id')                # -> [99, 99]（命中第 2 列，而非第一列 [1,2]）
    q.QAXColIndex('id')           # -> 1

即重名后按名操作会**静默命中其中一列**（实现相关），不会报错——属「静默错列」
（算错列/删错列），比抛错更难排查。

修复：`Table.add_col`（`Qax.AddCol` 委托它）、`Qax.InsertCol`、以及
`Table.set_col_name`/`Qax.SetColName`（改名为另一已存在列名）统一拒绝重名，
抛 `ValueError`；改成自身原名保持幂等。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


@pytest.fixture()
def q():
    return Qax([[1, 'a']], columns=['id', 'name'])


@pytest.fixture()
def t():
    return Table([[1, 'a']], columns=['id', 'name'])


class TestDuplicateRejected:
    def test_qax_add_col_duplicate(self, q):
        with pytest.raises(ValueError, match='已存在'):
            q.AddCol('id', 0)

    def test_qax_insert_col_duplicate(self, q):
        with pytest.raises(ValueError, match='已存在'):
            q.InsertCol(1, 'id')

    def test_table_add_col_duplicate(self, t):
        with pytest.raises(ValueError, match='已存在'):
            t.add_col('id', 0)

    def test_rename_to_existing_name(self, t):
        with pytest.raises(ValueError, match='已存在'):
            t.set_col_name(1, 'id')

    def test_qax_set_col_name_to_existing(self, q):
        with pytest.raises(ValueError, match='已存在'):
            q.SetColName('name', 'id')


class TestValidOperationsUnchanged:
    def test_add_col_new_name(self, q):
        q.AddCol('x', 0)
        assert q._columns == ['id', 'name', 'x']

    def test_insert_col_new_name(self, q):
        q.InsertCol(2, 'x', 9)
        assert q._columns == ['id', 'x', 'name']
        assert q._data[0] == [1, 9, 'a']

    def test_table_add_col_new_name(self, t):
        t.add_col('x', 0)
        assert t._columns == ['id', 'name', 'x']

    def test_rename_to_new_name(self, t):
        t.set_col_name(1, 'title')
        assert t._columns == ['id', 'title']

    def test_rename_to_same_name_idempotent(self, t):
        t.set_col_name(0, 'id')
        assert t._columns == ['id', 'name']

    def test_insert_col_front(self, q):
        q.InsertCol(1, 'first', 7)
        assert q._columns == ['first', 'id', 'name']


class TestColumnsStayUnique:
    @pytest.mark.parametrize('attempt', [
        lambda q: q.AddCol('name', 1),
        lambda q: q.InsertCol(3, 'name'),
        lambda q: q.SetColName('id', 'name'),
    ])
    def test_columns_unique_after_attempts(self, q, attempt):
        try:
            attempt(q)
        except ValueError:
            pass
        assert q._columns == ['id', 'name'], '失败操作不应改动列名'

    def test_name_lookup_unambiguous(self, q):
        with pytest.raises(ValueError):
            q.InsertCol(2, 'id', 99)
        # 未发生重名 -> 按名取值命中唯一列
        assert q.GetCol('id') == [1]
        assert q.QAXColIndex('id') == 1