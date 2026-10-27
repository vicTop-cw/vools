# -*- coding: utf-8 -*-
"""回归测试：sql 连接构造参数校验（BUG-350）。

## SqliteConnection

    SqliteConnection(None)   # 修复前 → 构造成功，connect() 时才由 sqlite3 抛
    SqliteConnection(123)    #   "TypeError: expected str, bytes or os.PathLike object"

## PostgresConnection（与 vools.db.PostgreSQLConnection 口径不一致）

    PostgresConnection(port="x")   # 修复前 → 全部静默接受
    PostgresConnection(port=-1)    # 直到 connect() 才由驱动报难读的错误
    PostgresConnection(host=123)

修复：sqlite 的 database 必须字符串；postgres 的 host 非空字符串、port 为
1..65535 的整数（bool 拒绝）、user/password/database 必须字符串。
"""

import os

import pytest

from vools.sql.postgres.connection import PostgresConnection
from vools.sql.sqlite.connection import SqliteConnection


class TestSqliteConnectionValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5, ["x"]])
    def test_database_must_be_str(self, bad):
        with pytest.raises(TypeError) as ei:
            SqliteConnection(bad)
        assert "database" in str(ei.value)

    @pytest.mark.parametrize("ok", [":memory:", ""])
    def test_valid_database_accepted(self, ok):
        assert isinstance(SqliteConnection(ok), SqliteConnection)

    def test_roundtrip_still_works(self):
        conn = SqliteConnection(":memory:")
        conn.connect()
        try:
            assert conn.execute("SELECT 1 AS v").scalar() == 1
        finally:
            conn.close()


class TestPostgresConnectionHostValidation:
    @pytest.mark.parametrize("bad", [123, None, ""])
    def test_host(self, bad):
        with pytest.raises(ValueError) as ei:
            PostgresConnection(host=bad)
        assert "host" in str(ei.value)


class TestPostgresConnectionPortValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_port_type(self, bad):
        with pytest.raises(TypeError) as ei:
            PostgresConnection(port=bad)
        assert "port" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1, 65536, 70000])
    def test_port_range(self, bad):
        with pytest.raises(ValueError) as ei:
            PostgresConnection(port=bad)
        assert "port" in str(ei.value)


class TestPostgresConnectionCredentialValidation:
    @pytest.mark.parametrize("field", ["user", "password", "database"])
    def test_must_be_str(self, field):
        with pytest.raises(TypeError) as ei:
            PostgresConnection(**{field: 123})
        assert field in str(ei.value)


class TestBehaviourUnchanged:
    def test_defaults(self):
        conn = PostgresConnection()
        assert conn._host == "localhost"
        assert conn._port == 5432
        assert conn._user == "postgres"
        assert conn._database == "postgres"

    def test_explicit_values(self):
        conn = PostgresConnection("db.local", 6543, "u", "p", "d")
        assert (conn._host, conn._port, conn._user, conn._password, conn._database) == (
            "db.local",
            6543,
            "u",
            "p",
            "d",
        )

    def test_connect_without_driver_raises_import_error(self):
        """仅在**本解释器无驱动**时断言 ImportError。

        注意：本测试曾被 FIST run_check 抓到失败——run_check 的 `python` 可能是
        PATH 上的另一个解释器（那里装了 psycopg2），此时 connect() 会走真实网络
        并抛 OperationalError/OSError 而非 ImportError。断言必须按环境分流，
        否则就是"环境依赖的坏测试"。
        """
        import importlib.util

        has_driver = any(
            importlib.util.find_spec(name) is not None for name in ("psycopg2", "psycopg")
        )
        if has_driver:
            pytest.skip("本解释器已安装 PostgreSQL 驱动，连接会走真实网络")
        with pytest.raises(ImportError):
            PostgresConnection().connect()

    def test_sqlite_file_path_roundtrip(self, tmp_path):
        path = str(tmp_path / "t.db")
        with SqliteConnection(path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS x (id INTEGER)")
            conn.execute("INSERT INTO x VALUES (1)")
        with SqliteConnection(path) as conn:
            assert conn.execute("SELECT COUNT(*) AS n FROM x").scalar() == 1
