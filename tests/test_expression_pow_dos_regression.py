# -*- coding: utf-8 -*-
"""回归测试：幂运算指数失控导致进程挂死（BUG-484，DoS）。

修复前安全表达式允许任意指数：

    safe_eval_expression("9**9**9")     # 9^(9^9) = 9^387420489 —— 进程 CPU 跑满、
                                        # 永不返回（实测挂死 >2 分钟，需 kill）

修复后在**验证期**做静态规模估算：
* 指数 |值| > 10000 → ExpressionSecurityError；
* 底数与指数均可静态求值且预计位数 > 1M 位 → ExpressionSecurityError。

正常幂运算（``2**10``、``2**64``、``1.5**3``、``(-2)**3``）与其余运算符不受影响。

残余风险（如实记录）：指数来自**宿主上下文变量**（``a ** b``，b 由调用方传入）时
无法静态估算，仍可能消耗资源——此类输入本身即可信边界内的宿主数据。
"""

import time

import pytest

from vools.datetime.dates_format import safe_eval_expression
from vools.security.expression_handler import ExpressionSecurityError


class TestPowDosBlocked:
    @pytest.mark.parametrize("expr", [
        "9**9**9",
        "2**100000",
        "2**(10**9)",
        "10**10001",
    ])
    def test_huge_exponent_rejected(self, expr):
        t0 = time.time()
        with pytest.raises(ExpressionSecurityError) as ei:
            safe_eval_expression(expr)
        # 必须是"快速拒绝"，不能真的算
        assert time.time() - t0 < 1.0
        assert "幂" in str(ei.value)

    def test_nested_static_pow_evaluated_safely(self):
        """内层 9**9 可静态求值 → 外层指数 387420489 超限被拒。"""
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("9**9**9")


class TestNormalPowersUnchanged:
    @pytest.mark.parametrize("expr,expected", [
        ("2**10", 1024),
        ("2**64", 18446744073709551616),
        ("1.5**3", 3.375),
        ("2**0", 1),
        ("(-2)**3", -8),
        ("(9**9)**9", 196627050475552913618075908526912116283103450944214766927315415537966391196809),
    ])
    def test_reasonable_powers(self, expr, expected):
        assert safe_eval_expression(expr) == expected


class TestOtherOperatorsUnchanged:
    def test_in_and_not_in(self):
        assert safe_eval_expression("1 in [1,2]") is True
        assert safe_eval_expression("3 not in [1,2]") is True

    def test_short_circuit(self):
        assert safe_eval_expression("False and (1/0)") is False

    def test_string_multiply(self):
        assert safe_eval_expression("'x'*3") == "xxx"

    def test_arithmetic(self):
        assert safe_eval_expression("(1 + 2) * 3 - 4 / 2") == 7.0
