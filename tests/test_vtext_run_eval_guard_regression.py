# -*- coding: utf-8 -*-
"""回归测试：VText._run 的 eval 路径阻断 MRO 逃逸（BUG-362）。

BUG-206 曾给 `VText._run` 加上受限 `__builtins__` 命名空间，并在注释里声称
"杜绝 __import__/open 等任意代码执行"。但**受限 builtins 不是沙箱**：

    VText("().__class__.__base__.__subclasses__()")._run("eval")
    # -> 459 个类名，含 Popen / BuiltinImporter / _wrap_close

且 `_run(eval)`（直接传内建 eval）走 `func(text)` 时**根本没有受限命名空间**。
与 BUG-361（lazy）、BUG-288（str.format）同族。

修复：
- 新增 `vools.security.expr_guard.validate_expression`（AST 守卫，拒绝下划线
  属性/名称、`format`/`format_map`、`import`）；
- `_run("eval")` 与 `_run(eval)` 求值前调用它，失败抛 ValueError；
- `exec` 路径无法等价加固（语句执行），文档改为明确说明其为"显式执行代码"，
  不适用于不可信输入。

普通求值（算术、纯函数调用、可调用直通）与 `exec` 的正常用法保持不变。
"""

import pytest

from vools.data.vtext import VText
from vools.security.expr_guard import ExpressionGuardError, validate_expression


class TestEvalStillWorks:
    def test_arithmetic(self):
        assert VText('1 + 1')._run('eval') == 2

    def test_function_call(self):
        assert VText('sum([1, 2, 3])')._run('eval') == 6

    def test_callable_eval_object(self):
        assert VText('2 * 3')._run(eval) == 6

    def test_callable_passthrough(self):
        assert VText('abc')._run(lambda t: t.upper()) == 'ABC'

    def test_exec_normal_code(self):
        # exec 路径按"显式执行代码"对待（文档已说明信任边界）
        assert VText('x = 1')._run('exec') is None


class TestEvalEscapeBlocked:
    @pytest.mark.parametrize('payload', [
        '().__class__.__base__.__subclasses__()',
        '().__class__.__mro__',
        'pow.__globals__',
        '().__class__.__init__.__globals__',
        "'{0.__class__}'.format(1)",
        "'{a}'.format_map({'a': 1})",
    ])
    def test_payload_rejected_string_mode(self, payload):
        # 修复前：返回 400+ 个类（含 Popen）
        with pytest.raises(ValueError):
            VText(payload)._run('eval')

    @pytest.mark.parametrize('payload', [
        '().__class__',
        '().__class__.__base__.__subclasses__()',
    ])
    def test_payload_rejected_callable_eval(self, payload):
        # 修复前：func(text) 直接用调用者全局命名空间执行
        with pytest.raises(ValueError):
            VText(payload)._run(eval)


class TestSharedGuard:
    @pytest.mark.parametrize('expr', [
        'a.__class__', 'a.__dict__', "'{}'.format(1)", "__builtins__",
    ])
    def test_guard_rejects(self, expr):
        with pytest.raises(ExpressionGuardError):
            validate_expression(expr)

    @pytest.mark.parametrize('expr', [
        '1 + 2', 'sum([1, 2])', 'x.y', 'len(items)', '[i for i in range(3)]',
    ])
    def test_guard_allows(self, expr):
        validate_expression(expr)  # 不抛即通过

    def test_syntax_error(self):
        with pytest.raises(ExpressionGuardError):
            validate_expression('1 +')