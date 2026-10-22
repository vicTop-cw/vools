# -*- coding: utf-8 -*-
"""回归测试：表达式沙箱的 format-field 属性遍历逃逸（BUG-288, critical）。

原实现两道防线都可被绕过：
① 原文子串黑名单：把字面量拆成两段拼接（'__cla' + 'ss__'）即规避；
② AST 校验把字符串字面量当普通常量放行——format-field 内的属性遍历
   （'{0.__class__}'）对 AST 完全不可见，而 `.format` 不在禁用属性表。
实测可抵达 `<class 'int'>`、`__mro__`，乃至 `__subclasses__` 绑定方法，
继而是典型的 Python 沙箱逃逸链（RCE）。

修复：Attribute 分支加固——拒绝所有 `_` 开头属性 + 拒绝 format/format_map。
合法属性访问（如 `x.year`，既有测试依赖）保持放行。
"""

import datetime

import pytest

from vools.security.expression_handler import (
    ExpressionSecurityError,
    create_filter_func,
    create_map_func,
    safe_compile_expression,
    safe_eval_expression,
)


class TestFormatEscapeBlocked:
    @pytest.mark.parametrize('expr', [
        # 拼接拆分 dunder，绕过原文黑名单
        "('{0.__cla' + 'ss__}').format(x)",
        "('{0.__cla' + 'ss__.__mr' + 'o__}').format(x)",
        "('{0.__cla' + 'ss__.__bas' + 'es__[0].__subcl' + 'asses__}').format(x)",
        # 未拆分（原文黑名单直接命中）
        "'{0.__class__}'.format(x)",
        "'{0.__class__.__mro__}'.format(x)",
        "'{k.__class__}'.format_map({'k': x})",
    ])
    def test_blocked(self, expr):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression(expr, {'x': 1})

    def test_format_attribute_directly_blocked(self):
        with pytest.raises(ExpressionSecurityError, match='format'):
            safe_eval_expression("'{}'.format(x)", {'x': 1})

    def test_dunder_attr_via_plain_attr_blocked(self):
        with pytest.raises(ExpressionSecurityError):
            safe_eval_expression("x.__class__", {'x': 1})

    def test_sandbox_compilers_block_too(self):
        with pytest.raises(ExpressionSecurityError):
            create_filter_func("('{0.__cla' + 'ss__}').format(x) or True")
        with pytest.raises(ExpressionSecurityError):
            create_map_func("('{0.__cla' + 'ss__}').format(x)")
        with pytest.raises(ExpressionSecurityError):
            safe_compile_expression("('{0.__cla' + 'ss__}').format(x)")


class TestLegitimateUsagePreserved:
    def test_attribute_access_year(self):
        # tests/datetime/test_eval_sandbox_escape.py 依赖此能力
        assert safe_eval_expression(
            'x.year', {'x': datetime.date(2026, 1, 1)}) == 2026

    def test_str_methods(self):
        assert safe_eval_expression("'ab'.upper()", {}) == 'AB'
        assert safe_eval_expression("','.join(['a', 'b'])", {}) == 'a,b'

    def test_comparisons_and_arithmetic(self):
        assert safe_eval_expression('x > 1', {'x': 2}) is True
        assert safe_eval_expression('x * 2 + 1', {'x': 1}) == 3

    def test_filter_map_builders(self):
        assert list(filter(create_filter_func('x > 1'), [1, 2, 3])) == [2, 3]
        assert list(map(create_map_func('x * 2'), [1, 2])) == [2, 4]