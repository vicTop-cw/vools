# -*- coding: utf-8 -*-
"""第 11 轮实证：artifacts 口径 / cleanup 名实 / cost 读端 / intent workflow / eventbus 订阅。"""
import json
import os
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='v21_home_')
META = tempfile.mkdtemp(prefix='v21_meta_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()
from vools.actus import records  # noqa: E402


def section(t):
    print('\n=== %s ===' % t)


section('① artifacts 口径：executor 写的格式 vs records 读的格式')
meta = tempfile.mkdtemp(prefix='art_meta_')
# executor._register_artifacts 的格式（executor.py:1366）
exec_schema = {'actions': {'demo.act': {'1.0.0': {'artifacts': {
    'out.txt': {'path': 'out.txt', 'sha256': 'abc', 'source_exec': 'e1', 'block': 0}}}}}}
with open(os.path.join(meta, 'artifacts.json'), 'w', encoding='utf-8') as f:
    json.dump(exec_schema, f)
print('executor 格式 registry: 顶层 keys =', list(exec_schema.keys()))
print('records.list_artifacts →', records.list_artifacts(meta))
print('records.cleanup_artifacts →', records.cleanup_artifacts(meta, max_age_days=0, max_count=0))
print('→ 清理后 executor 的登记还在:', 'actions' in json.load(
    open(os.path.join(meta, 'artifacts.json'), encoding='utf-8')))

section('② records.cleanup_artifacts 名实：只删登记，不删磁盘文件')
meta2 = tempfile.mkdtemp(prefix='art2_')
artifact_file = os.path.join(meta2, 'artifact.bin')
with open(artifact_file, 'wb') as f:
    f.write(b'x' * 1024)
reg = {'version': '1.0', 'artifacts': [{
    'id': 'a1', 'exec_id': 'e1', 'action_id': 'demo.act', 'name': 'f',
    'type': 'file', 'path': artifact_file, 'description': '',
    'timestamp': '2020-01-01T00:00:00+08:00'}]}
with open(os.path.join(meta2, 'artifacts.json'), 'w', encoding='utf-8') as f:
    json.dump(reg, f)
result = records.cleanup_artifacts(meta2, max_age_days=1)
print('cleanup 返回:', result)
print('磁盘文件仍存在:', os.path.isfile(artifact_file), '| 字节:', os.path.getsize(artifact_file))
print('→ "清理产物" 只清了登记表，文件未被回收')

section('③ cost：记账端已接线、读端无产品入口')
from vools.actus import cost
os.environ['HOME'] = HOME
cost.record_cost('demo.act', 0.01, tokens=10)
summary = cost.get_cost_summary()
print('get_cost_summary 可算:', {k: summary.get(k) for k in ('month', 'total_usd', 'calls')})
print('check_budget 可算:', cost.check_budget(10)['spent_usd'])
print('→ 读端函数本身正常；但全仓无 CLI/MCP 调用（见 grep 证据），记账写了没人看')

section('④ IntentRouter：workflow 注册后既无路由分支也无读取方')
from vools.actus.intent import IntentRouter
r = IntentRouter()
r.register_workflow('wf.demo', '演示工作流', tags=['demo'])
print('register_workflow 后 list_workflows =', r.list_workflows())
r.register_action('actus.demo.act', '演示动作', usage='', tags=['demo'])
print('route("演示工作流") =', r.route('演示工作流'))
print('→ route() 从不查 _workflows（源码 route 只遍历 _keyword_map/_actions）')

section('⑤ EventBus：subscribe 有产品调用，unsubscribe 无任何调用')
from vools.actus.eventbus import EventBus, EventType
bus = EventBus()
def cb(e):
    pass
bus.subscribe('demo.event', cb)
print('subscribe 后 subscriber_count =', bus.subscriber_count('demo.event'))
bus.clear_history()
print('clear_history 可用:', bus.get_history() == [])
print('→ unsubscribe / clear_history / subscriber_count 产品代码零调用（MCP 每次实例化都 subscribe 新闭包）')

section('⑥ 迁移类全景')
print('全仓 migrate/upgrade/backfill 函数仅 3 个（见扫描），且：')
print('  Vault2._migrate_key_protection   —— 仅 __init__ 内部调用（已接线 ✓）')
print('  Vault2.migrate_legacy_secrets    —— 只被模块级同名包装引用，而包装零调用')
print('  migrate_legacy_secrets（模块级） —— 零调用 → 批量迁移能力对用户不可达')
print('  v1→v2 迁移函数：不存在（docs/vault-v1-v2-merge.md 已列为建议）')
