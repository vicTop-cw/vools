# -*- coding: utf-8 -*-
"""回归测试：Table.query 的参数校验与 SQL 语义顺序（BUG-364/366）+ Table.range（BUG-365）。

【BUG-364】未知查询参数被静默忽略：把 `order_by` 拼成 `oder_by`（或 `wheres`）
时函数返回**全量数据**且毫无提示——用户以为已过滤。修复：未知键抛 ValueError，
并列出允许的键集合（kwargs 与 sql_like 串都校验）。

【BUG-366】原实现先 `select` 后 `where`，因此过滤列不在选取列中时（SQL 里完全
合法：`SELECT name FROM t WHERE id > 1`）where 找不到列 → 逐行 False → **静默
空表**。修复：按 SQL 语义重排为 WHERE → ORDER BY → LIMIT/OFFSET → SELECT。

【BUG-365】`Table.range(3)`（继承自 Seq 的类方法）把整数当"行"传入构造器，
抛 `TypeError: object of type 'int' has no len()`。修复：覆盖为清晰 TypeError
并给出可执行替代写法。
"""

import pytest

from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([[1, 'a'], [2, 'b'], [3, 'c']], columns=['id', 'name'])


class TestQueryUnknownKeys:
    @pytest.mark.parametrize('kwargs', [
        {'oder_by': 'id'},
        {'wheres': 'id>1'},
        {'limitt': 2},
    ])
    def test_kwargs_rejected(self, table, kwargs):
        with pytest.raises(ValueError) as ei:
            table.query(**kwargs)
        msg = str(ei.value)
        assert '未知查询参数' in msg and 'where' in msg

    def test_sql_like_rejected(self, table):
        with pytest.raises(ValueError):
            table.query('oder_by=id')

    def test_allowed_keys_still_work(self, table):
        assert table.query(where='id>1', order_by='id', desc=True,
                           limit=2).rows() == 2
        assert table.query(select='name')._columns == ['name']
        assert table.query(limit=1, offset=1).rows() == 1


class TestQuerySqlOrder:
    """BUG-366：SELECT 必须在 WHERE/ORDER BY/LIMIT 之后执行。"""

    def test_filter_on_unselected_column(self, table):
        # 修复前：静默空表
        r = table.query(select='name', where='id>1')
        assert r._columns == ['name']
        assert r._data == [['b'], ['c']]

    def test_select_with_limit(self, table):
        assert table.query(select='name', where='id>1', limit=1)._data == [['b']]

    def test_select_with_order_and_limit(self, table):
        r = table.query(select='id', order_by='id', desc=True, limit=2)
        assert r._data == [[3], [2]]

    def test_where_only_unchanged(self, table):
        assert table.query(where='id>1')._data == [[2, 'b'], [3, 'c']]

    def test_sql_like_unchanged(self, table):
        assert table.query('where=id>1&limit=1')._data == [[2, 'b']]

    def test_empty_query(self, table):
        assert table.query().rows() == 3


class TestTableRange:
    """BUG-365：Table.range 应给出清晰错误而不是 len() TypeError。"""

    @pytest.mark.parametrize('args', [(3,), (1, 5), (1, 10, 2)])
    def test_clear_type_error(self, args):
        with pytest.raises(TypeError) as ei:
            Table.range(*args)
        assert 'Table.range 不适用' in str(ei.value)

    def test_suggested_alternative_works(self):
        t = Table([[v] for v in range(3)], columns=['value'])
        assert t._data == [[0], [1], [2]]


class TestOtherConstructorsUnaffected:
    def test_of(self):
        assert Table.of([1, 2])._data == [[1, 2]]

    def test_new(self):
        assert Table.new().rows() == 0

    def test_from_array(self):
        assert Table.from_array([[1, 2]])._data == [[1, 2]]