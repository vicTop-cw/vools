"""全量合规检查脚本"""
import ast, os, sys

base = 'vools'
report = []

# --- 1. __all__ ---
all_miss = []
for r, _, fs in os.walk(base):
    for fn in fs:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(r, fn)
        rel = os.path.relpath(p, base).replace('\\', '/')
        if fn.endswith('__init__.py'):
            continue
        src = open(p, encoding='utf-8').read()
        if '__all__' not in src:
            all_miss.append(rel)
report.append(f"1. Missing __all__: {len(all_miss)}")
for x in sorted(all_miss):
    report.append(f"   {x}")

# --- 2. README ---
pkg_set = set()
for r, _, fs in os.walk(base):
    if '__init__.py' in fs:
        pkg_set.add(os.path.relpath(r, base).replace('\\', '/'))
readme_miss = []
for p in sorted(pkg_set):
    if not os.path.exists(os.path.join(base, p.replace('/', '\\'), 'README.md')):
        readme_miss.append(p)
report.append(f"\n2. Missing README: {len(readme_miss)}")
for x in readme_miss:
    report.append(f"   {x}")

# --- 3. Return annotations ---
ret_miss = []
for r, _, fs in os.walk(base):
    for fn in fs:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(r, fn)
        rel = os.path.relpath(p, base).replace('\\', '/')
        tree = ast.parse(open(p, encoding='utf-8').read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                if node.returns is None:
                    ret_miss.append(f"{rel}:L{node.lineno} def {node.name}")
            if isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith('_'):
                        if m.returns is None:
                            ret_miss.append(f"{rel}:L{m.lineno} {node.name}.{m.name}")
report.append(f"\n3. Missing return annotations: {len(ret_miss)}")
for x in sorted(ret_miss):
    report.append(f"   {x}")

# --- 4. Missing docstrings ---
doc_miss = []
for r, _, fs in os.walk(base):
    for fn in fs:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(r, fn)
        rel = os.path.relpath(p, base).replace('\\', '/')
        tree = ast.parse(open(p, encoding='utf-8').read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith('_'):
                        has_doc = bool(
                            m.body and isinstance(m.body[0], ast.Expr)
                            and isinstance(m.body[0].value, ast.Constant)
                        )
                        if not has_doc:
                            doc_miss.append(f"{rel}:L{m.lineno} {node.name}.{m.name}")
report.append(f"\n4. Missing docstrings (public methods): {len(doc_miss)}")
for x in sorted(doc_miss):
    report.append(f"   {x}")

# Print
print('\n'.join(report))
print(f"\n=== Summary ===")
print(f"__all__: {len(all_miss)} | README: {len(readme_miss)} | Annotations: {len(ret_miss)} | Docstrings: {len(doc_miss)}")
