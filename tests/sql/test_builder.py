"""tests/sql/test_builder.py — SQL 构建器测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.sql.core.builder import BaseSqlBuilder, SqlBuilder


class TestBaseSqlBuilder:
    """BaseSqlBuilder 核心构建测试"""

    def test_select_all(self):
        sql, params = BaseSqlBuilder().select('*').from_('users').build()
        assert sql == 'SELECT * FROM users'
        assert params == ()

    def test_select_columns(self):
        sql, params = BaseSqlBuilder().select('id', 'name', 'email').from_('users').build()
        assert sql == 'SELECT id, name, email FROM users'

    def test_select_with_alias(self):
        sql, params = BaseSqlBuilder().select('id', 'name AS username').from_('users').build()
        assert 'AS username' in sql

    def test_from_multiple_tables(self):
        sql, params = BaseSqlBuilder().select('*').from_('users', 'orders').build()
        assert 'FROM users, orders' in sql

    def test_where_simple(self):
        sql, params = BaseSqlBuilder().select('*').from_('users').where('id = %s', 1).build()
        assert 'WHERE' in sql
        assert 'id =' in sql

    def test_where_with_qmark(self):
        builder = BaseSqlBuilder()
        builder._paramstyle = 'qmark'
        sql, params = builder.select('*').from_('users').where('id = ?', 1).build()
        assert '?' in sql

    def test_where_and(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .where('age > %s', 18)
            .and_('status = %s', 'active')
            .build()
        )
        assert 'AND' in sql

    def test_where_or(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .where('role = %s', 'admin')
            .or_('role = %s', 'moderator')
            .build()
        )
        assert 'OR' in sql

    def test_order_by(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .order_by('name ASC', 'id DESC')
            .build()
        )
        assert 'ORDER BY' in sql
        assert 'name ASC' in sql

    def test_group_by(self):
        sql, params = (
            BaseSqlBuilder()
            .select('department', 'COUNT(*)').from_('employees')
            .group_by('department')
            .build()
        )
        assert 'GROUP BY department' in sql

    def test_having(self):
        sql, params = (
            BaseSqlBuilder()
            .select('department', 'COUNT(*)').from_('employees')
            .group_by('department')
            .having('COUNT(*) > %s', 5)
            .build()
        )
        assert 'HAVING' in sql

    def test_limit(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .limit(10)
            .build()
        )
        assert 'LIMIT' in sql

    def test_offset(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .offset(20)
            .build()
        )
        assert 'OFFSET' in sql

    def test_limit_and_offset(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .limit(10).offset(20)
            .build()
        )
        assert 'LIMIT' in sql
        assert 'OFFSET' in sql

    def test_insert_simple(self):
        sql, params = (
            BaseSqlBuilder()
            .insert_into('users')
            .values(name='Alice', age=30)
            .build()
        )
        assert sql.startswith('INSERT INTO users')
        assert 'VALUES' in sql

    def test_insert_default_values(self):
        sql, params = BaseSqlBuilder().insert_into('users').build()
        assert 'DEFAULT VALUES' in sql

    def test_update_simple(self):
        sql, params = (
            BaseSqlBuilder()
            .update('users')
            .set_(name='Bob')
            .build()
        )
        assert sql.startswith('UPDATE users')
        assert 'SET' in sql

    def test_update_with_where(self):
        sql, params = (
            BaseSqlBuilder()
            .update('users')
            .set_(name='Bob')
            .where('id = %s', 1)
            .build()
        )
        assert 'WHERE' in sql

    def test_delete(self):
        sql, params = (
            BaseSqlBuilder()
            .delete_from('users')
            .where('id = %s', 1)
            .build()
        )
        assert sql.startswith('DELETE FROM users')

    def test_delete_all(self):
        sql, params = BaseSqlBuilder().delete_from('users').build()
        assert sql == 'DELETE FROM users'

    def test_join(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .join('orders', 'users.id = orders.user_id')
            .build()
        )
        assert 'JOIN orders ON' in sql

    def test_left_join(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .left_join('orders', 'users.id = orders.user_id')
            .build()
        )
        assert 'LEFT JOIN' in sql

    def test_inner_join(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .inner_join('orders', 'users.id = orders.user_id')
            .build()
        )
        assert 'INNER JOIN' in sql

    def test_right_join(self):
        sql, params = (
            BaseSqlBuilder()
            .select('*').from_('users')
            .right_join('orders', 'users.id = orders.user_id')
            .build()
        )
        assert 'RIGHT JOIN' in sql

    def test_complex_query(self):
        sql, params = (
            BaseSqlBuilder()
            .select('u.name', 'COUNT(o.id)')
            .from_('users', 'u')
            .left_join('orders o', 'u.id = o.user_id')
            .where('u.active = %s', True)
            .group_by('u.name')
            .having('COUNT(o.id) > %s', 5)
            .order_by('COUNT(o.id) DESC')
            .limit(10)
            .build()
        )
        assert 'SELECT' in sql
        assert 'LEFT JOIN' in sql
        assert 'GROUP BY' in sql
        assert 'ORDER BY' in sql

    def test_reset(self):
        builder = BaseSqlBuilder()
        builder.select('*').from_('users')
        builder._reset()
        assert builder._columns == []
        assert builder._tables == []

    def test_paramstyle_numeric(self):
        builder = BaseSqlBuilder()
        builder._paramstyle = 'numeric'
        assert builder._placeholder(0) == ':1'

    def test_paramstyle_named(self):
        builder = BaseSqlBuilder()
        builder._paramstyle = 'named'
        assert builder._placeholder(0) == ':param_0'

    def test_paramstyle_pyformat(self):
        builder = BaseSqlBuilder()
        builder._paramstyle = 'pyformat'
        assert builder._placeholder(0) == '%s'


class TestSqlBuilderAbstract:
    """SqlBuilder 抽象接口测试"""

    def test_is_abstract(self):
        import abc
        assert hasattr(SqlBuilder, '__abstractmethods__')

    def test_base_implements_all(self):
        builder = BaseSqlBuilder()
        # 验证实现了所有抽象方法
        assert hasattr(builder, 'select')
        assert hasattr(builder, 'from_')
        assert hasattr(builder, 'where')
        assert hasattr(builder, 'build')
