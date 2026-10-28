# -*- coding: utf-8 -*-
"""`__all__` 导出但无跨模块引用的扫描（只看校验/安全相关模块）。"""
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')
MODULES = ['validate.py', 'security.py', 'adapter.py', 'trust_model.py', 'registry.py',
           'omega_strong.py', 'sigma.py', 'notify.py', 'dependency.py']
sys.stdout.reconfigure(encoding='utf-8')


def files(base):
    for dp, dirs, fs in os.walk(base):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in fs:
            if f.endswith('.py'):
                yield os.path.join(dp, f)


prod_text = {}
for p in files(PKG):
    rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
    prod_text[rel] = open(p, encoding='utf-8', errors='replace').read()
test_text = '\n'.join(open(p, encoding='utf-8', errors='replace').read()
                      for p in files(TESTS))

for mod in MODULES:
    path = os.path.join(PKG, mod)
    text = open(path, encoding='utf-8').read()
    tree = ast.parse(text)
    exported = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') == '__all__' for t in node.targets):
            try:
                exported = ast.literal_eval(node.value)
            except Exception:
                exported = None
    if not exported:
        continue
    dead = []
    for name in exported:
        ref = re.compile(r'\b%s\b' % re.escape(name))
        ext = sum(len(ref.findall(t)) for f, t in prod_text.items()
                  if f != 'vools/actus/' + mod)
        tst = len(ref.findall(test_text))
        if ext == 0:
            dead.append((name, tst))
    if dead:
        print('%-16s __all__ 中无跨模块引用（%d 个）:' % (mod, len(dead)))
        for n, t in dead:
            print('   - %-38s tests 引用 %d' % (n, t))
