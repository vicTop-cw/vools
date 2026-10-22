# -*- coding: utf-8 -*-
"""回归测试：sql_function 静态模板模式支持关键字形式的 SQL 参数（BUG-297）。

原实现静态模板分支 `params = remaining_args`——除 connection 外的剩余
**关键字参数被静默丢弃**：`q(conn, id=1)` 时 SQL 少绑定，DB 端报
`ProgrammingError: Incorrect number of bindings supplied`（错误指不到真因）。

修复：按函数签名参数顺序把 remaining_kwargs 合并进 params（位置参数在前，
其余按 param_names 补齐；签名外多余关键字按提供顺序追加）。
"""

import pytest

from vools.sql.core.decorators import sql_function
from vools.sql.sqlite.connection import SqliteConnection


@pytest.fixture()
def conn(tmp_path):
    c = SqliteConnection(str(tmp_path / 't.db'))
    c.connect()
    c.execute('CREATE TABLE t (id INTEGER, name TEXT)')
    c.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    yield c
    c.close()


def _rows(result):
    return getattr(result, 'rowcount', None)


class TestStaticTemplateKwArgs:
    def test_positional(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ?')
        def q(conn, id):
            pass

        assert _rows(q(conn, 1)) == 1

    def test_keyword(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ?')
        def q(conn, id):
            pass

        # 修复前：ProgrammingError: Incorrect number of bindings supplied
        assert _rows(q(conn, id=1)) == 1

    def test_keyword_with_connection_kwarg(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ?')
        def q(conn, id):
            pass

        assert _rows(q(id=1, connection=conn)) == 1

    def test_positional_with_connection_kwarg(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ?')
        def q(conn, id):
            pass

        assert _rows(q(1, connection=conn)) == 1

    def test_named_placeholder_keyword(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = :id')
        def q(conn, id):
            pass

        assert _rows(q(conn, id=1)) == 1

    def test_multi_param_keyword_order(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ? AND name = ?')
        def q(conn, id, name):
            pass

        # 关键字乱序传入，应按签名顺序绑定
        assert _rows(q(conn, name='b', id=2)) == 1

    def test_multi_param_mixed(self, conn):
        @sql_function(sql='SELECT id, name FROM t WHERE id = ? AND name = ?')
        def q(conn, id, name):
            pass

        assert _rows(q(conn, 2, name='b')) == 1


class TestDynamicModeUnchanged:
    def test_dynamic_sql_with_connection_kwarg(self, conn):
        @sql_function()
        def dyn(n):
            return 'SELECT %s AS v' % n

        assert _rows(dyn(5, connection=conn)) == 1

    def test_dynamic_sql_params_tuple(self, conn):
        @sql_function()
        def dyn(n):
            return 'SELECT id FROM t WHERE id = ?', (n,)

        assert _rows(dyn(2, connection=conn)) == 1

    def test_default_connection(self, conn):
        @sql_function(connection=conn)
        def dyn():
            return 'SELECT count(*) AS c FROM t'

        assert _rows(dyn()) == 1