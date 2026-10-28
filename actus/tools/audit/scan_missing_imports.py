# -*- coding: utf-8 -*-
"""全库扫描：函数内把 X 当模块用（X.attr），但模块级/函数内都没有 import X。"""
import ast, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MODULES = ('os','sys','json','io','time','re','subprocess','shutil','glob','base64',
           'hashlib','tempfile','threading','socket','urllib','datetime','pathlib',
           'random','uuid','math','sqlite3','logging','shlex','copy','traceback',
           'platform','getpass','stat','textwrap','itertools','collections','typing')
hits = []
for dirpath, _dirs, files in os.walk(os.path.join(ROOT, 'vools', 'actus')):
    if '__pycache__' in dirpath: continue
    for fn in files:
        if not fn.endswith('.py'): continue
        path = os.path.join(dirpath, fn)
        try:
            src = open(path, encoding='utf-8').read()
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError) as exc:
            hits.append((path, 0, '<parse>', str(exc))); continue
        mod_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                for a in node.names: mod_level.add((a.asname or a.name).split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names: mod_level.add(a.asname or a.name)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            local = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    for a in sub.names: local.add((a.asname or a.name).split('.')[0])
                elif isinstance(sub, ast.ImportFrom):
                    for a in sub.names: local.add(a.asname or a.name)
            for mod in MODULES:
                if mod in mod_level or mod in local: continue
                used = any(isinstance(s, ast.Attribute) and isinstance(s.value, ast.Name)
                           and s.value.id == mod for s in ast.walk(node))
                if used:
                    hits.append((path, node.lineno, node.name, mod))
for path, lineno, func, what in hits:
    print('%s:%s | %s | %s' % (os.path.relpath(path, ROOT), lineno, func, what))
print('\n合计:', len(hits))
