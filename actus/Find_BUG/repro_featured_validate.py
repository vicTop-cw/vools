# -*- coding: utf-8 -*-
"""复现 curator.get_featured + validate.normalize_multi_field / check_secrets 缺陷：

BUG-F1（契约漂移，curator.get_featured）：docstring 承诺
  “featured = popular ∩ trending……trending 保证近期活跃——避免纯安装量榜单
  把死动作顶在前面”。实现是 popular 全量入榜 + 不在 trending 时 growth=0.0，
  交集从未执行；且 score = log1p(count)*0.7 + growth*0.3 下，
  一个 30 日窗口内 100 次执行、近 7 日 0 次的“死动作”仍排第一。

BUG-N1（契约漂移，validate.normalize_multi_field）：docstring 承诺“截断到 max_n”。
  实现是 `if len(valid)+len(warnings) > max_n: valid = valid[:max_n]`——只截已知值，
  未知值（warnings）永不截，且 valid 本来就 ≤ max_n 时截不动。传入 6 个值
  （3 已知 + 3 未知）、max_n=5：返回 3+3=6 个被接受的值，总量超限，截断是空操作。

BUG-S1（逻辑，validate.check_secrets）：两条都缺 provider 的 secrets 条目，
  第一条把 None 加入 providers 集合，第二条命中 `provider in providers` →
  除了「缺少 provider」还额外误报「provider 重复: None」。
"""
import sys, os, json, tempfile, sqlite3, time
from datetime import datetime, timezone, timedelta
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus import curator, calllog
from vools.actus.validate import normalize_multi_field, check_secrets
from vools.actus.constants import PURPOSE_LEVELS

TZ8 = timezone(timedelta(hours=8))

print('== BUG-F1: get_featured 不做 popular∩trending，死动作居首 ==')
tmp = tempfile.mkdtemp(prefix='feat_repro_')
meta_dir = os.path.join(tmp, '_meta')
os.makedirs(meta_dir)
db = os.path.join(meta_dir, 'call_log.db')
conn = sqlite3.connect(db)
conn.execute(calllog._METRICS_DDL)
now = datetime.now(TZ8)
dead_ts = (now - timedelta(days=20)).isoformat(timespec='seconds')
hot_ts = now.isoformat(timespec='seconds')
# 死动作：100 次执行，全在 20 天前（近 7 日 0 次）
for _ in range(100):
    conn.execute("INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms) VALUES (?,?,?,?,?)",
                 ('dead.heavy', dead_ts, 'cli', 1, 10))
# 11 个热动作：各 3 次执行，全在今天（挤爆 trending limit=10，把死动作挤出 trending 集）
for i in range(11):
    for _ in range(3):
        conn.execute("INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms) VALUES (?,?,?,?,?)",
                     (f'hot.act{i}', hot_ts, 'cli', 1, 10))
conn.commit()
conn.close()

pop = calllog.popular_actions(limit=20, meta_dir=meta_dir)
tr = calllog.trending_actions(limit=20, meta_dir=meta_dir)
print('  popular top:', [(p['action_id'], p['count']) for p in pop[:3]])
dead_t = [t for t in tr if t['action_id'] == 'dead.heavy']
print('  trending 中 dead.heavy:', dead_t, '(count_7d=0, growth=0 → 完全不活跃)')
feat = curator.get_featured(limit=10, meta_dir=meta_dir)
print('  get_featured 第一名:', feat[0])
assert feat[0]['action_id'] == 'dead.heavy', feat[:2]
assert feat[0]['growth'] == 0.0 and feat[0]['count'] == 100
print('  → 确认：growth=0 的 20 天前死动作照样入榜并压过全部近期活跃动作——'
      'docstring「featured = popular ∩ trending（死动作不顶前面）」落空')

print()
print('== BUG-N1: normalize_multi_field 截断是空操作 ==')
vals = ['source', 'sink', 'transform', 'bogus1', 'bogus2', 'bogus3']
valid, warns = normalize_multi_field(vals, PURPOSE_LEVELS, max_n=5)
kept = len(valid) + sum(1 for w in warns if not w.startswith('值数量超出'))
print('  in:', vals, 'max_n=5')
print('  valid:', valid)
print('  warnings:', warns)
print('  实际被接受的值总数:', kept)
assert len(valid) == 3 and kept == 6 > 5
print('  → 确认：6 个值全部保留（3 已知+3 未知），"截断到 max_n=5" 未生效；'
      '且截断分支只对 valid 动刀，valid>max_n 且带未知值时 valid[:max_n] 还会把未知值永久挤在 valid 之外')

print()
print('== BUG-S1: 双缺 provider 误报 "重复: None" ==')
errs = check_secrets({'secrets': [
    {'env': 'AAA_KEY'},
    {'env': 'BBB_KEY'},
]})
print('  errors:', errs)
assert any('重复' in e for e in errs), errs
print('  → 确认：两条缺 provider 报出 3 条错（2 缺失 + 1 假重复）')
print('ALL FEATURED/VALIDATE REPROS OK')
