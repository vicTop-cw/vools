"""tests/sql/test_sqlite_dialect.py — SQLite 方言测试"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.sql.sqlite.dialect import SqliteDialect


class TestSqliteDialect:
    """SqliteDialect 测试"""

    @pytest.fixture
    def dialect(self):
        return SqliteDialect()

    def test_is_available(self, dialect):
        assert dialect.is_available() is True

    def test_get_paramstyle(self, dialect):
        assert dialect.get_paramstyle() == 'qmark'

    def test_quote_identifier(self, dialect):
        assert dialect.quote_identifier('users') == '"users"'

    def test_quote_identifier_with_special(self, dialect):
        result = dialect.quote_identifier('table"name')
        assert '""' in result  # 双引号转义

    def test_quote_string(self, dialect):
        assert dialect.quote_string("hello") == "'hello'"

    def test_quote_string_with_quote(self, dialect):
        result = dialect.quote_string("it's")
        assert "''" in result  # 单引号转义

    def test_get_config(self, dialect):
        config = dialect.get_config()
        assert config.name == 'sqlite'
        assert config.driver == 'sqlite3'

    def test_get_type_mapper(self, dialect):
        from vools.sql.core.types import SqlTypeMapper
        mapper = dialect.get_type_mapper()
        assert mapper is SqlTypeMapper or isinstance(mapper, SqlTypeMapper)

    def test_get_builder_class(self, dialect):
        from vools.sql.core.builder import BaseSqlBuilder
        assert dialect.get_builder_class() == BaseSqlBuilder

    def test_create_connection(self, dialect):
        conn = dialect.create_connection(database=':memory:')
        assert conn is not None

    def test_connection_execute(self, dialect):
        conn = dialect.create_connection(database=':memory:')
        conn.connect()
        conn.execute('CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute('INSERT INTO test (name) VALUES (?)', ('Alice',))
        result = conn.execute('SELECT * FROM test')
        rows = result.fetchall()
        assert len(rows) == 1
        conn.close()

    def test_connection_context_manager(self, dialect):
        conn = dialect.create_connection(database=':memory:')
        with conn:
            conn.execute('CREATE TABLE t (id INTEGER)')
        # 无异常即通过

    def test_integration_select(self, dialect):
        conn = dialect.create_connection(database=':memory:')
        conn.connect()
        conn.execute('CREATE TABLE users (id INTEGER, name TEXT)')
        conn.execute('INSERT INTO users VALUES (?, ?)', (1, 'Alice'))
        conn.execute('INSERT INTO users VALUES (?, ?)', (2, 'Bob'))
        result = conn.execute('SELECT * FROM users WHERE id = ?', (1,))
        row = result.fetchone()
        assert row[0] == 1
        assert row[1] == 'Alice'
        conn.close()

    def test_builder_integration(self, dialect):
        builder_class = dialect.get_builder_class()
        builder = builder_class()
        builder._paramstyle = dialect.get_paramstyle()
        sql, params = builder.select('*').from_('users').where('id = ?', 1).build()
        assert 'SELECT * FROM users' in sql
        assert '?' in sql

    def test_quote_identifier_empty(self, dialect):
        result = dialect.quote_identifier('')
        assert result == '""'

    def test_quote_string_empty(self, dialect):
        result = dialect.quote_string('')
        assert result == "''"
