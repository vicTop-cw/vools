# -*- coding: utf-8 -*-
"""第 11 轮验收：cost / selfdrive / workflow / artifacts / unsubscribe。"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix='r11_home_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
META = tempfile.mkdtemp(prefix='r11_meta_')
os.environ['ACTUS_META_DIR'] = META
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

PY = sys.executable
ENV = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'),
           PYTHONIOENCODING='utf-8')


def section(t):
    print('\n=== %s ===' % t)


def cli(*args, cwd=None):
    return subprocess.run([PY, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=cwd or REPO, env=ENV, timeout=120)


section('① cost CLI：无记账 → 如实说"暂无"；有记账 → spend/model 分组')
p = cli('cost')
d = json.loads(p.stdout[p.stdout.index('{'):])
inner = d.get('data') or {}
inner = inner.get('data') if 'data' in inner else inner
print('  空账本: rc=%d recorded=%s message=%s' % (
    p.returncode, inner.get('recorded'), inner.get('message')))
from vools.actus import cost as _cost  # noqa: E402
_cost.record_cost('ai.llm.complete', 'openai', 0.0123, tokens=120, model='gpt-4o')
p2 = cli('cost')
d2 = json.loads(p2.stdout[p2.stdout.index('{'):])
inner2 = d2.get('data') or {}
inner2 = inner2.get('data') if 'data' in inner2 else inner2
print('  有记账: rc=%d spend=%s calls=%s by_model=%s budget.over=%s' % (
    p2.returncode, inner2.get('spend_usd'), inner2.get('calls'),
    inner2.get('by_model'), inner2.get('budget', {}).get('over_budget')))

section('② selfdrive CLI：echo 运行 + status 列表 + 参数校验')
p = cli('selfdrive', 'run', '演示目标：拆解并验证', '--max-depth', '0')
d = json.loads(p.stdout[p.stdout.index('{'):])
run_data = d.get('data') or {}
print('  echo run: rc=%d status=%s worker_kind=%s run_id=%s' % (
    p.returncode, d.get('status'), run_data.get('worker_kind'), (run_data.get('run_id') or '')[:12]))
rid = run_data.get('run_id')
p = cli('selfdrive', 'status')
d = json.loads(p.stdout[p.stdout.index('{'):])
sd_data = d.get('data') or {}
print('  status: rc=%d count=%s 首条 goal=%s' % (
    p.returncode, sd_data.get('count'),
    (sd_data.get('runs') or [{}])[0].get('goal')))
if rid:
    p = cli('selfdrive', 'status', rid)
    d = json.loads(p.stdout[p.stdout.index('{'):])
    one = (d.get('data') or {})
    print('  status <run_id>: rc=%d goal=%s' % (p.returncode, one.get('goal')))
p = cli('selfdrive', 'run', '')     # 缺 goal
print('  缺 goal: rc=%d error=%s' % (
    p.returncode, json.loads(p.stdout[p.stdout.index('{'):]).get('error', {}).get('code')))
p = cli('selfdrive', 'run', 'g', '--worker', 'action')   # 缺 plan
print('  action 缺 plan: rc=%d error=%s' % (
    p.returncode, json.loads(p.stdout[p.stdout.index('{'):]).get('error', {}).get('code')))

section('③ MCP actus_cost 工具')
from vools.actus import mcp_server as M  # noqa: E402
server = M.MCPServer()
res = server._call_tool({'name': 'actus_cost', 'arguments': {}})
payload = json.loads(res['content'][0]['text'])
print('  actus_cost: isError=%s recorded=%s spend=%s' % (
    res.get('isError'), payload['data'].get('recorded'),
    payload['data'].get('spend_usd')))

section('④ workflow 路由（register_workflow 现在真的被 route 读取）')
from vools.actus.intent import IntentRouter  # noqa: E402
r = IntentRouter()
r.register_workflow('wf.release', '发布前检查工作流', tags=['release', '发布'])
print('  route("发布前检查") =', r.route('发布前检查'))
print('  route("无关查询xyz") =', r.route('无关查询xyz'))

section('⑤ artifacts 统一格式：executor 写入 → records 可见；cleanup 真删文件')
from vools.actus import records as rec  # noqa: E402
from vools.actus import executor as EX  # noqa: E402
from vools.actus.model import parse_cfg_from_file  # noqa: E402
action_dir = tempfile.mkdtemp()
apath = os.path.join(action_dir, 'a.actus.md')
with open(apath, 'w', encoding='utf-8') as f:
    f.write('```json #!cfg\n%s\n```\n\n```python #!run tag=main\nprint(1)\n```\n'
            % json.dumps({'id': 'demo.art.act', 'name': 'A', 'version': '1.0.0',
                          'trust': 'sandbox', 'kind': 'exec', 'entry': 'main',
                          'platform': ['desktop']}))
action = parse_cfg_from_file(apath)
meta = tempfile.mkdtemp(prefix='r11_art_')
out_file = os.path.join(meta, 'out.bin')
with open(out_file, 'wb') as f:
    f.write(b'y' * 2048)
EX._register_artifacts(meta, action, 'exec-1',
                       [{'name': 'out', 'path': out_file, 'block': 0}])
listed = rec.list_artifacts(meta)
print('  executor 登记后 records.list_artifacts =', [
    (a['name'], a.get('version'), bool(a.get('sha256'))) for a in listed])
# 让该产物"过期"：把 timestamp 改成很久以前，再 cleanup
reg = rec.load_artifacts_registry(meta)
for a in reg['artifacts']:
    a['timestamp'] = '2020-01-01T00:00:00+08:00'
rec._save_artifacts_registry(meta, reg)
result = rec.cleanup_artifacts(meta, max_age_days=1)
print('  cleanup =', result)
print('  磁盘文件仍存在:', os.path.isfile(out_file))

section('⑥ 事件订阅不累积：两个 MCPServer → 2 个订阅；close 后 0')
from vools.actus.eventbus import get_event_bus  # noqa: E402
bus = get_event_bus()
s1 = M.MCPServer()
s2 = M.MCPServer()
print('  两个实例后 subscriber_count =', bus.subscriber_count())
s2.close()
print('  s2.close() 后 =', bus.subscriber_count())
s1.close()
print('  s1.close() 后 =', bus.subscriber_count())
st = json.loads(server._call_tool({'name': 'actus_status', 'arguments': {}})['content'][0]['text'])
print('  actus_status.event_subscribers =', st['data'].get('event_subscribers'))
