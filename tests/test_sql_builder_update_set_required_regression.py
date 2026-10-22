# -*- coding: utf-8 -*-
"""回归测试：SqlBuilder UPDATE 缺 SET 显式报错（BUG-286）。

原 `_build_update` 在未调用 `set_()`（或 `set_()` 无字段）时静默产出非法
SQL `('UPDATE t', ())`——缺 SET 子句在任何数据库都是语法错误，且错误暴露在
execute 端（离构建点远）。`build()` docstring 承诺「组装 SQL 字符串」（可用
语句），故属静默无效产出（与 BUG-284 / BUG-129 同形）。

修复：无更新字段时 raise ValueError 并提示先用 set_(...)。
"""

import pytest

from vools.sql.core.builder import BaseSqlBuilder


class TestUpdateRequiresSet:
    def test_update_without_set_raises(self):
        with pytest.raises(ValueError, match='SET'):
            BaseSqlBuilder().update('t').build()

    def test_update_with_empty_set_raises(self):
        with pytest.raises(ValueError, match='set_'):
            BaseSqlBuilder().update('t').set_().build()

    def test_valid_update(self):
        assert BaseSqlBuilder().update('t').set_(a=1).build() == \
            ('UPDATE t SET a = %s', (1,))

    def test_update_with_where(self):
        assert BaseSqlBuilder().update('t').set_(a=2).where('id = %s', 5).build() == \
            ('UPDATE t SET a = %s WHERE id = %s', (2, 5))

    def test_multi_field_update_param_order(self):
        sql, params = BaseSqlBuilder().update('t').set_(a=1, b=2).build()
        assert sql == 'UPDATE t SET a = %s, b = %s'
        assert params == (1, 2)


class TestOtherStatementsUnchanged:
    def test_insert_empty_values_default_values(self):
        assert BaseSqlBuilder().insert_into('t').build() == \
            ('INSERT INTO t DEFAULT VALUES', ())

    def test_delete(self):
        assert BaseSqlBuilder().delete_from('t').where('id = %s', 5).build() == \
            ('DELETE FROM t WHERE id = %s', (5,))

    def test_select_chain(self):
        assert BaseSqlBuilder().select('*').from_('t').where('a = %s', 1).build() == \
            ('SELECT * FROM t WHERE a = %s', (1,))

    def test_select_without_where(self):
        assert BaseSqlBuilder().select('a', 'b').from_('t').build() == \
            ('SELECT a, b FROM t', ())