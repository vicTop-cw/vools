"""P0 证据：`vault2` 的 master_key 把**当前 60s 动态码**混进了 KDF →
L2/L3 身份的 secrets 在下一个时间窗口就解不开了。

同时验证「可迁移性」：每条 secret 行有 `created_at`，用它反推当时的窗口计数器，
就能重建当时的 master_key 并解密旧密文 —— 即**旧数据可救**。

跑法：`python tools/audit/prove_vault2_window_master.py`（tmp 隔离）
"""
import os
import sqlite3
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

sandbox = tempfile.mkdtemp(prefix='v2-window-p0-')
os.environ['ACTUS_VAULT2_DIR'] = os.path.join(sandbox, 'vault2')
os.environ['HOME'] = sandbox
os.environ['USERPROFILE'] = sandbox
os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'unit-test-passphrase'
for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
    os.environ.pop(k, None)

import vools.actus.vault2 as v2mod
import vools.security.otp as otp

vault = v2mod._get_vault2()
reg = vault.register('alice', '123456', security_level='L2')
ident, machine = reg['identity_id'], reg['machine_id']

a1 = vault.auth(ident, machine, '123456')
tok1 = a1['session_token']
print('[窗口1] auth=%s code=%s' % (a1.get('status'), a1.get('dynamic_code')))
print('         set_secret(K)=%s' % vault.set_secret(tok1, 'K', 'TOP-SECRET')['status'])
print('         get(K)=%r' % (vault.get_secret(tok1, 'K') or {}).get('value'))

# 记录写入时的 created_at（迁移时用它反推窗口）
con = sqlite3.connect(vault.db_path)
row = con.execute("SELECT value, created_at, key_salt, cipher_alg FROM secrets "
                  "WHERE identity_id=? AND name='K'", (ident,)).fetchone()
con.close()
enc_value, created_at, key_salt_hex, cipher_alg = row
print('\nrow: created_at=%d (窗口=%d) key_salt=%s…' % (created_at, created_at // 60, (key_salt_hex or '')[:8]))

# ── 切到下一个窗口：重新 auth 后应该解不开（P0）──
real_v2, real_otp = v2mod.time, otp.time


def _shift(mod, delta):
    class Shifted:
        def __getattr__(self, name):
            return getattr(mod, name)

        @staticmethod
        def time():
            return mod.time() + delta
    return Shifted()


v2mod.time = _shift(real_v2, 300)
otp.time = _shift(real_otp, 300)
try:
    a2 = vault.auth(ident, machine, '123456')
    print('\n[窗口2 +300s] auth=%s code=%s' % (a2.get('status'), a2.get('dynamic_code')))
    g2 = vault.get_secret(a2['session_token'], 'K')
    print('              get(K)=%s | message=%s' % (g2.get('status'), (g2.get('message') or '')[:50]))
    p0 = g2.get('status') != 'ok'
finally:
    v2mod.time, real_otp_time = real_v2, v2mod.time
    otp.time = real_otp

# ── 可迁移性：用 created_at 反推窗口 → 重建 master → 解开旧密文 ──
con = sqlite3.connect(vault.db_path)
seed_stored, protection, key_meta, key_salt = con.execute(
    "SELECT seed_key, key_protection, key_meta, key_salt FROM identities WHERE id=?",
    (ident,)).fetchone()
con.close()
seed_hex = vault._decode_seed_hex(ident, seed_stored, protection, key_meta)
window = created_at // 60
# 复刻 auth 的派生：derive_master_key(seed_hex, TOTP(seed, window), key_salt)
import struct, hmac, hashlib


def _code_for_window(seed_bytes, counter):
    digest = hmac.new(seed_bytes, struct.pack('>Q', counter), hashlib.sha256).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10 ** 6).zfill(6)


seed_bytes = bytes.fromhex(seed_hex)
master_at_write = otp.derive_master_key(seed_hex, _code_for_window(seed_bytes, window),
                                        bytes.fromhex(key_salt))
row_key = v2mod._derive_row_key(master_at_write, bytes.fromhex(key_salt_hex)) \
    if key_salt_hex else master_at_write
backend = v2mod._make_backend(cipher_alg or 'fernet', row_key)
try:
    recovered = backend.decrypt(enc_value)
except Exception as exc:                       # noqa: BLE001
    recovered = '<失败: %s>' % exc
print('\n[可迁移性] 用 created_at 反推窗口 %d 重建 master → 解密旧密文 = %r' % (window, recovered))
print('\n结论：')
print('  P0 复现（跨窗口读失败）      =', p0)
print('  旧数据可用 created_at 救回    =', recovered == 'TOP-SECRET')
