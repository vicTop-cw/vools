"""Fix remaining 4 files with do() indentation errors"""
import py_compile, os

ROOT = r'E:\IDEProjects\AI\vools'
files = ['vools/config.py', 'vools/decorators/curry_decorator.py', 
         'vools/serialize/decorators.py', 'vools/utils/stuff.py']

for rel in files:
    path = os.path.join(ROOT, rel)
    try:
        py_compile.compile(path, doraise=True)
        print(f'{rel}: OK')
    except py_compile.PyCompileError as e:
        print(f'{rel}: {e}')
        # Read the file and find the do() method, check its indentation
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the problematic do() method and its context
        for i, line in enumerate(lines):
            if 'def do(self, f=print' in line:
                indent = len(line) - len(line.lstrip())
                # Look at surrounding lines for context
                print(f'  Line {i+1}: indent={indent}, prev={repr(lines[i-1].rstrip() if i>0 else "")}')
                print(f'  Content: {line.rstrip()}')
                if i+1 < len(lines):
                    print(f'  Next: {repr(lines[i+1].rstrip())}')
