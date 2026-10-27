# -*- coding: utf-8 -*-
"""回归测试：@sql_module 的类级 connection/dialect 未下发给已装饰方法（BUG-355）。

修复前：

    @sql_module(connection=conn)
    class Repo:
        @sql_function(sql="SELECT COUNT(*) FROM u")
        def count(self) -> int: ...

    Repo().count()
    # RuntimeError: sql_function: 提供了静态 SQL 模板但未提供数据库连接...
    #   —— 类上明明给了 connection；根因是 sql_module 对已带 _sql_info 的方法
    #   **整体跳过**（continue），类级配置完全不下发；且内层装饰把 self 当成 SQL 参数

修复：sql_module 对已装饰方法按「方法自身配置优先、类级配置兜底」重新包装
（skip_first_arg=True），并保留 @sql_func_name 与静态 SQL。
"""

import pytest

from vools.sql.core.decorators import sql_func_name, sql_function, sql_module
from vools.sql.sqlite.connection import SqliteConnection


@pytest.fixture()
def conns(tmp_path):
    c1 = SqliteConnection(str(tmp_path / "a.db"))
    c1.connect()
    c1.execute("CREATE TABLE u (id INTEGER, name TEXT)")
    c1.execute("INSERT INTO u VALUES (1, 'a'), (2, 'b')")
    c1.commit()

    c2 = SqliteConnection(str(tmp_path / "b.db"))
    c2.connect()
    c2.execute("CREATE TABLE v (x INTEGER)")
    c2.execute("INSERT INTO v VALUES (42)")
    c2.commit()
    yield c1, c2
    c1.close()
    c2.close()


class TestClassLevelConnectionApplied:
    def test_inner_static_sql_uses_module_connection(self, conns):
        c1, _ = conns

        @sql_module(connection=c1)
        class Repo:
            @sql_function(sql="SELECT COUNT(*) FROM u")
            def count(self) -> int:
                pass

        assert Repo().count() == 2

    def test_inner_sql_with_params(self, conns):
        c1, _ = conns

        @sql_module(connection=c1)
        class Repo:
            @sql_function(sql="SELECT name FROM u WHERE id = :id")
            def name_of(self, id: int) -> str:
                pass

        assert Repo().name_of(1) == "a"

    def test_method_own_connection_wins(self, conns):
        c1, c2 = conns

        @sql_module(connection=c1)
        class Repo:
            @sql_function(connection=c2, sql="SELECT x FROM v")
            def x(self) -> int:
                pass

        assert Repo().x() == 42

    def test_func_name_preserved(self, conns):
        c1, _ = conns

        @sql_module(connection=c1)
        class Repo:
            @sql_func_name("count_users")
            @sql_function(sql="SELECT COUNT(*) FROM u")
            def count(self) -> int:
                pass

        wrapped = Repo.count
        assert wrapped._sql_info.get("func_name") == "count_users"
        assert Repo().count() == 2


class TestUndecoratedMethodsUnchanged:
    def test_method_returning_sql_template(self, conns):
        c1, _ = conns

        @sql_module(connection=c1)
        class Repo:
            def list_names(self) -> list:
                return "SELECT name FROM u"

        assert Repo().list_names() == [{"name": "a"}, {"name": "b"}]

    def test_method_without_sql_returns_none(self, conns):
        c1, _ = conns

        @sql_module(connection=c1)
        class Repo:
            def nothing(self):
                pass

        assert Repo().nothing() is None


class TestSqlFunctionValidationUnchanged:
    def test_unknown_dialect(self):
        with pytest.raises(ValueError):
            sql_function(dialect="bogus")

    def test_non_str_dialect(self):
        with pytest.raises(ValueError):
            sql_function(dialect=123)

    def test_standalone_connection_usage(self, conns):
        c1, _ = conns

        @sql_function(connection=c1, sql="SELECT COUNT(*) FROM u")
        def count() -> int:
            pass

        assert count() == 2
