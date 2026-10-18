# -*- coding: utf-8 -*-
"""tests/security/test_safe_eval_comparison.py — 排序比较运算符编译（钉 BUG-91）

BUG-91：safe_lambda 在编译期用字符串占位符（f'_v_{i}'）验证 AST，当表达式包含
排序比较（x > 3, x < 3, x >= 3, x <= 3）时，'_v_0' > 3 抛 TypeError（str 与 int
不可排序比较），SafeEvalError 吞掉后编译失败。

连带影响：vools.functional.iif 的 '->' 前缀与 supp 模式的字符串条件在含排序比较
时静默回退到 bool(condition)（非空字符串恒 True），导致 iif("-> x < 3", data=5)
错误返回 true 分支。

修复：引入 _Placeholder 占位符类，所有比较/算术运算符恒返回 True/占位符，
AST 验证只检查结构不执行真实运算。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.security.safe_eval import safe_lambda, SafeEvalError  # noqa: E402


class TestSafeLambdaComparison:
    """排序比较运算符必须能编译并正确求值"""

    def test_gt(self):
        f = safe_lambda(('x',), 'x > 3')
        assert f(5) is True
        assert f(1) is False

    def test_lt(self):
        f = safe_lambda(('x',), 'x < 3')
        assert f(1) is True
        assert f(5) is False

    def test_ge(self):
        f = safe_lambda(('x',), 'x >= 3')
        assert f(3) is True
        assert f(2) is False

    def test_le(self):
        f = safe_lambda(('x',), 'x <= 3')
        assert f(3) is True
        assert f(4) is False

    def test_eq(self):
        f = safe_lambda(('x',), 'x == 5')
        assert f(5) is True
        assert f(6) is False

    def test_ne(self):
        f = safe_lambda(('x',), 'x != 5')
        assert f(6) is True
        assert f(5) is False

    def test_string_compare(self):
        f = safe_lambda(('x',), "x == 'hello'")
        assert f('hello') is True
        assert f('world') is False

    def test_chain_compare(self):
        f = safe_lambda(('x',), '1 < x < 10')
        assert f(5) is True
        assert f(0) is False
        assert f(11) is False

    def test_mixed_arithmetic_and_compare(self):
        f = safe_lambda(('x',), 'x * 2 > 10')
        assert f(6) is True
        assert f(4) is False

    def test_multi_param_compare(self):
        f = safe_lambda(('x', 'y'), 'x > y')
        assert f(5, 3) is True
        assert f(3, 5) is False


class TestSafeLambdaSafety:
    """修复不能放开安全白名单"""

    def test_import_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "__import__('os').system('echo hi')")

    def test_eval_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "eval('1+1')")

    def test_open_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "open('/etc/passwd').read()")

    def test_builtins_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "__builtins__")

    def test_exec_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "exec('print(1)')")

    def test_attribute_access_blocked(self):
        with pytest.raises(SafeEvalError):
            safe_lambda(('x',), "x.__class__.__bases__")