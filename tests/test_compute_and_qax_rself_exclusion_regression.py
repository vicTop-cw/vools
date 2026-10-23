# -*- coding: utf-8 -*-
"""回归测试：compute 族错误可诊断（BUG-321）与子类 rself 豁免继承（BUG-322）。

【BUG-321】
A. `Table.compute(<非 str>)` 原直接 `expression.upper()` →
   `AttributeError: 'int' object has no attribute 'upper'`（内部错误掩盖真因）。
   修复：入口 `isinstance(expression, str)` 校验，抛清晰 TypeError。
B. `Qax.QAXCompute(<int>)`（func=None）同样撞 AttributeError，而带 func 的路径
   明确支持 1-based 列号（BUG-178/251）。修复：func=None 时先 `_check_1based`
   解析为列名，越界抛 IndexError。

【BUG-322】
`@rself` 取 `getattr(type(self), '_rself_exclude', ())`，**不做 MRO 合并**；
`Qax._rself_exclude` 原为独立元组，覆盖掉 Table 的
('max','min','get_cell','get_cell2','compute')，使 BUG-313/314 的修复在 Qax
上失效（get_cell 越界、compute 未匹配聚合再次返回整表 self）。
修复：Qax 的豁免元组显式包含基类条目。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


@pytest.fixture()
def t():
    return Table([[1, 'a', 10], [2, 'b', 20]], columns=['id', 'name', 'score'])


@pytest.fixture()
def q():
    return Qax([[1, 'a', 10], [2, 'b', 20]], columns=['id', 'name', 'score'])


# --------------------------------------------------------------------------
# BUG-321 A: Table.compute 非 str 参数 -> 清晰 TypeError
# --------------------------------------------------------------------------
class TestTableComputeTypeCheck:
    @pytest.mark.parametrize('bad', [3, 0, None, ['score'], 1.5])
    def test_non_str_raises_typeerror(self, t, bad):
        with pytest.raises(TypeError, match='expression'):
            t.compute(bad)

    def test_valid_expression_still_works(self, t):
        assert t.compute('SUM(score)') == 30
        assert t.compute('COUNT(id)') == 2

    def test_unmatched_returns_none(self, t):
        assert t.compute('score') is None


# --------------------------------------------------------------------------
# BUG-321 B: Qax.QAXCompute(int) 支持 1-based 列号并校验越界
# --------------------------------------------------------------------------
class TestQaxComputeIntColumn:
    def test_valid_int_resolves_to_column(self, q):
        # 未匹配聚合表达式 -> None（而不是 AttributeError 或整表）
        assert q.QAXCompute(2) is None

    @pytest.mark.parametrize('bad', [0, -1, 99])
    def test_out_of_range_raises_indexerror(self, q, bad):
        with pytest.raises(IndexError):
            q.QAXCompute(bad)

    def test_with_func_still_works(self, q):
        assert q.QAXCompute(3, 'sum') == 30
        assert q.QAXCompute(1, 'sum') == 3


# --------------------------------------------------------------------------
# BUG-322: Qax 继承 Table 的 None 语义（豁免不被覆盖）
# --------------------------------------------------------------------------
class TestQaxInheritsTableExclusions:
    def test_get_cell_out_of_range_none(self, q):
        # 修复前：返回整表 Qax（is_self=True）
        assert q.get_cell(99, 0) is None
        assert q.get_cell(0, 99) is None

    def test_get_cell2_unknown_column_none(self, q):
        assert q.get_cell2(0, 'nope') is None

    def test_compute_unmatched_none(self, q):
        assert q.compute('BOGUS(x)') is None

    def test_qax_compute_unmatched_none(self, q):
        assert q.QAXCompute('BOGUS(x)') is None
        assert q.QAXCompute('score') is None

    def test_normal_paths_unchanged(self, q):
        assert q.get_cell(0, 0) == 1
        assert q.compute('SUM(id)') == 3
        assert q.QAXMax('id') == 2

    def test_qax_exclude_contains_base_entries(self):
        ex = Qax._rself_exclude
        for name in ('max', 'min', 'get_cell', 'get_cell2', 'compute'):
            assert name in ex, f'Qax._rself_exclude 缺少基类条目 {name}'
        for name in ('QAXMax', 'QAXMin', 'QAXCompute'):
            assert name in ex

    def test_table_exclusions_unchanged(self, t):
        assert t.get_cell(99, 0) is None
        assert t.get_cell2('nope', 0) is None
        assert t.compute('BOGUS(x)') is None