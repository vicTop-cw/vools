# -*- coding: utf-8 -*-
"""第 18 轮：按「5 类测试盲区谱系」静态扫描 actus/tests（只读审计）。

输出：每个测试文件的命中标记 + 第 5 类候选清单。
"""
import ast
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTS = os.path.join(ROOT, 'tests')

TIME_WORDS = re.compile(
    r'\b(expire|expires|expiry|ttl|timeout|max_age|rotate|rollback|used_codes|totp|'
    r'dynamic_code|window|deadline|future|past|old|stale|age|sleep|monotonic|'
    r'time\.time|datetime\.now|utcnow|timestamp|cache_ttl|lockout)\b', re.I)
ADVANCE_WORDS = re.compile(
    r'(advance|fake_clock|freeze|monkeypatch\.setattr\(time|time_machine|'
    r'freezegun|utcnow\s*=|_now\s*=|window\s*\+|_totp_window|move_time|travel)', re.I)
SOURCE_STR = re.compile(r'assert\s+.*(in\s+src|in\s+source|in\s+text\s*[,)]|'
                        r'\.read\(\)|getsource|inspect\.getsource)', re.I)
LIBS = ['src', 'source', 'raw', 'text', 'body', 'content', 'code']
MCP = re.compile(r'mcp|MCPServer|_call_tool|isError', re.I)
CLI = re.compile(r'subprocess|cli\(|run_cli|_cmd_|argv', re.I)


def funcs(tree):
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith('test')]


def call_text(node):
    return ast.get_source_segment(SRC[node_name(node)], node) or ''


rows = []
for name in sorted(os.listdir(TESTS)):
    if not name.endswith('.py') or name == 'conftest.py':
        continue
    path = os.path.join(TESTS, name)
    src = io.open(path, encoding='utf-8', errors='replace').read()
    tree = ast.parse(src)
    lines = src.splitlines()
    tests = funcs(tree)
    flags = {'class1': '', 'class2': '', 'class3': '', 'class5': ''}
    # class2 源码字符串断言
    for m in re.finditer(r'assert\s+[^\n]*\((?:[^)]*\b(src|source|raw_src|text)\b[^)]*)\)?\s*(?:,|$)', src):
        pass
    for i, line in enumerate(lines, 1):
        if re.search(r'assert\s+.*\bin\s+(src|source|raw_src|_src)\b', line) or \
           re.search(r'assert\s+.*\bin\s+\w+\.read\(\)', line) or \
           ('getsource' in line and 'assert' in line):
            flags['class2'] = 'L%d:%s' % (i, line.strip()[:90])
            break
    # 每个测试体：时间词 + 是否有跨窗口手段
    for fn in tests:
        seg = ast.get_source_segment(src, fn) or ''
        if not TIME_WORDS.search(seg):
            continue
        advance = bool(ADVANCE_WORDS.search(seg))
        # 只记录"涉及时间语义但无跨窗口手段"的
        if not advance:
            flags['class5'] = 'L%d:%s' % (fn.lineno, fn.name)
            break
    # 需要跨窗口的正向样本：有 advance
    for fn in tests:
        seg = ast.get_source_segment(src, fn) or ''
        if TIME_WORDS.search(seg) and ADVANCE_WORDS.search(seg):
            flags['class5_ok'] = 'L%d:%s' % (fn.lineno, fn.name)
            break
    # class1：只测单入口（有 cli 无 mcp，或反之），且文件主题涉及 API/命令
    has_cli = bool(CLI.search(src))
    has_mcp = bool(MCP.search(src))
    if has_cli != has_mcp and ('cli' in name or 'mcp' in name):
        flags['class1'] = 'cli=%s mcp=%s' % (has_cli, has_mcp)
    # class3：基线绝对计数断言（== 常量 或 base+常量）
    for i, line in enumerate(lines, 1):
        if re.search(r'assert\s+.*(==\s*[1-9]\d*\s*(,|$)|==\s*base\s*\+\s*\d+)', line):
            flags['class3'] = 'L%d:%s' % (i, line.strip()[:90])
            break
    rows.append((name, len(tests), flags, src))

print('测试文件数:', len(rows), '| 测试函数总数:', sum(r[1] for r in rows))
print('\n=== 第 5 类候选（时间语义测试中缺少跨窗口手段的文件）===')
for name, n, flags, _src in rows:
    if flags.get('class5'):
        ok = flags.get('class5_ok')
        print('  %-46s %s%s' % (name, flags['class5'],
                                '   [同文件有跨窗口样本: %s]' % ok if ok else ''))
print('\n=== 第 2 类（源码字符串断言）===')
for name, n, flags, _src in rows:
    if flags.get('class2'):
        print('  %-46s %s' % (name, flags['class2']))
print('\n=== 第 1 类（单入口）===')
for name, n, flags, _src in rows:
    if flags.get('class1'):
        print('  %-46s %s' % (name, flags['class1']))
print('\n=== 第 3 类（可能绝对基线断言，需人工复核）===')
cnt = 0
for name, n, flags, _src in rows:
    if flags.get('class3'):
        cnt += 1
        if cnt <= 12:
            print('  %-46s %s' % (name, flags['class3']))
print('  … 共', cnt, '个文件命中')
