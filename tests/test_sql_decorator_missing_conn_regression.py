# -*- coding: utf-8 -*-
"""回归测试：静态 SQL 模板缺连接时给出明确错误（BUG-235）。

原 `_make_sql_wrapper`：静态 sql 模板 + 无连接调用时 `result` 从未赋值，
落到结果转换/返回处抛 `UnboundLocalError`（内部错误，用户看不出真正原因
是缺连接）；同文件动态模式有明确的 `conn is None: return result` 语义。

修复：`result` 预初始化；静态模板且无连接时抛带三种提供连接方式的
RuntimeError；动态模式（sql is None）既有返回语义完全不动。
"""

import pytest

from vools.sql.core.decorators import sql_function
from vools.sql.sqlite.connection import SqliteConnection


@pytest.fixture
def conn():
    c = SqliteConnection(':memory:')
    c.connect()
    yield c
    c.close()


class TestStaticTemplateRequiresConnection:
    """BUG-235 核心：静态模板缺连接 → 明确 RuntimeError 而非 UnboundLocalError。"""

    def test_missing_connection_raises_runtime_error(self):
        @sql_function(sql="SELECT 1")
        def fn():
            pass

        with pytest.raises(RuntimeError, match="静态 SQL 模板但未提供数据库连接"):
            fn()

    def test_error_not_unbound_local(self):
        @sql_function(sql="SELECT 1")
        def fn():
            pass

        try:
            fn()
        except RuntimeError:
            pass
        except UnboundLocalError:  # pragma: no cover
            pytest.fail("仍是内部 UnboundLocalError，未给出缺连接指引")

    def test_with_connection_works(self, conn):
        @sql_function(sql="SELECT 1 AS x")
        def fn():
            pass

        result = fn(conn)
        assert result is not None

    def test_connection_keyword_works(self, conn):
        @sql_function(sql="SELECT 1")
        def fn():
            pass

        assert fn(connection=conn) is not None

    def test_decorator_level_connection(self, conn):
        @sql_function(connection=conn, sql="SELECT 1")
        def fn():
            pass

        assert fn() is not None


class TestDynamicModeSemanticsUnchanged:
    """动态模式（sql=None）既有返回语义不动（测试锁死项）。"""

    def test_dynamic_no_conn_returns_sql_text(self):
        @sql_function()
        def fn():
            return "SELECT 1"

        assert fn() == "SELECT 1"

    def test_dynamic_with_args_no_conn(self):
        @sql_function()
        def fn(x):
            return f"SELECT {x}"

        assert fn(5) == "SELECT 5"

    def test_dynamic_with_conn_executes(self, conn):
        @sql_function()
        def fn():
            return "SELECT 1"

        assert fn(conn) is not None

    def test_dynamic_returns_non_sql_result(self):
        # 函数直接返回非 SQL 结果（非 str/tuple）→ 原样返回
        @sql_function()
        def fn():
            return {"a": 1}

        assert fn() == {"a": 1}