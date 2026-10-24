# -*- coding: utf-8 -*-
"""复现 quality.py + executor 埋点 + calllog 三处缺陷：

BUG-Q1（契约漂移/功能死锁）：模块表承诺 gold/platinum 判据含 “Omega spec 通过”，
  _probe_omega 只扫 `<repo>/_meta/specs/*.json`——但全仓没有任何代码往 _meta/specs
  写文件（omega spec 真源落点是 actions/<vis>/omega/<name>.spec.json，见 omega.py）。
  于是 has_omega 恒 False → platinum/gold 永久不可达，quality_scale 最高只能 silver。
  另：`aid in fn` 子串匹配 → id 'a.b' 会被 'a.b.c.spec.json' 冒领（虚报 has_omega）。

BUG-Q2（internal 等级死代码）：QUALITY_LEVELS/表含 internal（引擎/系统动作），
  _LEVEL_RANK 也给 internal 排序位，registry.filter_by_quality('internal') 消费——
  但 quality_scale 的分级判定永不返回 'internal'，任何动作（含 0 执行的引擎动作）
  兜底都是 bronze。

BUG-Q3（自指排除死代码）：设计原则 3 承诺“排除 quality 计算自身的调用”，
  _SELF_TOOLS 常量全仓无人使用；_probe_metrics 的“排除”只是 unique_callers<=0，
  而 executor 写行恒带 caller（'confirmed'/'executor'），'' 也算 1 个 distinct——
  该门等价于 total==0，自指排除从未实现。

BUG-X1（数据完整性，executor 埋点）：awaiting_confirmation（audit 动作正常待确认态）
  经 finish() 落指标 ok=False → success_rate 被永久拉低；后续 confirm 重跑另记一行
  ok=True，旧的假失败行不撤销——反复查看待确认队列会把 quality 指标洗污
  （platinum 要求 99% 成功率，一次“预览未确认”就是一次假失败）。

BUG-X2（exec_iface 契约漂移，dry_run）：ExecutionContext.dry_run 文档承诺
  “True 时只预览不执行”，但 _ExecutorIface 完全不看 ctx.dry_run——对 executor
  源的 dry_run=True 照样真执行（trusted 动作当场跑掉）。
"""
import sys, os, json, tempfile, sqlite3, types
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
from vools.actus.quality import quality_scale, QUALITY_LEVELS
from vools.actus import calllog
from vools.actus.indexer import _repo_root

print('== BUG-Q1: _meta/specs 目录无人产出（对照 omega 真源路径）==')
specs_dir = os.path.join(_repo_root(), '_meta', 'specs')
print('  仓库 _meta/specs 存在:', os.path.isdir(specs_dir))
print('  omega 真源查找路径（omega._find_omega_spec）: actions/{private,public}/omega/*.spec.json')

class FakeAction:
    def __init__(self, aid, path):
        self.meta = {'id': aid}
        self.path = path

# 用临时 repo root 证明：即便按真实规范放置 spec，_probe_omega 也看不见
tmp = tempfile.mkdtemp(prefix='q_repro_')
os.environ['ACTUS_REPO_ROOT'] = tmp
omega_dir = os.path.join(tmp, 'actions', 'public', 'omega')
os.makedirs(omega_dir)
open(os.path.join(omega_dir, 'foo.bar.spec.json'), 'w').write('{}')
from vools.actus.quality import _probe_omega
print('  按规范放置 actions/public/omega/foo.bar.spec.json 后 _probe_omega:',
      _probe_omega(FakeAction('foo.bar', '')))
assert _probe_omega(FakeAction('foo.bar', '')) is False
# 手工把它放进 _meta/specs 才亮 —— 但没有任何写方
mspecs = os.path.join(tmp, '_meta', 'specs')
os.makedirs(mspecs)
open(os.path.join(mspecs, 'foo.bar.json'), 'w').write('{}')
assert _probe_omega(FakeAction('foo.bar', '')) is True
print('  仅 _meta/specs/foo.bar.json 存在时 _probe_omega 才 True（该目录无写入方）')
# 子串冒领
open(os.path.join(mspecs, 'foo.bar.baz.json'), 'w').write('{}')
os.remove(os.path.join(mspecs, 'foo.bar.json'))
print('  _meta/specs 只有 foo.bar.baz.json 时 _probe_omega(foo.bar):',
      _probe_omega(FakeAction('foo.bar', '')))
assert _probe_omega(FakeAction('foo.bar', '')) is True, '子串匹配冒领'
print('  → 确认：真源放置永远不可见；放置目录对了但 id 是前缀也冒领（虚报 has_omega）')

print()
print('== BUG-Q2: internal 永不返回 ==')
q = quality_scale(FakeAction('engine.sys', os.path.join(tmp, 'nonexist.md')),
                  meta_dir=os.path.join(tmp, '_meta'))
print('  引擎动作（0 执行、无签名）quality_scale →', q['quality'])
assert q['quality'] == 'bronze'
assert 'internal' in QUALITY_LEVELS
print('  → 确认：QUALITY_LEVELS/文档表/registry.filter_by_quality 都认 internal，判定分支产不出')

print()
print('== BUG-Q3: _SELF_TOOLS 死代码 ==')
import vools.actus.quality as qmod
src = open(qmod.__file__, encoding='utf-8').read()
uses = [ln for ln in src.split('\n') if '_SELF_TOOLS' in ln]
print('  _SELF_TOOLS 出现行:', uses)
assert len(uses) == 1  # 只有定义没有使用
print('  → 确认：注释承诺的“自指排除”未接线')

print()
print('== BUG-X1: awaiting_confirmation 记成失败 ==')
meta_dir = os.path.join(tmp, '_meta2')
os.makedirs(meta_dir, exist_ok=True)
calllog.write_action_metric('audit.act', ok=False, caller='executor', meta_dir=meta_dir)
agg = calllog.aggregate_metrics('audit.act', meta_dir=meta_dir)
print('  一次 awaiting（ok=False）后 aggregate:', agg)
assert agg['success_rate'] == 0.0
calllog.write_action_metric('audit.act', ok=True, caller='confirmed', meta_dir=meta_dir)
agg2 = calllog.aggregate_metrics('audit.act', meta_dir=meta_dir)
print('  再补一次真正确认执行（ok=True）后:', agg2)
# 假失败行仍在：success_rate 0.5，永远修不回 1.0
assert agg2['success_rate'] == 0.5
print('  → 确认：待确认轮询的 ok=False 行永久留在账上，success_rate 被不可逆拉低')

print()
print('== BUG-X2: executor 源无视 dry_run ==')
from vools.actus.exec_iface import executor_for, ExecutionContext
ran = []
fake = types.ModuleType('vools.actus.executor')
def fake_execute(action_id, params):
    ran.append(action_id)
    return {'status': 'ok', 'data': 42, 'error': None, 'artifacts': []}
fake.execute = fake_execute
sys.modules['vools.actus.executor'] = fake
class A:
    id = 'trusted.act'; meta = {'id': 'trusted.act'}
res = executor_for('executor').execute(A(), ExecutionContext(params={}, dry_run=True))
print('  dry_run=True 调用后 fake.execute 实际执行:', ran, '结果:', res.status, res.data)
assert ran == ['trusted.act'] and res.status == 'ok' and res.data == 42
print('  → 确认：ExecutionContext.dry_run 文档承诺“只预览不执行”，executor 路照样真跑且返回执行数据')
print('ALL QUALITY/CALLLOG/EXECUTOR REPROS OK')
