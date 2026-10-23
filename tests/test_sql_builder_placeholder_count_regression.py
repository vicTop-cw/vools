# -*- coding: utf-8 -*-
"""回归测试：SQL builder 占位符与参数数量一致性校验（BUG-351）。

`BaseSqlBuilder.where('a = ? AND b = ?', 1)` 原实现静默产出
「2 个占位符 + 1 个参数」的 SQL，直到真正执行时才由 DB 驱动报错
（例如 sqlite3: Incorrect number of bindings supplied），错误信息不含条件文本，
定位困难；参数过多同样静默通过。

修复：`_collect_condition_params` 在 build 期按**引号感知**方式统计占位符，
与参数个数不一致时抛 ValueError（含条件、占位符数、参数数）。

计数与替换共用 `_sub_placeholders`，因此 SQL 字面量里的 `?` / `%s`
（如 `note = 'why?'`）不会被误计。
"""

import pytest

from vools.sql.core.builder import BaseSqlBuilder


class TestMatchingCounts:
    def test_single(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('a = ?', 1).build())
        assert sql == 'SELECT * FROM t WHERE a = %s'
        assert params == (1,)

    def test_multiple(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('a=? AND b=?', 1, 2).build())
        assert sql.count('%s') == 2
        assert params == (1, 2)

    def test_pyformat_style(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('a = %s', 1).build())
        assert params == (1,)

    def test_no_placeholder_no_params(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('a = 1').build())
        assert sql == 'SELECT * FROM t WHERE a = 1'
        assert params == ()

    def test_quoted_question_mark_not_counted(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("n = ? AND m = 'why?'", 'x').build())
        assert sql.count('%s') == 1
        assert params == ('x',)

    def test_quoted_percent_s_not_counted(self):
        # 引号内的 %s 属于字面量：build 成功即证明计数未把它算进去
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where("n = ? AND m = '%s-ish'", 'x').build())
        assert params == ('x',)
        assert "'%s-ish'" in sql


class TestMismatchesRejected:
    def test_fewer_params_than_placeholders(self):
        builder = (BaseSqlBuilder().select('*').from_('t')
                   .where('a = ? AND b = ?', 1))
        with pytest.raises(ValueError) as ei:
            builder.build()
        msg = str(ei.value)
        assert '占位符' in msg and '参数' in msg
        # where() 在调用期已把 ? 规范化为 %s，错误信息里是规范化后的条件
        assert 'a = %s AND b = %s' in msg

    def test_more_params_than_placeholders(self):
        builder = (BaseSqlBuilder().select('*').from_('t')
                   .where('a = ?', 1, 2))
        with pytest.raises(ValueError):
            builder.build()

    def test_params_without_placeholders(self):
        builder = (BaseSqlBuilder().select('*').from_('t')
                   .where('a = 1', 5))
        with pytest.raises(ValueError):
            builder.build()

    def test_having_also_validated(self):
        builder = (BaseSqlBuilder().select('a').from_('t')
                   .group_by('a').having('count(*) > ?'))
        with pytest.raises(ValueError):
            builder.build()

    def test_error_mentions_counts(self):
        builder = (BaseSqlBuilder().select('*').from_('t')
                   .where('a = ? AND b = ?', 7))
        with pytest.raises(ValueError) as ei:
            builder.build()
        assert '2' in str(ei.value) and '1' in str(ei.value)


class TestOtherStatementsUnaffected:
    def test_insert(self):
        sql, params = (BaseSqlBuilder().insert_into('t')
                       .values(a=1, b='x').build())
        assert sql == 'INSERT INTO t (a, b) VALUES (%s, %s)'
        assert params == (1, 'x')

    def test_update_with_where(self):
        sql, params = (BaseSqlBuilder().update('t').set_(a=2)
                       .where('id = ?', 5).build())
        assert sql == 'UPDATE t SET a = %s WHERE id = %s'
        assert params == (2, 5)

    def test_delete_with_where(self):
        sql, params = (BaseSqlBuilder().delete_from('t')
                       .where('id = ?', 7).build())
        assert sql == 'DELETE FROM t WHERE id = %s'
        assert params == (7,)

    def test_chained_and_or(self):
        sql, params = (BaseSqlBuilder().select('*').from_('t')
                       .where('a = ?', 1).and_('b > ?', 2).or_('c < ?', 3).build())
        assert params == (1, 2, 3)