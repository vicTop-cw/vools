# -*- coding: utf-8 -*-
"""端到端复现 BUG-X1：audit 动作「待人工确认」的正常回执被记成失败指标。

execute() 的 awaiting_confirmation 分支（executor.py L423-437）经 finish() 出口
写 action_metrics：ok=(status in ('ok','partial')) → 'awaiting_confirmation' 记 False。
后果：MCP/CLI 每次"预览一次待确认动作"就在指标账上添一条假失败，
  - quality_scale 的 success_rate 被拉低（platinum 要求 99%）；
  - 该行动作可能直接从 silver 掉到 bronze；
  - 行不撤销，永久污染。
"""
import sys, os, json, tempfile, sqlite3
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import executor as ex_mod
from vools.actus import calllog
from vools.actus.quality import quality_scale

tmp = tempfile.mkdtemp(prefix='x1_e2e_')
act_dir = os.path.join(tmp, 'actions'); os.makedirs(act_dir)
meta_dir = os.path.join(tmp, '_meta')

CFG = {'id': 'audit.demo', 'name': 'AuditDemo', 'version': '1.0.0',
       'trust': 'audit', 'entry': 'main', 'platform': ['desktop'],
       'kind': 'exec'}
p = os.path.join(act_dir, 'audit.actus.md')
open(p, 'w', encoding='utf-8').write(
    '```json #!cfg\n' + json.dumps(CFG) + '\n```\n\n'
    '#!entry main\n```python #!tag=main\nprint("hello")\n```\n')
# 满足 docs/47 §4 audit↔测试绑定（否则当场打回，走不到 awaiting_confirmation）
tdir = os.path.join(tmp, 'tests'); os.makedirs(tdir)
open(os.path.join(tdir, 't_audit.py'), 'w', encoding='utf-8').write('# audit.demo\n')

# 1) 未确认调用 → awaiting_confirmation（正常业务态，非失败）
os.environ['ACTUS_REPO_ROOT'] = tmp          # 隔离缓存/索引落点
r1 = ex_mod.execute('audit.demo', {}, confirmed=False,
                    meta_dir=meta_dir, actions_dir=act_dir)
print('第 1 次调用 status:', r1['status'], '| error:', r1.get('error'))
assert r1['status'] == 'awaiting_confirmation'

# 2) 再"预览"两次（模拟 MCP 面板反复查看待确认队列）
ex_mod.execute('audit.demo', {}, confirmed=False, meta_dir=meta_dir, actions_dir=act_dir)
ex_mod.execute('audit.demo', {}, confirmed=False, meta_dir=meta_dir, actions_dir=act_dir)

# 3) 真正人工确认后执行成功
r4 = ex_mod.execute('audit.demo', {}, confirmed=True,
                    meta_dir=meta_dir, actions_dir=act_dir)
print('确认后 status:', r4['status'])

db = os.path.join(meta_dir, 'call_log.db')
conn = sqlite3.connect(db)
rows = conn.execute("SELECT ts, caller, ok FROM action_metrics WHERE action_id='audit.demo'").fetchall()
conn.close()
print('action_metrics 落库行:', rows)
agg = calllog.aggregate_metrics('audit.demo', meta_dir=meta_dir)
print('aggregate:', agg)
assert agg['total'] == 4, agg
print('→ 确认：1 次真实执行成功 + 3 次“待确认预览”记为失败 → success_rate = %.3f'
      % agg['success_rate'])
# 10 次执行成功 + 3 次预览污染，就够把 99%/95% 门槛打掉
class A:
    meta = {'id': 'audit.demo'}
    path = p
import time
os.utime(p, (time.time(), time.time()))
q = quality_scale(A(), meta_dir=meta_dir, signed=True)
print('quality_scale（即便签名+维护+omega 齐）→', q['quality'],
      'success_rate=', q['evidence']['success_rate'])
assert q['evidence']['success_rate'] < 0.90
print('  silver 门槛（≥0.90）被“待确认预览”打到不及格 → 分级掉 bronze')
print('BUG-X1 E2E CONFIRMED')
