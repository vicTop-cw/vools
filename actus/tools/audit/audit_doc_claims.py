# -*- coding: utf-8 -*-
"""扫描「文档/注释声称有 actus CLI/MCP 入口，但实际不存在」的清单。"""
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(ROOT, 'vools', 'actus')
DOCS = os.path.join(ROOT, 'docs')
CLI = os.path.join(PKG, 'cli.py')
MCP = os.path.join(PKG, 'mcp_server.py')
sys.stdout.reconfigure(encoding='utf-8')


def read(p):
    try:
        return open(p, 'r', encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


def py_files(base):
    for dp, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(dp, fn)


# CLI 子命令真源：add_parser('name', ...)
cli_text = read(CLI)
cli_cmds = set(re.findall(r"add_parser\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", cli_text))
# MCP tool 真源：'name': 'actus_xxx' 或 tools 列表中的 name 字段
mcp_text = read(MCP)
mcp_tools = set(re.findall(r"['\"](actus_[a-zA-Z0-9_]+)['\"]", mcp_text))
mcp_tools |= set(re.findall(r"\bname['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9_]+)['\"]", mcp_text))

print('CLI 子命令 %d 个 | MCP tool 名 %d 个' % (len(cli_cmds), len(mcp_tools)))

# 从 .py docstring/注释 和 docs/*.md 中提取 `actus xxx ...` 形式
CLAIM = re.compile(r'`?actus\s+([a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*)?)')
SUSPECT_DOCS_WORDS = ('入口', 'CLI', 'MCP', '命令', 'tool', '接入点', '已接通', '支持')

rows = []
for path in list(py_files(PKG)) + [os.path.join(DOCS, f) for f in os.listdir(DOCS)
                                   if f.endswith('.md')] if os.path.isdir(DOCS) else py_files(PKG):
    rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
    text = read(path)
    for m in CLAIM.finditer(text):
        cmd = m.group(1).split()[0].strip().rstrip('`')
        if cmd in ('run', 'install', 'search', 'validate', 'list', 'status', 'init',
                   'uninstall', 'update', 'self', 'no', 'the', 'a', 'an', 'is'):
            pass
        line_no = text.count('\n', 0, m.start()) + 1
        line = text.splitlines()[line_no - 1].strip()
        if cmd not in cli_cmds and cmd not in mcp_tools and not cmd.startswith('actus_'):
            rows.append((rel, line_no, cmd, line[:110]))

seen = set()
out = []
for rel, ln, cmd, line in rows:
    key = (rel, cmd, line)
    if key in seen:
        continue
    seen.add(key)
    out.append((rel, ln, cmd, line))

print('\n疑似「声称有 CLI 入口但 CLI 无该子命令」: %d 条' % len(out))
for rel, ln, cmd, line in out[:60]:
    print('  %-44s:%-5d  actus %-14s  %s' % (rel, ln, cmd, line))
