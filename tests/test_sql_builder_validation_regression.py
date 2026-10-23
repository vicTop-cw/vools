# -*- coding: utf-8 -*-
"""回归测试：SQL 构建器的非法输入不再生成「语法非法 SQL」（BUG-395）。

`BaseSqlBuilder`（链式 SQL 构建器）对三类输入毫无校验，构造出的 SQL 文本
**本身就是非法/语义错误**，却要到执行阶段才炸（或静默出错）：

1. `join(..., join_type='BOGUS')` → `SELECT * FROM a BOGUS JOIN b ON ...`
2. `where('')` / `having('')` / `and_('')` → `SELECT * FROM t WHERE `（悬空子句）
3. `limit(-1)` / `limit('10')` / `offset(-5)` → `LIMIT %s` 绑定非法值

修复：
- `join_type` 白名单：INNER / LEFT / RIGHT / OUTER / FULL / CROSS（大小写、空白容错）；
- 条件表达式必须是非空字符串（`TypeError` / `ValueError`）；
- `limit` / `offset` 必须是非负 int（`0` 合法，返回空集）。

正常构建（含 BUG-232 引号内占位符保护、参数索引顺序、DML）行为不变。
"""

import pytest

from vools.sql.core.builder import BaseSqlBuilder


def _b():
    return BaseSqlBuilder()


class TestJoinType:
    @pytest.mark.parametrize('bad', ['BOGUS', 'NATURAL', None, 123, ''])
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            _b().select('*').from_('a').join('b', 'a.id = b.aid', join_type=bad)
        assert 'join_type' in str(ei.value)

    @pytest.mark.parametrize('jt,expected', [
        ('INNER', 'INNER JOIN'), ('LEFT', 'LEFT JOIN'), ('RIGHT', 'RIGHT JOIN'),
        ('OUTER', 'OUTER JOIN'), ('FULL', 'FULL JOIN'), ('CROSS', 'CROSS JOIN'),
        (' left ', 'LEFT JOIN'),
    ])
    def test_valid(self, jt, expected):
        sql, _ = _b().select('*').from_('a').join('b', 'a.id = b.aid', join_type=jt).build()
        assert expected in sql

    def test_helpers(self):
        assert 'INNER JOIN' in _b().select('*').from_('a').inner_join('b', '1=1').build()[0]
        assert 'LEFT JOIN' in _b().select('*').from_('a').left_join('b', '1=1').build()[0]
        assert 'RIGHT JOIN' in _b().select('*').from_('a').right_join('b', '1=1').build()[0]


class TestEmptyConditions:
    @pytest.mark.parametrize('method', ['where', 'and_', 'or_', 'having'])
    @pytest.mark.parametrize('cond', ['', '   ', '\t\n'])
    def test_rejected(self, method, cond):
        b = _b().select('*').from_('t')
        with pytest.raises(ValueError) as ei:
            getattr(b, method)(cond)
        assert '不能为空' in str(ei.value)

    @pytest.mark.parametrize('bad', [None, 0, ['a = 1']])
    def test_non_str_rejected(self, bad):
        with pytest.raises(TypeError):
            _b().select('*').from_('t').where(bad)


class TestLimitOffset:
    @pytest.mark.parametrize('bad', [-1, -100])
    def test_negative_rejected(self, bad):
        with pytest.raises(ValueError):
            _b().select('*').from_('t').limit(bad)
        with pytest.raises(ValueError):
            _b().select('*').from_('t').offset(bad)

    @pytest.mark.parametrize('bad', ['10', 1.5, None, True])
    def test_non_int_rejected(self, bad):
        with pytest.raises(TypeError):
            _b().select('*').from_('t').limit(bad)
        with pytest.raises(TypeError):
            _b().select('*').from_('t').offset(bad)

    def test_zero_allowed(self):
        sql, params = _b().select('*').from_('t').limit(0).build()
        assert 'LIMIT' in sql and params == (0,)


class TestNormalBuildUnchanged:
    def test_basic_select(self):
        sql, params = _b().select('id', 'name').from_('users').where('id > ?', 1).build()
        assert sql == 'SELECT id, name FROM users WHERE id > %s'
        assert params == (1,)

    def test_quote_aware_placeholders(self):
        sql, params = (_b().select('*').from_('t')
                       .where("name = 'what?' AND id = ?", 5).build())
        assert "'what?'" in sql and sql.count('%s') == 1
        assert params == (5,)

    def test_param_order(self):
        sql, params = (_b().select('*').from_('t')
                       .where('a = ? AND b = ?', 1, 2).and_('c = ?', 3).build())
        assert sql.count('%s') == 3 and params == (1, 2, 3)

    def test_dml(self):
        i = _b().insert_into('t').values(a=1, b='x').build()
        u = _b().update('t').set_(a=1).where('id = ?', 2).build()
        d = _b().delete_from('t').where('id = ?', 1).build()
        assert i == ('INSERT INTO t (a, b) VALUES (%s, %s)', (1, 'x'))
        assert u == ('UPDATE t SET a = %s WHERE id = %s', (1, 2))
        assert d == ('DELETE FROM t WHERE id = %s', (1,))

    def test_group_having_order(self):
        sql, params = (_b().select('k', 'COUNT(*)').from_('t')
                       .group_by('k').having('COUNT(*) > ?', 1)
                       .order_by('k DESC').limit(10).offset(5).build())
        assert 'GROUP BY k' in sql and 'HAVING COUNT(*) > %s' in sql
        assert 'ORDER BY k DESC' in sql and 'LIMIT %s OFFSET %s' in sql
        assert params == (1, 10, 5)