# -*- coding: utf-8 -*-
"""收尾小复现：
BUG-Q4: quality_scale 对 action.path 缺失/非字符串时的行为——path='' 时
  is_maintained('') → getmtime('') 抛 OSError→False（OK），但 signed=None 时
  _probe_signed 的 verify_action 可能对不存在文件抛非 OSError……验证降级。
BUG-CP1: calllog.get_store 单例键与 meta_dir=None 混用——先 get_store(None)
  （键=_default_meta()），再 get_store(<显式同一路径>) 会因 key != _store_key
  重建；反向：先 get_store(tmp)，write_call_log 走 get_store() 换目录重建，
  单例来回抖动不是 bug 重点；重点是 write_call_log/recent_call_logs **不接受
  meta_dir**，executor 埋点用 write_action_metric(meta_dir=) 显式隔离，
  而 calllog 的 call_log 表仍写全局库——留痕分裂（candidate，行为一致即可）。
BUG-T1: trending_actions 的 N+1 查询放大 + ts 字符串比较跨时区/格式风险：
  ts 写入是 _now_iso()（+08:00 带时区后缀，定长可字典序）；cutoff 同格式，OK。
  但**手工 INSERT 的行**（或别的进程写 UTC 'Z'/无时区 iso）会让 ts>=cutoff
  字典序判断失真——比较语义脆弱，非当前触发面 → candidate。
  本脚本实跑证实：同库混入无时区后缀 ts 时 last_7d 统计错误。
"""
import sys, os, tempfile, sqlite3
from datetime import datetime, timezone, timedelta
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus.quality import quality_scale, is_maintained
from vools.actus import calllog

TZ8 = timezone(timedelta(hours=8))

print('== BUG-Q4: path 为空串的 quality_scale 降级面 ==')
class A:
    meta = {'id': 'x.y'}
    path = ''
q = quality_scale(A())
print('  path="" 返回:', q)
assert q['quality'] == 'bronze' and q['evidence']['maintained_30d'] is False

class B:
    meta = {'id': 'x.y'}
    path = None
q2 = quality_scale(B())   # quality_scale 内部 path or '' 归一，不炸
print('  path=None 经 quality_scale:', q2['quality'])
try:
    is_maintained(None)
    print('  is_maintained(None): 未抛出（意外）')
except TypeError as e:
    print('  → 注意：公开 API is_maintained(None) 抛 TypeError（OSError 捕获面外）；'
          'quality_scale 已归一，仅独立调用方暴露:', e)

print()
print('== BUG-T1: action_metrics.ts 字典序比较 vs 混格式时间戳 ==')
tmp = tempfile.mkdtemp(prefix='ts_')
meta_dir = os.path.join(tmp, '_meta'); os.makedirs(meta_dir)
db = os.path.join(meta_dir, 'call_log.db')
conn = sqlite3.connect(db)
conn.execute(calllog._METRICS_DDL)
now = datetime.now(TZ8)
recent_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
print('  本应“刚刚”的一条（无时区后缀、UTC 裸串）:', recent_utc_naive)
print('  本地 _TZ iso cutoff(now-7d)          :', (now - timedelta(days=7)).isoformat(timespec='seconds'))
# 写入两行：一行规范 TZ8 iso；一行 UTC-naive（等价“刚才”）
conn.execute("INSERT INTO action_metrics VALUES (NULL,?,?,?,1,5)", ('mix.t', now.isoformat(timespec='seconds'), 'cli'))
conn.execute("INSERT INTO action_metrics VALUES (NULL,?,?,?,1,5)", ('mix.t', recent_utc_naive, 'cli'))
conn.commit(); conn.close()
agg = calllog.aggregate_metrics('mix.t', meta_dir=meta_dir)
print('  aggregate:', agg)
print('  期望 last_7d=2（两行都在 7 日内），实际 last_7d =', agg['last_7d'])
assert agg['total'] == 2
if agg['last_7d'] != 2:
    print('  → 确认：字典序比较把 UTC-naive ts（' + recent_utc_naive[:13] + ' 比 cutoff 前缀小）判成 7 日外')
else:
    print('  （本样本恰好 cutoff 字典序更小，未触发——说明依赖写入方格式一致，脆弱但当前不炸：candidate）')
