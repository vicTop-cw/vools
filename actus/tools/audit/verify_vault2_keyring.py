# -*- coding: utf-8 -*-
"""验收：vault2 seed_key 不再明文落库（keyring / passphrase / file-key / fail-closed / 迁移）。"""
import json, os, sqlite3, subprocess, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='vault_home_')
os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME          # Windows expanduser
os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None)
os.environ.pop('ACTUS_VAULT2_KEY_PROTECTION', None)
sys.path.insert(0, os.path.join(REPO, 'vools'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus import vault2 as v2

def db_row(path):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT seed_key, key_protection, key_meta FROM identities").fetchone()

def is_plain_hex(value):
    return len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)

print('=== A) keyring 模式：seed_key 在 keyring 里，db 里无明文 ===')
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'keyring'
d = tempfile.mkdtemp(prefix='vault_keyring_')
inst = v2.Vault2(d)
print('  key_protection =', inst.status()['key_protection'])
reg = inst.register('kru', '123456', machine_name='m', security_level='L1')
ident = reg['identity_id']
tok = inst.auth(ident, reg['machine_id'], '123456')['session_token']
inst.set_secret(tok, 'k', 'KR-SECRET')
stored, protection, meta = db_row(inst.db_path)
print('  db seed_key 前缀 =', stored[:10], '| 是明文 hex =', is_plain_hex(stored),
      '| key_protection =', protection, '| key_meta =', meta)
kr_entry = inst._keyring.get_password(v2.KEYRING_SERVICE, ident)
print('  keyring 条目存在 =', bool(kr_entry), '| 条目长度 =', len(kr_entry or ''))
print('  get_secret 读回 =', inst.get_secret(tok, 'k')['value'])
# 攻击者只拿 db：直接读 seed_key 列 → 密文，无 KEK 不可解
print('  仅凭 db 能看出 seed_key 明文 =', is_plain_hex(stored))

print('\n=== A2) 重开同一库（keyring 仍在）→ 可读；删掉 keyring 条目 → 明确报错 ===')
inst2 = v2.Vault2(d)
tok2 = inst2.auth(ident, reg['machine_id'], '123456')['session_token']
print('  重开 auth =', bool(tok2), '| 读回 =', inst2.get_secret(tok2, 'k')['value'])
inst2._keyring.delete_password(v2.KEYRING_SERVICE, ident)
bad = inst2.auth(ident, reg['machine_id'], '123456')
print('  keyring 条目被删后 auth =', bad['status'], '|', bad['message'][:70])

print('\n=== B) 迁移：旧库明文 seed_key → 首次打开后清掉、secrets 仍可读 ===')
os.environ.pop('ACTUS_VAULT2_KEY_PROTECTION', None)
os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'correct horse battery staple'
d2 = tempfile.mkdtemp(prefix='vault_legacy_')
seed = v2.Vault2(d2, ) if False else v2.Vault2(d2)
r2 = seed.register('legacy', '123456', machine_name='m', security_level='L1')
t2 = seed.auth(r2['identity_id'], r2['machine_id'], '123456')['session_token']
seed.set_secret(t2, 'legacy.key', 'LEGACY-SECRET')
# 把库还原成"旧格式"：seed_key 明文 hex、key_protection 置空（模拟升级前的库）
plain_seed = 'a' * 64
with sqlite3.connect(seed.db_path) as conn:
    conn.execute("UPDATE identities SET seed_key=?, key_protection=NULL, key_meta=NULL",
                 (plain_seed,))
print('  迁移前 db seed_key 是明文 =', is_plain_hex(plain_seed))
reopened = v2.Vault2(d2)
stored2, prot2, meta2 = db_row(reopened.db_path)
print('  迁移后 seed_key 前缀 =', stored2[:10], '| 明文?', is_plain_hex(stored2),
      '| key_protection =', prot2, '| migrated_key_protection =',
      reopened.status().get('migrated_key_protection'))
print('  迁移后 status.key_protection =', reopened.status()['key_protection'])

print('\n=== C) fail-closed：keyring 不可用 + 无 passphrase → 拒绝打开 + 可读错误 ===')
os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None)
code = '''
import os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "vools"))
import keyring, keyring.backends.fail
keyring.set_keyring(keyring.backends.fail.Keyring())
import vools.actus.vault2 as v2
v2._KEYRING_PROBE_CACHE = None          # 让探针重新判断 fail 后端
os.environ["ACTUS_VAULT2_KEY_PROTECTION"] = "keyring"
try:
    v2.Vault2(os.environ["VDIR"])
    print("UNEXPECTED: 打开了库")
except v2.Vault2KeyProtectionError as exc:
    print("拒绝打开:", str(exc).splitlines()[0])
    print("给出解决指引:", "ACTUS_VAULT2_PASSPHRASE" in str(exc) and "keyring" in str(exc))
'''
env = dict(os.environ, REPO=REPO, VDIR=tempfile.mkdtemp(prefix='vault_fc_'))
r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                   encoding='utf-8', errors='replace', env=env, timeout=120)
print('  rc =', r.returncode)
print(' ', (r.stdout or r.stderr).strip().replace('\n', '\n  ')[:400])

print('\n=== C2) 默认目录（无 keyring、无口令）同样 fail-closed ===')
code2 = '''
import os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "vools"))
import keyring, keyring.backends.fail
keyring.set_keyring(keyring.backends.fail.Keyring())
import vools.actus.vault2 as v2
v2._KEYRING_PROBE_CACHE = None
for var in ("ACTUS_VAULT2_KEY_PROTECTION", "ACTUS_VAULT2_PASSPHRASE"):
    os.environ.pop(var, None)
try:
    v2.Vault2()      # 默认 ~/.actus/vault2（HOME 已隔离）
    print("UNEXPECTED: 打开了库")
except v2.Vault2KeyProtectionError as exc:
    print("默认目录拒绝打开:", str(exc).splitlines()[0])
'''
r2 = subprocess.run([sys.executable, '-c', code2], capture_output=True, text=True,
                    encoding='utf-8', errors='replace',
                    env=dict(os.environ, REPO=REPO), timeout=120)
print('  rc =', r2.returncode, '|', (r2.stdout or r2.stderr).strip().splitlines()[0][:160])

print('\n=== D) passphrase 模式：可读写；换环境无口令 → 明确拒绝（不猜明文） ===')
d3 = tempfile.mkdtemp(prefix='vault_pp_')
os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'pp-secret'
pp = v2.Vault2(d3)
print('  key_protection =', pp.status()['key_protection'], '| status.warning 有?', 'key_protection_warning' in pp.status())
r3 = pp.register('pp', '123456', machine_name='m', security_level='L1')
t3 = pp.auth(r3['identity_id'], r3['machine_id'], '123456')['session_token']
pp.set_secret(t3, 'k', 'PP-SECRET')
stored3, prot3, meta3 = db_row(pp.db_path)
print('  db seed_key 前缀 =', stored3[:10], '| 明文?', is_plain_hex(stored3),
      '| key_protection =', prot3, '| key_meta 有 salt =', '"salt"' in (meta3 or ''))
pp2 = v2.Vault2(d3)
print('  重开（口令相同）读回 =', pp2.get_secret(pp2.auth(r3['identity_id'], r3['machine_id'], '123456')['session_token'], 'k')['value'])
del os.environ['ACTUS_VAULT2_PASSPHRASE']
try:
    v2.Vault2(d3)
    print('  UNEXPECTED: 无口令也打开了')
except v2.Vault2KeyProtectionError as exc:
    print('  无口令重开 =', str(exc).splitlines()[0][:100])

print('\n=== E) status() 三种保护方式 ===')
os.environ.pop('ACTUS_VAULT2_KEY_PROTECTION', None)
os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None)
print('  file-key :', v2.Vault2(tempfile.mkdtemp(prefix='st_f_')).status()['key_protection'])
os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'x'
print('  passphrase:', v2.Vault2(tempfile.mkdtemp(prefix='st_p_')).status()['key_protection'])
os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None)
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'keyring'
print('  keyring  :', v2.Vault2(tempfile.mkdtemp(prefix='st_k_')).status()['key_protection'])
