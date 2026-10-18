# -*- coding: utf-8 -*-
"""BUG-101: dates_format.py eval 沙箱逃逸（Python 对象模型绕过 __builtins__ 限制）

self.context 作为 __builtins__ 传给 eval，但 Python 的对象模型
(().__class__.__base__.__subclasses__()) 可在没有 __builtins__ 的情况下
访问任意模块（含 os/subprocess）。攻击者可构造 {__import__('os')} 等表达式。

修复方案：safe_eval_expression 加强 ast.Attribute 校验（拒绝 __class__/__base__
等危险属性），dates_format 改用 safe_eval_expression 替代裸 eval。
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.datetime.dates_format import EnhancedDateFormatter  # noqa: E402
from vools.security.expression_handler import (  # noqa: E402
    safe_eval_expression,
    ExpressionSecurityError,
)


class TestEvalSandboxEscape:
    """验证 dates_format 的 eval 沙箱可被 Python 对象模型绕过"""

    def test_object_model_escape(self):
        """Python 对象模型不应绕过 __builtins__ 限制（修复后应被拒）"""
        formatter = EnhancedDateFormatter(
            template="hello {x}", default_run_date="20260101"
        )
        # _evaluate_expression 接收的是 {} 内部内容，不含花括号
        payload = "().__class__.__base__.__subclasses__()"
        result = formatter._evaluate_expression(payload)
        # 修复后：safe_eval 拒绝 __class__ 属性访问，返回原始表达式字符串
        # 修复前：返回 subclasses() 列表（沙箱逃逸成功）
        assert not isinstance(result, list)

    def test_subclasses_count_large(self):
        """subclasses() 不应能列出类（修复后应被拒）"""
        formatter = EnhancedDateFormatter(
            template="hello {x}", default_run_date="20260101"
        )
        payload = "len(().__class__.__base__.__subclasses__())"
        result = formatter._evaluate_expression(payload)
        assert not (isinstance(result, int) and result > 50)

    def test_os_module_reachable_via_subclasses(self):
        """通过 object.__subclasses__() 的 __globals__ 不应能获取 os 模块"""
        formatter = EnhancedDateFormatter(
            template="hello {x}", default_run_date="20260101"
        )
        # 在 py3.11 中 _TrivialRe 的 __init__.__globals__ 包含 os 模块
        payload = (
            "[x for x in ().__class__.__base__.__subclasses__() "
            "if x.__name__ == '_TrivialRe'][0].__init__.__globals__.get('os')"
        )
        result = formatter._evaluate_expression(payload)
        # 修复后：safe_eval 拒绝 __globals__ 属性访问
        # 修复前：返回 os 模块对象（RCE 可行）
        assert not (hasattr(result, 'system') and callable(result.system))


class TestSafeEvalAttributeValidation:
    """safe_eval_expression 必须拒绝对象模型逃逸"""

    @pytest.mark.parametrize("expr", [
        "().__class__.__base__.__subclasses__()",
        "1 .__class__",
        "'x'.__class__.__mro__",
        "[].__class__.__bases__",
    ])
    def test_reject_object_model_escape(self, expr):
        """对象模型逃逸必须被拒绝"""
        with pytest.raises(Exception):
            safe_eval_expression(expr, {})

    def test_reject_double_underscore_attr(self):
        """__class__/__base__/__globals__/__subclasses__/__mro__ 等双下划线属性必须被拒"""
        for bad in [
            '().__class__',
            '().__class__.__base__',
            'x.__globals__',
            'x.__dict__',
            'x.__mro__',
            'x.__subclasses__()',
            'x.__init__',
            'x.__getattribute__',
        ]:
            with pytest.raises(Exception):
                safe_eval_expression(bad, {'x': 1})

    def test_allow_normal_attribute(self):
        """正常单下划线属性仍应允许"""
        # datetime 的 year 属性
        import datetime
        result = safe_eval_expression("x.year", {'x': datetime.date(2026, 1, 1)})
        assert result == 2026