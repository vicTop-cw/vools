# -*- coding: utf-8 -*-
"""回归测试：Table.query 消费 sql_like 串（BUG-224）。

原 `query(sql_like, **kwargs)` 的函数体只读 kwargs，`sql_like` 位置参数
声明且 docstring 给出用法示例（"where=age>25&limit=5"）却完全未消费——
按文档传串的用户静默拿到全量数据（以为已过滤）。

修复：解析 "k=v&k=v" 与 kwargs 合并，显式 kwargs 优先；limit/offset 转
int、desc 转 bool、无 '=' 的段明确 ValueError。
"""

import pytest

from vools.data.table import Table


@pytest.fixture
def table():
    return Table([[1, 'a'], [2, 'b'], [3, 'c']], columns=['id', 'name'])


class TestSqlLikeConsumed:
    """BUG-224 核心：过滤串真实生效，不再静默全量。"""

    def test_where_filters(self, table):
        assert table.query("where=id>999").rows() == 0
        assert table.query("where=id>1").rows() == 2

    def test_combined(self, table):
        assert table.query("where=id>1&limit=2")._data == [[2, 'b'], [3, 'c']]

    def test_limit_int_cast(self, table):
        assert table.query("limit=1")._data == [[1, 'a']]

    def test_desc_parsed(self, table):
        r = table.query("order_by=id&desc=true")
        assert r._data[0][0] == 3

    def test_offset(self, table):
        assert table.query("offset=1&limit=1")._data == [[2, 'b']]

    def test_malformed_raises(self, table):
        with pytest.raises(ValueError, match="Invalid sql_like segment"):
            table.query("where")


class TestPrecedenceAndCompat:
    """显式 kwargs 优先 + 原路径兼容。"""

    def test_explicit_kwargs_win(self, table):
        # sql_like 只补缺（setdefault），显式 kwargs 优先
        assert table.query("limit=2", limit=3).rows() == 3

    def test_mixed_sources(self, table):
        assert table.query("where=id>1", limit=1).rows() == 1

    def test_kwargs_only_unchanged(self, table):
        assert table.query(where='id>1', limit=2)._data == [[2, 'b'], [3, 'c']]

    def test_no_args_returns_self_data(self, table):
        assert table.query().rows() == 3