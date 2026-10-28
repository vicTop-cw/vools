# -*- coding: utf-8 -*-
"""第 11 轮审计：stats/cleanup/migrate/register 四类「写了但没接线」扫描。"""
import ast
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')
sys.stdout.reconfigure(encoding='utf-8')

CATEGORIES = [
    ('stats', re.compile(r'^(?:_)?(stats?|count|summary|report|metric|aggregate|tally|histogram)\w*$', re.I)),
    ('cleanup', re.compile(r'^(?:_)?(cleanup|clean|gc|purge|prune|invalidate|reset|clear|remove_all)\w*$', re.I)),
    ('migrate', re.compile(r'^(?:_)?(migrate|upgrade|backfill|convert|migrate_)\w*$', re.I)),
    ('register', re.compile(r'^(?:_)?(enable|disable|register|subscribe|unsubscribe|hook|attach|install_hook|on_event|emit|dispatch)\w*$', re.I)),
]


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
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')

        def walk(node, prefix=''):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for cat, rx in CATEGORIES:
                        if rx.match(ch.name):
                            out.append({'name': ch.name, 'cat': cat,
                                        'file': rel, 'line': ch.lineno,
                                        'qual': prefix + ch.name})
                            break
                    walk(ch, prefix + ch.name + '.')
                elif isinstance(ch, ast.ClassDef):
                    walk(ch, prefix + ch.name + '.')
        walk(tree)
    return out


def main():
    defs = collect()
    counts = defaultdict(int)
    for d in defs:
        counts[d['cat']] += 1
    print('枚举总数 %d | 分类分布 %s' % (len(defs), dict(counts)))

    prod = {}
    tests = {}
    for path in py_files(PKG):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        prod[rel] = read(path)
    test_text = '\n'.join(read(p) for p in py_files(TESTS))

    rows = []
    for d in defs:
        name = d['name']
        rx = re.compile(r'\b%s\b' % re.escape(name))
        # 产品里的引用（含注释/字符串，稍后再按行判断）
        refs = {}
        for rel, text in prod.items():
            hits = []
            for m in rx.finditer(text):
                ln = text.count('\n', 0, m.start()) + 1
                line = text.splitlines()[ln - 1]
                if re.match(r'\s*(async\s+)?def\s+%s\b' % re.escape(name), line):
                    continue
                hits.append((ln, line.strip()[:100]))
            if hits:
                refs[rel] = hits
        tcount = len(rx.findall(test_text))
        cross = {f: v for f, v in refs.items() if f != d['file']}
        same = refs.get(d['file'], [])
        if cross:
            status = 'prod_cross'
        elif same:
            status = 'prod_same'
        elif tcount:
            status = 'only_tests'
        else:
            status = 'zero'
        d.update(dict(status=status, refs=refs, tests=tcount, same=same, cross=cross))
        rows.append(d)

    for cat in ('stats', 'cleanup', 'migrate', 'register'):
        print('\n########## %s ##########' % cat)
        for d in sorted([r for r in rows if r['cat'] == cat],
                        key=lambda x: x['file']):
            print('%-46s %s:%d  %-11s tests=%d' % (
                d['qual'], d['file'], d['line'], d['status'], d['tests']))
            if d['status'] in ('prod_same', 'only_tests'):
                for ln, line in d['same'][:2]:
                    print('      same:%d  %s' % (ln, line))
                if d['status'] == 'only_tests':
                    for f, hits in list(d['refs'].items())[:1]:
                        for ln, line in hits[:1]:
                            print('      prod:%s:%d  %s' % (f.split('/')[-1], ln, line))


if __name__ == '__main__':
    main()
