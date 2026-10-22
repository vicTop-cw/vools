# -*- coding: utf-8 -*-
"""回归测试：_parse_value 有符号整数不再降级为 float（BUG-300）。

原实现 `if value_str.isdigit(): return int(...)` 后直接 `float(...)`——
`str.isdigit()` 不识别正负号与下划线分隔：
- '1' -> int 1，但 '-1' -> float -1.0、'+7' -> 7.0、'1_000' -> 1000.0

端到端表现为同一「数字字面量」类型与渲染文本不一致：
- `{x<-1;x}` -> '1'，而 `{x<- -1;x}` -> '-1.0'（应 '-1'）
- `{x<- -1;x*2}` -> '-2.0'（应 '-2'）

修复：先 int()（接受符号与下划线），失败再 float()，最后才走 safe_eval
（0x10 等进制字面量仍经安全求值得 int）。
"""

import pytest

from vools.datetime.dates_format import EnhancedDateFormatter as E


@pytest.fixture()
def fmt():
    return E('')


class TestSignedIntegers:
    @pytest.mark.parametrize('literal,expected', [
        ('1', 1), ('0', 0), ('42', 42),
        ('-1', -1), ('+7', 7), ('1_000', 1000), ('0x10', 16),
    ])
    def test_int_literals(self, fmt, literal, expected):
        parsed = fmt._parse_value(literal)
        assert parsed == expected
        assert isinstance(parsed, int) and not isinstance(parsed, bool)

    @pytest.mark.parametrize('literal,expected', [
        ('1.5', 1.5), ('-1.5', -1.5), ('1e3', 1000.0),
    ])
    def test_float_literals(self, fmt, literal, expected):
        parsed = fmt._parse_value(literal)
        assert parsed == expected
        assert isinstance(parsed, float)


class TestTemplateRendering:
    @pytest.mark.parametrize('template,expected', [
        ('{x<-1;x}', '1'),
        ('{x<- -1;x}', '-1'),
        ('{x<--1;x}', '-1'),
        ('{x<- -1;x*2}', '-2'),
        ('{x<- -1;x+1}', '0'),
        ('{x<-+7;x}', '7'),
        ('{x<-1.0;x}', '1.0'),
    ])
    def test_render(self, template, expected):
        assert E(template).format() == expected


class TestOtherLiteralsUnaffected:
    def test_quoted_string(self, fmt):
        assert fmt._parse_value('"abc"') == 'abc'

    def test_none_true_false(self, fmt):
        assert fmt._parse_value('None') is None
        assert fmt._parse_value('true') is True
        assert fmt._parse_value('FALSE') is False

    def test_list_and_dict(self, fmt):
        assert fmt._parse_value('[1,2]') == [1, 2]
        assert fmt._parse_value("{'k':1}") == {'k': 1}

    def test_plain_text_fallback(self, fmt):
        assert fmt._parse_value('abc') == 'abc'