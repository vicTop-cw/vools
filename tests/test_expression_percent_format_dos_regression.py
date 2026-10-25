# -*- coding: utf-8 -*-
"""回归测试：百分号格式化宽度放大（BUG-487，security）。

``%`` 作用在字符串上就是格式化——宽度/精度控制输出长度，此前毫无约束：

    safe_eval_expression("'%9999999d' % 5")     # 10MB 字符串（0.03s）
    safe_eval_expression("'%999999999d' % 5")   # **1GB** 字符串（2.87s）

修复后从**常规模板字面量**提取最大宽度/精度，超过 1,000,000 即拒绝
（与 BUG-485 序列放大同阈值）；数字取模、正常格式化不受影响。
"""

import time

import pytest

from vools.datetime.dates_format import safe_eval_expression
from vools.security.expression_handler import ExpressionSecurityError


class TestFormatAmplificationBlocked:
    @pytest.mark.parametrize("expr", [
        "'%9999999d' % 5",
        "'%999999999d' % 5",
        "'%.10000000f' % 1.5",
        "b'%999999999d' % 5",
        "'%2000000s' % 'x'",
    ])
    def test_huge_width_rejected(self, expr):
        t0 = time.time()
        with pytest.raises(ExpressionSecurityError) as ei:
            safe_eval_expression(expr)
        assert time.time() - t0 < 1.0
        assert "宽度" in str(ei.value) or "精度" in str(ei.value)


class TestValidFormattingUnchanged:
    @pytest.mark.parametrize("expr,expected", [
        ("'%10d' % 5", "         5"),
        ("'%.2f' % 3.14159", "3.14"),
        ("'%s' % 1", "1"),
        ("'%d%%' % 50", "50%"),
    ])
    def test_formatting(self, expr, expected):
        assert safe_eval_expression(expr) == expected

    @pytest.mark.parametrize("expr,expected", [
        ("10 % 3", 1),
        ("7.5 % 2", 1.5),
    ])
    def test_numeric_modulo(self, expr, expected):
        assert safe_eval_expression(expr) == expected


class TestOtherGuardsIntact:
    @pytest.mark.parametrize("expr", [
        "list(range(10**8))",
        "'x' * 10**8",
        "9**9**9",
        "[x for x in range(1000) for y in range(1000) for z in range(1000)]",
        "__import__('os')",
    ])
    def test_still_blocked(self, expr):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(expr)

    def test_normal_arithmetic(self):
        assert safe_eval_expression("1 + 2 * 3 - 4 % 3") == 6   # 1+6-1
        assert safe_eval_expression("-1") == -1
