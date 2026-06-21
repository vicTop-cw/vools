"""Fix remaining 4 broken files - remove broken do() methods"""
import os, re

ROOT = r'E:\IDEProjects\AI\vools'
fixes = {
    'vools/config.py': [
        # Remove do() method placed after class docstring
        ('\n    def do(self, f=print, pre_f=None, sub_f=None):\n        """Apply a function for side effects, return self.\n\n        Args:\n            f: Function to apply (default print)\n            pre_f: Pre-processing function\n            sub_f: Post-processing function (no return value expected)\n\n        Returns:\n            self, for chaining\n        """\n        rs = self\n        if pre_f:\n            rs = pre_f(rs)\n        rs = f(rs)\n        if sub_f:\n            sub_f(rs)\n        return self', ''),
    ],
    'vools/decorators/curry_decorator.py': [
        # Remove do() at indent 4 (line 127)
        ('\n    def do(self, f=print, pre_f=None, sub_f=None):\n        """Apply a function for side effects, return self.\n\n        Args:\n            f: Function to apply (default print)\n            pre_f: Pre-processing function\n            sub_f: Post-processing function (no return value expected)\n\n        Returns:\n            self, for chaining\n        """\n        rs = self\n        if pre_f:\n            rs = pre_f(rs)\n        rs = f(rs)\n        if sub_f:\n            sub_f(rs)\n        return self', ''),
        # Remove do() at indent 8 (line 168)
        ('\n        def do(self, f=print, pre_f=None, sub_f=None):\n            """Apply a function for side effects, return self.\n\n            Args:\n                f: Function to apply (default print)\n                pre_f: Pre-processing function\n                sub_f: Post-processing function (no return value expected)\n\n            Returns:\n                self, for chaining\n            """\n            rs = self\n            if pre_f:\n                rs = pre_f(rs)\n            rs = f(rs)\n            if sub_f:\n                sub_f(rs)\n            return self', ''),
    ],
    'vools/serialize/decorators.py': [
        # Remove do() at indent 12 (line 124, 179, 230)
        ('\n            def do(self, f=print, pre_f=None, sub_f=None):\n                """Apply a function for side effects, return self.\n\n                Args:\n                    f: Function to apply (default print)\n                    pre_f: Pre-processing function\n                    sub_f: Post-processing function (no return value expected)\n\n                Returns:\n                    self, for chaining\n                """\n                rs = self\n                if pre_f:\n                    rs = pre_f(rs)\n                rs = f(rs)\n                if sub_f:\n                    sub_f(rs)\n                return self', ''),
    ],
    'vools/utils/stuff.py': [
        # Remove do() at indent 4
        ('\n    def do(self, f=print, pre_f=None, sub_f=None):\n        """Apply a function for side effects, return self.\n\n        Args:\n            f: Function to apply (default print)\n            pre_f: Pre-processing function\n            sub_f: Post-processing function (no return value expected)\n\n        Returns:\n            self, for chaining\n        """\n        rs = self\n        if pre_f:\n            rs = pre_f(rs)\n        rs = f(rs)\n        if sub_f:\n            sub_f(rs)\n        return self', ''),
        # Remove do() at indent 8
        ('\n        def do(self, f=print, pre_f=None, sub_f=None):\n            """Apply a function for side effects, return self.\n\n            Args:\n                f: Function to apply (default print)\n                pre_f: Pre-processing function\n                sub_f: Post-processing function (no return value expected)\n\n            Returns:\n                self, for chaining\n            """\n            rs = self\n            if pre_f:\n                rs = pre_f(rs)\n            rs = f(rs)\n            if sub_f:\n                sub_f(rs)\n            return self', ''),
    ],
}

for rel, replacements in fixes.items():
    path = os.path.join(ROOT, rel)
    with open(path, encoding='utf-8') as f:
        text = f.read()
    for old, new in replacements:
        text = text.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'[OK] Fixed {rel}')

# Verify
print()
import py_compile
for rel in fixes:
    path = os.path.join(ROOT, rel)
    try:
        py_compile.compile(path, doraise=True)
        print(f'[OK] {rel} compiles')
    except py_compile.PyCompileError as e:
        print(f'[ERR] {rel}: {e}')
