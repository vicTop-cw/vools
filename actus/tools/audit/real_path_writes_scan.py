# -*- coding: utf-8 -*-
"""测试卫生扫描：找出 tests/ 里可能**写真实仓库文件**的语句。

判定：AST 找文件写操作（open 写模式 / write_text / write_bytes / copy / move /
remove / unlink / rename / replace / touch），把目标表达式原文打印出来；
目标表达式里出现 tmp_path/tmpdir/world/fake_repo/probe/repo/home/config/meta/
actions_dir 等"隔离"关键词的标为 SAFE，其余标为 REVIEW 供人工复核。

只读脚本（tools/audit，不参与 pytest 收集）。
"""
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TESTS = os.path.join(ROOT, 'tests')

_WRITE_ATTRS = {'write_text', 'write_bytes', 'touch', 'symlink_to', 'hardlink_to'}
_OS_ATTRS = {'remove', 'unlink', 'rename', 'replace'}
_WRITE_FUNCS = {
    'open', 'remove', 'unlink', 'rename', 'replace',
    'copy', 'copy2', 'copytree', 'move', 'rmtree',
}
_SAFE_HINTS = (
    'tmp_path', 'tmpdir', 'world', 'fake_repo', 'probe', 'repo', 'home',
    'config', 'meta', 'actions_dir', 'adir', 'cache_file', 'blocked',
    'directory', 'cache', 'fixture',
)


def _mode_is_write(call):
    for kw in call.keywords:
        if kw.arg in ('mode', 'newline'):
            continue
        if kw.arg == 'encoding':
            continue
    args = list(call.args)
    if len(args) >= 2:
        try:
            mode = ast.literal_eval(args[1])
        except Exception:
            return True          # 非字面量模式 → 视为可能写
        return any(ch in str(mode) for ch in 'wax+')
    return False


def _text(node):
    try:
        return ast.unparse(node)
    except Exception:
        return '<expr>'


def main():
    review = []
    safe = []
    for name in sorted(os.listdir(TESTS)):
        if not name.endswith('.py'):
            continue
        path = os.path.join(TESTS, name)
        try:
            tree = ast.parse(open(path, encoding='utf-8', errors='replace').read())
        except (OSError, SyntaxError):
            continue
        funcs = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    funcs[id(child)] = node.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = None
            kind = None
            if isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                recv = node.func.value
                recv_name = _text(recv)
                if attr in _WRITE_ATTRS:
                    target = recv
                    kind = '.' + attr
                elif attr in _OS_ATTRS:
                    if not (recv_name in ('os', 'shutil') or 'path' in recv_name.lower()):
                        continue      # 字符串 .replace 等误报
                    target = node.args[-1] if node.args else None
                    kind = recv_name + '.' + attr
                elif attr in ('copy', 'copy2', 'copytree', 'move', 'rmtree'):
                    if node.args:
                        target = node.args[-1]
                        kind = 'shutil.' + attr
                elif attr == 'open':
                    if _mode_is_write(node):
                        target = node.func.value
                        kind = '.open(write)'
            elif isinstance(node.func, ast.Name) and node.func.id in _WRITE_FUNCS:
                if node.func.id == 'open':
                    if not _mode_is_write(node):
                        continue
                    target = node.args[0] if node.args else None
                elif node.func.id in ('remove', 'unlink', 'rename', 'replace'):
                    target = node.args[0] if node.args else None
                kind = node.func.id
            if target is None or kind is None:
                continue
            expr = _text(target)
            fname = funcs.get(id(node), '<module>')
            row = (name, node.lineno, fname, kind, expr)
            lowered = expr.lower()
            if any(h in lowered for h in _SAFE_HINTS):
                safe.append(row)
            else:
                review.append(row)

    print('=== REVIEW（可能写真实仓库，需人工确认）%d 处 ===' % len(review))
    for name, lineno, fname, kind, expr in review:
        print('  %-38s:%-4d %-38s %-14s %s' % (name, lineno, fname, kind, expr))
    print('\n=== SAFE（目标含隔离关键词，抽查）%d 处 ===' % len(safe))
    for name, lineno, fname, kind, expr in safe[:15]:
        print('  %-38s:%-4d %-38s %-14s %s' % (name, lineno, fname, kind, expr))
    print('  ...（共 %d 处）' % len(safe))


if __name__ == '__main__':
    main()
