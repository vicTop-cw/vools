# -*- coding: utf-8 -*-
"""回归测试：QaxGroup 未知聚合方法显式报错（BUG-284）。

原实现在 `agg_spec` 的聚合方法名不匹配任何已知分支时走 `else: row.append(None)`，
静默产出整列 None：`QaxGroup('g', {'v': 'avgg'})`（拼错）与
`{'v': 'unknown'}` 都不报错，调用方无法区分「聚合结果为空」与「方法名写错」。
与 BUG-129（regexp_split 静默返回 None → 显式 ValueError）同形。

修复：else 分支改抛 ValueError，消息列出支持集合
（sum/avg/mean/count/min/max 或可调用对象），docstring 同步更新。
"""

import pytest

from vools.data.qax import Qax


def _mk():
    return Qax([[1, 'a', 10], [1, 'b', 20], [2, 'c', 30]],
               columns=['g', 'name', 'v'])


class TestSupportedAggregations:
    def test_sum(self):
        r = _mk().QaxGroup('g', {'v': 'sum'})
        assert r.QAXToArray(include_fields=False) == [[1, 30], [2, 30]]

    def test_avg_and_mean(self):
        for name in ('avg', 'mean'):
            r = _mk().QaxGroup('g', {'v': name})
            assert r.QAXToArray(include_fields=False) == [[1, 15.0], [2, 30.0]]

    def test_count(self):
        r = _mk().QaxGroup('g', {'v': 'count'})
        assert r.QAXToArray(include_fields=False) == [[1, 2], [2, 1]]

    def test_min_max(self):
        assert _mk().QaxGroup('g', {'v': 'min'}).QAXToArray(include_fields=False) == [[1, 10], [2, 30]]
        assert _mk().QaxGroup('g', {'v': 'max'}).QAXToArray(include_fields=False) == [[1, 20], [2, 30]]

    def test_callable(self):
        r = _mk().QaxGroup('g', {'v': lambda vals: max(vals) - min(vals)})
        assert r.QAXToArray(include_fields=False) == [[1, 10], [2, 0]]

    def test_no_agg_spec(self):
        assert _mk().QaxGroup('g').QAXToArray(include_fields=False) == [[1], [2]]

    def test_multi_group_cols(self):
        assert _mk().QaxGroup(['g', 'name'], {'v': 'sum'}).QAXRows() == 3


class TestUnknownAggregationRaises:
    @pytest.mark.parametrize('bad', ['avgg', 'maxx', 'unknown', 'SUM', 'minn'])
    def test_raises_value_error(self, bad):
        # 修复前：静默产出整列 None
        with pytest.raises(ValueError, match='不支持的聚合方法'):
            _mk().QaxGroup('g', {'v': bad})

    def test_message_lists_supported(self):
        with pytest.raises(ValueError) as ei:
            _mk().QaxGroup('g', {'v': 'nope'})
        msg = str(ei.value)
        for name in ('sum', 'avg', 'mean', 'count', 'min', 'max', '可调用'):
            assert name in msg