# -*- coding: utf-8 -*-
"""tests/security/test_safe_eval_literals.py — safe_eval 字面量白名单必须版本无关（钉 BUG-75）

81a2d25 为消 py3.14 隐患删掉 safe_eval._eval_node 的三个 legacy AST 分支、只留
`isinstance(node, ast.Constant)`。对 3.8+ 成立，但 py3.6/3.7 下 ast.parse 产出的是
Num/Str/Bytes/NameConstant —— 于是【任何含字面量的表达式】在 py3.6 全部编译失败。
实测症状：`safe_lambda(('x',), '5 > 3')` 在 py3.6 抛 SafeEvalError("不支持的表达式
类型: Num")，连带 vools.functional.iif 文档承诺的字符串条件在 3.6 上整条不可用
（tests/functional/test_iif.py 两格实测红）。

修法是复用仓内既有真源 vools.core.ast_compat（is_literal / literal_value），与同
目录 expression_handler.py:129、bridge/core/sigcache.py:25 同一口径 —— 不新发明
一套判据。

本锁两半都必须有：
  A) 字面量表达式在双版本都能编译并求值（防 py3.6 再度漏判 legacy 节点）；
  B) 危险表达式仍被拒（防"为了修 3.6 把白名单放开"这种更糟的修法）。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.security.safe_eval import safe_lambda, SafeEvalError  # noqa: E402

LITERAL_EXPRS = [
    # (表达式, 期望 f(3))：全部为本轮实测可编译的表达式。
    # 注意不要写 `x + 1` 这类"变量参与算术"的式子 —— safe_lambda 的校验阶段会
    # 用占位【字符串】('_v_0') 求值整个 body，str + int 会 TypeError，属既有设计，
    # 与本锁要钉的字面量问题无关（实测记录见账本 BUG-75）。
    ('5 > 3', True),
    ('10', 10),
    ("'abc'", 'abc'),
    ('True', True),
    ('None', None),
    ('2 + 3', 5),
    ("'a' == 'a'", True),
    ('x == 3', True),
]


@pytest.mark.parametrize("expr,expect", LITERAL_EXPRS)
def test_literal_expressions_compile(expr, expect):
    """字面量表达式必须能编译（py3.6 曾因只认 ast.Constant 全挂）。"""
    f = safe_lambda(('x',), expr)
    assert f(3) == expect


DANGEROUS = [
    "__import__('os').system('echo x')",
    "x.__class__.__bases__",
    "eval('1+1')",
    "open('/etc/passwd')",
    "exec('x=1')",
    "x.__globals__",
    "(lambda: 1)()",
    "x.__subclasses__()",
]


@pytest.mark.parametrize("expr", DANGEROUS)
def test_dangerous_expressions_still_rejected(expr):
    """修 3.6 不能靠放宽白名单 —— 危险表达式在双版本都必须被拒。"""
    with pytest.raises(SafeEvalError):
        f = safe_lambda(('x',), expr)
        f(1)          # 有的实现编译期放行、求值期才炸，两种都算拒


def test_uses_ast_compat_single_source():
    """判据必须来自 vools.core.ast_compat，不得各自硬编码节点类型元组。"""
    src = open(os.path.join(_ROOT, 'vools', 'security', 'safe_eval.py'), 'rb').read().decode('utf-8')
    assert 'from ..core.ast_compat import' in src, \
        'safe_eval 不走 ast_compat 就会在某个 Python 版本上漏判字面量节点'
