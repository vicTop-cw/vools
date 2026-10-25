# -*- coding: utf-8 -*-
"""回归测试：嵌套推导式的元素数乘积爆炸（BUG-486，security）。

BUG-485 只限制了**单个** ``range(...)`` 的元素数，嵌套推导式可绕开：

    [x for x in range(1000) for y in range(1000) for z in range(1000)]
    # 每个 range 都 ≤ 1e6，但真实元素数 1e9 → 求值期内存打满

    len([(x, y) for x in range(10**6) for y in range(10**6)])
    # 10^12 项

修复后在验证期把各 generator 的静态元素数**相乘**，乘积 > 1,000,000 即拒绝
（列表/集合/字典/生成器推导式都覆盖）。单层与小规模嵌套不受影响。
"""

import ast
import time

import pytest

from vools.datetime.dates_format import safe_eval_expression
from vools.security.expression_handler import (
    ExpressionSecurityError,
    _validate_ast_node,
)


def _validate_only(expr):
    """只做验证、不执行（避免测试本身触发 DoS）。"""
    _validate_ast_node(ast.parse(expr, mode="eval").body, set())


class TestNestedComprehensionBlocked:
    @pytest.mark.parametrize("expr", [
        "[x for x in range(1000) for y in range(1000) for z in range(1000)]",
        "[(x, y) for x in range(10**6) for y in range(10**6)]",
        "{x: y for x in range(10**6) for y in range(10**6)}",
        "{x for x in range(10**4) for y in range(10**4)}",
        "(x for x in range(10**4) for y in range(10**4))",
    ])
    def test_product_exceeds_limit(self, expr):
        t0 = time.time()
        with pytest.raises(ExpressionSecurityError) as ei:
            _validate_only(expr)
        assert time.time() - t0 < 1.0
        assert "推导式" in str(ei.value)

    def test_eval_also_blocked(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(
                "[1 for x in range(1000) for y in range(1000) for z in range(1000)]")


class TestSmallComprehensionsAllowed:
    @pytest.mark.parametrize("expr,expected_len", [
        ("[x for x in range(100)]", 100),
        ("[(x, y) for x in range(10) for y in range(10)]", 100),
        ("[x * 2 for x in [1, 2, 3]]", 3),
        ("[(x, y) for x in range(1000) for y in range(1000)]", 1_000_000),
    ])
    def test_allowed(self, expr, expected_len):
        assert len(safe_eval_expression(expr)) == expected_len

    def test_string_iterable(self):
        assert safe_eval_expression("[c for c in 'abc']") == ["a", "b", "c"]

    def test_list_literal_iterable(self):
        assert safe_eval_expression("[x for x in [1, 2]]") == [1, 2]


class TestPreviousGuardsIntact:
    @pytest.mark.parametrize("expr", [
        "list(range(10**8))",
        "'x' * 10**8",
        "tuple([1]) * 10**7",
        "9**9**9",
        "__import__('os')",
        "open('/etc/passwd')",
    ])
    def test_still_blocked(self, expr):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(expr)

    def test_normal_arithmetic(self):
        assert safe_eval_expression("1 + 2 * 3") == 7
        assert safe_eval_expression("-1") == -1
        assert safe_eval_expression("2**10") == 1024
