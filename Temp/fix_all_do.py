"""Fix ALL do() method indentation across ALL files - comprehensive approach"""
import os, re

ROOT = r'E:\IDEProjects\AI\vools'

# The correct do() method template with {indent} placeholder
DO_TMPL = '''{i}def do(self, f=print, pre_f=None, sub_f=None):
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

# Match: from 'def do(self, f=print' through 'return self' (including body lines)
DO_RE = re.compile(
    r'^([ \t]*)def do\(self, f=print, pre_f=None, sub_f=None\).*?\n(.*?)return self',
    re.MULTILINE | re.DOTALL
)

fixed = 0
errors = []

for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        with open(path, 'rb') as f:
            raw = f.read()
        # Quick check: does this file contain the do method?
        if b'def do(self, f=print' not in raw:
            continue
        
        src = raw.decode('utf-8')
        orig = src
        
        # Find each do method
        idx = 0
        while True:
            m = DO_RE.search(src, idx)
            if not m:
                break
            do_indent = m.group(1)  # current indentation of 'def do'
            body = m.group(2)       # everything between def line and 'return self'
            
            # Look backward from the 'def do' position to find the class
            before = src[:m.start()]
            lines = before.split('\n')
            class_indent = 0
            for line in reversed(lines):
                st = line.strip()
                if st.startswith('class '):
                    class_indent = len(line) - len(st)
                    break
            correct = ' ' * (class_indent + 4)
            
            # If the current do_indent is wrong, replace
            if do_indent != correct:
                new_do = DO_TMPL.format(i=correct)
                src = src[:m.start()] + new_do + '\n' + src[m.end():]
                fixed += 1
                print(f'  fix: {os.path.relpath(path, ROOT)}@{m.start()}: indent {len(do_indent)}->{len(correct)}')
                idx = m.start() + len(new_do)
            else:
                idx = m.end()
        
        if src != orig:
            with open(path, 'wb') as f:
                f.write(src.encode('utf-8'))

print(f'\n[OK] Fixed {fixed} instances')

# Verify all files compile
print('[VERIFY] Checking compilation...')
compile_errors = []
for root, dirs, files in os.walk(os.path.join(ROOT, 'vools')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding='utf-8') as f:
                code = f.read()
            if 'def do(self, f=print' in code:
                compile(code, path, 'exec')
        except IndentationError as e:
            compile_errors.append((path, str(e)))

if compile_errors:
    print(f'[ERR] {len(compile_errors)} still failing:')
    for p, e in compile_errors:
        print(f'  {p}: {e}')
else:
    print('[OK] All files compile cleanly')
