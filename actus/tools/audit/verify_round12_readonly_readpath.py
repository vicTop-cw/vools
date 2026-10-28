# -*- coding: utf-8 -*-
"""第 12 轮残留验收：resolve_secret / resolver_status / vault get / executor vault:// 读路径零写。"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

ROOT = tempfile.mkdtemp(prefix='r12d_')
os.environ['HOME'] = ROOT
os.environ['USERPROFILE'] = ROOT
META = os.path.join(ROOT, 'meta')
V2DIR = os.path.join(ROOT, 'vault2')
os.environ['ACTUS_META_DIR'] = META
os.environ['ACTUS_VAULT2_DIR'] = V2DIR
os.environ['ACTUS_VAULT_KEY'] = 'master-key-readonly-0123456789abcdef'
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'
os.environ.pop('ACTUS_VAULT_LAZY_MIGRATE', None)

from vools.actus import vault as V  # noqa: E402
from vools.actus import vault2 as V2  # noqa: E402
from vools.actus import executor as EX  # noqa: E402

v2v = V2._get_vault2()
reg = v2v.register('u', '123456', machine_name='m', security_level='L1')
auth = v2v.auth(reg['identity_id'], reg['machine_id'], '123456')
os.environ['VAULT_IDENTITY_ID'] = reg['identity_id']
os.environ['VAULT_MACHINE_ID'] = reg['machine_id']
os.environ['VAULT_PIN'] = '123456'
token = auth['session_token']
v1 = V.Vault(META)
v2v.set_secret(token, 'v2-only', 'V2VAL')
v1.set('v1-only', 'V1VAL')
v1.set('both-equal', 'SAME')
v2v.set_secret(token, 'both-equal', 'SAME')
v1.set('both-conflict', 'FROM_V1')
v2v.set_secret(token, 'both-conflict', 'FROM_V2')

DB = os.path.join(V2DIR, 'vault2.db')
KEYS = os.path.join(META, 'vault', 'keys.json')


def snap():
    out = {}
    for p in (DB, KEYS):
        try:
            with open(p, 'rb') as f:
                out[p] = {'sha256': hashlib.sha256(f.read()).hexdigest(),
                          'mtime': os.path.getmtime(p), 'size': os.path.getsize(p)}
        except OSError:
            out[p] = None
    return out


def section(t):
    print('\n=== %s ===' % t)


def compare(name, before, after, label):
    same = before == after
    print('  %-38s db/keys 逐字节不变: %s' % (label, same))
    if not same:
        for p in before:
            if before[p] != after[p]:
                print('    CHANGED:', os.path.basename(p), before[p], '->', after[p])
    return same


def auth_read_replica(name):
    """复刻**改前** `_v2_read_secret` 的 auth 版实现，用于输出对比。"""
    v2, tok, reason = V._v2_session()
    if reason:
        return {'state': 'unavailable', 'reason': reason}
    try:
        result = v2.get_secret(tok, name, caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return {'state': 'unavailable', 'reason': str(exc)}
    if result.get('status') == 'ok':
        return {'state': 'found', 'value': result.get('value')}
    msg = str(result.get('message') or '')
    if '凭证不存在' in msg:
        return {'state': 'absent'}
    return {'state': 'error', 'reason': msg}


section('① 改前（auth 复刻） vs 改后（只读）逐字段对比')
cases = ['v2-only', 'v1-only', 'both-equal', 'both-conflict']
for name in cases:
    ro = V._v2_read_secret(name)          # 改后：只读会话
    au = auth_read_replica(name)          # 改前：auth 会话
    ro_v2 = {'state': ro[0], 'value': ro[1]}
    same = (ro_v2.get('state') == au.get('state')
            and ro_v2.get('value') == au.get('value'))
    public = V.resolve_secret(name, meta_dir=META)
    print('  %-14s v2 读取: 只读=%s/%r  auth=%s/%r  一致:%s | resolve: status=%s source=%s value=%r'
          % (name, ro_v2.get('state'), ro_v2.get('value'),
             au.get('state'), au.get('value'), same,
             public.get('status'), public.get('source'), public.get('value')))
# 与上一轮汇报的预期输出逐字段一致（读值/source/warnings 不变）
expected = {
    'v2-only': ('ok', 'v2', 'V2VAL'),
    'v1-only': ('ok', 'v1', 'V1VAL'),
    'both-equal': ('ok', 'v2+v1', 'SAME'),
    'both-conflict': ('conflict', 'v1+v2', None),
}
print('  与上轮输出逐字段一致:',
      all((V.resolve_secret(n, meta_dir=META).get('status'),
           V.resolve_secret(n, meta_dir=META).get('source'),
           V.resolve_secret(n, meta_dir=META).get('value')) == expected[n]
          for n in cases))
# resolver_status：只读 vs auth 的可用性判断应一致
st_ro = V.resolver_status()
v2a, _t, reason_a = V._v2_session()
print('  resolver_status: 只读 v2_available=%s reason=%s | auth v2_available=%s reason=%s | 一致:%s'
      % (st_ro.get('v2_available'), st_ro.get('v2_reason'),
         v2a is not None, reason_a,
         st_ro.get('v2_available') == (v2a is not None)))

section('② resolve_secret / resolver_status 前后 vault2.db + keys.json 不变')
before = snap()
for name in cases:
    V.resolve_secret(name, meta_dir=META)
V.resolver_status()
after = snap()
compare('resolve_secret×4 + resolver_status', before, after,
        '② 读路径（含冲突/回退 v1）')

section('③ CLI `vault get v2-only` 前后 db 不变')
ENV = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), PYTHONIOENCODING='utf-8')
before = snap()
p = subprocess.run([sys.executable, '-m', 'vools.actus.cli', 'vault', 'get', 'v2-only'],
                   capture_output=True, text=True, encoding='utf-8', errors='replace',
                   cwd=REPO, env=ENV, timeout=120)
after = snap()
payload = json.loads(p.stdout)
print('  CLI 输出:', json.dumps(payload, ensure_ascii=False)[:120])
compare('CLI vault get', before, after, '③ CLI vault get')

section('④ executor 的 vault:// 解析前后 db 不变')
before = snap()
action = SimpleNamespace(id='demo.ro', path='x.actus.md', env_prefix='ACTUS_RO_',
                         meta={'secrets': [{'env': 'RO_SECRET', 'key': 'vault://v2-only'}]})
os.environ.pop('RO_SECRET', None)
EX._apply_env_injections(action, {}, 'exec-ro', META, False, META)
after = snap()
print('  注入值:', os.environ.get('RO_SECRET'), '| 与 resolve_secret 一致:',
      os.environ.get('RO_SECRET') == V.resolve_secret('v2-only', meta_dir=META).get('value'))
compare('executor vault://', before, after, '④ executor vault://')

section('⑤ 只读会话缓存：重复读不重复 pbkdf2（热路径不退化）')
V._V2_READONLY_CACHE.clear()
t0 = time.time()
V.resolve_secret('v2-only', meta_dir=META)
first = time.time() - t0
t0 = time.time()
for _ in range(20):
    V.resolve_secret('v2-only', meta_dir=META)
twenty = time.time() - t0
print('  首次（含建会话）: %.1f ms | 之后 20 次合计: %.1f ms（每次 %.2f ms）'
      % (first * 1000, twenty * 1000, twenty * 50))

section('⑥ 失败模式：PIN 错误时只读拒绝且**不写** db（读不是登录）')
before = snap()
os.environ['VAULT_PIN'] = '000000'
V._V2_READONLY_CACHE.clear()
wrong = V.resolve_secret('v2-only', meta_dir=META)
status = V.resolver_status()
os.environ['VAULT_PIN'] = '123456'
V._V2_READONLY_CACHE.clear()
after = snap()
print('  PIN 错误 → resolve:', wrong.get('status'), '| source:', wrong.get('source'),
      '| warnings:', (wrong.get('warnings') or [])[-1:])
print('  resolver_status v2_available:', status.get('v2_available'),
      '| v2_reason:', status.get('v2_reason'))
compare('PIN 错误读（只读会话不累计失败）', before, after, '⑥ 失败读')

section('⑦ auth 会话（写路径）仍然保留：_v2_session 调用点')
import re  # noqa: E402
src = open(os.path.join(REPO, 'vools/actus/vault.py'), encoding='utf-8').read()
lines = [(i + 1, line.strip()) for i, line in enumerate(src.splitlines())
         if line.strip().startswith('v2, token, reason = _v2_session(')]
print('  vault.py 中仍使用 auth 会话的行号:', lines)
