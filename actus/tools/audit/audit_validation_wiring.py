# -*- coding: utf-8 -*-
"""审计：枚举校验/验证类函数并统计真实调用方（只读，输出表格原料）。"""
import ast
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')

PATTERN = re.compile(r'^(?:_)?(validate|verify|check|audit|inspect|ensure)_?\w*$', re.I)
ALSO = re.compile(r'^(stats|summary|cleanup|clean|gc)_\w+$', re.I)

sys.stdout.reconfigure(encoding='utf-8')


def py_files(base):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def collect_defs():
    defs = []
    for path in py_files(PKG):
        text = read(path)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            print('SKIP parse error %s: %s' % (path, exc))
            continue
        rel = os.path.relpath(path, ROOT).replace('\\', '/')

        def walk(node, prefix=''):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = prefix + child.name
                    if PATTERN.match(child.name) or ALSO.match(child.name):
                        defs.append({
                            'name': child.name, 'qual': qual, 'file': rel,
                            'line': child.lineno,
                            'private': child.name.startswith('_'),
                            'group': 'val' if PATTERN.match(child.name) else 'aux',
                        })
                    walk(child, qual + '.')
                elif isinstance(child, ast.ClassDef):
                    walk(child, prefix + child.name + '.')
        walk(tree)
    return defs


def count_refs(name):
    """返回 {file: [lineno...]}（产品代码中的引用；tests 单独）。"""
    ref = defaultdict(list)
    tests_ref = defaultdict(list)
    word = re.compile(r'(?<![\w.])%s\s*\(' % re.escape(name))
    attr = re.compile(r'\.%s\s*\(' % re.escape(name))
    for path in py_files(PKG):
        text = read(path)
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        for m in word.finditer(text):
            line = line_of(text, m.start())
            if re.match(r'^(\s*)def\s', text[text.rfind('\n', 0, m.start()) + 1:m.start()].lstrip()
                        if False else '') and False:
                pass
            ref[rel].append(line)
        for m in attr.finditer(text):
            ref[rel].append(line_of(text, m.start()))
    for path in py_files(TESTS):
        text = read(path)
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        for m in word.finditer(text):
            tests_ref[rel].append(line_of(text, m.start()))
        for m in attr.finditer(text):
            tests_ref[rel].append(line_of(text, m.start()))
    return ref, tests_ref


def strip_def_self(ref, file_rel, name):
    """去掉定义行自身（def name(）的命中。"""
    out = {}
    for f, lines in ref.items():
        kept = []
        for ln in lines:
            if f == file_rel:
                # 读该行判断是否 def 行
                pass
            kept.append(ln)
        out[f] = sorted(set(kept))
    return out


def is_def_line(file_rel, lineno, name):
    path = os.path.join(ROOT, file_rel)
    text = read(path).splitlines()
    if 0 < lineno <= len(text):
        return re.match(r'\s*(async\s+)?def\s+%s\b' % re.escape(name), text[lineno - 1]) is not None
    return False


def main():
    defs = collect_defs()
    print('枚举函数总数: %d（val=%d, aux=%d）' % (
        len(defs), sum(1 for d in defs if d['group'] == 'val'),
        sum(1 for d in defs if d['group'] == 'aux')))
    rows = []
    for d in defs:
        ref, tref = count_refs(d['name'])
        # 清理：同文件定义行自身、以及"仅调用但定义自身"误命中
        prod = {}
        for f, lines in ref.items():
            kept = [ln for ln in lines if not is_def_line(f, ln, d['name'])]
            if kept:
                prod[f] = kept
        prod_total = sum(len(v) for v in prod.values())
        test_total = sum(len(v) for v in tref.values())
        cross = {f: v for f, v in prod.items() if f != d['file']}
        same = {f: v for f, v in prod.items() if f == d['file']}
        if cross:
            status = 'product_called'
        elif same:
            status = 'same_module_only'
        elif test_total:
            status = 'only_tests'
        else:
            status = 'zero_refs'
        rows.append(dict(d, prod=prod, tests=tref, prod_total=prod_total,
                         test_total=test_total, cross=cross, same=same,
                         status=status))

    from collections import Counter
    c = Counter(r['status'] for r in rows)
    print('状态分布:', dict(c))
    for status in ('only_tests', 'zero_refs', 'same_module_only'):
        print('\n########## %s ##########' % status)
        for r in rows:
            if r['status'] == status:
                print('%-45s %s:%d  prod=%d tests=%d %s' % (
                    r['qual'], r['file'], r['line'], r['prod_total'],
                    r['test_total'], 'PRIVATE' if r['private'] else ''))
                if r['status'] == 'zero_refs':
                    continue
                for f, lines in list(r['prod'].items())[:3]:
                    print('    prod ref %s:%s' % (f, lines[:4]))
                for f, lines in list(r['tests'].items())[:2]:
                    print('    test ref %s:%s' % (f, lines[:3]))


if __name__ == '__main__':
    main()
