# -*- coding: utf-8 -*-
"""回归测试：VList.pop/shift 空弹 None 契约不被 @rself 吞（BUG-221）。

原实现与 docstring 明写「列表为空则返回 None」，但 `@rself` 链式兜底把
方法返回值 None 转成 self——`VList([]).pop()` 返回整条空列表本身，
`is None` 判断永假，调用方把空列表当弹出的元素消费。与 BUG-220
（VText.regexp_substr）同族。

修复：VList 声明 `_rself_exclude = ('pop', 'shift')`（BUG-200/220 官方
逃生门先例），弹出语义对齐内置 list：空列表 None、非空原始元素。
"""

from vools.data.vlist import VList


class TestEmptyPopReturnsNone:
    """BUG-221 核心：空列表弹出信号真实可判。"""

    def test_empty_pop_is_none(self):
        assert VList([]).pop() is None

    def test_empty_shift_is_none(self):
        assert VList([]).shift() is None

    def test_exhaust_then_pop_is_none(self):
        v = VList([7])
        assert v.pop() == 7
        assert v.pop() is None          # 弹尽后也是 None 而非空 VList


class TestPopReturnsNativeElement:
    """非空路径返回原始元素（不被包装）。"""

    def test_pop_last(self):
        v = VList([1, 2, 3])
        assert v.pop() == 3
        assert v.collect() == [1, 2]

    def test_shift_first(self):
        w = VList(['a', 'b'])
        assert w.shift() == 'a'
        assert w.collect() == ['b']

    def test_nested_list_element_not_wrapped(self):
        x = VList([[1, 2], [3, 4]])
        p = x.pop()
        assert p == [3, 4]
        assert type(p) is list          # 弹出的是元素不是集合——不应转 VList


class TestChainSemanticsPreserved:
    """其他方法的 @rself 链式语义不受排除影响（防修复过度）。"""

    def test_sorted_returns_vlist(self):
        assert isinstance(VList([3, 1, 2]).sorted(), VList)

    def test_add_returns_vlist(self):
        assert isinstance(VList([1]).add(2), VList)

    def test_unshift_returns_self(self):
        u = VList([2]).unshift(1)
        assert isinstance(u, VList)
        assert u.collect() == [1, 2]

    def test_property_intact(self):
        # BUG-17 的 property 保护（None 不转 self）+ size property 照常
        v = VList([5])
        assert v.size == 1