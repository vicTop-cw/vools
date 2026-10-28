"""只读审计：静态校验 vools.actus 内部所有 `from vools.actus.X import Y` 是否可解析。

只 import 模块、取属性，不执行任何 CLI 路径。产出不可解析的 (文件:行, 模块, 名字)。
"""
import ast
import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)

bad = []
for dirpath, _dirnames, filenames in os.walk(os.path.join(ROOT, 'vools', 'actus')):
    if '__pycache__' in dirpath:
        continue
    for fn in filenames:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(dirpath, fn)
        try:
            tree = ast.parse(open(path, encoding='utf-8').read())
        except SyntaxError as exc:
            bad.append((path, 0, '<syntax>', str(exc)))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            mod = node.module
            if not (mod == 'vools.actus' or mod.startswith('vools.actus.')):
                continue
            if node.level:      # 相对导入，父模块不一定可直接 import，跳过
                continue
            try:
                target = importlib.import_module(mod)
            except Exception as exc:
                bad.append((path, node.lineno, mod, 'IMPORT-FAIL: %s' % exc))
                continue
            for alias in node.names:
                if alias.name == '*':
                    continue
                if not hasattr(target, alias.name):
                    bad.append((path, node.lineno, mod, 'MISSING: %s' % alias.name))

for path, lineno, mod, why in bad:
    rel = os.path.relpath(path, ROOT)
    print('%s:%d | %s | %s' % (rel, lineno, mod, why))
print('\n合计不可解析 import：%d' % len(bad))
