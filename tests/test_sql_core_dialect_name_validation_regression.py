# -*- coding: utf-8 -*-
"""回归测试：sql.core.dialect 的 has_dialect/get_dialect 名称零校验（BUG-520）。

修复前（裸 AttributeError，且与同模块 register_dialect 的校验口径不一致）：

    core.has_dialect(None)     # AttributeError: 'NoneType' object has no attribute 'lower'
    core.has_dialect(123)      # AttributeError: 'int' object has no attribute 'lower'
    core.get_dialect(None)     # 同上
    sq.has_dialect(None)       # 同上（顶层先惰性加载，静默失败后落到 core）

修复后：非空字符串校验前置，统一 ValueError（带类型与实参）。
"""

import importlib

import pytest

import vools.sql as sq
import vools.sql.core.dialect as cd


class TestHasDialectValidation:
    @pytest.mark.parametrize("bad", [None, 123, "", "   "])
    def test_core_has_dialect(self, bad):
        with pytest.raises(ValueError) as ei:
            cd.has_dialect(bad)
        assert "方言名称" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_top_level_has_dialect(self, bad):
        with pytest.raises(ValueError):
            sq.has_dialect(bad)


class TestGetDialectValidation:
    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_core_get_dialect(self, bad):
        with pytest.raises(ValueError) as ei:
            cd.get_dialect(bad)
        assert "方言名称" in str(ei.value)


class TestBehaviourUnchanged:
    def test_has_dialect_builtin(self):
        assert sq.has_dialect("sqlite") is True
        assert cd.has_dialect("sqlite") is True

    def test_has_dialect_unknown(self):
        assert normalised(cd.has_dialect("_bug520_zzz")) is False
        assert sq.has_dialect("_bug520_zzz") is False

    def test_get_dialect_builtin(self):
        assert cd.get_dialect("sqlite").__name__ == "SqliteDialect"
        assert sq.get_dialect("sqlite").__name__ == "SqliteDialect"

    def test_get_dialect_unknown_keyerror(self):
        with pytest.raises(KeyError) as ei:
            cd.get_dialect("_bug520_zzz")
        assert "not registered" in str(ei.value)

    def test_case_insensitive(self):
        assert cd.has_dialect("SQLITE") is True


def normalised(value):
    """has_dialect 返回 bool；这里做恒等归一以便断言。"""
    return value
