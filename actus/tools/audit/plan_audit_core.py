# -*- coding: utf-8 -*-
"""第 16 轮：核心库计划核实（file-based AST，根 = 仓库 vools/）。"""
import ast
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 核心库根：仓库根（本脚本在 actus/tools/audit 下）
CORE = os.path.dirname(ROOT)          # actus 的上一级 = 仓库根

symbols = {}
files = {}
for dp, dirs, fs in os.walk(os.path.join(CORE, 'vools')):
    dirs[:] = [d for d in dirs if d not in ('__pycache__', '__persist__')]
    for f in fs:
        if not f.endswith('.py'):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, CORE).replace(os.sep, '/')
        files[rel] = p
        try:
            tree = ast.parse(io.open(p, encoding='utf-8', errors='replace').read())
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.setdefault(node.name, []).append('%s:%d' % (rel, node.lineno))

print('=== FEATURE_EXTENSION_PLAN 条目核实（核心库 vools/）===')
features = [
    ('Result/Success/Failure', ['Result', 'Success', 'Failure']),
    ('Maybe/Some/Nothing', ['Maybe', 'Some']),
    ('pluck', ['pluck']), ('pluck_attr', ['pluck_attr']),
    ('merge', ['merge']), ('merge_with', ['merge_with']),
    ('get_in', ['get_in']), ('set_in', ['set_in']), ('update_in', ['update_in']),
    ('walk', ['walk']), ('mapcat', ['mapcat']),
    ('compact', ['compact']), ('flatten', ['flatten']),
    ('split_at', ['split_at']), ('butlast', ['butlast']),
    ('cons', ['cons']), ('conj', ['conj']),
    ('compose_left', ['compose_left']), ('flip', ['flip']),
    ('constantly', ['constantly']),
    ('excepts', ['excepts']), ('silent', ['silent']),
    ('suppress', ['suppress']), ('ignore', ['ignore']),
    ('interleave', ['interleave']), ('interpose', ['interpose']),
    ('dissoc', ['dissoc']), ('assoc', ['assoc']), ('assoc_in', ['assoc_in']),
    ('count_by（对比表）', ['count_by']),
]
miss = []
for label, names in features:
    found = {n: symbols.get(n) for n in names}
    ok = all(found.values())
    print('  %-5s %-28s %s' % ('OK' if ok else 'MISS', label,
          {n: (v[0] if v else None) for n, v in found.items()}))
    if not ok:
        miss.append(label)

print('\n=== IMPLEMENTATION_PLAN 条目核实 ===')
impl = [
    ('vDate', ['vDate']), ('get_recently_months', ['get_recently_months']),
    ('get_recently_weeks', ['get_recently_weeks']),
    ('get_recently_days', ['get_recently_days']), ('get_dates', ['get_dates']),
    ('get_date_range', ['get_date_range']), ('VDate 类', ['VDate']),
    ('vicDate（计划名）', ['vicDate']),
    ('register_all_udfs', ['register_all_udfs']),
    ('_extract_json_keys_native', ['_extract_json_keys_native']),
    ('_array_sum_native', ['_array_sum_native']),
    ('PostgreSQLConnection', ['PostgreSQLConnection']),
    ('overload', ['overload']), ('overloads', ['overloads']),
    ('overcurry', ['overcurry']),
]
for label, names in impl:
    found = {n: symbols.get(n) for n in names}
    ok = all(found.values())
    print('  %-5s %-28s %s' % ('OK' if ok else 'MISS', label,
          {n: (v[0] if v else None) for n, v in found.items()}))
    if not ok:
        miss.append(label)
# 文件/结构
for rel in ('vools/datetime/utils.py', 'vools/datetime/vdate_class.py',
            'vools/datetime/__init__.py', 'vools/spark/udf.py',
            'vools/db/postgresql.py', 'vools/config.py',
            'vools/config.template.py', 'vools/look_upon.py',
            'vools/spark/init.py', 'setup.py', 'requirements.txt',
            'pyproject.toml'):
    p = os.path.join(CORE, rel)
    print('  %-5s 文件 %-40s %s' % ('OK' if os.path.isfile(p) else 'MISS', rel,
                                    '存在' if os.path.isfile(p) else '不存在'))
    if not os.path.isfile(p):
        miss.append('文件 ' + rel)

def grep(rel, pattern):
    p = os.path.join(CORE, rel)
    if not os.path.isfile(p):
        return False
    return pattern in io.open(p, encoding='utf-8', errors='replace').read()

print('\n  config DB 配置:', grep('vools/config.py', 'DATABASE_CONFIG'))
print('  postgresql 连接池关键字:', 'pool' in io.open(
    os.path.join(CORE, 'vools/db/postgresql.py'), encoding='utf-8',
    errors='replace').read().lower())
spark_init = os.path.join(CORE, 'vools/spark/__init__.py')
print('  SparkSession 初始化:',
      grep('vools/spark/__init__.py', 'getOrCreate') or grep('vools/spark/__init__.py', 'SparkSession'))
print('\n核心/实现计划 MISS:', miss)
