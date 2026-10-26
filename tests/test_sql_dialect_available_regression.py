# -*- coding: utf-8 -*-
"""回归测试：方言注册的默认 driver 被覆盖成方言名，is_available 恒 False（BUG-519）。"""

import importlib

import pytest

import vools.sql as sq

mod = importlib.import_module("vools.sql.manager")
manager = mod.manager


def _fresh_registry():
    """把内置方言重新注册一遍（清掉可能被别的测试改过的配置）。"""
    from vools.sql.sqlite.dialect import SqliteDialect

    manager.register("sqlite", SqliteDialect)


class TestDefaultConfigUsesDialectDriver:
    def test_sqlite_available(self):
        assert sq.is_available("sqlite") is True

    def test_unknown_dialect_false(self):
        assert sq.is_available("_bug519_zzz") is False

    def test_sqlite_config_driver_is_sqlite3(self):
        sq.get_dialect("sqlite")              # 触发惰性注册
        cfg = manager._configs["sqlite"]
        assert cfg.driver == "sqlite3"        # 不是 'sqlite'

    def test_sqlite_config_keeps_dialect_defaults(self):
        sq.get_dialect("sqlite")
        cfg = manager._configs["sqlite"]
        # 方言自己声明的默认值必须保留（原实现会落成 DialectConfig 平台默认）
        assert cfg.default_database == ":memory:"
        assert cfg.paramstyle == "qmark"

    def test_fallback_when_no_get_config(self):
        class _NoConfig:
            pass

        manager.register("_bug519_nocfg", _NoConfig)
        try:
            # 无 get_config → 退回旧行为（driver=方言名），不抛错
            assert manager._configs["_bug519_nocfg"].driver == "_bug519_nocfg"
        finally:
            manager.unregister("_bug519_nocfg")


class TestNameValidationUnchanged:
    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_is_available_name(self, bad):
        with pytest.raises(ValueError):
            sq.is_available(bad)


class TestDialectAccessUnchanged:
    def test_get_dialect(self):
        assert sq.get_dialect("sqlite").__name__ == "SqliteDialect"

    def test_create_dialect(self):
        assert sq.create_dialect("sqlite").__class__.__name__ == "SqliteDialect"

    def test_list_dialects_contains_sqlite(self):
        assert "sqlite" in list(sq.list_dialects())
