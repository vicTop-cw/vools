# -*- coding: utf-8 -*-
"""测试 vools.sql.postgres.connection — PostgresConnection。"""

import sys
import pytest

from vools.sql.postgres.connection import PostgresConnection

__all__ = ["TestInit", "TestConnect", "TestClose", "TestExecute",
           "TestExecuteMany", "TestCommitRollback", "TestCursor",
           "TestDriverName", "TestImport"]


class _FakeCursor:
    def __init__(self, description=None, rows=None, rowcount=0):
        self.description = description
        self._rows = rows or []
        self.rowcount = rowcount
        self.executed = []
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, seq_of_params):
        self.executed.append((sql, seq_of_params))
        self.rowcount = len(seq_of_params)

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, cursor_obj=None):
        self._cursor = cursor_obj or _FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# 模块级 fake 模块，避免动态类 method binding
_LAST_CONN = None
_LAST_KWARGS = None


def _fake_psycopg2_connect(**kw):
    global _LAST_CONN, _LAST_KWARGS
    _LAST_CONN = _FakeConn()
    _LAST_KWARGS = kw
    return _LAST_CONN


def _fake_psycopg_connect(**kw):
    global _LAST_CONN, _LAST_KWARGS
    _LAST_CONN = _FakeConn()
    _LAST_KWARGS = kw
    return _LAST_CONN


def _install_fake_psycopg2(monkeypatch, connect_fn=None):
    import types
    m = types.ModuleType("psycopg2")
    m.connect = connect_fn or _fake_psycopg2_connect
    monkeypatch.setitem(sys.modules, "psycopg2", m)


def _install_fake_psycopg(monkeypatch, connect_fn=None):
    import types
    m = types.ModuleType("psycopg")
    m.connect = connect_fn or _fake_psycopg_connect
    monkeypatch.setitem(sys.modules, "psycopg", m)


def _block_psycopg2(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psycopg2":
            raise ImportError("no psycopg2")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", fake_import)


class TestInit:
    """__init__ 测试。"""

    def test_defaults(self):
        c = PostgresConnection()
        assert c._host == "localhost"
        assert c._port == 5432
        assert c._user == "postgres"
        assert c._password == ""
        assert c._database == "postgres"
        assert c._conn is None
        assert c._connected is False
        assert c._driver_name is None

    def test_custom(self):
        c = PostgresConnection(host="db", port=5433, user="u", password="p",
                               database="d", sslmode="require")
        assert c._host == "db"
        assert c._extra_kwargs == {"sslmode": "require"}


class TestConnect:
    """connect 测试。"""

    def test_psycopg2(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        assert c._connected is True
        assert c._driver_name == "psycopg2"
        assert _LAST_CONN is not None

    def test_psycopg_fallback(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch, connect_fn=lambda **kw: (_ for _ in ()).throw(ImportError("no psycopg2")))
        _install_fake_psycopg(monkeypatch)
        c = PostgresConnection()
        c.connect()
        assert c._driver_name == "psycopg"

    def test_no_driver(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name in ("psycopg2", "psycopg"):
                raise ImportError("no driver")
            return real_import(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", fake_import)
        c = PostgresConnection()
        with pytest.raises(ImportError):
            c.connect()

    def test_already_connected(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        c.connect()
        assert c._connected is True

    def test_kwargs_override(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection(host="h", user="u")
        c.connect(host="h2", user="u2", extra="x")
        assert _LAST_KWARGS["host"] == "h2"
        assert _LAST_KWARGS["user"] == "u2"
        assert _LAST_KWARGS["extra"] == "x"


class TestClose:
    """close 测试。"""

    def test_close(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        c.close()
        assert _LAST_CONN.closed is True
        assert c._conn is None
        assert c._connected is False

    def test_close_not_connected(self):
        c = PostgresConnection()
        c.close()


class TestExecute:
    """execute 测试。"""

    def test_not_connected(self):
        c = PostgresConnection()
        with pytest.raises(RuntimeError):
            c.execute("SELECT 1")

    def test_success(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        _LAST_CONN._cursor = _FakeCursor(
            description=[("id",), ("name",)],
            rows=[(1, "a"), (2, "b")],
            rowcount=2,
        )
        rs = c.execute("SELECT id, name FROM users")
        assert rs.rowcount == 2
        assert len(rs.to_list()) == 2

    def test_with_params(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        c.execute("INSERT INTO t VALUES (%s)", (1,))
        assert _LAST_CONN._cursor.executed[0][1] == (1,)

    def test_cursor_closed(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        c.execute("SELECT 1")
        assert _LAST_CONN._cursor.closed is True


class TestExecuteMany:
    """executemany 测试。"""

    def test_not_connected(self):
        c = PostgresConnection()
        with pytest.raises(RuntimeError):
            c.executemany("INSERT", [(1,), (2,)])

    def test_success(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        n = c.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,), (3,)])
        assert n == 3
        assert _LAST_CONN._cursor.closed is True


class TestCommitRollback:
    """commit / rollback 测试。"""

    def test_commit(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.commit()
        assert _LAST_CONN is None or not _LAST_CONN.committed
        c.connect()
        c.commit()
        assert _LAST_CONN.committed is True

    def test_rollback(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.rollback()
        c.connect()
        c.rollback()
        assert _LAST_CONN.rolled_back is True


class TestCursor:
    """cursor 测试。"""

    def test_not_connected(self):
        c = PostgresConnection()
        with pytest.raises(RuntimeError):
            c.cursor()

    def test_success(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        assert c.cursor() is _LAST_CONN._cursor


class TestDriverName:
    """driver_name 测试。"""

    def test_none(self):
        c = PostgresConnection()
        assert c.driver_name is None

    def test_after_connect(self, monkeypatch):
        _install_fake_psycopg2(monkeypatch)
        c = PostgresConnection()
        c.connect()
        assert c.driver_name == "psycopg2"


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sql.postgres.connection import __all__
        assert "PostgresConnection" in __all__
