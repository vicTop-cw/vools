# -*- coding: utf-8 -*-
"""第 13 轮实证：只读命名函数的写副作用快照（isolation: ACTUS_REPO_ROOT / ACTUS_META_DIR / HOME）。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_ACTIONS = os.path.join(REPO, 'vools', 'actus', 'actions')


def mk_world(with_actions=True):
    root = tempfile.mkdtemp(prefix='r13_')
    home = os.path.join(root, 'home')
    meta = os.path.join(root, 'meta')
    repo = os.path.join(root, 'repo')
    os.makedirs(os.path.join(repo, 'actions'), exist_ok=True)
    if with_actions and os.path.isdir(SRC_ACTIONS):
        for item in os.listdir(SRC_ACTIONS):
            src = os.path.join(SRC_ACTIONS, item)
            dst = os.path.join(repo, 'actions', item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            elif item != '__pycache__':
                shutil.copy2(src, dst)
    env = dict(os.environ)
    env.update({'HOME': home, 'USERPROFILE': home, 'ACTUS_META_DIR': meta,
                'ACTUS_REPO_ROOT': repo,
                'PYTHONPATH': os.path.join(REPO, 'vools'),
                'PYTHONIOENCODING': 'utf-8'})
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN',
              'ACTUS_VAULT_LAZY_MIGRATE', 'ACTUS_EVENTS_PERSIST'):
        env.pop(k, None)
    return {'root': root, 'home': home, 'meta': meta, 'repo': repo, 'env': env}


def files_of(root):
    out = {}
    if not os.path.isdir(root):
        return out
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in fs:
            p = os.path.join(dp, f)
            try:
                with open(p, 'rb') as fh:
                    out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()[:12]
            except OSError:
                pass
    return out


def run_cli(world, *args):
    return subprocess.run([sys.executable, '-m', 'vools.actus.cli'] + list(args),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=REPO, env=world['env'], timeout=180)


def section(t):
    print('\n=== %s ===' % t)


PY = sys.executable
section('A) CLI `info`（读命令）→ 是否在 _meta 下写缓存')
w = mk_world()
before = files_of(w['meta'])
p = run_cli(w, 'info', 'actus.basics.calculator')
after = files_of(w['meta'])
print('  rc=%s | 新增/变更文件: %s' % (p.returncode,
      sorted(set(after) - set(before)) or '无'))
print('  meta 内文件:', sorted(after))

section('B) MCP `_list_tools()`（tools/list 只读 RPC）→ 是否建索引落盘')
code = r'''
import json, os, sys
sys.path.insert(0, os.path.join(r"%s", "vools"))
sys.path.insert(0, os.path.join(r"%s", "tests"))
import _ai_local_bootstrap
_ai_local_bootstrap.install()
from vools.actus import mcp_server
srv = mcp_server.MCPServer()
tools = srv._list_tools()
print(json.dumps({"tools": len(tools)}))
''' % (REPO, REPO)
w = mk_world()
before = files_of(w['meta'])
p = subprocess.run([PY, '-c', code], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', cwd=REPO, env=w['env'], timeout=300)
after = files_of(w['meta'])
print('  rc=%s | stdout=%s' % (p.returncode, (p.stdout or '').strip()[:80]))
print('  meta 新增/变更文件:', sorted(set(after) - set(before)) or '无')
if p.returncode != 0:
    print('  stderr:', (p.stderr or '')[-300:])

section('C) `cost.get_cost_summary()`（只读汇总）→ 是否建目录')
code = r'''
import os, sys
sys.path.insert(0, os.path.join(r"%s", "vools"))
sys.path.insert(0, os.path.join(r"%s", "tests"))
import _ai_local_bootstrap
_ai_local_bootstrap.install()
from vools.actus import cost
print(cost.get_cost_summary("2026-10").get("calls"))
''' % (REPO, REPO)
w = mk_world()
before = files_of(w['meta'])
p = subprocess.run([PY, '-c', code], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', cwd=REPO, env=w['env'], timeout=300)
after = files_of(w['meta'])
print('  rc=%s | 新增路径: %s' % (p.returncode, sorted(set(after) - set(before)) or '无'))
print('  meta 目录存在:', os.path.isdir(w['meta']),
      '| 子项:', sorted(os.listdir(w['meta'])) if os.path.isdir(w['meta']) else [])

section('D) `vault2.get_secret()`（名字读取）→ audit.log 追加 + 旧行懒迁移写 db')
code = r'''
import hashlib, json, os, sys, time
sys.path.insert(0, os.path.join(r"%s", "vools"))
sys.path.insert(0, os.path.join(r"%s", "tests"))
import _ai_local_bootstrap
_ai_local_bootstrap.install()
from vools.actus import vault2 as V2
v = V2._get_vault2()
reg = v.register("u", "123456", machine_name="m", security_level="L1")
tok = v.auth(reg["identity_id"], reg["machine_id"], "123456")["session_token"]
v.set_secret(tok, "plain.one", "NEWVAL")
audit = os.path.join(v.vault_dir, "audit.log")
db = os.path.join(v.vault_dir, "vault2.db")
def snap():
    return {"audit": os.path.getsize(audit) if os.path.isfile(audit) else 0,
            "db": hashlib.sha256(open(db, "rb").read()).hexdigest()[:12]}
s0 = snap()
r1 = v.get_secret(tok, "plain.one")
s1 = snap()
# 构造旧格式行（key_salt=NULL，用 session master_key 直接 fernet 加密），模拟历史数据
sess = v._sessions[tok]
backend = V2._make_backend("fernet", sess["master_key"])
enc = backend.encrypt("LEGACY")
with v._db() as conn:
    conn.execute("UPDATE secrets SET value=?, cipher_alg=NULL, key_salt=NULL, key_iters=NULL, key_dklen=NULL WHERE identity_id=? AND name=?", (enc, reg["identity_id"], "plain.one"))
    conn.commit()
s2 = snap()
r2 = v.get_secret(tok, "plain.one")
s3 = snap()
print(json.dumps({"first_read": s0, "after_first_read": s1, "before_legacy_read": s2, "after_legacy_read": s3, "legacy_value": r2.get("value")}))
''' % (REPO, REPO)
w = mk_world(with_actions=False)
p = subprocess.run([PY, '-c', code], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', cwd=REPO, env=w['env'], timeout=300)
print('  rc=%s' % p.returncode)
print(' ', (p.stdout or '').strip()[:400])
if p.returncode != 0:
    print('  stderr:', (p.stderr or '')[-300:])

section('E) CLI `search`（曾写 .actus.registry.json）→ 现已修复?')
w = mk_world()
p = run_cli(w, 'search', 'calculator')
reg_path = os.path.join(w['repo'], '.actus.registry.json')
print('  rc=%s | 仓库内 .actus.registry.json 是否被创建: %s'
      % (p.returncode, os.path.isfile(reg_path)))
print('  repo 新增文件:', sorted(set(files_of(w['repo'])) - set(files_of(w['repo']))) or '无')

section('F) CLI `publish --dry-run` → 索引是否落盘（曾假干跑）')
w = mk_world()
p = run_cli(w, 'publish', '--dry-run')
reg_path = os.path.join(w['repo'], '.actus.registry.json')
print('  rc=%s | .actus.registry.json 是否被创建: %s' % (p.returncode, os.path.isfile(reg_path)))
print('  stdout 前 100:', (p.stdout or '')[:100].replace('\n', ' | '))
