"""Fix ALL do() method indentation issues across 15 files"""
import os

ROOT = r'E:\IDEProjects\AI\vools'
files_to_fix = [
    r'vools\crypto\core.py',
    r'vools\decorators\rself.py',
    r'vools\encoding\core.py',
    r'vools\functional\placeholder.py',
    r'vools\functional\placeholder_impl.py',
    r'vools\functional\result.py',
    r'vools\functional\__init__.py',
    r'vools\oop\calltype.py',
    r'vools\oop\mixer.py',
    r'vools\reactive\core\observable.py',
    r'vools\reactive\core\subject.py',
    r'vools\serialize\callable\__init__.py',
    r'vools\task\core\models.py',
    r'vools\task\rules\engine.py',
    r'vools\task\rules\rule.py',
]

def fix_indent(text, file_path):
    """Fix do() method indentation by finding the enclosing class"""
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith('def do(self, f=print'):
            # Look backwards for the nearest class definition
            current_indent = len(line) - len(stripped)
            class_indent = 0
            for j in range(i-1, -1, -1):
                prev = lines[j]
                ps = prev.lstrip()
                if ps.startswith('class '):
                    class_indent = len(prev) - len(ps)
                    break
            correct_indent = class_indent + 4
            if current_indent != correct_indent:
                # Fix this line and all following do() method lines
                k = i
                while k < len(lines):
                    kl = lines[k]
                    ks = kl.lstrip()
                    if ks and not ks.startswith('#') and not ks.startswith('"""') and not ks.startswith("'''"):
                        k_indent = len(kl) - len(ks)
                        if k_indent <= current_indent and k != i:
                            # We've reached the end of the do method
                            break
                        if k_indent >= current_indent:
                            # Fix indentation
                            extra = k_indent - current_indent
                            lines[k] = ' ' * (correct_indent + extra) + ks
                    elif ks.startswith('"""') or ks.startswith("'''"):
                        # Fix docstring lines
                        k_indent = len(kl) - len(ks)
                        if k_indent >= current_indent:
                            extra = k_indent - current_indent
                            lines[k] = ' ' * (correct_indent + extra) + ks
                    k += 1
                print(f'  Fixed: {file_path}:{i+1} indent {current_indent}->{correct_indent}')
                i = k
                continue
        result.append(line)
        i += 1
    return '\n'.join(result)

for rel in files_to_fix:
    path = os.path.join(ROOT, rel)
    with open(path, encoding='utf-8') as f:
        text = f.read()
    fixed = fix_indent(text, rel)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)

print('\n[DONE] Checking for remaining errors...')

# Verify
import subprocess
errors = []
for rel in files_to_fix:
    path = os.path.join(ROOT, rel)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    if 'def do(self, f=print' not in content:
        continue
    try:
        compile(content, path, 'exec')
    except IndentationError as e:
        errors.append((rel, str(e)))

if errors:
    print(f'\n[ERR] {len(errors)} remaining:')
    for rel, err in errors:
        print(f'  {rel}: {err}')
else:
    print('[OK] All indentation fixed!')
