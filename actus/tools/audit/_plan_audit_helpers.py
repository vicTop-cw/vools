# -*- coding: utf-8 -*-
"""第 16 轮审计共享辅助：宽松判定收紧为精确判定（单一实现，供审计脚本与测试同引用）。

背景（ACTUS_REFACTOR_PLAN §六.6 复核）：plan_audit_actus.py 早期用正则 / 字符串
包含判定「kind 执行语义已落地」，历史说明注释里出现 `kind == 'alias'` 之类字样
就可能误报 OK。这里改为 AST 解析真实代码节点 —— 注释、docstring、字符串字面量
天然不在 AST 里，只统计真实可执行代码中的判定。
"""
import ast


def code_kind_comparisons(src: str) -> set:
    """AST 收集真实代码中对 `kind` 变量的 == / in 判定字面量（精确匹配）。

    相比正则 / 字符串包含判定：
      * 注释、docstring、字符串字面量天然不在 AST 里 —— 历史说明里出现
        `kind == 'alias'` 之类字样不会误报"已落地"；
      * 只认 `kind` 变量（Name 节点）；`meta.get('kind') == 'x'` 这类调用
        表达式 left 不是 Name('kind')，不参与（执行语义判定以局部变量为准）；
      * `kind != 'exec'`（NotEq）不算执行语义落地判定，不收集；
      * `kind in (...)` 支持元组 / 列表 / 集合三种容器字面量。

    Args:
        src: Python 源码文本（如 executor.py 全文）。

    Returns:
        被判定的 kind 字面量集合（空集 = 源码解析失败或无判定）。
    """
    found = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == 'kind'):
            continue
        if not node.ops:
            continue
        op = node.ops[0]
        if isinstance(op, ast.Eq) and len(node.comparators) == 1:
            value = node.comparators[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(value.value)
        elif isinstance(op, ast.In) and len(node.comparators) == 1:
            container = node.comparators[0]
            if isinstance(container, (ast.Tuple, ast.List, ast.Set)):
                for elt in container.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        found.add(elt.value)
    return found
