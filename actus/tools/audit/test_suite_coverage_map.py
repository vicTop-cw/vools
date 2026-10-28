# -*- coding: utf-8 -*-
"""测试覆盖测绘：哪些 vools/actus 模块没有被任何测试文件引用/断言到。

只读审计脚本（不参与 pytest 收集：文件名不以 test_ 开头，且在 build/ 下）。
输出：
  1. 每个产品模块被 tests/ 引用的证据条数（import 形态 / 模块名 / 公开符号名）；
  2. 零引用模块清单（按行数排序）；
  3. 引用极少的 top 大模块（覆盖强度不足候选）。
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
TESTS = os.path.join(ROOT, 'tests')


def read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return ''


def public_symbols(src):
    names = re.findall(r'^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)', src, re.M)
    return [n for n in names if not n.startswith('_')]


def main():
    test_src = ''
    for name in sorted(os.listdir(TESTS)):
        if name.endswith('.py'):
            test_src += read(os.path.join(TESTS, name))

    rows = []
    for name in sorted(os.listdir(PKG)):
        path = os.path.join(PKG, name)
        if not os.path.isfile(path) or not name.endswith('.py'):
            continue
        if name in ('__init__.py',):
            continue
        mod = name[:-3]
        src = read(path)
        lines = src.count('\n') + 1
        syms = [s for s in public_symbols(src) if len(s) >= 5]
        refs = 0
        refs += len(re.findall(r'vools\.actus\.%s\b' % re.escape(mod), test_src))
        refs += len(re.findall(r'from\s+vools\.actus\s+import\s+%s\b' % re.escape(mod), test_src))
        sym_hits = [s for s in syms if s in test_src]
        # 符号命中给个上限，避免大模块靠一个通用名虚高
        refs += min(len(sym_hits), 20)
        rows.append({
            'module': mod,
            'lines': lines,
            'refs': refs,
            'symbols_hit': sym_hits[:8],
            'symbols_total': len(syms),
        })

    print('=== 零引用模块（行数降序）===')
    zero = [r for r in rows if r['refs'] == 0]
    for r in sorted(zero, key=lambda x: -x['lines']):
        print('  %-22s %6d 行' % (r['module'], r['lines']))
    if not zero:
        print('  （无）')

    print('\n=== 引用强度不足的大模块（>=300 行且 refs<=2）===')
    weak = [r for r in rows if r['lines'] >= 300 and r['refs'] <= 2]
    for r in sorted(weak, key=lambda x: -x['lines']):
        print('  %-22s %6d 行 refs=%-2d symbols=%d/%d hit=%r' % (
            r['module'], r['lines'], r['refs'], len(r['symbols_hit']),
            r['symbols_total'], r['symbols_hit']))
    if not weak:
        print('  （无）')

    print('\n=== 统计 ===')
    print('  模块总数=%d 零引用=%d 弱引用=%d' % (len(rows), len(zero), len(weak)))
    total_lines = sum(r['lines'] for r in rows)
    zero_lines = sum(r['lines'] for r in zero)
    print('  总行数=%d 零引用模块行数=%d (%.0f%%)' % (
        total_lines, zero_lines, 100.0 * zero_lines / max(1, total_lines)))


if __name__ == '__main__':
    main()
