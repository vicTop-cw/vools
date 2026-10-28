# -*- coding: utf-8 -*-
"""第 14 轮验收：D 类 vault2.get_secret(read_only) + indexer/MCP 只读路径零写。"""
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

ROOT = tempfile.mkdtemp(prefix='r14_')
os.environ['HOME'] = ROOT
os.environ['USERPROFILE'] = ROOT
META = os.path.join(ROOT, 'meta')
V2DIR = os.path.join(ROOT, 'vault2')
os.environ['ACTUS_META_DIR'] = META
os.environ['ACTUS_VAULT2_DIR'] = V2DIR
os.environ['ACTUS_VAULT_KEY'] = 'master-key-r14-0123456789abcdef'
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'file-key'
os.environ.pop('ACTUS_VAULT_LAZY_MIGRATE', None)

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


# 建世界：v2 密钥 + v1 密钥 + 一条 legacy 行
v2v = V2._get_vault2()
reg = v2v.register('u', '123456', machine_name='m', security_level='L1')
auth = v2v.auth(reg['identity_id'], reg['machine_id'], '123456')
os.environ['VAULT_IDENTITY_ID'] = reg['identity_id']
os.environ['VAULT_MACHINE_ID'] = reg['machine_id']
os.environ['VAULT_PIN'] = '123456'
token = auth['session_token']
v2v.set_secret(token, 'v2-only', 'V2VAL')
v1 = V.Vault(META)
v1.set('v1-only', 'V1VAL')
# 构造 legacy 行：key_salt=NULL，用 session master_key 直接 fernet 加密
sess = v2v._sessions[token]
backend = V2._make_backend('fernet', sess['master_key'])
enc = backend.encrypt('LEGACYVAL')
with v2v._db() as conn:
    conn.execute(
        "UPDATE secrets SET value=?, cipher_alg=NULL, key_salt=NULL, "
        "key_iters=NULL, key_dklen=NULL WHERE identity_id=? AND name=?",
        (enc, reg['identity_id'], 'v2-only'))
    conn.commit()

section('① D 类：resolve_secret 读 legacy 行（read_only=True）→ db + audit.log 均不变')
before = snap()
r = V.resolve_secret('v2-only', meta_dir=META)
after = snap()
print('  resolve:', json.dumps({k: r.get(k) for k in ('status', 'source', 'value')},
                             ensure_ascii=False))
print('  db/audit 完全不变:', before == after, '|', before, '->', after)

section('② CLI `vault get` / `vault list` / executor vault:// → db + audit.log 不变')
ENV = dict(os.environ, PYTHONPATH=os.path.join(REPO, 'vools'), PYTHONIOENCODING='utf-8')
def cli(*args):
    return subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=REPO, env=ENV, timeout=120)
for cmd in (('vault', 'get', 'v2-only'), ('vault', 'list')):
    before = snap()
    p = cli(*cmd)
    after = snap()
    print('  %-22s rc=%s 不变=%s' % (' '.join(cmd), p.returncode, before == after))
from types import SimpleNamespace  # noqa: E402
from vools.actus import executor as EX  # noqa: E402
before = snap()
action = SimpleNamespace(id='demo.ro', path='x.actus.md', env_prefix='ACTUS_R14_',
                         meta={'secrets': [{'env': 'R14', 'key': 'vault://v2-only'}]})
os.environ.pop('R14', None)
EX._apply_env_injections(action, {}, 'exec-r14', META, False, META)
after = snap()
print('  executor vault://      注入=%s 不变=%s' % (os.environ.get('R14'), before == after))

section('③ 显式迁移入口：migrate_legacy_rows() 才写 db（并且可以正常读出）')
before = snap()
mig = v2v.migrate_legacy_rows(token)
after = snap()
print('  migrate_legacy_rows:', json.dumps(mig, ensure_ascii=False))
print('  db 已变更（预期 True）:', before['vault2.db'][0] != after['vault2.db'][0],
      '| audit 追加（预期 True）:', before['audit.log'][1] < after['audit.log'][1])
print('  迁移后普通读取:', json.dumps(
    {k: v2v.get_secret(token, 'v2-only').get(k) for k in ('status', 'value', 'legacy')},
    ensure_ascii=False))

section('④ indexer：info / MCP tools/list 冷启动零写；显式 build 仍落盘')
def files_of(root):
    out = set()
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in fs:
            out.add(os.path.relpath(os.path.join(dp, f), root))
    return out

# info
w = tempfile.mkdtemp(prefix='r14_idx_')
env2 = dict(ENV, ACTUS_META_DIR=os.path.join(w, 'meta'))
def run_cli2(*args):
    return subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=REPO, env=env2, timeout=180)
before = files_of(os.path.join(w, 'meta'))
p = run_cli2('info', 'actus.basics.calculator')
after = files_of(os.path.join(w, 'meta'))
print('  CLI info（读命令）新增文件:', sorted(after - before) or '无（✅ 零写）')
# MCP tools/list
code = r'''
import os, sys
sys.path.insert(0, os.path.join(r"%s", "vools"))
sys.path.insert(0, os.path.join(r"%s", "tests"))
import _ai_local_bootstrap
_ai_local_bootstrap.install()
from vools.actus import mcp_server
srv = mcp_server.MCPServer()
tools = srv._list_tools()
print(len(tools))
''' % (REPO, REPO)
w2 = tempfile.mkdtemp(prefix='r14_mcp_')
env3 = dict(ENV, ACTUS_META_DIR=os.path.join(w2, 'meta'))
before = files_of(os.path.join(w2, 'meta'))
p = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', cwd=REPO, env=env3, timeout=300)
after = files_of(os.path.join(w2, 'meta'))
print('  MCP _list_tools()（tools/list）新增文件:', sorted(after - before) or '无（✅ 零写）',
      '| 工具数:', (p.stdout or '').strip()[:4])
# 显式 build 仍落盘
code2 = r'''
import os, sys
sys.path.insert(0, os.path.join(r"%s", "vools"))
sys.path.insert(0, os.path.join(r"%s", "tests"))
import _ai_local_bootstrap
_ai_local_bootstrap.install()
from vools.actus.indexer import build_index
idx = build_index()
print(len(idx.get("actions", {})))
''' % (REPO, REPO)
w3 = tempfile.mkdtemp(prefix='r14_build_')
env4 = dict(ENV, ACTUS_META_DIR=os.path.join(w3, 'meta'))
p = subprocess.run([sys.executable, '-c', code2], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', cwd=REPO, env=env4, timeout=300)
print('  显式 build_index() 落盘文件:', sorted(files_of(os.path.join(w3, 'meta'))) or '无',
      '| 动作数:', (p.stdout or '').strip()[:5])

section('⑤ resolve_vault_refs(read_only=True) 不再写 audit')
os.environ['R14B'] = ''
before = snap()
res = v2v.resolve_vault_refs(token, [{'env': 'R14B', 'key': 'vault://v2-only'}],
                             read_only=True)
after = snap()
print('  resolve_vault_refs:', json.dumps(
    {k: res.get(k) for k in ('status', 'resolved')}, ensure_ascii=False)[:120])
print('  db/audit 不变:', before == after)
