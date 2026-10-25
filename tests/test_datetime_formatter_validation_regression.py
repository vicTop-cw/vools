# -*- coding: utf-8 -*-
"""回归测试：EnhancedDateFormatter 模板校验 + parse_date_expression 语义（BUG-481）。

修复前 ``EnhancedDateFormatter(None)`` / ``(123)`` 会在正则替换处抛 cryptic 的
``TypeError: expected string or bytes-like object, got 'NoneType'``。

``DateProcessor.parse_date_expression`` 在两种格式都无法解析时返回 ``None``——
这是**有意行为**（内部 formatter 依赖它判断"不是日期表达式"），但此前未写入
docstring，调用方易误读。本轮只补文档，行为不变；需要"非法即报错"请用
``get_single_date()`` / ``get_date_list()``（它们抛 ValueError）。
"""

import pytest

from vools.datetime.dates_format import DateProcessor, EnhancedDateFormatter


class TestFormatterTemplateValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5, ["tpl"]])
    def test_non_str_template(self, bad):
        with pytest.raises(TypeError) as ei:
            EnhancedDateFormatter(bad)
        assert "template" in str(ei.value)

    def test_valid_template(self):
        f = EnhancedDateFormatter("x={a}")
        f.set(a=1)
        assert f.format() == "x=1"


class TestFormatterSemanticsUnchanged:
    def test_default_run_date_and_variables(self):
        f = EnhancedDateFormatter(
            "商品：{goods}，数量：{len(goods)}，日期：{run_date_std}",
            default_run_date="2026-02-26")
        f.set(goods=["苹果", "香蕉"])
        assert f.format() == "商品：[苹果, 香蕉]，数量：2，日期：2026-02-26"

    def test_missing_placeholder_preserved(self):
        f = EnhancedDateFormatter("a={a}, b={b}")
        assert f.format() == "a={a}, b={b}"
        f.set(a=1)
        assert f.format() == "a=1, b={b}"

    def test_remaining_placeholders(self):
        f = EnhancedDateFormatter("a={a}, b={b}")
        f.set(a=1)
        # get_remaining_placeholders() 返回带花括号的占位符串（如 '['{b}']'）
        assert "{b}" in f.get_remaining_placeholders()

    def test_date_expression(self):
        f = EnhancedDateFormatter("{run_week+3&3}", default_run_date="2024-03-15")
        assert f.format() == "20240403"

    def test_bad_default_run_date_is_loud(self):
        with pytest.raises(ValueError):
            EnhancedDateFormatter("{run_date}", default_run_date="nope")


class TestParseDateExpressionContract:
    def test_single_date_expression(self):
        p = DateProcessor()
        p.set_run_date("2024-03-15")
        assert isinstance(p.parse_date_expression("run_date"), str)

    def test_date_list_expression(self):
        p = DateProcessor()
        p.set_run_date("2024-03-15")
        result = p.parse_date_expression("run_days>2")
        assert isinstance(result, str) and "202403" in result

    def test_invalid_returns_none_documented(self):
        """文档化语义：两种格式都无法解析 → None（内部 formatter 依赖）。"""
        p = DateProcessor()
        assert p.parse_date_expression("nope") is None

    def test_strict_apis_are_loud(self):
        p = DateProcessor()
        with pytest.raises(ValueError):
            p.get_single_date("nope")
        with pytest.raises(ValueError):
            p.get_date_list("nope")
