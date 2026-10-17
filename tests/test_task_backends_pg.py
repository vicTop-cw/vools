# -*- coding: utf-8 -*-
"""测试 vools.task.backends.pg — PgTaskBackend / DEFAULT_PG_SCHEMA / _loads。"""

import pytest

from vools.task.backends.pg import PgTaskBackend, DEFAULT_PG_SCHEMA, _loads

__all__ = ["TestLoads", "TestSchema", "TestInit", "TestClose", "TestImport"]


class TestLoads:
    """_loads 测试。"""

    def test_none(self):
        assert _loads(None) is None
        assert _loads(None, default=[]) == []

    def test_dict(self):
        d = {"a": 1}
        assert _loads(d) is d

    def test_list(self):
        l = [1, 2]
        assert _loads(l) is l

    def test_json_str(self):
        assert _loads('{"a": 1}') == {"a": 1}

    def test_json_list(self):
        assert _loads('[1, 2]') == [1, 2]

    def test_invalid(self):
        assert _loads("not json") == "not json"

    def test_int(self):
        assert _loads(123) == 123


class TestSchema:
    """DEFAULT_PG_SCHEMA 测试。"""

    def test_has_create(self):
        assert "CREATE TABLE" in DEFAULT_PG_SCHEMA

    def test_has_indexes(self):
        assert "idx_{table}_status" in DEFAULT_PG_SCHEMA
        assert "idx_{table}_priority" in DEFAULT_PG_SCHEMA

    def test_format(self):
        sql = DEFAULT_PG_SCHEMA.format(table="test_tasks")
        assert "test_tasks" in sql
        assert "CREATE TABLE IF NOT EXISTS test_tasks" in sql


class TestInit:
    """__init__ 测试。"""

    def test_defaults(self):
        b = PgTaskBackend("postgresql://localhost/db")
        assert b.dsn == "postgresql://localhost/db"
        assert b.table == "vic_tasks_task"
        assert b.max_retries == 3
        assert b.retry_delay_min == 5
        assert b.autocommit is True
        assert b._conn is None

    def test_custom(self):
        b = PgTaskBackend("dsn", table="t2", max_retries=5,
                          retry_delay_min=1, autocommit=False)
        assert b.table == "t2"
        assert b.max_retries == 5
        assert b.retry_delay_min == 1
        assert b.autocommit is False


class TestClose:
    """close 测试。"""

    def test_close_no_conn(self):
        b = PgTaskBackend("dsn")
        b.close()
        assert b._conn is None

    def test_close_with_conn(self):
        class FakeConn:
            closed = False

            def close(self):
                self.closed = True

        b = PgTaskBackend("dsn")
        fc = FakeConn()
        b._conn = fc
        b.close()
        assert fc.closed is True
        assert b._conn is None


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.task.backends.pg import __all__
        assert "PgTaskBackend" in __all__
        assert "DEFAULT_PG_SCHEMA" in __all__
