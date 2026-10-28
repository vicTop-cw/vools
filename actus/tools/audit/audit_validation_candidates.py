# -*- coding: utf-8 -*-
"""第三轮：候选函数的全部引用行（产品 / 测试），带行文本用于区分注释/导出/真实调用。"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')
sys.stdout.reconfigure(encoding='utf-8')

CANDIDATES = [
    'check_available', 'validate_adapter_spec', 'check_all', 'check_rules',
    'check_path', 'check_file_access', 'check_network_access',
    'check_schema_md_structure', 'check_classification', 'verify_spec',
    'check_scope_permission', 'verify_gate', 'check_gate',
    'cleanup_probe_tmpdir', 'add_rule', 'stats', 'scan_action',
    'validate_entry', 'validate_params', 'check_fingerprint',
]


def py_files(base):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


def scan(name, base, label):
    call_re = re.compile(r'\b%s\b' % re.escape(name))
    hits = []
    for path in py_files(base):
        text = open(path, 'r', encoding='utf-8', errors='replace').read()
        rel = os.path.relpath(path, ROOT).replace('\\', '/')
        for m in call_re.finditer(text):
            line_no = text.count('\n', 0, m.start()) + 1
            line = text.splitlines()[line_no - 1].strip()
            if re.match(r'(async\s+)?def\s+%s\b' % re.escape(name), line):
                continue
            hits.append((rel, line_no, line[:110]))
    return hits


for name in CANDIDATES:
    prod = scan(name, PKG, 'prod')
    tests = scan(name, TESTS, 'test')
    print('\n### %s  (prod=%d, tests=%d)' % (name, len(prod), len(tests)))
    for rel, ln, line in prod[:8]:
        print('  P %s:%s  %s' % (rel, ln, line))
    for rel, ln, line in tests[:5]:
        print('  T %s:%s  %s' % (rel, ln, line))
    if not prod and not tests:
        print('  （零命中）')
