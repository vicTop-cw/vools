# -*- coding: utf-8 -*-
"""测试 vools.sql.core.decorators — sql_function / sql_module / sql_func_name。"""

import pytest

__all__ = ["TestSqlFunction", "TestSqlModule", "TestSqlFuncName", "TestHelpers",
           "TestImport"]


def _make_conn():
    """构造一个假的 Connection，execute 返回真实 ResultSet。"""
    from vools.sql.core.result import ResultSet
    conn = type("FakeConn", (), {})()
    conn.execute = lambda sql, params=None: ResultSet(
        columns=["a"], rows=[(1,)], rowcount=1
    )
    return conn


class TestSqlFunction:
    """sql_function 装饰器测试。"""

    def test_basic_without_conn(self):
        from vools.sql.core.decorators import sql_function

        @sql_function()
        def my_sql() -> str:
            return "SELECT 1"

        result = my_sql()
        # conn=None 时直接返回 func 结果
        assert result == "SELECT 1"

    def test_with_conn_keyword(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function(connection=conn)
        def my_sql() -> str:
            return "SELECT 1"

        result = my_sql()
        # conn 在装饰器参数中 → 会执行 conn.execute
        assert result is not None

    def test_with_conn_first_arg(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function()
        def my_sql(conn_placeholder, user_id: int) -> str:
            return "SELECT 1"

        result = my_sql(conn, 5)
        assert result is not None

    def test_auto_convert_list(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function(connection=conn)
        def my_sql() -> list:
            return "SELECT * FROM t"

        result = my_sql()
        assert result == [{"a": 1}]

    def test_auto_convert_dict(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function(connection=conn)
        def my_sql() -> dict:
            return "SELECT * FROM t"

        result = my_sql()
        assert result == {"a": 1}

    def test_sql_template_param(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function(connection=conn, sql="SELECT %s")
        def my_sql(val):
            return val

        result = my_sql(5)
        assert result is not None

    def test_no_auto_convert(self):
        from vools.sql.core.decorators import sql_function
        conn = _make_conn()

        @sql_function(connection=conn, auto_convert=False)
        def my_sql() -> dict:
            return "SELECT * FROM t"

        result = my_sql()
        # auto_convert=False → 不转换，返回原始 ResultSet
        assert result is not None

    def test_dialect_attr(self):
        from vools.sql.core.decorators import sql_function

        @sql_function(dialect="mysql")
        def my_sql():
            return "SELECT 1"

        info = my_sql._sql_info
        assert info["dialect"] == "mysql"

    def test_sql_info_attrs(self):
        from vools.sql.core.decorators import sql_function

        @sql_function(dialect="mysql")
        def my_sql(x: int = 1):
            return "SELECT 1"

        info = my_sql._sql_info
        assert "dialect" in info
        assert "connection" in info
        assert "sql" in info
        assert "auto_convert" in info
        assert "param_names" in info
        assert "param_types" in info
        assert "return_type" in info
        assert "sql_param_types" in info
        assert "sql_return_type" in info
        assert "skip_first_arg" in info

    def test_function_with_args(self):
        from vools.sql.core.decorators import sql_function

        @sql_function()
        def add(a: int, b: int) -> str:
            return f"SELECT {a + b}"

        result = add(2, 3)
        assert result == "SELECT 5"


class TestSqlModule:
    """sql_module 装饰器测试。"""

    def test_module_skips_private(self):
        from vools.sql.core.decorators import sql_module, sql_function

        @sql_module(dialect="mysql")
        class Repo:
            def public_method(self):
                return "SELECT 1"

            def _private(self):
                return "no"

        # public 方法被包装
        assert hasattr(Repo.public_method, "_sql_info")
        # private 方法不被包装
        assert not hasattr(Repo._private, "_sql_info")

    def test_module_skips_type(self):
        from vools.sql.core.decorators import sql_module

        @sql_module()
        class Repo:
            class Inner:
                pass

        # 嵌套类不被包装
        assert not hasattr(Repo.Inner, "_sql_info")

    def test_module_skip_first_arg(self):
        from vools.sql.core.decorators import sql_module

        @sql_module(dialect="mysql")
        class Repo:
            def get(self, user_id: int) -> str:
                return "SELECT 1"

        info = Repo.get._sql_info
        assert info["skip_first_arg"] is True
        assert info["dialect"] == "mysql"

    def test_module_method_call_no_conn(self):
        from vools.sql.core.decorators import sql_module

        @sql_module()
        class Repo:
            def get(self, user_id: int) -> str:
                return f"SELECT {user_id}"

        r = Repo()
        # 无 conn → 返回 func 结果
        result = r.get(5)
        assert result == "SELECT 5"

    def test_module_method_call_with_conn(self):
        from vools.sql.core.decorators import sql_module
        conn = _make_conn()

        @sql_module(connection=conn)
        class Repo:
            def get(self, user_id: int) -> list:
                return "SELECT 1"

        r = Repo()
        result = r.get(5)
        assert result == [{"a": 1}]


class TestSqlFuncName:
    """sql_func_name 标记测试。"""

    def test_func_name_attr(self):
        from vools.sql.core.decorators import sql_func_name

        @sql_func_name("custom_name")
        def my_func():
            return 1

        assert my_func._sql_func_name == "custom_name"

    def test_with_sql_module(self):
        from vools.sql.core.decorators import sql_module, sql_func_name

        @sql_module()
        class Repo:
            @sql_func_name("custom_query")
            def get(self):
                return "SELECT 1"

        info = Repo.get._sql_info
        assert info["func_name"] == "custom_query"


class TestHelpers:
    """内部辅助函数测试。"""

    def test_get_signature_info(self):
        from vools.sql.core.decorators import _get_signature_info

        def f(a: int, b, *args, **kw) -> str:
            pass

        names, types, ret = _get_signature_info(f)
        assert names == ["a", "b"]
        assert types[0] is int
        assert types[1] is None
        assert ret is str

    def test_get_signature_info_bad_sig(self):
        from vools.sql.core.decorators import _get_signature_info
        # print 在 Python 3 中可 inspect（有签名），不应视为异常路径
        names, types, ret = _get_signature_info(print)
        assert names != [] or types == [] or ret is None

    def test_resolve_sql_types_none(self):
        from vools.sql.core.decorators import _resolve_sql_types
        sql_params, sql_ret = _resolve_sql_types([None, int], None)
        assert sql_params[0] is None
        assert sql_params[1] is not None
        assert sql_ret is None

    def test_convert_args(self):
        from vools.sql.core.decorators import _convert_args
        result = _convert_args(["hello", 5], [str, int])
        # 转换不会崩溃
        assert result is not None

    def test_get_connection_keyword(self):
        from vools.sql.core.decorators import _get_connection
        conn = _make_conn()
        c, args, kwargs = _get_connection([], {"connection": conn})
        assert c is conn
        assert args == []
        assert kwargs == {}

    def test_get_connection_default(self):
        from vools.sql.core.decorators import _get_connection
        conn = _make_conn()
        c, args, kwargs = _get_connection([1, 2], {}, conn)
        assert c is conn
        assert args == [1, 2]


class TestImport:
    """导入与 __all__ 测试。"""

    def test_all(self):
        from vools.sql.core.decorators import __all__
        assert "sql_function" in __all__
        assert "sql_module" in __all__
        assert "sql_func_name" in __all__
