"""仅补充 __all__（安全版，不改注解/docstring）"""
import ast, os

base = 'vools'
skip = {'__pycache__', '.git', '.pytest_cache', 'Temp'}

for r, dirs, fs in os.walk(base):
    dirs[:] = [d for d in dirs if d not in skip]
    for fname in fs:
        if not fname.endswith('.py'):
            continue
        p = os.path.join(r, fname)
        src = open(p, encoding='utf-8').read()
        if '__all__' in src or fname == '__init__.py':
            continue

        tree = ast.parse(src)
        names = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                names.append(node.name)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
                names.append(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and not t.id.startswith('_') and t.id != '__all__':
                        names.append(t.id)

        if not names:
            continue

        # 找插入位置
        tree = ast.parse(src)
        insert = 0
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                insert = node.end_lineno
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                insert = max(insert, node.end_lineno)

        lines = src.splitlines()
        lines.insert(insert, f'__all__ = {names!r}')
        open(p, 'w', encoding='utf-8').write('\n'.join(lines))
        print(f'  {os.path.relpath(p, base)}')
