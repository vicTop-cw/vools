# -*- coding: utf-8 -*-
"""第 15 轮验收：actus vault migrate CLI + MCP（dry-run 零写 / 迁移 / 失败 / 无凭据）。"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

ROOT = tempfile.mkdtemp(prefix='r15_')
os.environ['HOME'] = ROOT
os.environ['USERPROFILE'] = ROOT
META = os.path.join(ROOT, 'meta')
V2DIR = os.path.join(ROOT, 'vault2')
os.environ['ACTUS_META_DIR'] = META
os.environ['ACTUS_VAULT2_DIR'] = V2DIR
os.environ['ACTUS_VAULT_KEY'] = 'master-key-r15-0123456789abcdef'
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'

from vools.actus import vault as V  # noqa: E402
from vools.actus import vault2 as V2  # noqa: E402

DB = os.path.join(V2DIR, 'vault2.db')
AUDIT = os.path.join(V2DIR, 'audit.log')


def snap():
    out = {}
    for p in (DB, AUDIT):
        try:
            with open(p, 'rb') as f:
                out[os.path.basename(p)] = (hashlib.sha256(f.read()).hexdigest()[:12],
                                            os.path.getsize(p), os.path.getmtime(p))
        except OSError:
            out[os.path.basename(p)] = None
    return out


def section(t):
    print('\n=== %s ===' % t)


def cli(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'),
               PYTHONIOENCODING='utf-8')
    p = subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=REPO, env=env, timeout=180)
    body = {}
    if p.stdout.strip().startswith('{'):
        body = json.loads(p.stdout)
        if isinstance(body.get('data'), dict):
            body = body['data']
    return p, body


# 建世界：1 条普通 + 2 条 legacy（1 好 1 坏）
v2v = V2._get_vault2()
reg = v2v.register('u', '123456', machine_name='m', security_level='L1')
tok = v2v.auth(reg['identity_id'], reg['machine_id'], '123456')['session_token']
os.environ['VAULT_IDENTITY_ID'] = reg['identity_id']
os.environ['VAULT_MACHINE_ID'] = reg['machine_id']
os.environ['VAULT_PIN'] = '123456'
v2v.set_secret(tok, 'normal.one', 'NORMAL')
v2v.set_secret(tok, 'legacy-good', 'GOOD')
v2v.set_secret(tok, 'legacy-bad', 'BAD')
sess = v2v._sessions[tok]
backend = V2._make_backend('fernet', sess['master_key'])
with v2v._db() as conn:
    conn.execute("UPDATE secrets SET value=?, cipher_alg=NULL, key_salt=NULL, "
                 "key_iters=NULL, key_dklen=NULL WHERE identity_id=? AND name IN "
                 "('legacy-good','legacy-bad')",
                 (backend.encrypt('GOOD'), reg['identity_id']))
    conn.execute("UPDATE secrets SET value=?, cipher_alg=NULL, key_salt=NULL, "
                 "key_iters=NULL, key_dklen=NULL WHERE identity_id=? AND name=?",
                 ('not-a-valid-fernet-token', reg['identity_id'], 'legacy-bad'))
    conn.commit()

section('① CLI --dry-run：只统计、不写 db/audit')
before = snap()
p, body = cli('vault', 'migrate', '--dry-run')
after = snap()
print('  rc=%s' % p.returncode)
print('  data=', json.dumps({k: body.get(k) for k in (
    'status', 'checked', 'migrated', 'failed', 'failed_names', 'dry_run')},
    ensure_ascii=False))
print('  legacy_names=', body.get('legacy_names'))
print('  db/audit 逐字节不变:', before == after)

section('② CLI 真迁移：db 变更 + legacy 标记消失（坏行→partial+failed_names）')
before = snap()
p, body = cli('vault', 'migrate')
after = snap()
print('  rc=%s | data=' % p.returncode, json.dumps({k: body.get(k) for k in (
    'status', 'checked', 'migrated', 'failed', 'failed_names', 'dry_run')},
    ensure_ascii=False))
print('  db 已变更:', before['vault2.db'][0] != after['vault2.db'][0],
      '| audit 追加:', before['audit.log'][1] < after['audit.log'][1])
print('  好行 legacy 标记:',
      v2v.get_secret(tok, 'legacy-good', read_only=True).get('legacy'))
print('  坏行 legacy 标记:',
      v2v.get_secret(tok, 'legacy-bad', read_only=True).get('legacy'))
print('  正常行值:', v2v.get_secret(tok, 'normal.one', read_only=True).get('value'))

section('③ 无 v2 凭据 → refused + hint（rc≠0，不报 ok）')
saved = os.environ.pop('VAULT_PIN', None)
V._V2_SESSION_CACHE.clear()
V._V2_ERROR_CACHE.clear()
V._V2_READONLY_CACHE.clear()
p, body = cli('vault', 'migrate', '--dry-run')
print('  rc=%s | status=%s | code=%s' % (p.returncode, body.get('status'),
                                        body.get('code')))
print('  hint:', body.get('hint'))
os.environ['VAULT_PIN'] = saved

section('④ MCP actus_vault_migrate：dry_run 零写 / 真迁移')
from vools.actus import mcp_server as M  # noqa: E402
srv = M.MCPServer()
def mcp_call(**args):
    r = srv._call_tool({'name': 'actus_vault_migrate', 'arguments': args})
    payload = json.loads(r['content'][0]['text'])
    return r.get('isError'), payload

# 先把好行重新变回 legacy，供 dry_run 预览
with v2v._db() as conn:
    conn.execute("UPDATE secrets SET value=?, cipher_alg=NULL, key_salt=NULL, "
                 "key_iters=NULL, key_dklen=NULL WHERE identity_id=? AND name='legacy-good'",
                 (backend.encrypt('GOOD2'), reg['identity_id']))
    conn.commit()
before = snap()
is_err, payload = mcp_call(dry_run=True)
after = snap()
print('  MCP dry_run: isError=%s data=%s' % (is_err, json.dumps(
    {k: payload.get(k) for k in ('status', 'checked', 'migrated', 'failed',
                                 'failed_names', 'dry_run')}, ensure_ascii=False)))
print('  db/audit 逐字节不变:', before == after)
is_err, payload = mcp_call()
print('  MCP 真迁移: isError=%s status=%s migrated=%s failed=%s failed_names=%s'
      % (is_err, payload.get('status'), payload.get('migrated'),
         payload.get('failed'), payload.get('failed_names')))

section('⑤ 无凭据的 MCP 调用 → isError=True + hint')
os.environ.pop('VAULT_PIN', None)
V._V2_SESSION_CACHE.clear()
V._V2_ERROR_CACHE.clear()
V._V2_READONLY_CACHE.clear()
is_err, payload = mcp_call(dry_run=True)
print('  isError=%s status=%s code=%s' % (is_err, payload.get('status'),
                                          payload.get('code')))
print('  hint:', payload.get('hint'))
os.environ['VAULT_PIN'] = '123456'

section('⑥ 工具清单里 actus_vault_migrate 的必需参数（供 cmd-test 登记）')
tools = [t for t in srv._list_tools() if t['name'] == 'actus_vault_migrate']
print('  ', tools[0]['name'], '| required =', (tools[0]['inputSchema'].get('required') or []))
