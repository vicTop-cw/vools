# -*- coding: utf-8 -*-
"""回归测试：SqlTypeMapper 参数校验（BUG-457）。

修复前：

    SqlTypeMapper.register_type(123, 456)   # AttributeError: 'int' object has no attribute 'upper'
    SqlTypeMapper.register_type(int, 123)   # 同上（看不出是哪个参数）
    SqlTypeMapper.get_py_type(123)          # AttributeError
    SqlTypeMapper.register_type(int, '')    # 静默注册空类型 → get_sql_type(int) 返回 ''
                                            # （映射被污染且无提示）

修复后：py_type 必须是类型、sql_type 必须是非空字符串、get_py_type 的
sql_type 必须是字符串，全部带参数名报错；合法路径（大小写不敏感查询、
自定义类型注册、convert_args）不变。
"""

import pytest

from vools.sql import SqlTypeMapper


class CustomType:
    pass


class TestRegisterTypeValidation:
    def test_py_type_must_be_type(self):
        with pytest.raises(TypeError) as ei:
            SqlTypeMapper.register_type(123, "INT")
        assert "py_type" in str(ei.value)

    def test_py_type_str_rejected(self):
        with pytest.raises(TypeError) as ei:
            SqlTypeMapper.register_type("notatype", "X")
        assert "py_type" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, 1.5])
    def test_sql_type_must_be_str(self, bad):
        with pytest.raises(ValueError) as ei:
            SqlTypeMapper.register_type(CustomType, bad)
        assert "sql_type" in str(ei.value)

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_sql_type_must_be_non_empty(self, bad):
        """空串原本会静默污染映射（get_sql_type 返回 ''）。"""
        with pytest.raises(ValueError) as ei:
            SqlTypeMapper.register_type(CustomType, bad)
        assert "sql_type" in str(ei.value)

    def test_empty_registration_does_not_pollute(self):
        before = SqlTypeMapper.get_sql_type(CustomType)
        with pytest.raises(ValueError):
            SqlTypeMapper.register_type(CustomType, "")
        assert SqlTypeMapper.get_sql_type(CustomType) == before


class TestGetPyTypeValidation:
    @pytest.mark.parametrize("bad", [123, None, 1.5, ["INT"]])
    def test_non_str(self, bad):
        with pytest.raises(TypeError) as ei:
            SqlTypeMapper.get_py_type(bad)
        assert "sql_type" in str(ei.value)


class TestValidPaths:
    def test_case_insensitive_lookup(self):
        assert SqlTypeMapper.get_py_type("VARCHAR") is str
        assert SqlTypeMapper.get_py_type("varchar") is str
        assert SqlTypeMapper.get_py_type("VarChar") is str

    def test_unknown_sql_type_returns_none(self):
        assert SqlTypeMapper.get_py_type("NOT_A_REAL_TYPE") is None

    def test_get_sql_type(self):
        assert SqlTypeMapper.get_sql_type(str) == "VARCHAR"
        assert SqlTypeMapper.get_sql_type(dict) == "JSON"
        assert SqlTypeMapper.get_sql_type(CustomType) is None

    def test_register_and_lookup(self):
        mapper = SqlTypeMapper()
        mapper.register_type(CustomType, "CUSTOM")
        assert mapper.get_sql_type(CustomType) == "CUSTOM"
        assert mapper.get_py_type("custom") is CustomType

    def test_convert_args(self):
        assert SqlTypeMapper.convert_args((1, "a"), ["INTEGER", "VARCHAR"]) == [1, "a"]
