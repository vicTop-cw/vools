# -*- coding: utf-8 -*-
"""回归测试：EnhancedDateFormatter 的日期格式说明符（BUG-369）。

文档声明支持 `{variable:format}`，但 `_value_to_string` **只对 (int, float)
应用格式说明符**。日期变量在上下文中是**字符串**（'20260226' / '2026-02-26'），
因此日期格式被静默丢弃：

    EnhancedDateFormatter('{run_date:%Y/%m/%d}', default_run_date='2026-02-26').format()
    # 修复前 -> '20260226'（期望 '2026/02/26'）

修复：字符串分支在格式含 `%` 时按常见日期布局解析后 `strftime`；非 `%` 格式
按普通字符串格式（如 `{n:>5}`）应用；日期对象直接 `strftime`。
非法 strftime 指令（Windows 会把 `%Q` 原样留下）显式判失败 → 保留原始占位符
（与"计算失败保留原占位符"的既有语义一致）。
"""

import pytest

from vools.datetime.dates_format import EnhancedDateFormatter

BASE = dict(default_run_date='2026-02-26')


def fmt(template, **ctx):
    return EnhancedDateFormatter(template, **{**BASE, **ctx}).format()


class TestDateFormats:
    @pytest.mark.parametrize('template,expected', [
        ('{run_date:%Y/%m/%d}', '2026/02/26'),
        ('{run_date:%d.%m.%Y}', '26.02.2026'),
        ('{run_date_std:%Y%m%d}', '20260226'),
        ('{run_week_begin:%Y/%m/%d}', '2026/02/23'),
    ])
    def test_date_spec_applied(self, template, expected):
        assert fmt(template) == expected

    def test_invalid_directive_keeps_placeholder(self):
        # Windows 的 strftime 会把未知 %Q 原样保留，这里统一判失败
        assert fmt('{run_date:%Q}') == '{run_date:%Q}'

    def test_plain_date_var_unchanged(self):
        assert fmt('{run_date}') == '20260226'
        assert fmt('{run_date_std}') == '2026-02-26'


class TestOtherFormatsUnchanged:
    def test_float(self):
        assert fmt('{price:.2f}', price=1.5) == '1.50'

    def test_int(self):
        assert fmt('{n:03d}', n=7) == '007'

    def test_str_alignment(self):
        assert fmt('{n:>5}', n='ab') == '   ab'

    def test_list(self):
        assert fmt('{goods}', goods=['a', 'b']) == '[a, b]'

    def test_expression(self):
        assert fmt('{price * 2}', price=10) == '20'

    def test_unknown_kept(self):
        assert fmt('{unknown_var}') == '{unknown_var}'


class TestSecurityStillApplied:
    @pytest.mark.parametrize('template', [
        '{obj.__class__}',
        '{__import__("os").getcwd()}',
        '{"{0.__class__}".format(1)}',
    ])
    def test_unsafe_expression_kept_as_literal(self, template):
        # safe_eval_expression 拒绝 -> 保留原始占位符，不执行
        assert fmt(template, obj=1) == template