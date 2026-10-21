# -*- coding: utf-8 -*-
"""回归测试：SQLite 连接层结果集判定与连接守卫（BUG-236）。

① 原 `execute` 用 SQL 前缀 `startswith(('SELECT','WITH',...))` 判断有无结果集
——带前导/块注释的 SELECT 与 `INSERT ... RETURNING` 被误判为 DML，真实
返回行被静默丢弃（rows=[]、rowcount=-1）。修复：改用 DB-API 权威信号
`cursor.description is not None`。

② `executemany` 缺连接守卫，未连接时抛 `AttributeError` 而非类内统一的
`RuntimeError('Database connection is not established')`。
"""

import pytest

from vools.sql.sqlite.connection import SqliteConnection


@pytest.fixture
def conn():
    c = SqliteConnection(':memory:')
    c.connect()
    yield c
    c.close()


class TestResultSetDetection:
    """BUG-236 ①：有结果集的语句都不得丢行。"""

    def test_line_comment_prefixed_select(self, conn):
        r = conn.execute("-- leading comment\nSELECT 1 AS x")
        assert [list(row) for row in r.fetchall()] == [[1]]
        assert r.columns == ['x']

    def test_block_comment_prefixed_select(self, conn):
        r = conn.execute("/* c */ SELECT 3 AS z")
        assert [list(row) for row in r.fetchall()] == [[3]]

    def test_insert_returning(self, conn):
        conn.execute("CREATE TABLE t (id INTEGER)")
        r = conn.execute("INSERT INTO t VALUES (7) RETURNING id")
        assert [list(row) for row in r.fetchall()] == [[7]]

    def test_plain_select(self, conn):
        r = conn.execute("SELECT 1 AS x")
        assert [list(row) for row in r.fetchall()] == [[1]]

    def test_with_query(self, conn):
        r = conn.execute("WITH t AS (SELECT 2 AS y) SELECT y FROM t")
        assert [list(row) for row in r.fetchall()] == [[2]]

    def test_pragma(self, conn):
        r = conn.execute("PRAGMA user_version")
        assert r.columns  # 有描述列


class TestDmlPathUnchanged:
    """DML 走 rowcount 分支的行为保持。"""

    def test_insert_rowcount(self, conn):
        conn.execute("CREATE TABLE u (id INTEGER)")
        r = conn.execute("INSERT INTO u VALUES (1)")
        assert r.rowcount == 1
        assert r.fetchall() == []

    def test_update_rowcount(self, conn):
        conn.execute("CREATE TABLE u (id INTEGER)")
        conn.execute("INSERT INTO u VALUES (1)")
        assert conn.execute("UPDATE u SET id = 2").rowcount == 1

    def test_delete_rowcount(self, conn):
        conn.execute("CREATE TABLE u (id INTEGER)")
        conn.execute("INSERT INTO u VALUES (1)")
        assert conn.execute("DELETE FROM u").rowcount == 1


class TestExecutemanyConnectionGuard:
    """BUG-236 ②：executemany 未连接时与 execute/cursor 同款 RuntimeError。"""

    def test_closed_connection_raises_runtime_error(self):
        c = SqliteConnection(':memory:')
        with pytest.raises(RuntimeError, match="connection is not established"):
            c.executemany("INSERT INTO t VALUES (?)", [(1,)])

    def test_works_when_connected(self, conn):
        conn.execute("CREATE TABLE u (id INTEGER)")
        assert conn.executemany("INSERT INTO u VALUES (?)",
                                [(10,), (11,), (12,)]) == 3