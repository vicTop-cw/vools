"""Fix ALL do() method indentation across all files"""
import os, re

ROOT = r'E:\IDEProjects\AI\vools'
DO_SRC = '''{indent}def do(self, f=print, pre_f=None, sub_f=None):
{indent}    """Apply a function for side effects, return self.

{indent}    Args:
{indent}        f: Function to apply (default print)
{indent}        pre_f: Pre-processing function
{indent}        sub_f: Post-processing function (no return value expected)

{indent}    Returns:
{indent}        self, for chaining
{indent}    """
{indent}    rs = self
{indent}    if pre_f:
{indent}        rs = pre_f(rs)
{indent}    rs = f(rs)
{indent}    if sub_f:
{indent}        sub_f(rs)
{indent}    return self'''

# Pattern to match any do() method (including wrong indentation)
# Match from 'def do(self, f=print' to 'return self'
DO_PATTERN = re.compile(
    r'([ \t]*)def do\(self, f=print, pre_f=None, sub_f=None\).*?return self\n',
    re.DOTALL
)

fixed_count = 0
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fname in files:
        if not fname.endswith('.py'):
            continue
        path = os.path.join(root, fname)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        
        if 'def do(self, f=print' not in text:
            continue
        
        original = text
        # Find each do method and fix its indentation
        def fix_match(m):
            indent = m.group(1)
            # Calculate correct indentation by looking backward for class
            pos = m.start()
            before = text[:pos]
            lines = before.split('\n')
            class_indent = 0
            for line in reversed(lines):
                stripped = line.strip()
                if stripped.startswith('class '):
                    class_indent = len(line) - len(stripped)
                    break
                elif stripped.startswith('@') or stripped == '':
                    continue
            correct_indent = ' ' * (class_indent + 4)
            return DO_SRC.format(indent=correct_indent) + '\n'
        
        text = DO_PATTERN.sub(fix_match, text)
        
        if text != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            fixed_count += 1
            print(f'  Fixed: {os.path.relpath(path, ROOT)}')

# Verify all files compile
print(f'\n[OK] Fixed {fixed_count} files')
compile_errors = []
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fname in files:
        if not fname.endswith('.py'):
            continue
        path = os.path.join(root, fname)
        try:
            compile(open(path, encoding='utf-8').read(), path, 'exec')
        except IndentationError as e:
            compile_errors.append((path, str(e)))

if compile_errors:
    print(f'\n[ERR] {len(compile_errors)} files with compile errors:')
    for p, e in compile_errors:
        print(f'  {p}: {e}')
else:
    print('[OK] All files compile cleanly')
