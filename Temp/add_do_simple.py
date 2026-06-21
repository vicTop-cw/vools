"""Add do() method using pure text approach - find last def at class indent"""
import os

ROOT = r'E:\IDEProjects\AI\vools'
SKIP_CLASSES = {'_OnceWrapper', '_NONE', '_IndexHolder', 'Input', 'KEYBDINPUT', 'KBDLLHOOKSTRUCT',
                'MOUSEINPUT', 'MSLLHOOKSTRUCT', 'INPUT'}
SKIP_PREFIX = ('Test', 'Example', '_')
SKIP_SUFFIX = ('Meta', 'Error', 'Exception')

DO_LINES = [
    'def do(self, f=print, pre_f=None, sub_f=None):',
    '    """Apply a function for side effects, return self.',
    '',
    '    Args:',
    '        f: Function to apply (default print)',
    '        pre_f: Pre-processing function',
    '        sub_f: Post-processing function (no return value expected)',
    '',
    '    Returns:',
    '        self, for chaining',
    '    """',
    '    rs = self',
    '    if pre_f:',
    '        rs = pre_f(rs)',
    '    rs = f(rs)',
    '    if sub_f:',
    '        sub_f(rs)',
    '    return self',
]

def has_enum_base(source, class_line_idx):
    """Check if class has Enum base by looking at the class definition line"""
    line = source[class_line_idx].strip()
    return any(x in line for x in ('Enum', 'IntEnum', 'IntFlag', 'Flag'))

def has_do_method(source, class_indent, start, end):
    """Check if class already has a do() method"""
    for i in range(start, min(end, len(source))):
        line = source[i]
        stripped = line.lstrip()
        if stripped.startswith('def do('):
            line_indent = len(line) - len(stripped)
            if line_indent == class_indent:
                return True
    return False

total = 0
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
        
        modified = False
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()
            if not stripped.startswith('class '):
                i += 1
                continue
            
            # Get class name and indent
            class_indent = len(line) - len(stripped)
            name = stripped.split()[1].split('(')[0].split(':')[0].strip()
            
            # Skip conditions
            if any(name.startswith(p) for p in SKIP_PREFIX) and name not in SKIP_CLASSES:
                i += 1
                continue
            if name.endswith('Meta') or name in SKIP_CLASSES:
                i += 1
                continue
            
            # Find class end (next line with same or less indent)
            class_end = i + 1
            while class_end < len(lines):
                nl = lines[class_end]
                ns = nl.lstrip()
                if ns and not ns.startswith('#') and not ns.startswith('"""') and not ns.startswith("'''"):
                    n_indent = len(nl) - len(ns)
                    if n_indent <= class_indent and ns != '...':
                        break
                class_end += 1
            
            # Body lines are i+1 to class_end-1
            body_start = i + 1
            body_end = class_end
            
            if body_start >= body_end:
                i = class_end
                continue
            
            # Check for __slots__ in class body
            has_slots = False
            for j in range(body_start, body_end):
                bl = lines[j]
                if bl.lstrip().startswith('__slots__'):
                    has_slots = True
                    break
            if has_slots:
                i = class_end
                continue
            
            # Check Enum base
            if has_enum_base(lines, i):
                i = class_end
                continue
            
            # Check existing do()
            if has_do_method(lines, class_indent + 4, body_start, body_end):
                i = class_end
                continue
            
            # Find the LAST method in the class body
            last_method_idx = -1
            for j in range(body_start, body_end):
                bl = lines[j]
                bs = bl.lstrip()
                b_indent = len(bl) - len(bs)
                if bs.startswith('def ') and b_indent == class_indent + 4:
                    last_method_idx = j
            
            if last_method_idx < 0:
                i = class_end
                continue
            
            # Insert do() method BEFORE the last method
            do_indent = ' ' * (class_indent + 4)
            do_text = '\n' + '\n'.join(do_indent + dl if dl else '' for dl in DO_LINES) + '\n'
            
            lines.insert(last_method_idx, do_text)
            modified = True
            total += 1
            
            # class_end shifts by 1 due to insertion
            i = last_method_idx + 12  # skip past inserted do method
        
        if modified:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            rel = os.path.relpath(path, ROOT)
            print(f'  {rel}')

# Verify
print(f'\n[DONE] Added do() to {total} classes')
print('[VERIFY] Checking compilation...')
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
            compile(src, path, 'exec')
        except (SyntaxError, IndentationError) as e:
            errors.append(f'{os.path.relpath(path, ROOT)}')

if errors:
    print(f'[ERR] {len(errors)} files with errors:')
    for e in errors[:10]:
        print(f'  {e}')
    if len(errors) > 10:
        print(f'  ... and {len(errors)-10} more')
else:
    print('[OK] All files compile cleanly')
