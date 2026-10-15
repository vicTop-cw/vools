"""
ast 兼容层 — 统一处理 Python 不同版本的 AST 字面量节点

Python 3.8 起，字面量节点被统一为 ``ast.Constant``：
``ast.Str`` / ``ast.Num`` / ``ast.Bytes`` / ``ast.NameConstant`` 变成
``ast.Constant`` 的别名（且从 3.12 起彻底移除）。因此直接写
``isinstance(node, ast.Constant)`` 的代码在 **Python 3.6/3.7 上会漏判**
真实的字面量节点（字符串、数字、None 等），表现为静默拿到空值。

本模块提供版本无关的判定与取值函数：

- ``is_literal(node)``        → 是否是字面量节点
- ``literal_value(node)``     → 取字面量的值
- ``is_none_literal(node)``   → 是否是 None 字面量（兼容 py3.6 Info)
"""

import ast
import sys

__all__ = [
    'is_literal',
    'literal_value',
    'is_none_literal',
    'LITERAL_TYPES',
]

# py3.8+ 只有 ast.Constant；py3.6/3.7 需要把旧节点类型一并纳入。
if sys.version_info >= (3, 8):
    LITERAL_TYPES = (ast.Constant,)
else:
    LITERAL_TYPES = (ast.Constant, ast.Str, ast.Num, ast.Bytes, ast.NameConstant)


def is_literal(node) -> bool:
    """判断 AST 节点是否是字面量（字符串/数字/bytes/None/True/False）。

    Args:
        node: AST 节点。

    Returns:
        bool: 是字面量返回 True。
    """
    return isinstance(node, LITERAL_TYPES)


def literal_value(node):
    """取出字面量节点承载的值（版本无关）。

    py3.6/3.7 的 ``ast.Str`` 值在 ``.s``、``ast.Bytes`` 在 ``.s``、
    ``ast.Num`` 在 ``.n``、``ast.NameConstant`` 在 ``.value``；
    py3.8+ 统一在 ``ast.Constant.value``。

    Args:
        node: 字面量 AST 节点。

    Returns:
        节点承载的 Python 值；无法取出时返回 None。
    """
    if not is_literal(node):
        return None
    if sys.version_info >= (3, 8):
        return node.value
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Bytes):
        return node.s
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.NameConstant):
        return node.value
    return getattr(node, 'value', None)


def is_none_literal(node) -> bool:
    """判断 AST 节点是否是 None 字面量。

    常用于识别「函数体只有一行 None」这种占位实现（``def f(): None``），
    在 py3.6 下对应 ``ast.NameConstant(value=None)``，py3.8+ 对应
    ``ast.Constant(value=None)``。

    Args:
        node: 待检查的 AST 表达式节点。

    Returns:
        bool: 是 None 字面量返回 True。
    """
    return is_literal(node) and literal_value(node) is None
