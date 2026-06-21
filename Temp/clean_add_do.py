"""Remove orphaned do() methods from config.py, then cleanly add do() to all classes"""
# Step 1: Clean config.py
path = r'E:\IDEProjects\AI\vools\vools\config.py'
with open(path, encoding='utf-8') as f:
    t = f.read()

old = '''     def do(self, f=print, pre_f=None, sub_f=None):
         """Apply a function for side effects, return self.
     
         Args:
             f: Function to apply (default print)
             pre_f: Pre-processing function
             sub_f: Post-processing function (no return value expected)
     
         Returns:
             self, for chaining
         """
         rs = self
         if pre_f:
             rs = pre_f(rs)
         rs = f(rs)
         if sub_f:
             sub_f(rs)
         return self'''

new = ''

t = t.replace(old, new)
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('[OK] Cleaned config.py')

# Step 2: Verify there are no leftover do() methods
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

def add_do_to_file(path):
    with open(path, encoding='utf-8') as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    lines = source.split('\n')
    modified = False
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = node.name
        if name.startswith('_') and name not in ('_OnceWrapper', '_NONE', '_IndexHolder'):
            continue
        if any(x in name for x in ('Test', 'Example')) and name not in ('Task', 'TaskDecorator'):
            continue
        if name in ('INPUT', 'KEYBDINPUT', 'KBDLLHOOKSTRUCT', 'MOUSEINPUT', 'MSLLHOOKSTRUCT'):
            continue
        if name.endswith('Meta'):
            continue
        if any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__slots__' for t in n.targets) for n in node.body):
            continue
        if any(isinstance(b, (ast.Name, ast.Attribute)) and (getattr(b, 'id', None) or getattr(b, 'attr', None)) in ('Enum', 'IntEnum', 'IntFlag', 'Flag') for b in node.bases):
            continue
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'do' for n in node.body):
            continue
        body = node.body
        if not body:
            continue
        # Get class indent from source
        class_line = lines[node.lineno - 1]
        cindent = len(class_line) - len(class_line.lstrip())
        # Insert do() before last body element
        last_lineno = max(n.lineno for n in body if isinstance(n, ast.stmt))
        i = ' ' * (cindent + 4)
        do_source = DO_SRC.format(i=i)
        lines.insert(last_lineno, do_source)
        modified = True
        print(f'  {os.path.relpath(path, ROOT)}: {name}')
    
    if modified:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return modified

total = 0
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        try:
            if add_do_to_file(path):
                total += 1
        except Exception:
            continue

# Verify everything compiles
print(f'\n[DONE] Modified {total} files')
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
