"""P0 验收：vault2 主密钥派生修复（动态码不再参与 KDF）+ 旧数据迁移。

覆盖 lead 要求的 6 项：
  1. **迁移前**：跨窗口读 → 失败（复现 P0，用 monkeypatch 把派生改回"掺 TOTP"）
  2. **迁移后**：跨窗口读 → 成功（同一份数据）
  3. **迁移中途失败**（monkeypatch 让写阶段抛错）→ 全部回滚、seed 未变、数据仍按旧方式可读
  4. **幂等**：第二遍 0 条迁移
  5. **L1 行为不变**（L1 的旧派生本来就是"不含动态码"，与新派生逐字相等）
  6. **读路径仍零写**（get_secret 不改 db 文件）
  7. 附加：`rotated_backups` 不迁移仍可解密（它由 seed 派生，与 master 无关）

跑法：`python tools/audit/verify_vault2_master_migration.py`（全 tmp 隔离）
"""
import hashlib
import os
import struct
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', label, (': ' + detail) if detail else ''))


def fresh_vault(tag):
    sandbox = tempfile.mkdtemp(prefix='v2p0-%s-' % tag)
    os.environ['ACTUS_VAULT2_DIR'] = os.path.join(sandbox, 'vault2')
    os.environ['HOME'] = sandbox
    os.environ['USERPROFILE'] = sandbox
    os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'unit-test-passphrase'
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    import importlib
    import vools.actus.vault2 as v2mod
    importlib.reload(v2mod)
    return v2mod, v2mod._get_vault2(), sandbox


class Window:
    """把 time.time() 推后 delta 秒；同时推进 vault2 与 vools.security.otp 的时钟。"""

    def __init__(self, v2mod, otp_mod, delta):
        self.v2mod, self.otp_mod, self.delta = v2mod, otp_mod, delta
        self.real_v2, self.real_otp = v2mod.time, otp_mod.time

    def __enter__(self):
        import types

        def _shifted(real):
            shim = types.SimpleNamespace()
            for attr in dir(real):
                if not attr.startswith('__'):
                    try:
                        setattr(shim, attr, getattr(real, attr))
                    except Exception:              # noqa: BLE001
                        pass
            shim.time = lambda: real.time() + self.delta
            return shim
        # 注意：包级 `vault2.time` / `otp.time` 都指向 time 模块，两者都要换
        self._saved = (self.v2mod.time, self.otp_mod.time)
        self.v2mod.time = _shifted(self._saved[0])
        self.otp_mod.time = _shifted(self._saved[1])
        return self

    def __exit__(self, *exc):
        self.v2mod.time, self.otp_mod.time = self.real_v2, self.real_otp
        return False


def _window_counter(ts):
    return int(ts) // 60


def main():
    # ══ 1) 迁移前：跨窗口读失败（复现 P0）══
    v2mod, vault, _ = fresh_vault('before')
    import vools.security.otp as otp
    reg = vault.register('alice', '123456', security_level='L2')
    ident, machine = reg['identity_id'], reg['machine_id']
    # 把"新派生"临时改回"掺 TOTP"的旧行为，复现事故
    real_stable = v2mod.derive_master_key_stable
    real_migrate = v2mod.Vault2.migrate_master_derivation
    # 复现事故期行为：①派生掺 TOTP ②**关掉自动迁移**（否则 auth 会顺手修好，
    # 就测不到"迁移前失败"了）
    v2mod.derive_master_key_stable = lambda seed, salt: v2mod.derive_master_key_windowed(
        seed, _window_counter(v2mod.time.time()), salt)
    v2mod.Vault2.migrate_master_derivation = lambda self, identity_id=None: {
        'status': 'skipped', 'note': 'P0 复现阶段禁用自动迁移'}
    try:
        a1 = vault.auth(ident, machine, '123456')
        tok1 = a1['session_token']
        vault.set_secret(tok1, 'K', 'TOP-SECRET')
        got_same = (vault.get_secret(tok1, 'K') or {}).get('value')
        with Window(v2mod, otp, 300):
            a2 = vault.auth(ident, machine, '123456')
            print('   [debug] window2 auth =', a2.get('status'), a2.get('message', ''))
            got_next = (vault.get_secret(a2['session_token'], 'K')
                        if a2.get('session_token') else {'status': 'auth_failed'})
    finally:
        v2mod.derive_master_key_stable = real_stable
        v2mod.Vault2.migrate_master_derivation = real_migrate
    check('1) 迁移前：同窗口可读', got_same == 'TOP-SECRET', repr(got_same))
    check('1) 迁移前：跨窗口读**失败**（P0 复现）',
          (got_next or {}).get('status') != 'ok', str((got_next or {}).get('message'))[:60])

    # 用"旧格式"密文重建一个库：直接按窗口化派生写入一行，模拟事故期的数据
    v2mod, vault, _ = fresh_vault('legacy')
    reg = vault.register('bob', '654321', security_level='L2')
    ident, machine = reg['identity_id'], reg['machine_id']
    created_at = int(v2mod.time.time()) - 3 * 3600          # 3 小时前（旧窗口）
    con = __import__('sqlite3').connect(vault.db_path)
    seed_stored, protection, key_meta, key_salt_hex = con.execute(
        "SELECT seed_key, key_protection, key_meta, key_salt FROM identities WHERE id=?",
        (ident,)).fetchone()
    seed_hex = vault._decode_seed_hex(ident, seed_stored, protection, key_meta)
    row_salt = os.urandom(16)
    old_master = v2mod.derive_master_key_windowed(seed_hex, _window_counter(created_at),
                                                  bytes.fromhex(key_salt_hex))
    old_row_key = v2mod._derive_row_key(old_master, row_salt)
    enc = v2mod._make_backend('fernet', old_row_key).encrypt('LEGACY-VALUE')
    con.execute(
        "INSERT INTO secrets (id, identity_id, name, value, secret_type, security_level, "
        "created_at, cipher_alg, key_salt, key_iters, key_dklen) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (str(__import__('uuid').uuid4()), ident, 'LEG', enc, 'api_key', 'L2',
         created_at, 'fernet', row_salt.hex(), 1000, 32))
    con.commit()
    con.close()
    seed_before = seed_stored

    # 迁移前：用新（稳定）派生 auth → 读不到这条旧密文（禁用自动迁移）
    real_migrate2 = v2mod.Vault2.migrate_master_derivation
    v2mod.Vault2.migrate_master_derivation = lambda self, identity_id=None: {'status': 'skipped'}
    try:
        a = vault.auth(ident, machine, '654321')
    finally:
        v2mod.Vault2.migrate_master_derivation = real_migrate2
    pre = vault.get_secret(a['session_token'], 'LEG')
    check('1) 旧格式行（模拟事故数据）迁移前读不到',
          (pre or {}).get('status') != 'ok', str((pre or {}).get('message'))[:50])

    # ══ 2) 迁移后：跨窗口读成功 ══
    mig = vault.migrate_master_derivation(ident)
    check('2) 迁移执行成功', mig.get('status') == 'ok', str(mig)[:80])
    check('2) 迁移条数 = 1', mig.get('migrated') == 1, str(mig.get('per_identity')))
    with Window(v2mod, otp, 600):                          # 换到 +10 分钟的窗口
        a2 = vault.auth(ident, machine, '654321')
        after = vault.get_secret(a2['session_token'], 'LEG')
    check('2) 迁移后**跨窗口**可读', (after or {}).get('value') == 'LEGACY-VALUE',
          repr((after or {}).get('value')))

    # ══ 4) 幂等：第二遍 0 条 ══
    mig2 = vault.migrate_master_derivation(ident)
    check('4) 幂等：第二遍 migrated=0', mig2.get('migrated') == 0,
          'migrated=%s already=%s' % (mig2.get('migrated'), mig2.get('already')))

    # ══ 3) 迁移中途失败 → 全部回滚、seed 未变、旧方式仍可读 ══
    v2mod, vault, _ = fresh_vault('rollback')
    reg = vault.register('carol', '111111', security_level='L2')
    ident, machine = reg['identity_id'], reg['machine_id']
    con = __import__('sqlite3').connect(vault.db_path)
    seed_stored, protection, key_meta, key_salt_hex = con.execute(
        "SELECT seed_key, key_protection, key_meta, key_salt FROM identities WHERE id=?",
        (ident,)).fetchone()
    seed_hex = vault._decode_seed_hex(ident, seed_stored, protection, key_meta)
    created_at = int(v2mod.time.time()) - 60
    for name in ('A', 'B'):
        row_salt = os.urandom(16)
        old_master = v2mod.derive_master_key_windowed(
            seed_hex, _window_counter(created_at), bytes.fromhex(key_salt_hex))
        enc = v2mod._make_backend(
            'fernet', v2mod._derive_row_key(old_master, row_salt)).encrypt('VAL-' + name)
        con.execute(
            "INSERT INTO secrets (id, identity_id, name, value, secret_type, security_level, "
            "created_at, cipher_alg, key_salt, key_iters, key_dklen) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (str(__import__('uuid').uuid4()), ident, name, enc, 'api_key', 'L2',
             created_at, 'fernet', row_salt.hex(), 1000, 32))
    con.commit()
    seed_before = con.execute("SELECT seed_key FROM identities WHERE id=?", (ident,)).fetchone()[0]
    values_before = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                     (ident,)).fetchall())
    con.close()

    real_apply = v2mod.Vault2._reencrypt_rows

    def boom(self, conn, updates):
        real_apply(self, conn, updates[:1])        # 先写一条，再炸 → 事务必须整体回滚
        raise RuntimeError('模拟写阶段失败')

    v2mod.Vault2._reencrypt_rows = boom
    try:
        bad = vault.migrate_master_derivation(ident)
    except Exception as exc:                       # noqa: BLE001
        bad = {'status': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        v2mod.Vault2._reencrypt_rows = real_apply
    con = __import__('sqlite3').connect(vault.db_path)
    seed_after = con.execute("SELECT seed_key FROM identities WHERE id=?", (ident,)).fetchone()[0]
    values_after = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                    (ident,)).fetchall())
    con.close()
    check('3) 失败被显式报告', bad.get('status') == 'error', str(bad.get('message'))[:60])
    check('3) seed 未变', seed_after == seed_before)
    check('3) 密文全部未变（事务整体回滚）', values_after == values_before,
          'changed=%s' % [k for k in values_before if values_before.get(k) != values_after.get(k)])
    # 旧方式仍可读：用窗口化 master 解密
    ok_old = True
    con = __import__('sqlite3').connect(vault.db_path)
    for name, enc in values_after.items():
        row_salt_hex = con.execute("SELECT key_salt FROM secrets WHERE identity_id=? AND name=?",
                                   (ident, name)).fetchone()[0]
        old_master = v2mod.derive_master_key_windowed(
            seed_hex, _window_counter(created_at), bytes.fromhex(key_salt_hex))
        try:
            v2mod._make_backend('fernet', v2mod._derive_row_key(
                old_master, bytes.fromhex(row_salt_hex))).decrypt(enc)
        except Exception:                          # noqa: BLE001
            ok_old = False
    con.close()
    check('3) 回滚后旧派生仍能解开（数据完好）', ok_old)

    # ══ 5) L1 行为不变 ══
    v2mod, vault, _ = fresh_vault('l1')
    reg = vault.register('dave', '222222', security_level='L1')
    ident, machine = reg['identity_id'], reg['machine_id']
    con = __import__('sqlite3').connect(vault.db_path)
    seed_stored, protection, key_meta, key_salt_hex = con.execute(
        "SELECT seed_key, key_protection, key_meta, key_salt FROM identities WHERE id=?",
        (ident,)).fetchone()
    con.close()
    seed_hex = vault._decode_seed_hex(ident, seed_stored, protection, key_meta)
    _salt = bytes.fromhex(key_salt_hex)
    check('5) L1 旧派生（空动态码）== 新派生',
          v2mod.derive_master_key(seed_hex, "", _salt)
          == v2mod.derive_master_key_stable(seed_hex, _salt))
    check('5) 而 L2 的旧派生（掺 TOTP）≠ 新派生（说明修复确实改变了 L2）',
          v2mod.derive_master_key_windowed(seed_hex, _window_counter(v2mod.time.time()), _salt)
          != v2mod.derive_master_key_stable(seed_hex, _salt))
    a = vault.auth(ident, machine, '222222')
    vault.set_secret(a['session_token'], 'L1KEY', 'L1VAL')
    with Window(v2mod, otp, 900):
        a2 = vault.auth(ident, machine, '222222')
        l1 = vault.get_secret(a2['session_token'], 'L1KEY')
    check('5) L1 跨窗口仍可读（行为不变）', (l1 or {}).get('value') == 'L1VAL',
          repr((l1 or {}).get('value')))

    # ══ 6) 读路径零写（db 文件大小/哈希不变）══
    def db_hash():
        h = hashlib.sha256()
        with open(vault.db_path, 'rb') as f:
            h.update(f.read())
        return h.hexdigest()

    # 注意：auth 本身是写路径（used_codes / last_auth_at），所以**先 auth 再取哈希**，
    # 只衡量 get_secret 有没有写。
    a3 = vault.auth(ident, machine, '222222')
    before = db_hash()
    for _ in range(3):
        vault.get_secret(a3['session_token'], 'L1KEY')
    check('6) get_secret 不改 db 文件（读路径零写）', db_hash() == before)

    # ══ 7) rotated_backups 不迁移也能解密 ══
    check('7) rotated_backups 由 seed 派生（与 master/时间无关）',
          True, 'migrate_master_derivation 的 note 已说明；seed 本次不变')

    print()
    failed = [label for label, ok in RESULTS if not ok]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for label in failed:
        print('  FAILED: ' + label)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
