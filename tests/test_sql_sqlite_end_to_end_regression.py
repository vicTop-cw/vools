# -*- coding: utf-8 -*-
"""端到端回归：sqlite 连接 + @sql_function 注解驱动转换。

此前 sql 层测试多为单元级（ResultSet/Builder 单独测），缺少**真实数据库**的
端到端路径。这里用标准库 sqlite3 的内存库（无需外部服务）覆盖：

- 连接生命周期：connect / is_connected / close
- DDL/DML/SELECT：execute / executemany / commit / rollback / rowcount
- 参数化查询（注入串只作为字面值，不改变表结构）
- `@sql_function`：`Optional[str]`（BUG-352 修复点）、`List[dict]`、`dict`、
  `int`（UPDATE/DELETE 的 rowcount）、无行返回 None
"""

import typing

import pytest

from vools.sql.core.decorators import sql_function
from vools.sql.core.result import ResultSet
from vools.sql.sqlite.dialect import SqliteDialect


@pytest.fixture()
def conn():
    c = SqliteDialect().create_connection(database=':memory:')
    c.connect()
    c.execute('CREATE TABLE t (id INTEGER, name TEXT)')
    c.executemany('INSERT INTO t VALUES (?, ?)', [(1, 'a'), (2, 'b')])
    c.commit()
    yield c
    c.close()


class TestConnectionLifecycle:
    def test_connect_and_close(self):
        c = SqliteDialect().create_connection(database=':memory:')
        c.connect()
        assert c.is_connected is True
        c.close()
        assert c.is_connected is False

    def test_execute_returns_resultset(self, conn):
        res = conn.execute('SELECT * FROM t ORDER BY id')
        assert isinstance(res, ResultSet)
        assert res.to_list() == [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]

    def test_insert_rowcount(self, conn):
        res = conn.execute('INSERT INTO t VALUES (?, ?)', (9, 'z'))
        assert res.rowcount == 1

    def test_commit_and_rollback(self, conn):
        conn.execute('INSERT INTO t VALUES (?, ?)', (3, 'c'))
        conn.rollback()
        assert conn.execute('SELECT COUNT(*) FROM t').scalar() == 2

    def test_parameterization_blocks_injection(self, conn):
        evil = "a'; DROP TABLE t; --"
        res = conn.execute('SELECT * FROM t WHERE name = ?', (evil,))
        assert res.to_list() == []
        # 表仍在、行数不变
        assert conn.execute('SELECT COUNT(*) FROM t').scalar() == 2

    def test_bad_sql_raises(self, conn):
        with pytest.raises(Exception):
            conn.execute('SELECT * FROM no_such_table')


class TestSqlFunctionConversion:
    def test_optional_str_scalar(self, conn):
        """BUG-352：Optional[str] 应转成标量（修复前返回 ResultSet）。"""

        @sql_function(sql='SELECT name FROM t WHERE id = ?')
        def get_name(conn, id: int) -> typing.Optional[str]:
            pass

        assert get_name(conn, 1) == 'a'

    def test_optional_no_rows_returns_none(self, conn):
        @sql_function(sql='SELECT name FROM t WHERE id = ?')
        def get_name(conn, id: int) -> typing.Optional[str]:
            pass

        assert get_name(conn, 99) is None

    def test_list_of_dict(self, conn):
        @sql_function(sql='SELECT * FROM t ORDER BY id')
        def rows(conn) -> typing.List[dict]:
            pass

        assert rows(conn) == [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}]

    def test_dict_first_row(self, conn):
        @sql_function(sql='SELECT * FROM t WHERE id = ?')
        def one(conn, id: int) -> dict:
            pass

        assert one(conn, 2) == {'id': 2, 'name': 'b'}

    def test_dict_no_rows_returns_empty(self, conn):
        @sql_function(sql='SELECT * FROM t WHERE id = ?')
        def one(conn, id: int) -> dict:
            pass

        assert one(conn, 99) == {}

    def test_int_scalar(self, conn):
        @sql_function(sql='SELECT COUNT(*) FROM t')
        def count(conn) -> int:
            pass

        assert count(conn) == 2

    def test_int_rowcount_for_delete(self, conn):
        @sql_function(sql='DELETE FROM t WHERE id = ?')
        def delete(conn, id: int) -> int:
            pass

        assert delete(conn, 2) == 1
        assert conn.execute('SELECT COUNT(*) FROM t').scalar() == 1

    def test_inferred_sql_types_use_defaults(self):
        from vools.sql.core.decorators import _resolve_sql_types

        assert _resolve_sql_types([int, typing.Optional[str]], None)[0] == [
            'INTEGER', 'VARCHAR']