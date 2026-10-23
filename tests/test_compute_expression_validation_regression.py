# -*- coding: utf-8 -*-
"""回归测试：compute 聚合表达式显式校验（BUG-378）。

`Table.compute` / `Qax.QAXCompute` 对**未识别的聚合表达式**原先静默返回
`default_value`（默认 `None`）：

    table.compute('SUMM(v)')        # -> None（函数名拼错毫无提示）
    table.compute('v')              # -> None（裸列名不是聚合形式）
    table.compute('max(v)-min(v)')  # -> KeyError: 'v)-min(v'（难以理解）
    QAXCompute('v', 'nope')         # -> None

而同类的 `QaxGroup(agg_spec)` 对不支持的聚合方法明确 `ValueError`（BUG-284），
口径不一致。

修复：
- 未识别的聚合形式 → `ValueError`（列出 SUM/AVG/COUNT/MAX/MIN 与单列示例）；
- 形如 `max(v)-min(v)` 的**列间运算** → 明确"只支持单列名"的 ValueError；
- 列不存在 → `KeyError`，错误信息带表达式上下文；
- "匹配但无数值 → default_value" 的既有语义保留；
- 原 docstring 示例 `SUM(price * quantity)` 实际不可用（列查找 KeyError），
  一并修正为单列示例。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


@pytest.fixture()
def table():
    return Table([[1, 'a', 30], [2, 'b', 10], [1, 'c', 20]],
                 columns=['id', 'name', 'v'])


class TestValidAggregations:
    @pytest.mark.parametrize('expr,expected', [
        ('SUM(v)', 60), ('avg(v)', 20.0), ('COUNT(name)', 3),
        ('MAX(v)', 30), ('MIN(v)', 10),
    ])
    def test_aggregates(self, table, expr, expected):
        assert table.compute(expr) == expected

    def test_filter_expr(self, table):
        assert table.compute('SUM(v)', filter_expr='id > 1') == 10

    def test_default_value_when_no_numeric(self, table):
        assert table.compute('SUM(name)') is None
        assert table.compute('SUM(name)', default_value=-1) == -1


class TestUnrecognizedExpression:
    @pytest.mark.parametrize('expr', ['SUMM(v)', 'v', 'score', 'AVG'])
    def test_raises_value_error(self, table, expr):
        # 修复前：静默返回 default_value(None)
        with pytest.raises(ValueError) as ei:
            table.compute(expr)
        assert '无法识别' in str(ei.value) or '不支持' in str(ei.value)

    def test_column_arithmetic_message(self, table):
        # 修复前：KeyError: 'v)-min(v'
        with pytest.raises(ValueError) as ei:
            table.compute('max(v)-min(v)')
        assert '单列' in str(ei.value)

    def test_missing_column_context(self, table):
        with pytest.raises(KeyError) as ei:
            table.compute('SUM(nope)')
        msg = str(ei.value)
        assert 'nope' in msg and 'compute' in msg


class TestQaxComputeInherits:
    @pytest.fixture()
    def qax(self):
        return Qax([[1, 'a', 30], [2, 'b', 10]], columns=['id', 'name', 'v'])

    def test_func_name(self, qax):
        assert qax.QAXCompute('v', 'sum') == 40

    def test_one_based_index(self, qax):
        assert qax.QAXCompute(3, 'sum') == 40

    def test_expression_form(self, qax):
        assert qax.QAXCompute('sum(v)') == 40

    def test_bad_func_raises(self, qax):
        # 修复前：静默 None
        with pytest.raises(ValueError):
            qax.QAXCompute('v', 'nope')

    def test_out_of_range_index(self, qax):
        with pytest.raises(IndexError):
            qax.QAXCompute(99, 'sum')