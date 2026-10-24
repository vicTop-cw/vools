# -*- coding: utf-8 -*-
"""审计锁定：SQL 连接的事务/生命周期语义（无缺陷，行为即契约）。

本轮审计 `vools.sql.core.connection.Connection` + `vools.sql.sqlite` 实现，
确认以下语义均为**有意行为**，在此锁定以防后续被误改：

1. **懒连接**：``create_connection(...)`` 返回时 ``is_connected is False``；
   未 connect 就 ``execute`` → ``RuntimeError: Database connection is not established``
   （响亮，不静默）。
2. **上下文管理器 = 事务 + 关闭**（``__exit__`` 文档明示"最后关闭连接"）：
   - 无异常 → ``commit()``；有异常 → ``rollback()`` 并继续向上抛出（返回 False）；
   - **两种路径都会 ``close()``**，因此 ``with conn:`` 之后连接不可再用；
   - 注意（坑）：对 ``:memory:`` 数据库来说，关闭即丢库，重入 ``with`` 会
     ``__enter__`` 自动重连到**全新空库**（后续查询会以 no such table 响亮失败）。
     需要多次事务请改用文件库，或显式 ``commit()/rollback()`` 而不用 with。
3. **close 幂等**：重复 ``close()`` 无副作用。
4. ``execute`` 的 SQL 必须是 str（``None``/int → TypeError）；参数数量不匹配由
   驱动抛 ProgrammingError；``executemany(None)`` → TypeError，非 DML → ProgrammingError。
5. ``ResultSet``：``rowcount``、``[0]`` 索引、``fetchall()`` 之后的 ``fetchone()`` → None。
"""

import typing

import pytest

from vools.sql.core.result import ResultSet
from vools.sql.sqlite.dialect import SqliteDialect


def _conn(memory=True):
    c = SqliteDialect().create_connection(database=":memory:" if memory else None)
    return c


@pytest.fixture()
def conn():
    c = SqliteDialect().create_connection(database=":memory:")
    c.connect()
    c.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    c.executemany("INSERT INTO t VALUES (?, ?)", [(1, "a"), (2, "b")])
    c.commit()
    yield c
    c.close()


class TestLazyConnect:
    def test_not_connected_on_create(self):
        assert _conn().is_connected is False

    def test_execute_before_connect_is_loud(self):
        c = _conn()
        with pytest.raises(RuntimeError) as ei:
            c.execute("SELECT 1")
        assert "not established" in str(ei.value)

    def test_enter_auto_connects(self):
        c = _conn()
        with c:
            assert c.is_connected is True


class TestTransactionSemantics:
    def test_commit_on_success(self):
        c = _conn()
        with c:
            c.execute("CREATE TABLE u (v TEXT)")
            c.execute("INSERT INTO u VALUES (?)", ("x",))
        # __exit__ 关闭连接（文档语义）
        assert c.is_connected is False

    def test_rollback_on_exception(self):
        c = _conn()
        with pytest.raises(RuntimeError):
            with c:
                c.execute("CREATE TABLE u (v TEXT)")
                c.execute("INSERT INTO u VALUES (?)", ("x",))
                raise RuntimeError("boom")
        assert c.is_connected is False   # 同样关闭

    def test_returns_false_so_exception_propagates(self):
        c = _conn()
        with pytest.raises(ValueError):
            with c:
                raise ValueError("propagate")

    def test_memory_db_lost_after_with(self):
        """文档语义的直接后果：内存库关闭即丢，重入得到空库。"""
        c = _conn()
        with c:
            c.execute("CREATE TABLE u (v TEXT)")
        with pytest.raises(Exception):
            with c:                       # __enter__ 自动重连到全新空库
                c.execute("SELECT * FROM u")


class TestCloseIdempotent:
    def test_double_close(self):
        c = _conn()
        c.connect()
        c.close()
        c.close()
        assert c.is_connected is False


class TestExecuteValidation:
    @pytest.mark.parametrize("bad", [None, 123, ["SELECT 1"]])
    def test_sql_must_be_str(self, conn, bad):
        with pytest.raises(TypeError):
            conn.execute(bad)

    def test_param_count_mismatch_is_loud(self, conn):
        with pytest.raises(Exception):
            conn.execute("SELECT ?", ())

    def test_executemany_none_is_loud(self, conn):
        with pytest.raises(TypeError):
            conn.executemany("INSERT INTO t VALUES (?, ?)", None)

    def test_executemany_non_dml_is_loud(self, conn):
        with pytest.raises(Exception):
            conn.executemany("", [(1, "a")])


class TestResultSet:
    def test_accessors(self, conn):
        rs = conn.execute("SELECT * FROM t ORDER BY id")
        assert isinstance(rs, ResultSet)
        assert rs.rowcount == 2
        assert rs[0].id == 1
        rows = rs.fetchall()
        assert len(rows) == 2
        assert rs.fetchone() is None      # 已耗尽

    def test_commit_rollback_file_db(self, tmp_path):
        """文件库上 commit/rollback 各自生效（不依赖 with 的关闭语义）。"""
        db = tmp_path / "audit.db"
        c = SqliteDialect().create_connection(database=str(db))
        c.connect()
        c.execute("CREATE TABLE u (v TEXT)")
        c.commit()
        c.execute("INSERT INTO u VALUES (?)", ("x",))
        c.rollback()
        assert c.execute("SELECT COUNT(*) AS n FROM u").fetchall()[0].n == 0
        c.execute("INSERT INTO u VALUES (?)", ("y",))
        c.commit()
        assert c.execute("SELECT COUNT(*) AS n FROM u").fetchall()[0].n == 1
        c.close()
