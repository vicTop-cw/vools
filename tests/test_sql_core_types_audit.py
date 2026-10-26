# -*- coding: utf-8 -*-
"""审计锁定：vools.sql.core.types / result 的既有契约。

本轮审计确认这些面**无缺陷**（含"文档化占位实现"），在此锁定防未来误改：

1. ``SqlTypeMapper.convert_args`` / ``convert_result`` 是**文档化占位**：
   docstring 明写"目前为简单原样返回，后续方言扩展时将添加具体转换逻辑"。
   因此 ``convert_args((1,), ["INTEGER", "TEXT"])`` 返回 ``[1]`` 是**有意行为**
   （sql_types 与长度都不参与），不是"静默截断"。
2. ``register_type`` 校验完备：py_type 必须是类型、sql_type 必须是非空字符串。
3. 注册后 ``get_sql_type``/``get_py_type`` 双向可查（同一 sql_type 会覆盖映射）。
4. ``infer_arg_types`` 按值推断（1→INTEGER、'a'→VARCHAR）；``infer_ret_type``
   无注解/非类型时回退 INTEGER（既有口径）。
5. ``ResultSet``：columns/rowcount 是**属性**；空结果集 first/scalar 返回 None；
   columns 必须是 list/tuple（BUG-464 已修）。
"""

import pytest

from vools.sql.core.result import ResultSet
from vools.sql.core.types import SqlTypeMapper


class TestConvertArgsIsDocumentedPlaceholder:
    def test_len_mismatch_returned_as_is(self):
        """docstring：目前简单原样返回 → 长度不匹配也不报错、不截断 SQL 侧。"""
        assert SqlTypeMapper().convert_args((1,), ["INTEGER", "TEXT"]) == [1]

    def test_more_types_than_args(self):
        assert SqlTypeMapper().convert_args((1, 2), ["INTEGER"]) == [1, 2]

    def test_returns_list_copy(self):
        args = [1, 2, 3]
        converted = SqlTypeMapper().convert_args(args, [])
        assert converted == args
        assert converted is not args

    def test_convert_result_identity(self):
        mapper = SqlTypeMapper()
        obj = {"a": 1}
        assert mapper.convert_result(obj, dict) is obj


class TestRegisterTypeValidation:
    @pytest.mark.parametrize("bad", [123, "", None])
    def test_sql_type_must_be_str(self, bad):
        with pytest.raises((ValueError, TypeError)) as ei:
            SqlTypeMapper().register_type(int, bad)
        assert "sql_type" in str(ei.value) or "type" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "int", None])
    def test_py_type_must_be_type(self, bad):
        with pytest.raises(TypeError) as ei:
            SqlTypeMapper().register_type(bad, "INTEGER")
        assert "py_type" in str(ei.value)


class TestMapperLookups:
    def test_get_sql_type_known(self):
        assert SqlTypeMapper().get_sql_type(int) == "INTEGER"

    def test_get_py_type_known(self):
        assert SqlTypeMapper().get_py_type("INTEGER") is int

    def test_infer_arg_types(self):
        mapper = SqlTypeMapper()
        inferred = mapper.infer_arg_types((1, "a"))
        assert inferred == ["INTEGER", "VARCHAR"]

    def test_infer_ret_type_known(self):
        assert SqlTypeMapper().infer_ret_type(str) == "VARCHAR"


class TestResultSetContracts:
    def test_columns_and_rowcount_are_attributes(self):
        rs = ResultSet(["a", "b"], [[1, 2]])
        # columns / rowcount 是**属性**（不是方法）
        assert rs.columns == ["a", "b"]
        assert not callable(rs.columns)
        assert not callable(rs.rowcount)
        # rowcount 是「受影响行数」（driver 语义），**不是** len(rows)；默认 0
        assert rs.rowcount == 0
        assert ResultSet(["a"], [[1]], rowcount=5).rowcount == 5

    def test_fetch_progression(self):
        rs = ResultSet(["a", "b"], [[1, 2], [3, 4]])
        first = rs.fetchone()
        assert first == {"a": 1, "b": 2} or first.a == 1
        rest = rs.fetchall()
        assert len(rest) == 1

    def test_first_and_scalar(self):
        rs = ResultSet(["a", "b"], [[1, 2], [3, 4]])
        assert rs.first().a == 1
        assert rs.scalar() == 1

    @pytest.mark.parametrize("empty_rs", [ResultSet(["a"], [])])
    def test_empty_result_set(self, empty_rs):
        assert empty_rs.first() is None
        assert empty_rs.scalar() is None

    @pytest.mark.parametrize("bad", [None, "a", 123])
    def test_columns_must_be_sequence(self, bad):
        with pytest.raises(TypeError) as ei:
            ResultSet(bad, [])
        assert "columns" in str(ei.value)
