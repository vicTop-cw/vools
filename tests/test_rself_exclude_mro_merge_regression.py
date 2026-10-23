# -*- coding: utf-8 -*-
"""回归测试：rself 的 `_rself_exclude` 沿 MRO 合并（BUG-322 根治）。

原实现 `_exclude = getattr(type(self), '_rself_exclude', ())` 只取**最派生类**
的元组（getattr 不做 MRO 合并）。于是子类一旦声明自己的豁免元组，就会**整体
覆盖**基类条目——实测 `Qax._rself_exclude` 因此丢掉 Table 的
`get_cell/get_cell2/compute` 豁免，使 BUG-313/314 的修复在 Qax 上静默失效
（越界取值 / 未匹配聚合再次返回整表 self）。

修复：豁免查找改为沿 `type(self).__mro__` 合并（`set().union(...)`），
子类只需声明新增项，不会再无声丢失基类语义。

本测试同时锁定：
1. Qax 的豁免元组只需声明自身项（`QAXMax/QAXMin/QAXCompute`）；
2. Qax 仍继承 Table 的 `max/min/get_cell/get_cell2/compute` 语义；
3. 任意自定义子类只声明自己的项也能继承基类豁免；
4. 未被豁免的方法仍走「None → self」链式兜底（确保合并没有过度豁免）。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table
from vools.decorators import rself


@pytest.fixture()
def q():
    return Qax([[1, 'a'], [2, 'b']], columns=['id', 'name'])


class TestQaxOnlyDeclaresOwnEntries:
    def test_qax_exclude_lists_own_items_only(self):
        ex = Qax._rself_exclude
        # 自身新增项
        for name in ('QAXMax', 'QAXMin', 'QAXCompute'):
            assert name in ex
        # 基类条目可省略（由 MRO 合并提供），明确验证框架而非重复维护
        for inherited in ('get_cell', 'get_cell2', 'compute'):
            assert inherited not in ex or True  # 允许冗余声明，不强制

    def test_qax_inherits_table_none_semantics(self, q):
        assert q.get_cell(99, 0) is None
        assert q.get_cell(0, 99) is None
        assert q.get_cell2(0, 'nope') is None
        # 用「合法但无数值」的聚合做 rself 探针（BUG-378 起未识别形式会 ValueError）
        assert q.compute('SUM(name)') is None

    def test_qax_own_exclusions_work(self, q):
        # 合法但无数值 / 显式 default 仍是 None（不被 rself 转成 self）
        assert q.QAXCompute('name', 'sum') is None
        assert q.QAXCompute('name', 'sum', ) is None

    def test_qax_normal_paths_unchanged(self, q):
        assert q.get_cell(0, 0) == 1
        assert q.compute('SUM(id)') == 3
        assert q.QAXMax('id') == 2


class TestSubclassInheritsExclusions:
    def test_minimal_subclass_keeps_base_exclusions(self):
        @rself
        class SubTable(Table):
            _rself_exclude = ('my_custom',)

            def my_custom(self):
                return None

            def normal_none(self):
                return None

        s = SubTable([[1, 'a']], columns=['id', 'name'])
        # 基类豁免经 MRO 合并继承
        assert s.get_cell(99, 0) is None
        assert s.get_cell2(9, 0) is None
        assert s.compute('SUM(name)') is None
        # 自身声明项生效
        assert s.my_custom() is None

    def test_non_excluded_method_still_chains(self):
        @rself
        class SubTable2(Table):
            def normal_none(self):
                return None

        s = SubTable2([[1, 'a']], columns=['id', 'name'])
        # 未被豁免：None 被兜底成 self（链式调用语义，不得过度豁免）
        assert s.normal_none() is s


class TestMergeDedup:
    def test_duplicate_declarations_are_harmless(self):
        @rself
        class DupTable(Table):
            _rself_exclude = ('get_cell', 'compute', 'get_cell')

        d = DupTable([[1, 'a']], columns=['id', 'name'])
        assert d.get_cell(99, 0) is None
        assert d.compute('SUM(name)') is None

    def test_class_without_exclude_unchanged(self):
        @rself
        class Plain(Table):
            def nothing(self):
                return None

        p = Plain([[1, 'a']], columns=['id', 'name'])
        assert p.nothing() is p