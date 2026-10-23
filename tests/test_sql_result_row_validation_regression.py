# -*- coding: utf-8 -*-
"""回归测试：Row 构造期的一致性校验（BUG-350）。

`Row.__init__` 原实现只做两次 `object.__setattr__`，**不校验列数与值数是否相等**：

    Row(['a', 'b'], (1,))       # 静默构造成功
    r['b']                      # -> IndexError（不是清楚的"列不存在/数据不一致"）
    r.as_dict()                 # -> 只有 a，与 keys() 声称的两列不符

即「坏行」可以被创建并传播到 ResultSet，直到下游访问才以难懂的错误炸开。

修复：构造期校验长度，并统一把 values 规范化为 tuple（类型契约）。
`ResultSet(columns, rows)` 构造坏行同样立即报错。
"""

import pytest

from vools.sql.core.result import ResultSet, Row


class TestRowValidation:
    def test_valid_row(self):
        r = Row(['id', 'name'], (1, 'a'))
        assert r.as_dict() == {'id': 1, 'name': 'a'}

    def test_list_values_normalized_to_tuple(self):
        r = Row(['a'], [1])
        assert isinstance(r.values(), tuple)

    def test_fewer_values_than_columns(self):
        with pytest.raises(ValueError) as ei:
            Row(['a', 'b'], (1,))
        msg = str(ei.value)
        assert '列数' in msg and '值数' in msg

    def test_more_values_than_columns(self):
        with pytest.raises(ValueError):
            Row(['a'], (1, 2))

    def test_empty_row_allowed(self):
        assert len(Row([], ())) == 0

    def test_matching_lengths_still_work(self):
        r = Row(['a', 'b'], (1, 2))
        assert (r['a'], r['b'], r[1]) == (1, 2, 2)


class TestResultSetPropagation:
    def test_good_rows(self):
        rs = ResultSet(['x', 'y'], [(1, 2), (3, 4)])
        assert rs.to_list() == [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}]

    def test_bad_row_rejected(self):
        # 修复前：静默构造出列数不符的 Row
        with pytest.raises(ValueError):
            ResultSet(['x', 'y'], [(1,)])


class TestExistingBehaviourUnchanged:
    def test_access_modes(self):
        r = Row(['id', 'name'], (1, 'a'))
        assert r['id'] == 1
        assert r[0] == 1
        assert r.name == 'a'
        assert list(r) == [1, 'a']
        assert 'id' in r
        assert r.get('zzz', 9) == 9
        assert r.items() == [('id', 1), ('name', 'a')]

    def test_immutable(self):
        r = Row(['id'], (1,))
        with pytest.raises(AttributeError):
            r.id = 2

    def test_unknown_column(self):
        r = Row(['id'], (1,))
        with pytest.raises(KeyError):
            r['nope']