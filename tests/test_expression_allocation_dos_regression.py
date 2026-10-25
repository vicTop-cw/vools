# -*- coding: utf-8 -*-
"""回归测试：表达式求值的**内存耗尽型 DoS**（BUG-485，security）。

修复前 ``range``/``list``/``sorted`` 都在 ALLOWED_BUILTINS 里，且序列乘法无约束：

    safe_eval_expression("list(range(10**8))")   # 真的分配 ~800MB
    safe_eval_expression("range(10**9)")         # 10 亿项
    safe_eval_expression("'x' * 10**8")          # 100MB 字符串
    safe_eval_expression("tuple([1]) * 10**7")   # 实测 0.51s 产出 1000 万项（~80MB）

修复后在**验证期**静态估算并拒绝：
* ``range(...)`` 元素数 > 1,000,000；
* 字面量序列 × 大数 > 1,000,000 项/字节；
* 调用结果 × 大数（长度未知）时，倍数 > 1,000,000。

正常小规模用法（``range(5)``、``'x'*3``、``tuple([1])*3``、``len(x)*2``、
``sum(range(10))``）不受影响。
"""

import time

import pytest

from vools.datetime.dates_format import safe_eval_expression
from vools.security.expression_handler import ExpressionSecurityError


class TestRangeAllocation:
    @pytest.mark.parametrize("expr", [
        "list(range(10**8))",
        "range(10**9)",
        "sorted(range(10**7))",
        "list(range(0, 10**8))",
        "list(range(0, 10**7, 1))",
    ])
    def test_huge_range_rejected(self, expr):
        t0 = time.time()
        with pytest.raises(ExpressionSecurityError) as ei:
            safe_eval_expression(expr)
        assert time.time() - t0 < 1.0
        assert "range" in str(ei.value)

    def test_range_with_keywords_rejected(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("range(stop=5)")

    @pytest.mark.parametrize("expr,expected_len", [
        ("list(range(100))", 100),
        ("range(5)", 5),
    ])
    def test_small_range_ok(self, expr, expected_len):
        assert len(list(safe_eval_expression(expr))) == expected_len


class TestSequenceAmplification:
    @pytest.mark.parametrize("expr", [
        "'x' * 10**8",
        "[0] * 10**8",
        "(1, 2) * 10**7",
        "tuple([1]) * 10**7",
    ])
    def test_amplification_rejected(self, expr):
        t0 = time.time()
        with pytest.raises(ExpressionSecurityError) as ei:
            safe_eval_expression(expr)
        assert time.time() - t0 < 1.0
        assert "放大" in str(ei.value)

    @pytest.mark.parametrize("expr,expected", [
        ("'x' * 3", "xxx"),
        ("[0] * 5", [0, 0, 0, 0, 0]),
        ("tuple([1]) * 3", (1, 1, 1)),
        ("len([1,2]) * 2", 4),
    ])
    def test_small_amplification_ok(self, expr, expected):
        assert safe_eval_expression(expr) == expected


class TestNothingElseRegressed:
    @pytest.mark.parametrize("expr,env,expected", [
        ("range(5)", {}, None),
        ("sum(range(10))", {}, 45),
        ("a * 2", {"a": 21}, 42),
        ("sorted([3,1,2])", {}, [1, 2, 3]),
        ("2**10", {}, 1024),
        ("-1", {}, -1),
    ])
    def test_expected(self, expr, env, expected):
        result = safe_eval_expression(expr, env)
        if expected is None:
            assert list(result) == [0, 1, 2, 3, 4]
        else:
            assert result == expected

    @pytest.mark.parametrize("expr", [
        "__import__('os')", "open('/etc/passwd')", "().__class__", "9**9**9",
    ])
    def test_security_guards_intact(self, expr):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(expr)
