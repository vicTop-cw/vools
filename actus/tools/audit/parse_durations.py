# -*- coding: utf-8 -*-
"""解析 pytest --durations=0 输出 → 按文件汇总 + >3s 清单 + 基线 JSON。"""
import json
import re
import sys
from collections import defaultdict

path = sys.argv[1]
out_json = sys.argv[2] if len(sys.argv) > 2 else '/tmp/durations_baseline.json'
rows = []
for line in open(path, encoding='utf-8', errors='replace'):
    m = re.match(r'\s*([0-9.]+)s\s+(call|setup|teardown)\s+(tests/\S+|tests\\S+)', line)
    if m:
        rows.append((float(m.group(1)), m.group(2), m.group(3)))
by_file = defaultdict(lambda: [0.0, 0])
for sec, phase, name in rows:
    f = name.split('::')[0].replace('\\', '/')
    by_file[f][0] += sec
    by_file[f][1] += 1
print('=== 按文件总耗时 Top 15 ===')
for f, (sec, n) in sorted(by_file.items(), key=lambda kv: -kv[1][0])[:15]:
    print('%7.2fs  %4d条  %s' % (sec, n, f))
print('\n=== 单条 >=3.0s ===')
slow = [r for r in rows if r[0] >= 3.0]
for sec, phase, name in sorted(slow, reverse=True):
    print('%6.2fs  %-8s %s' % (sec, phase, name))
print('\n单条>=3s 共 %d 条，合计 %.1fs' % (len(slow), sum(r[0] for r in slow)))
print('全部 duration 合计 %.1fs，记录 %d 行' % (sum(r[0] for r in rows), len(rows)))
json.dump({name: sec for sec, phase, name in rows if phase == 'call'},
          open(out_json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('基线写出:', out_json)
