# -*- coding: utf-8 -*-
"""回归测试：VText.regexp_substr 的 None 契约不被 @rself 吞掉（BUG-220）。

原 `@rself` 的链式兜底把方法返回值 None 转成 self（整条原文）、str 转成
VText——docstring 承诺的「无匹配时 None」永不可判（`is None` 恒 False），
调用方拿到整条原文在错误数据上静默继续链式计算。

修复：VText 声明 `_rself_exclude = ('regexp_substr',)`（BUG-200 官方
逃生门先例），与底层 vools/utils/tools.regexp_substr 契约一致：命中返回
原生 str、未命中返回 None。常规链式方法（regexp_replace/upper 等）不受
影响。
"""

from vools.data.vtext import VText


class TestNoMatchReturnsNone:
    """BUG-220 核心：无匹配信号真实可判。"""

    def test_no_match_is_none(self):
        assert VText("hello world").regexp_substr(r'xyz') is None

    def test_no_match_not_whole_string(self):
        # 修复前：返回 VText('hello world')——整条原文伪装成结果
        r = VText("hello world").regexp_substr(r'xyz')
        assert r != "hello world"

    def test_out_of_range_occurrence_is_none(self):
        assert VText("a1b2").regexp_substr(r'\d', occurrence=9) is None


class TestMatchReturnsNativeStr:
    """命中路径与 tools 层契约一致。"""

    def test_hit_value_and_type(self):
        r = VText("abc123").regexp_substr(r'\d+')
        assert r == '123'
        assert type(r) is str

    def test_occurrence(self):
        t = VText("abc123def45")
        assert t.regexp_substr(r'\d+', occurrence=1) == '45'

    def test_negative_occurrence(self):
        t = VText("a1b2c3")
        assert t.regexp_substr(r'\d', occurrence=-1) == '3'


class TestChainSemanticsPreserved:
    """其他方法的 @rself 链式兜底不受排除影响（防修复过度）。"""

    def test_regexp_replace_still_vtext(self):
        assert isinstance(VText("abc").regexp_replace('b', 'X'), VText)

    def test_upper_still_vtext(self):
        assert isinstance(VText("abc").upper(), VText)

    def test_regexp_instr_minus_one_kept(self):
        # int 不触发 None→self，同族行为保持
        assert VText("hello").regexp_instr(r'xyz') == -1

    def test_result_property_unchanged(self):
        # BUG-206 的 result 语义保持
        t = VText('1+1')
        assert t.run('eval') == 2
        assert t.result == 2