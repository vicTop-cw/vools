# -*- coding: utf-8 -*-
"""性能与 executor 门禁定向验收（③-C / ③-D 修正版）。"""
import glob
import json
import os
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='v20h3_')
META = tempfile.mkdtemp(prefix='v20m3_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus.model import parse_cfg_from_file  # noqa: E402
from vools.actus import validate as V  # noqa: E402
from vools.actus import executor as EX  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402


def section(t):
    print('\n=== %s ===' % t)


files = sorted(glob.glob(os.path.join(REPO, 'vools/actus/actions/**/*.actus*.md'),
                         recursive=True))
actions = [parse_cfg_from_file(f) for f in files]

section('③-C 性能（预热 + 交替三轮取中位数）')
def bench(fn, rounds=10):
    t0 = time.perf_counter()
    for _ in range(rounds):
        for a in actions:
            fn(a)
    return time.perf_counter() - t0

# 预热
for a in actions:
    V.validate_action(a)
orig = V.check_security
results = []
for i in range(3):
    with_scan = bench(V.validate_action)
    V.check_security = lambda action: []
    try:
        without = bench(V.validate_action)
    finally:
        V.check_security = orig
    results.append((with_scan, without))
    print('  第 %d 轮: 完整 %.1f ms | 不扫描 %.1f ms' % (
        i + 1, with_scan * 1000, without * 1000))
med_full = sorted(r[0] for r in results)[1]
med_base = sorted(r[1] for r in results)[1]
delta = (med_full - med_base) * 1000
print('  中位数：完整 %.1f ms / 不扫描 %.1f ms / 增量 %.1f ms（%d 个动作）'
      % (med_full * 1000, med_base * 1000, delta, len(actions)))
print('  单动作增量约 %.2f ms；按 14 个动作的仓库全量校验约 +%.1f ms'
      % (delta / len(actions), delta))

section('③-D executor._security_gate 定向：低信任 + 危险内容 → permission_denied')
danger_dir = tempfile.mkdtemp()
p = os.path.join(danger_dir, 'evil.actus.md')
with open(p, 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n%s\n```\n\n```python #!run tag=main\n'
            'import subprocess\nsubprocess.run("x", shell=True)\n```\n' % json.dumps(
                {'id': 'a.evil.x', 'name': 'E', 'version': '1.0.0',
                 'trust': 'sandbox', 'kind': 'exec', 'entry': 'main',
                 'platform': ['desktop']}))
evil = parse_cfg_from_file(p)
try:
    info = EX._security_gate(evil, 'a.evil.x')
    print('  UNEXPECTED: 未拒绝 ->', info)
except ActionError as exc:
    print('  低信任动作 →', exc.code, '|', str(exc.message)[:80])

section('③-D2 高信任 + 同样内容 → 只留痕不拦截')
evil.meta['trust'] = 'trusted'
info = EX._security_gate(evil, 'a.evil.x')
print('  trusted →', info)

section('③-D3 干净动作 → 门禁放行（无误伤）')
clean = [a for a in actions if a.meta.get('trust') in ('sandbox', 'community')]
print('  仓库里 sandbox/community 动作数:', len(clean))
blocked = []
for a in clean:
    try:
        EX._security_gate(a, a.meta.get('id', ''))
    except ActionError as exc:
        blocked.append((a.meta.get('id'), exc.message[:60]))
print('  被误拦的干净动作:', blocked or '无')
