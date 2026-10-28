# -*- coding: utf-8 -*-
"""第二轮：统计"裸引用"（表驱动/动态接线）与真实调用，区分死代码 vs 动态接线。"""
import ast
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')
PATTERN = re.compile(r'^(?:_)?(validate|verify|check|audit|inspect|ensure)_?\w*$', re.I)
sys.stdout.reconfigure(encoding='utf-8')


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


def collect():
    out = []
    for path in py_files(PKG):
        text = read(path)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = os.path.relpath(path, ROOT).replace('\\', '/')

        def walk(node):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if PATTERN.match(ch.name):
                        out.append((ch.name, rel, ch.lineno))
                    walk(ch)
                elif isinstance(ch, ast.ClassDef):
                    walk(ch)
        walk(tree)
    return out


def scan(defs):
    prod_bare = defaultdict(lambda: defaultdict(list))   # name -> file -> lines
    test_bare = defaultdict(lambda: defaultdict(list))
    call_re = {}
    for name, _rel, _ln in defs:
        call_re[name] = re.compile(r'(?<![\w.])%s\s*\(' % re.escape(name))
    for path in py_files(PKG):
        text = read(path)
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        for name in call_re:
            for m in re.finditer(r'\b%s\b' % re.escape(name), text):
                line = text.count('\n', 0, m.start()) + 1
                line_text = text.splitlines()[line - 1]
                if re.match(r'\s*(async\s+)?def\s+%s\b' % re.escape(name), line_text):
                    continue
                prod_bare[name][rel].append(line)
    for path in py_files(TESTS):
        text = read(path)
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        for name in call_re:
            for m in re.finditer(r'\b%s\b' % re.escape(name), text):
                test_bare[name][rel].append(text.count('\n', 0, m.start()) + 1)
    rows = []
    for name, rel, ln in defs:
        prod = prod_bare.get(name, {})
        tests = test_bare.get(name, {})
        cross = {f: v for f, v in prod.items() if f != rel}
        same = {f: v for f, v in prod.items() if f == rel}
        if cross:
            status = 'prod_cross_file'
        elif same:
            status = 'prod_same_module'
        elif tests:
            status = 'only_tests'
        else:
            status = 'zero'
        rows.append(dict(name=name, file=rel, line=ln, status=status,
                         prod=prod, tests=tests))
    return rows


def main():
    rows = scan(collect())
    groups = defaultdict(list)
    for r in rows:
        groups[r['status']].append(r)
    print('总数 %d | %s' % (len(rows), {k: len(v) for k, v in groups.items()}))
    for status in ('zero', 'only_tests', 'prod_same_module'):
        print('\n########## %s ##########' % status)
        for r in sorted(groups[status], key=lambda x: (x['file'], x['line'])):
            refs = ''
            if status != 'zero':
                items = list(r['prod'].items()) or list(r['tests'].items())
                refs = ' | '.join('%s:%s' % (f.split('/')[-1], v[:3]) for f, v in items[:2])
            print('%-42s %s:%s   %s' % (r['name'], r['file'], r['line'], refs))


if __name__ == '__main__':
    main()
