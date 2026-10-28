# -*- coding: utf-8 -*-
"""迁移验收（语义正确版）：把真实 seed_key 改回明文 → 重开自动迁移 → 旧 secrets 仍可读。"""
import json, os, sqlite3, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HOME = tempfile.mkdtemp(prefix='mig_home_'); os.environ['HOME'] = HOME
os.environ['USERPROFILE'] = HOME
os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None); os.environ.pop('ACTUS_VAULT2_KEY_PROTECTION', None)
sys.path.insert(0, os.path.join(REPO, 'vools')); sys.path.insert(0, os.path.join(REPO, 'tests'))
import _ai_local_bootstrap; _ai_local_bootstrap.install()
from vools.actus import vault2 as v2

def row(path):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT id, seed_key, key_protection, key_meta FROM identities").fetchone()

print('=== 迁移 1：file-key 库 → 打回明文 → 重开自动迁移（同一 KEK，secrets 可读）===')
d = tempfile.mkdtemp(prefix='mig_fk_')
inst = v2.Vault2(d)
reg = inst.register('u', '123456', machine_name='m', security_level='L1')
ident = reg['identity_id']
tok = inst.auth(ident, reg['machine_id'], '123456')['session_token']
inst.set_secret(tok, 'api', 'VALUE-BEFORE-MIGRATE')
# 取回真实 seed_key 明文，然后把库打回"旧格式"
iid, stored, prot, meta = row(inst.db_path)
real_hex = inst._decode_seed_hex(iid, stored, prot, meta)
with sqlite3.connect(inst.db_path) as c:
    c.execute("UPDATE identities SET seed_key=?, key_protection=NULL, key_meta=NULL", (real_hex,))
print('  打回明文（长度 %d，全 hex=%s）' % (len(real_hex), all(ch in '0123456789abcdef' for ch in real_hex)))
re1 = v2.Vault2(d)
iid, stored, prot, meta = row(re1.db_path)
print('  迁移后: 前缀=%s 明文=%s protection=%s migrated=%s' % (
    stored[:10], len(stored) == 64 and all(ch in '0123456789abcdef' for ch in stored),
    prot, re1.status().get('migrated_key_protection')))
t = re1.auth(ident, reg['machine_id'], '123456')['session_token']
print('  旧 secret 仍可读 =', re1.get_secret(t, 'api')['value'])

print('\n=== 迁移 2：同样打法打回明文 → 用 keyring 保护打开 → 自动迁移 + secrets 可读 ===')
d2 = tempfile.mkdtemp(prefix='mig_kr_')
os.environ['ACTUS_VAULT2_KEY_PROTECTION'] = 'keyring'
i2 = v2.Vault2(d2)
r2 = i2.register('ku', '123456', machine_name='m', security_level='L1')
ident2 = r2['identity_id']
t2 = i2.auth(ident2, r2['machine_id'], '123456')['session_token']
i2.set_secret(t2, 'api', 'KR-MIGRATE-VALUE')
iid2, stored2, prot2, meta2 = row(i2.db_path)
real2 = i2._decode_seed_hex(iid2, stored2, prot2, meta2)
with sqlite3.connect(i2.db_path) as c:
    c.execute("UPDATE identities SET seed_key=?, key_protection=NULL, key_meta=NULL", (real2,))
i2._keyring.delete_password(v2.KEYRING_SERVICE, ident2)     # 清掉旧条目，模拟只有明文库
re2 = v2.Vault2(d2)                                          # 首次打开 → 重新写 keyring 条目 + 清明文
iid2, stored2, prot2, meta2 = row(re2.db_path)
print('  迁移后: 前缀=%s 明文=%s protection=%s migrated=%s' % (
    stored2[:10], len(stored2) == 64 and all(ch in '0123456789abcdef' for ch in stored2),
    prot2, re2.status().get('migrated_key_protection')))
print('  keyring 新条目存在 =', bool(re2._keyring.get_password(v2.KEYRING_SERVICE, ident2)))
t3 = re2.auth(ident2, r2['machine_id'], '123456')['session_token']
print('  旧 secret 仍可读 =', re2.get_secret(t3, 'api')['value'])
# 清理：删除本次验证写入的真实 keyring 条目
for ident in (ident2,):
    try:
        re2._keyring.delete_password(v2.KEYRING_SERVICE, ident)
        print('  已清理 keyring 测试条目:', ident)
    except Exception as exc:
        print('  清理失败:', exc)
