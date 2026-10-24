# -*- coding: utf-8 -*-
"""回归测试：sql_function/sql_module 的 dialect 参数校验（BUG-462）。

修复前 ``dialect`` 被原样塞进 ``_sql_info`` 元数据后**从未解析/校验**：

    @sql_function(dialect="nope")
    def fn() -> list: ...

装饰器静默生效——不报错、不改变任何行为，使用者会误以为占位符/类型映射
已按该方言处理。修复后未知方言在**装饰期**就报 ValueError（并列出可用方言）。

注意：方言注册表是**惰性加载**的（core 层首次访问前为空），校验走顶层
``vools.sql.get_dialect`` 以触发加载。
"""

import pytest

from vools.sql.core.decorators import sql_function, sql_module
from vools.sql.sqlite.dialect import SqliteDialect


def _noop():
    return "SELECT 1"


class TestDialectValidation:
    def test_unknown_dialect_rejected(self):
        with pytest.raises(ValueError) as ei:
            sql_function(dialect="nope")(_noop)
        msg = str(ei.value)
        assert "nope" in msg
        assert "sqlite" in msg          # 列出可用方言

    @pytest.mark.parametrize("bad", [123, "", "   ", 1.5])
    def test_bad_type_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            sql_function(dialect=bad)(_noop)
        assert "dialect" in str(ei.value)

    def test_sql_module_unknown_dialect(self):
        with pytest.raises(ValueError):
            sql_module(dialect="nope")(type("X", (), {}))

    def test_none_allowed(self):
        assert callable(sql_function(dialect=None)(_noop))


class TestValidDialect:
    def test_known_dialect_accepted(self):
        assert callable(sql_function(dialect="sqlite")(_noop))

    def test_known_dialect_end_to_end(self):
        conn = SqliteDialect().create_connection(database=":memory:")
        conn.connect()
        try:
            @sql_function(dialect="sqlite", connection=conn)
            def fn() -> list:
                return "SELECT 2 AS v"

            assert fn() == [{"v": 2}]
        finally:
            conn.close()

    def test_without_dialect_still_works(self):
        conn = SqliteDialect().create_connection(database=":memory:")
        conn.connect()
        try:
            @sql_function(connection=conn)
            def fn() -> list:
                return "SELECT 1 AS v"

            assert fn() == [{"v": 1}]
        finally:
            conn.close()

    def test_dialect_recorded_in_metadata(self):
        @sql_function(dialect="sqlite")
        def fn() -> list:
            return "SELECT 1"

        assert getattr(fn, "_sql_info", {}).get("dialect") == "sqlite"
