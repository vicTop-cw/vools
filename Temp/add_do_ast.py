"""Add do() method using AST - correct indentation guaranteed"""
import os, ast

ROOT = r'E:\IDEProjects\AI\vools'

DO_METHOD_SRC = '''\
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

def class_table(source):
    """Return list of (class_name, line_start, line_end, indent) for each class"""
    lines = source.split('\n')
    tree = ast.parse(source)
    classes = []
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
        # Check __slots__
        has_slots = any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == '__slots__' for t in n.targets
            ) for n in node.body
        )
        if has_slots:
            continue
        # Check Enum base
        is_enum = any(
            isinstance(b, (ast.Name, ast.Attribute)) and (getattr(b, 'id', None) or getattr(b, 'attr', None)) in ('Enum', 'IntEnum', 'IntFlag', 'Flag')
            for b in node.bases
        )
        if is_enum:
            continue
        # Check existing do()
        has_do = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'do'
            for n in node.body
        )
        if has_do:
            continue
        # Get class definition line for indentation
        line_idx = node.lineno - 1
        class_line = lines[line_idx]
        indent = len(class_line) - len(class_line.lstrip())
        # Get body range
        body = node.body
        if not body:
            continue
        # Find the line of the last body element
        last_line = max(
            n.lineno if isinstance(n, ast.stmt) else 0
            for n in body
        )
        classes.append((name, node.lineno, last_line, indent))
    return classes

fixed = 0
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding='utf-8') as f:
                source = f.read()
        except:
            continue
        
        classes = class_table(source)
        if not classes:
            continue
        
        lines = source.split('\n')
        modified = False
        
        # Process in reverse to preserve line numbers
        for cname, cl_start, cl_end, cindent in reversed(classes):
            # Insert do() method BEFORE the last body element (cl_end)
            insert_pos = cl_end  # 1-based, insert before this line
            i = ' ' * (cindent + 4)
            do_source = DO_METHOD_SRC.format(i=i)
            lines.insert(insert_pos, do_source)
            modified = True
            fixed += 1
        
        if modified:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            rel = os.path.relpath(path, ROOT)
            print(f'  {rel}: {", ".join(c[0] for c in classes)}')

# Verify compilation
print(f'\n[DONE] Added do() to {fixed} classes')
print('[VERIFY] Checking compilation...')
errs = []
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
            errs.append(f'{os.path.relpath(path, ROOT)}: {e}')

if errs:
    print(f'[ERR] {len(errs)} files:')
    for e in errs:
        print(f'  {e}')
else:
    print('[OK] All files compile cleanly')
