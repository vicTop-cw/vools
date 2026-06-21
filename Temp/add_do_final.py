"""Add do() method using simple text-based approach - reliable indentation"""
import os, ast

ROOT = r'E:\IDEProjects\AI\vools'

DO_SRC = '''\
{i}def do(self, f=print, pre_f=None, sub_f=None):
{i}    """Apply a function for side effects, return self.
{i}
{i}    Args:
{i}        f: Function to apply (default print)
{i}        pre_f: Pre-processing function
{i}        sub_f: Post-processing function (no return value expected)
{i}
{i}    Returns:
{i}        self, for chaining
{i}    """
{i}    rs = self
{i}    if pre_f:
{i}        rs = pre_f(rs)
{i}    rs = f(rs)
{i}    if sub_f:
{i}        sub_f(rs)
{i}    return self'''

def class_targets(path):
    """Return list of (class_indent, insert_line_index, class_name) or None if no class needs do()"""
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    
    try:
        tree = ast.parse(''.join(lines))
    except SyntaxError:
        return []
    
    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = node.name
        # Skip conditions
        if name.startswith('_') and name not in ('_OnceWrapper', '_NONE', '_IndexHolder'):
            continue
        if any(x in name for x in ('Test', 'Example')) and name not in ('Task', 'TaskDecorator'):
            continue
        if name in ('INPUT', 'KEYBDINPUT', 'KBDLLHOOKSTRUCT', 'MOUSEINPUT', 'MSLLHOOKSTRUCT'):
            continue
        if name.endswith('Meta'):
            continue
        # Check __slots__
        if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__slots__' for t in n.targets) for n in node.body):
            continue
        # Check Enum
        if any(isinstance(b, (ast.Name, ast.Attribute)) and (getattr(b, 'id', None) or getattr(b, 'attr', None)) in ('Enum', 'IntEnum', 'IntFlag', 'Flag') for b in node.bases):
            continue
        # Check existing do()
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'do' for n in node.body):
            continue
        if not node.body:
            continue
        
        # Get class indent
        class_line = lines[node.lineno - 1]
        cindent = len(class_line) - len(class_line.lstrip())
        
        # Find the class end: look from last body element's line forward
        # until we find a line with same or less indentation that's not empty/comment
        last_body_line = max(n.lineno for n in node.body if isinstance(n, ast.stmt)) - 1  # 0-indexed
        
        # Scan forward from last_body_line to find the actual end of class
        end_idx = last_body_line
        while end_idx < len(lines):
            sl = lines[end_idx].lstrip()
            if sl and not sl.startswith('#') and not sl.startswith('"""') and not sl.startswith("'''"):
                line_indent = len(lines[end_idx]) - len(sl)
                if line_indent <= cindent:
                    break
            end_idx += 1
        
        # Insert position: end of class (end_idx is first line OUTSIDE class)
        targets.append((cindent, end_idx, name))
    
    return targets

total = 0
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding='utf-8') as f:
                lines = f.readlines()
        except:
            continue
        
        targets = class_targets(path)
        if not targets:
            continue
        
        rel = os.path.relpath(path, ROOT)
        names = []
        for cindent, end_idx, cname in reversed(targets):
            i = ' ' * (cindent + 4)
            do_source = DO_SRC.format(i=i)
            lines.insert(end_idx, do_source)
            names.append(cname)
            total += 1
        
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f'  {rel}: {", ".join(names)}')

print(f'\n[DONE] Added do() to {total} classes')
print('[VERIFY] Compilation check...')
errors = []
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            if 'def do(self, f=print' in src:
                compile(src, path, 'exec')
        except IndentationError as e:
            errors.append(f'{os.path.relpath(path, ROOT)}: {e}')
        except SyntaxError as e:
            errors.append(f'{os.path.relpath(path, ROOT)}: {e}')

if errors:
    print(f'[ERR] {len(errors)} files with errors:')
    for e in errors:
        print(f'  {e}')
else:
    print('[OK] All files compile cleanly')
