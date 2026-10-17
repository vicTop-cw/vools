# -*- coding: utf-8 -*-
"""测试 vools.sql.core.result — Row / ResultSet。"""

import pytest

from vools.sql.core.result import Row, ResultSet

__all__ = ["TestRow", "TestResultSet", "TestImport"]


class TestRow:
    """Row 行为测试。"""

    def _row(self):
        return Row(["id", "name"], (1, "Alice"))

    def test_init(self):
        r = self._row()
        assert r._columns == ["id", "name"]
        assert r._values == (1, "Alice")

    def test_getitem_by_name(self):
        r = self._row()
        assert r["id"] == 1
        assert r["name"] == "Alice"

    def test_getitem_by_index(self):
        r = self._row()
        assert r[0] == 1
        assert r[1] == "Alice"

    def test_getitem_by_slice(self):
        r = self._row()
        assert r[0:1] == (1,)

    def test_getitem_key_error(self):
        r = self._row()
        with pytest.raises(KeyError, match="Column 'nope' not found"):
            r["nope"]

    def test_getitem_bad_type(self):
        r = self._row()
        with pytest.raises(TypeError):
            r[object()]

    def test_getattr(self):
        r = self._row()
        assert r.id == 1
        assert r.name == "Alice"

    def test_getattr_error(self):
        r = self._row()
        with pytest.raises(AttributeError):
            r.nonexistent

    def test_setattr_immutable(self):
        r = self._row()
        with pytest.raises(AttributeError, match="immutable"):
            r.id = 99

    def test_iter(self):
        r = self._row()
        assert list(r) == [1, "Alice"]

    def test_len(self):
        r = self._row()
        assert len(r) == 2

    def test_contains(self):
        r = self._row()
        assert "id" in r
        assert "nope" not in r

    def test_eq(self):
        r1 = self._row()
        r2 = Row(["id", "name"], (1, "Alice"))
        assert r1 == r2
        assert r1 != "not a row"
        r3 = Row(["id", "name"], (2, "Alice"))
        assert r1 != r3

    def test_repr(self):
        r = self._row()
        assert "id=1" in repr(r)
        assert "name='Alice'" in repr(r)

    def test_keys(self):
        r = self._row()
        assert r.keys() == ["id", "name"]

    def test_values(self):
        r = self._row()
        assert r.values() == (1, "Alice")

    def test_items(self):
        r = self._row()
        assert r.items() == [("id", 1), ("name", "Alice")]

    def test_as_dict(self):
        r = self._row()
        assert r.as_dict() == {"id": 1, "name": "Alice"}

    def test_get(self):
        r = self._row()
        assert r.get("id") == 1
        assert r.get("nope", "default") == "default"


class TestResultSet:
    """ResultSet 行为测试。"""

    def _rs(self):
        return ResultSet(
            columns=["id", "name"],
            rows=[(1, "Alice"), (2, "Bob"), (3, "Carol")],
            rowcount=3,
        )

    def test_init_empty(self):
        rs = ResultSet(["a", "b"])
        assert len(rs) == 0
        assert rs._rows == []

    def test_init_with_rows(self):
        rs = ResultSet(["a"], [(1,), (2,)])
        assert len(rs) == 2
        assert rs[0].a == 1

    def test_iter(self):
        rs = self._rs()
        assert len(list(rs)) == 3

    def test_len(self):
        rs = self._rs()
        assert len(rs) == 3

    def test_getitem(self):
        rs = self._rs()
        assert rs[0].name == "Alice"
        assert rs[-1].name == "Carol"

    def test_getitem_slice(self):
        rs = self._rs()
        slice_rows = rs[0:2]
        assert len(slice_rows) == 2

    def test_contains(self):
        rs = self._rs()
        assert Row(["id", "name"], (1, "Alice")) in rs
        assert Row(["id", "name"], (99, "Nobody")) not in rs

    def test_repr(self):
        rs = self._rs()
        assert "columns=" in repr(rs)
        assert "rows=3" in repr(rs)

    def test_columns_property(self):
        rs = self._rs()
        assert rs.columns == ["id", "name"]

    def test_rowcount_property(self):
        rs = self._rs()
        assert rs.rowcount == 3
        rs2 = ResultSet(["a"])
        assert rs2.rowcount == 0

    def test_fetchone(self):
        rs = self._rs()
        r = rs.fetchone()
        assert r.name == "Alice"
        assert rs.fetchone().name == "Bob"
        assert rs.fetchone().name == "Carol"
        assert rs.fetchone() is None

    def test_fetchmany_default(self):
        rs = self._rs()
        rows = rs.fetchmany()
        assert len(rows) == 1
        assert rows[0].name == "Alice"

    def test_fetchmany_size(self):
        rs = self._rs()
        rows = rs.fetchmany(2)
        assert len(rows) == 2

    def test_fetchmany_zero(self):
        rs = self._rs()
        assert rs.fetchmany(0) == []

    def test_fetchall(self):
        rs = self._rs()
        rows = rs.fetchall()
        assert len(rows) == 3
        assert rs.fetchall() == []  # 游标已到末尾

    def test_first(self):
        rs = self._rs()
        assert rs.first().name == "Alice"

    def test_first_empty(self):
        rs = ResultSet(["a"])
        assert rs.first() is None

    def test_scalar(self):
        rs = self._rs()
        assert rs.scalar() == 1

    def test_scalar_empty(self):
        rs = ResultSet(["a"])
        assert rs.scalar() is None

    def test_to_list(self):
        rs = self._rs()
        assert rs.to_list() == [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Carol"},
        ]

    def test_to_dataframe(self):
        rs = self._rs()
        df = rs.to_dataframe()
        assert len(df) == 3
        assert list(df.columns) == ["id", "name"]

    def test_reset_cursor(self):
        rs = self._rs()
        rs.fetchone()
        rs.fetchone()
        rs.reset_cursor()
        assert rs.fetchone().name == "Alice"

    def test_bool(self):
        rs = self._rs()
        assert bool(rs) is True
        empty = ResultSet(["a"])
        assert bool(empty) is False


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sql.core.result import __all__
        assert "Row" in __all__
        assert "ResultSet" in __all__
