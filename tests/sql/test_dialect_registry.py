"""tests/sql/test_dialect_registry.py — 方言注册表测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.sql.core.dialect import (
    register_dialect, get_dialect, list_dialects, has_dialect,
)


class TestDialectRegistry:
    """方言注册表测试"""

    def setup_method(self):
        # 确保 sqlite 方言已注册
        if not has_dialect('sqlite'):
            from vools.sql.sqlite.dialect import SqliteDialect
            register_dialect('sqlite', SqliteDialect)

    def test_list_dialects(self):
        dialects = list_dialects()
        assert isinstance(dialects, list)
        assert 'sqlite' in dialects

    def test_has_dialect_sqlite(self):
        assert has_dialect('sqlite') is True

    def test_has_dialect_nonexistent(self):
        assert has_dialect('nonexistent_xyz') is False

    def test_get_dialect_sqlite(self):
        dialect = get_dialect('sqlite')
        assert dialect is not None
        assert dialect.__name__ == 'SqliteDialect'

    def test_get_dialect_nonexistent_raises(self):
        with pytest.raises(KeyError):
            get_dialect('nonexistent_xyz')

    def test_register_custom_dialect(self):
        from vools.sql.core.dialect import Dialect
        from vools.sql.core.types import SqlTypeMapper
        from vools.sql.core.config import DialectConfig

        class CustomDialect(Dialect):
            def __init__(self):
                self._config = DialectConfig(
                    name='custom_test', driver='sqlite3',
                    default_port=0, default_host='', default_user='',
                    default_database=':memory:', paramstyle='qmark',
                    identifier_quote='"', string_quote="'",
                )
            def get_type_mapper(self): return SqlTypeMapper
            def create_connection(self, **kw): pass
            def quote_identifier(self, i): return f'"{i}"'
            def quote_string(self, v): return f"'{v}'"
            def get_builder_class(self): return None
            def get_paramstyle(self): return 'qmark'
            def get_config(self): return self._config

        register_dialect('custom_test', CustomDialect)
        assert has_dialect('custom_test') is True
        dialect = get_dialect('custom_test')
        assert dialect.__name__ == 'CustomDialect'
