# -*- coding: utf-8 -*-
"""AST 扫描：找出「所有断言都很弱」的测试函数（假绿灯高风险）。

弱断言定义（满足其一即计入弱）：
  * `assert True` / `assert <常量>`
  * `assert x is not None` / `assert x is None`
  * `assert isinstance(x, T)`
  * `assert x`（裸真值判断，没有任何期望值）
测试函数若**所有** assert 都属上述形态（或根本没有 assert），即列为「弱测试」。

只读脚本，不参与 pytest 收集（文件名不以 test_ 开头，位于 build/）。
"""
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TESTS = os.path.join(ROOT, 'tests')


def classify(node):
    """返回 'weak' / 'strong' / 'none'。"""
    test = node.test
    if isinstance(test, ast.Constant):
        return 'weak'            # assert True / assert 1
    if isinstance(test, ast.Name):
        return 'weak'            # assert x
    if isinstance(test, ast.UnaryOp):     # assert not x
        return 'weak'
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) \
            and test.func.id == 'isinstance':
        return 'weak'
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op = test.ops[0]
        if isinstance(op, (ast.Is, ast.IsNot)):
            right = test.comparators[0]
            if isinstance(right, ast.Constant) and right.value is None:
                return 'weak'    # is None / is not None
        # == / != / in / not in / </> 都算有期望值
        return 'strong'
    return 'strong'


def walk_asserts(node):
    out = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            out.append(child)
    return out


def main():
    rows = []
    for name in sorted(os.listdir(TESTS)):
        if not name.endswith('.py'):
            continue
        path = os.path.join(TESTS, name)
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                src = handle.read()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith('test'):
                continue
            asserts = walk_asserts(node)
            if not asserts:
                rows.append((name, node.lineno, node.name, 'no-assert'))
                continue
            kinds = [classify(a) for a in asserts]
            if all(k == 'weak' for k in kinds):
                rows.append((name, node.lineno, node.name,
                             'weak-only(%d asserts)' % len(asserts)))
    print('=== 弱测试 / 无断言测试（%d 个）===' % len(rows))
    for name, lineno, func, kind in rows:
        print('  %-42s :%-4d %-52s %s' % (name, lineno, func, kind))


if __name__ == '__main__':
    main()
