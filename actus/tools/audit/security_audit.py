# -*- coding: utf-8 -*-
"""安全审计：vault2.py / visibility.py（全部在 tmp 隔离目录，不碰 ~/.actus）。"""
import json, os, sqlite3, sys, tempfile, hashlib
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()

TMP = tempfile.mkdtemp(prefix='sec_audit_')
HOME_GUARD = os.path.expanduser('~/.actus')
def _snapshot(path):
    if not os.path.isdir(path):
        return ('missing',)
    out = []
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                out.append((os.path.relpath(p, path), os.path.getsize(p), os.path.getmtime(p)))
            except OSError:
                pass
    return tuple(sorted(out))
before_home = _snapshot(HOME_GUARD)

print('=== visibility：私有动作缺 author → 对所有人放行 ===')
from vools.actus.visibility import VisibilityEngine, VISIBILITY_PRIVATE, VISIBILITY_TEAM, is_internal_path
eng = VisibilityEngine(config_dir=os.path.join(TMP, 'vis'), current_user='alice')
eng.add_private_action('secret.act', {'name': '私有动作'})          # 没写 author
print('  (无 author) check_visibility(private, user=bob) =',
      eng.check_visibility('secret.act', VISIBILITY_PRIVATE, expected_user='bob'))
eng.add_private_action('secret2.act', {'name': 'x', 'author': 'alice'})
print('  (有 author=alice) user=bob =',
      eng.check_visibility('secret2.act', VISIBILITY_PRIVATE, expected_user='bob'))

print('\n=== visibility：团队可见性 _find_action 只查私有索引（docstring 说"所有注册表"）===')
eng.teams.create_team('t1', 'alice')
print('  注册表里有动作，但 _find_action 只看私有索引：')
print('  check_visibility(action 不在私有索引, team) =',
      eng.check_visibility('actus.cli.jq', VISIBILITY_TEAM, expected_user='alice'))

print('\n=== visibility：空 user id 加入团队 → is_member("") 命中 ===')
eng.teams.add_member('t1', '')          # add_member 不校验空 id
team = eng.teams.get_team('t1')
print('  is_member("") =', team.is_member(''), '| members =', [m.user_id for m in team.members])
eng2 = VisibilityEngine(config_dir=os.path.join(TMP, 'vis2'), current_user='')
eng2.add_private_action('team.act', {'name': 'x', 'team': 't1'})
eng2.teams.create_team('t1', 'alice'); eng2.teams.add_member('t1', '')
print('  current_user="" 访问 team 动作 =',
      eng2.check_visibility('team.act', VISIBILITY_TEAM))

print('\n=== visibility：团队名路径逃逸（直接写文件）===')
tm = eng.teams
escape_target = os.path.join(TMP, 'escaped_team.json')
try:
    tm.create_team('../../escaped_team', 'attacker')
    print('  create_team("../../escaped_team") 写出:', escape_target,
          '| 存在:', os.path.isfile(escape_target))
except Exception as exc:
    print('  create_team 抛错:', type(exc).__name__, str(exc)[:80])

print('\n=== visibility：is_internal_path 大小写绕过（Windows 文件系统不区分大小写）===')
print('  .../system/_internal/x →', is_internal_path(os.path.join(TMP, 'system', '_internal', 'x.actus.md')))
print('  .../system/_INTERNAL/x →', is_internal_path(os.path.join(TMP, 'system', '_INTERNAL', 'x.actus.md')))

print('\n=== vault2：默认库落在 os.getcwd()/_meta/vault ===')
old_cwd = os.getcwd(); work = os.path.join(TMP, 'repo_cwd'); os.makedirs(work, exist_ok=True)
os.chdir(work)
from vools.actus import vault2 as v2
v = v2.Vault2()                      # 不传 vault_dir → 默认
os.chdir(old_cwd)
print('  vault_dir =', v.vault_dir)
print('  db 存在 =', os.path.isfile(os.path.join(work, '_meta', 'vault', 'vault2.db')))
print('  audit.log 存在 =', os.path.isfile(os.path.join(work, '_meta', 'vault', 'audit.log')))
st = os.stat(os.path.join(work, '_meta', 'vault', 'vault2.db'))
print('  db 权限位 =', oct(st.st_mode & 0o777), '（无 chmod 加固）')

print('\n=== vault2：L1 身份（无动态码）→ 拿到 db 文件即可解密全部 secrets ===')
vault_dir = os.path.join(TMP, 'vaultL1')
vl = v2.Vault2(vault_dir)
reg = vl.register('l1user', '123456', machine_name='m1', security_level='L1')
ident = reg.get('identity_id') or reg.get('id')
mid = reg.get('machine_id')
authed = vl.auth(ident, mid, '123456')
tok = authed.get('session_token')
print('  register/auth:', reg.get('status'), authed.get('status'), '| level=L1')
setres = vl.set_secret(tok, 'api_key', 'sk-SUPER-SECRET-123', caller='audit')
print('  set_secret:', setres.get('status'), '| cipher_alg=', setres.get('cipher_alg'))
# 模拟"攻击者只拿到 db 文件"：不经过 PIN/auth，直接读库派生 master_key 解密密文
from cryptography.fernet import Fernet
import base64
conn = sqlite3.connect(os.path.join(vault_dir, 'vault2.db'))
seed_key_hex, key_salt_hex = conn.execute(
    'SELECT seed_key, key_salt FROM identities').fetchone()
value_enc, row_salt_hex, iters, dklen = conn.execute(
    'SELECT value, key_salt, key_iters, key_dklen FROM secrets').fetchone()
print('  从 db 直接读到 seed_key =', seed_key_hex[:16] + '...', '| key_salt =', (key_salt_hex or '')[:8] + '...')
master = v2.derive_master_key(seed_key_hex, '', bytes.fromhex(key_salt_hex))
row_key = v2._derive_row_key(master, bytes.fromhex(row_salt_hex), iters or 1000, dklen or 32)
plain = Fernet(base64.urlsafe_b64encode(row_key)).decrypt(value_enc.encode()).decode()
print('  不登录、不输入 PIN，仅凭 db 文件解密出的明文 =', repr(plain))

print('\n=== vault2：migrate_legacy_secrets 有失败仍返回 status=ok ===')
vl2 = v2.Vault2(os.path.join(TMP, 'vaultMix'))
reg2 = vl2.register('mixuser', '123456', machine_name='m2', security_level='L1')
tok2 = vl2.auth(reg2['identity_id'], reg2['machine_id'], '123456')['session_token']
vl2.set_secret(tok2, 'good', 'v', caller='audit')
with sqlite3.connect(os.path.join(TMP, 'vaultMix', 'vault2.db')) as c:
    c.execute("INSERT INTO secrets (id, identity_id, name, value, secret_type, "
              "security_level, created_at, cipher_alg, key_salt) VALUES "
              "('legacy1', ?, 'broken', 'not-a-fernet-token', 'api_key', 'L1', 0, 'fernet', NULL)",
              (reg2['identity_id'],))
mig = vl2.migrate_legacy_secrets(tok2)
print('  migrate 返回 =', json.dumps(mig, ensure_ascii=False))

print('\n=== vault2：status() 无需任何认证即泄露全局计数 ===')
print('  status() =', json.dumps(vl2.status(), ensure_ascii=False))

print('\n=== ~/.actus 零变化检查 ===')
after_home = _snapshot(HOME_GUARD)
print('  before == after:', before_home == after_home, '| 路径:', HOME_GUARD,
      '| 状态:', before_home[0] if before_home == ('missing',) else '%d 个文件' % len(before_home))
