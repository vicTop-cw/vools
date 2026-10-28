# -*- coding: utf-8 -*-
"""第 12 轮收尾验收：list_secret_names / delete_secret（与私有路径逐字段对比 + 只读快照）。"""
import hashlib
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

_COUNTER = [0]


def reset_env():
    from vools.actus import vault as V
    from vools.actus import vault2 as V2
    V2._vault2_singleton = None
    V._vault_singleton = None
    V._V2_SESSION_CACHE.clear()
    V._V2_ERROR_CACHE.clear()


def world(values=None):
    """建一个隔离世界：v1-only / v2-only / both-equal / both-conflict 四把密钥。"""
    _COUNTER[0] += 1
    root = tempfile.mkdtemp(prefix='r12b_%d_' % _COUNTER[0])
    meta = os.path.join(root, 'meta')
    v2dir = os.path.join(root, 'vault2')
    os.environ['HOME'] = root
    os.environ['USERPROFILE'] = root
    os.environ['ACTUS_META_DIR'] = meta
    os.environ['ACTUS_VAULT2_DIR'] = v2dir
    os.environ['ACTUS_VAULT_KEY'] = 'master-key-%d-0123456789abcdef' % _COUNTER[0]
    os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'
    os.environ.pop('ACTUS_VAULT_LAZY_MIGRATE', None)
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    reset_env()
    from vools.actus import vault as V
    from vools.actus import vault2 as V2
    v2v = V2._get_vault2()
    reg = v2v.register('u', '123456', machine_name='m', security_level='L1')
    auth = v2v.auth(reg['identity_id'], reg['machine_id'], '123456')
    os.environ['VAULT_IDENTITY_ID'] = reg['identity_id']
    os.environ['VAULT_MACHINE_ID'] = reg['machine_id']
    os.environ['VAULT_PIN'] = '123456'
    token = auth['session_token']
    v1 = V.Vault(meta)
    vals = values or {'v1-only': 'V1VAL', 'v2-only': 'V2VAL',
                      'both-equal': 'SAME', 'both-conflict-v1': None}
    v1.set('v1-only', vals['v1-only'])
    v2v.set_secret(token, 'v2-only', vals['v2-only'])
    v1.set('both-equal', vals['both-equal'])
    v2v.set_secret(token, 'both-equal', vals['both-equal'])
    v1.set('both-conflict', 'FROM_V1')
    v2v.set_secret(token, 'both-conflict', 'FROM_V2')
    return {'root': root, 'meta': meta, 'v1': v1, 'v2': v2v, 'token': token,
            'v2dir': v2dir}


def snap(paths):
    out = {}
    for p in paths:
        try:
            with open(p, 'rb') as f:
                out[p] = (hashlib.sha256(f.read()).hexdigest(), os.path.getmtime(p))
        except OSError:
            out[p] = None
    return out


def section(t):
    print('\n=== %s ===' % t)


# ── 1) 合并清单 ───────────────────────────────────────────────
section('1) list_secret_names 合并清单（v1-only / v2-only / 两者都有 / 冲突）')
from vools.actus import vault as V  # noqa: E402
w = world()
res = V.list_secret_names('global', w['meta'])
print('  count =', res['count'], '| v2_available =', res['v2_available'],
      '| v2_reason =', res['v2_reason'], '| v1_error =', res['v1_error'])
for row in res['keys']:
    print('   ', json.dumps(row, ensure_ascii=False))

# ── 2) 与 CLI 私有路径逐字段对比 ──────────────────────────────
section('2) 与 CLI 现有私有路径（_list_secrets_merged）逐字段对比')
from vools.actus import cli as CLI  # noqa: E402
w2 = world()
private = CLI._list_secrets_merged(w2['meta'], 'global', V.Vault, V.resolve_secret)
public = V.list_secret_names('global', w2['meta'])
print('  私有路径:', json.dumps(private, ensure_ascii=False))
print('  公开 API:', json.dumps(public, ensure_ascii=False))
print('  完全一致:', private == public)

# ── 3) 只读：快照 keys.json / meta.json / vault2.db ──────────
section('3) list_secret_names 无写副作用（mtime+sha256 快照）')
w3 = world()
vault_dir = os.path.join(w3['meta'], 'vault')
db = os.path.join(w3['v2dir'], 'vault2.db')
audit = os.path.join(w3['v2dir'], 'audit.log')
paths = [os.path.join(vault_dir, 'keys.json'), os.path.join(vault_dir, 'meta.json'), db]
before = snap(paths)
audit_before = os.path.getsize(audit) if os.path.isfile(audit) else None
res3 = V.list_secret_names('global', w3['meta'])
after = snap(paths)
audit_after = os.path.getsize(audit) if os.path.isfile(audit) else None
print('  快照完全一致:', before == after)
for p in paths:
    print('   ', os.path.basename(p), '| changed:', before.get(p) != after.get(p))
print('  audit.log 字节:', audit_before, '→', audit_after,
      '（审计追加“读过什么”，不是数据变更）')

# ── 4) delete_secret 行为 ────────────────────────────────────
section('4a) 默认只删 v2（v1 副本保留）')
w4 = world()
r = V.delete_secret('both-equal', 'global', w4['meta'])
print('  ', json.dumps(r, ensure_ascii=False))
print('  v1 里仍在:', w4['v1'].get('both-equal') == 'SAME',
      '| v2 里已删:', w4['v2'].get_secret(w4['token'], 'both-equal').get('status') == 'error')

section('4b) include_v1=True 才删 v1（破坏性，显式）')
w5 = world()
r = V.delete_secret('both-equal', 'global', w5['meta'], include_v1=True)
print('  ', json.dumps(r, ensure_ascii=False))
fresh_v1 = V.Vault(w5['meta'])
print('  v1 文件里已删:', fresh_v1.inspect('both-equal') == 'absent',
      '| v2 里已删:', w5['v2'].get_secret(w5['token'], 'both-equal').get('status') == 'error')

section('4c) v2 不可用 → failed + hint（不是静默 not_found）')
w6 = world()
os.environ.pop('VAULT_PIN', None)
V._V2_SESSION_CACHE.clear()
V._V2_ERROR_CACHE.clear()
r = V.delete_secret('v1-only', 'global', w6['meta'])
print('  ', json.dumps(r, ensure_ascii=False))
print('  v1 仍在:', w6['v1'].get('v1-only') == 'V1VAL')
os.environ['VAULT_PIN'] = '123456'

section('4d) 不存在的密钥 → not_found')
w7 = world()
print('  ', json.dumps(V.delete_secret('no-such-key', 'global', w7['meta']),
                        ensure_ascii=False))

section('4e) 与 CLI 私有路径（_delete_secret_merged）逐字段对比')
wA = world()
private_del = CLI._delete_secret_merged(wA['meta'], 'both-equal', 'global', include_v1=False)
wB = world()
public_del = V.delete_secret('both-equal', 'global', wB['meta'])
common = ('status', 'key', 'scope', 'deleted', 'deleted_v1', 'errors')
diff = {k: (private_del.get(k), public_del.get(k)) for k in common
        if private_del.get(k) != public_del.get(k)}
print('  私有路径:', json.dumps(private_del, ensure_ascii=False))
print('  公开 API:', json.dumps(public_del, ensure_ascii=False))
print('  公共字段差异:', diff or '无')
print('  额外字段（公开 API 增量）:',
      {k: public_del.get(k) for k in ('deleted_v2', 'not_found')})
