# -*- coding: utf-8 -*-
"""第 11 轮补充：后缀式 stats/summary/count/report 扫描 + 短名单引用证据（含 tests）。"""
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')
sys.stdout.reconfigure(encoding='utf-8')

SUFFIX = re.compile(r'(?:_|^)(stats|summary|count|counts|report|metrics?|usage|totals?)$', re.I)


def py_files(base):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def read(p):
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


defs = []
for path in py_files(PKG):
    text = read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    rel = os.path.relpath(path, ROOT).replace(os.sep, '/')

    def walk(node, prefix=''):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if SUFFIX.search(ch.name):
                    defs.append((ch.name, rel, ch.lineno, prefix + ch.name))
                walk(ch, prefix + ch.name + '.')
            elif isinstance(ch, ast.ClassDef):
                walk(ch, prefix + ch.name + '.')
    walk(tree)

prod = {os.path.relpath(p, ROOT).replace(os.sep, '/'): read(p) for p in py_files(PKG)}
test_text = '\n'.join(read(p) for p in py_files(TESTS))

print('后缀式统计函数 %d 个' % len(defs))
for name, rel, ln, qual in sorted(defs, key=lambda x: (x[1], x[2])):
    rx = re.compile(r'\b%s\b' % re.escape(name))
    hits = []
    for f, text in prod.items():
        for m in rx.finditer(text):
            l2 = text.count('\n', 0, m.start()) + 1
            line = text.splitlines()[l2 - 1]
            if re.match(r'\s*(async\s+)?def\s+%s\b' % re.escape(name), line):
                continue
            hits.append((f, l2, line.strip()[:90]))
    tc = len(rx.findall(test_text))
    cross = [h for h in hits if h[0] != rel]
    same = [h for h in hits if h[0] == rel]
    status = ('prod_cross' if cross else 'prod_same' if same
              else 'only_tests' if tc else 'zero')
    print('\n%-46s %s:%d  %s  tests=%d' % (qual, rel, ln, status, tc))
    for f, l2, line in (cross or same)[:3]:
        print('   P %s:%d  %s' % (f.split('/')[-1], l2, line))
    if status == 'only_tests':
        for m in list(rx.finditer(test_text))[:2]:
            l2 = test_text.count('\n', 0, m.start()) + 1
            print('   T test:%d  %s' % (l2, test_text.splitlines()[l2 - 1].strip()[:90]))
