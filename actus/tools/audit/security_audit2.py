# -*- coding: utf-8 -*-
"""安全审计 part2：团队文件写坏/路径逃逸/大小写绕过 + vault2 证据（全 tmp 隔离）。"""
import json, os, sqlite3, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
TMP = tempfile.mkdtemp(prefix='sec_audit2_')
HOME_GUARD = os.path.expanduser('~/.actus')
def snap(path):
    if not os.path.isdir(path): return ('missing',)
    out = []
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            p = os.path.join(dp, fn)
            try: out.append((os.path.relpath(p, path), os.path.getsize(p), os.path.getmtime(p)))
            except OSError: pass
    return tuple(sorted(out))
before = snap(HOME_GUARD)

def case(label, fn):
    try:
        print('  %-46s -> %r' % (label, fn()))
    except Exception as exc:
        print('  %-46s -> !!! %s: %s' % (label, type(exc).__name__, str(exc)[:90]))

from vools.actus.visibility import (VisibilityEngine, TeamManager, TeamConfig,
                                    TeamMember, VISIBILITY_TEAM, is_internal_path)

print('=== A) add_member 不校验空 user_id / 非法 role → 写入后读回崩溃 ===')
tm = TeamManager(config_dir=os.path.join(TMP, 'tm1'))
tm.create_team('t1', 'alice')
print('  add_member("t1", "") ->', tm.add_member('t1', ''))
path = os.path.join(TMP, 'tm1', 'teams', 't1.json')
print('  落盘文件:', os.path.isfile(path), '| 内容 members =',
      json.load(open(path, encoding='utf-8')).get('members'))
case('读回 get_team("t1")', lambda: tm.get_team('t1'))
case('load_team("t1")', lambda: tm.load_team('t1'))
tm2 = TeamManager(config_dir=os.path.join(TMP, 'tm2'))
tm2.create_team('t2', 'alice')
print('  add_member(role="superadmin") ->',
      tm2.add_member('t2', 'bob', role='superadmin'))
case('读回 get_team("t2")', lambda: tm2.get_team('t2'))
# 对可见性检查的影响：team 级动作判定直接崩
eng = VisibilityEngine(config_dir=os.path.join(TMP, 'tm1'), current_user='alice')
eng.add_private_action('team.act', {'team': 't1'})
case('check_visibility(team 级动作)', lambda: eng.check_visibility('team.act', VISIBILITY_TEAM))

print('\n=== B) 团队名路径逃逸（create_team / load_team / delete_team）===')
tm3 = TeamManager(config_dir=os.path.join(TMP, 'tm3'))
esc = os.path.join(TMP, 'escaped_team.json')
tm3.create_team('../../escaped_team', 'attacker')
print('  create_team("../../escaped_team") 写出到', esc, '| 存在:', os.path.isfile(esc))
print('  list_teams()（只列配置目录内）:', tm3.list_teams())
# 任意 json 读取：把一个假团队文件放到配置目录外，再用 ../../ 读它
outside = os.path.join(TMP, 'outside.json')
json.dump({'team': 'pwn', 'members': [{'id': 'attacker', 'role': 'admin'}]},
          open(outside, 'w', encoding='utf-8'))
case('load_team("../outside") 读目录外文件', lambda: tm3.load_team('../outside') and 'LOADED')
# 删除越界文件
victim = os.path.join(TMP, 'victim.json'); open(victim, 'w').write('{}')
case('delete_team("../victim")', lambda: (tm3.delete_team('../victim'),
     '文件仍存在' if os.path.isfile(victim) else '文件已被删除') and 'DELETED')

print('\n=== C) is_internal_path 大小写绕过（Windows 不区分大小写）===')
for p in ('system/_internal/x.actus.md', 'system/_INTERNAL/x.actus.md',
          'system/_Internal/x.actus.md'):
    print('  %-32s -> %s' % (p, is_internal_path(p)))

print('\n=== D) vault2：默认库落在 cwd/_meta/vault + 权限位 ===')
from vools.actus import vault2 as v2
old = os.getcwd(); work = os.path.join(TMP, 'repo'); os.makedirs(work)
os.chdir(work); v = v2.Vault2(); os.chdir(old)
db = os.path.join(work, '_meta', 'vault', 'vault2.db')
print('  vault_dir =', v.vault_dir)
print('  db 存在 =', os.path.isfile(db), '| 权限位 =', oct(os.stat(db).st_mode & 0o777) if os.path.isfile(db) else 'n/a')

print('\n=== E) vault2：L1 身份 → 仅凭 db 文件解密全部 secrets（无需 PIN/登录）===')
vdir = os.path.join(TMP, 'vaultL1'); vl = v2.Vault2(vdir)
reg = vl.register('l1user', '123456', machine_name='m1', security_level='L1')
tok = vl.auth(reg['identity_id'], reg['machine_id'], '123456')['session_token']
r = vl.set_secret(tok, 'api_key', 'sk-SUPER-SECRET-123', caller='audit')
print('  set_secret:', r.get('status'), '| alg =', r.get('cipher_alg'))
conn = sqlite3.connect(os.path.join(vdir, 'vault2.db'))
seed_hex, key_salt_hex = conn.execute('SELECT seed_key, key_salt FROM identities').fetchone()
value_enc, row_salt_hex, iters, dklen = conn.execute(
    'SELECT value, key_salt, key_iters, key_dklen FROM secrets').fetchone()
print('  db 里 seed_key 明文前 16 位 =', seed_hex[:16], '| key_salt 前 8 =', (key_salt_hex or '')[:8])
from cryptography.fernet import Fernet
import base64
master = v2.derive_master_key(seed_hex, '', bytes.fromhex(key_salt_hex))
row_key = v2._derive_row_key(master, bytes.fromhex(row_salt_hex), iters or 1000, dklen or 32)
plain = Fernet(base64.urlsafe_b64encode(row_key)).decrypt(value_enc.encode()).decode()
print('  仅凭 db 解密 =', repr(plain))

print('\n=== F) vault2：migrate_legacy 有失败仍 status=ok ===')
vdir2 = os.path.join(TMP, 'vaultMix'); vm = v2.Vault2(vdir2)
reg2 = vm.register('mixuser', '123456', machine_name='m2', security_level='L1')
tok2 = vm.auth(reg2['identity_id'], reg2['machine_id'], '123456')['session_token']
with sqlite3.connect(os.path.join(vdir2, 'vault2.db')) as c:
    c.execute("INSERT INTO secrets (id, identity_id, name, value, secret_type, "
              "security_level, created_at, cipher_alg, key_salt) VALUES "
              "('legacy1', ?, 'broken', 'not-a-fernet-token', 'api_key', 'L1', 0, 'fernet', NULL)",
              (reg2['identity_id'],))
print('  migrate =', json.dumps(vm.migrate_legacy_secrets(tok2), ensure_ascii=False))

print('\n=== G) vault2：status() 无认证泄露全局计数 ===')
print('  status =', json.dumps(vm.status(), ensure_ascii=False))

print('\n=== ~/.actus 零变化 ===')
after = snap(HOME_GUARD)
print('  before == after:', before == after, '| 状态:', before[0] if before == ('missing',) else '%d 文件' % len(before))
