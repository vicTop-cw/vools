# -*- coding: utf-8 -*-
"""回归测试：安全表达式拒绝一元正负号（BUG-483）。

修复前 ``ALLOWED_OPERATORS`` 没有 ``ast.USub`` / ``ast.UAdd``，于是**负数在表达式里
根本无法出现**：

    safe_eval_expression("-1")        # ExpressionSecurityError: 不允许的运算符: USub
    safe_eval_expression("2 * -3")    # 同上
    safe_eval_expression("abs(-1)")   # 同上
    EnhancedDateFormatter("{-1}").format()   # 占位符原样保留（静默不渲染）

修复后一元正负号正常求值；**危险内容仍被拦截**（``__import__``/``open``/``eval``/
双下划线链/`-__import__('os')` 全部 ExpressionSecurityError）。
"""

import pytest

from vools.datetime.dates_format import EnhancedDateFormatter, safe_eval_expression
from vools.security.expression_handler import ExpressionSecurityError


class TestUnaryOperators:
    @pytest.mark.parametrize("expr,env,expected", [
        ("-1", {}, -1),
        ("-a", {"a": 10}, -10),
        ("a - -1", {"a": 10}, 11),
        ("+1", {}, 1),
        ("2 * -3", {}, -6),
        ("abs(-1)", {}, 1),
        ("-(1+2)", {}, -3),
        ("-2.5", {}, -2.5),
        ("-a + 3", {"a": 2}, 1),
    ])
    def test_unary_evaluates(self, expr, env, expected):
        assert safe_eval_expression(expr, env) == expected

    def test_negative_in_template(self):
        assert EnhancedDateFormatter("{-1}").format() == "-1"
        assert EnhancedDateFormatter("{2 * -3}").format() == "-6"

    def test_negative_result_unchanged(self):
        f = EnhancedDateFormatter("{a - 5}")
        f.set(a=3)
        assert f.format() == "-2"


class TestSecurityNotWeakened:
    @pytest.mark.parametrize("expr", [
        "__import__('os')",
        "open('/etc/passwd')",
        "eval('1')",
        "exec('a=1')",
        "().__class__.__bases__",
        "globals()",
        "-__import__('os')",
        "-().__class__",
        "'{0.__class__}'.format(1)",
    ])
    def test_dangerous_still_blocked(self, expr):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(expr)

    def test_division_by_zero_loud(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("1/0")

    def test_syntax_error_loud(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("1+")

    def test_empty_expression_loud(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("")


class TestNormalExpressionsUnchanged:
    @pytest.mark.parametrize("expr,env,expected", [
        ("1+2", {}, 3),
        ("len([1,2])", {}, 2),
        ("a*2", {"a": 21}, 42),
        ("'x'*3", {}, "xxx"),
        ("sorted([3,1,2])", {}, [1, 2, 3]),
        ("round(1.234, 2)", {}, 1.23),
    ])
    def test_basic(self, expr, env, expected):
        assert safe_eval_expression(expr, env) == expected
