# -*- coding: utf-8 -*-
"""表达式安全守卫：拒绝沙箱逃逸向量（BUG-361 / BUG-362）。

`eval` + 受限 `__builtins__` **不是沙箱**：即便拿掉 `__import__`/`open`，
仍可用

    ().__class__.__base__.__subclasses__()

沿 MRO 链取到任意已加载类（实测可达 400+ 个子类，含 `Popen`/`BuiltinImporter`）。
本模块提供统一的 AST 校验，供各表达式求值入口复用：

- `lazy()` 的 `->` / `=>` 延迟表达式；
- `VText._run("eval")` / `_run(eval)` 的表达式求值路径。

规则（够用且不误伤常规表达式）：
1. 禁止下划线开头的**属性**（`__class__`/`__subclasses__`/`__globals__`/`__bases__`…）；
2. 禁止下划线开头的**名称**（`__builtins__` 等）；
3. 禁止 `.format` / `.format_map`（`str.format` 逃逸面，BUG-288 同族）；
4. 禁止 `import` 语句。

注意：`exec`（语句执行）无法用 AST 白名单等价加固，本守卫**不覆盖** exec 路径——
那类入口按"显式执行代码"对待，文档需说明其信任边界。
"""

import ast

__all__ = ['ExpressionGuardError', 'validate_expression']

_FORBIDDEN_ATTRS = frozenset({'format', 'format_map'})


class ExpressionGuardError(ValueError):
    """表达式触发安全限制。"""


def validate_expression(expr: str) -> None:
    """校验表达式；不安全时抛 :class:`ExpressionGuardError`。"""
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as exc:
        raise ExpressionGuardError(f"无效的表达式: {expr!r}（{exc}）") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith('_'):
                raise ExpressionGuardError(
                    f"表达式不允许访问下划线属性: .{node.attr}")
            if node.attr in _FORBIDDEN_ATTRS:
                raise ExpressionGuardError(
                    f"表达式不允许访问 .{node.attr}（format 逃逸风险，BUG-288）")
        elif isinstance(node, ast.Name):
            if node.id.startswith('_'):
                raise ExpressionGuardError(
                    f"表达式不允许使用下划线名称: {node.id}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ExpressionGuardError("表达式不允许 import")
