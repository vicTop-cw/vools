# -*- coding: utf-8 -*-
"""回归测试：@sql_function 的 List[标量] 返回类型（BUG-463）。

修复前 ``_convert_result`` 对任何 ``List[...]`` 一律返回 ``list[dict]``：

    @sql_function(connection=conn)
    def ids() -> typing.List[int]:
        return "SELECT id FROM t ORDER BY id"

    ids()   # 修复前 -> [{'id': 1}, {'id': 2}]   ← 注解被静默违背
            # 修复后 -> [1, 2]

``List[dict]`` / ``List[Row]`` / ``List[Any]`` / 裸 ``list`` 语义保持不变。
"""

import typing

from vools.sql.core.decorators import sql_function
from vools.sql.core.result import ResultSet, Row
from vools.sql.sqlite.dialect import SqliteDialect


def _conn():
    c = SqliteDialect().create_connection(database=":memory:")
    c.connect()
    c.execute("CREATE TABLE t (id INTEGER, name TEXT, score REAL)")
    c.executemany("INSERT INTO t VALUES (?, ?, ?)",
                  [(1, "a", 1.5), (2, "b", 2.5)])
    c.commit()
    return c


class TestListScalar:
    def test_list_int(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def ids() -> typing.List[int]:
                return "SELECT id FROM t ORDER BY id"

            assert ids() == [1, 2]
        finally:
            conn.close()

    def test_list_str(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def names() -> typing.List[str]:
                return "SELECT name FROM t ORDER BY id"

            assert names() == ["a", "b"]
        finally:
            conn.close()

    def test_list_float(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def scores() -> typing.List[float]:
                return "SELECT score FROM t ORDER BY id"

            assert scores() == [1.5, 2.5]
        finally:
            conn.close()

    def test_list_optional_int(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def ids() -> typing.List[typing.Optional[int]]:
                return "SELECT id FROM t ORDER BY id"

            assert ids() == [1, 2]
        finally:
            conn.close()

    def test_list_scalar_empty_result(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def ids() -> typing.List[int]:
                return "SELECT id FROM t WHERE id > 99"

            assert ids() == []
        finally:
            conn.close()


class TestExistingListSemanticsUnchanged:
    def test_list_dict(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def rows() -> typing.List[dict]:
                return "SELECT id, name FROM t ORDER BY id"

            assert rows() == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        finally:
            conn.close()

    def test_list_row(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def rows() -> typing.List[Row]:
                return "SELECT id FROM t ORDER BY id"

            result = rows()
            assert all(isinstance(r, Row) for r in result)
        finally:
            conn.close()

    def test_list_any(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def rows() -> typing.List[typing.Any]:
                return "SELECT id FROM t ORDER BY id"

            assert rows() == [{"id": 1}, {"id": 2}]
        finally:
            conn.close()

    def test_bare_list(self):
        conn = _conn()
        try:
            @sql_function(connection=conn)
            def rows() -> list:
                return "SELECT id FROM t ORDER BY id"

            assert rows() == [{"id": 1}, {"id": 2}]
        finally:
            conn.close()


class TestAutoConvertFalse:
    def test_returns_raw_resultset(self):
        conn = _conn()
        try:
            @sql_function(connection=conn, auto_convert=False)
            def raw() -> typing.List[int]:
                return "SELECT id FROM t ORDER BY id"

            result = raw()
            assert isinstance(result, ResultSet)
        finally:
            conn.close()
