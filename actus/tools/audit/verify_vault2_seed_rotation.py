"""`seed_key` 轮换验收（6 项，全 tmp 隔离）。

1) 轮换后：所有 secrets 仍可读、seed_key 变了
2) 轮换后：`rotated_backups` 仍能 rollback（**最容易漏**：备份由 seed 派生）
3) 中途失败（注入异常）→ seed 未变、密文全未变、旧数据仍可读
4) 连续两次轮换都成功
5) 读路径仍零写（get_secret / list_secrets 不改 db）
6) 跨窗口读仍正常（P0 未回归）

跑法：`python tools/audit/verify_vault2_seed_rotation.py`
"""
import hashlib
import os
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', label, (': ' + detail) if detail else ''))


def fresh():
    sandbox = tempfile.mkdtemp(prefix='v2rot-')
    os.environ['ACTUS_VAULT2_DIR'] = os.path.join(sandbox, 'vault2')
    os.environ['HOME'] = sandbox
    os.environ['USERPROFILE'] = sandbox
    os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'unit-test-passphrase'
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    import importlib
    import vools.actus.vault2 as v2mod
    import vools.security.otp as otp
    importlib.reload(v2mod)
    return v2mod, otp, v2mod._get_vault2()


class Shift:
    def __init__(self, mods, delta):
        self.mods, self.delta = mods, delta

    def __enter__(self):
        import types
        self.saved = [m.time for m in self.mods]
        for mod, real in zip(self.mods, self.saved):
            shim = types.SimpleNamespace()
            for attr in dir(real):
                if not attr.startswith('__'):
                    try:
                        setattr(shim, attr, getattr(real, attr))
                    except Exception:              # noqa: BLE001
                        pass
            shim.time = (lambda real=real: real.time() + self.delta)
            mod.time = shim
        return self

    def __exit__(self, *exc):
        import types
        for mod, real in zip(self.mods, self.saved):
            mod.time = real
        return False


def reauth(v2mod, otp, vault, ident, machine, pin, step):
    """换一个 60s 窗口再 auth（同窗口的 TOTP 已被上一次 auth 消费，会被防重放拦住）。"""
    with Shift([v2mod, otp], 120 * step):
        return vault.auth(ident, machine, pin)


def db_hash(vault):
    h = hashlib.sha256()
    with open(vault.db_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    v2mod, otp, vault = fresh()
    reg = vault.register('alice', '123456', security_level='L2')
    ident, machine = reg['identity_id'], reg['machine_id']
    a = vault.auth(ident, machine, '123456')
    tok = a['session_token']

    # 准备数据：两条 secret + 一条 rotated_backup（rotate_secret 会产生备份）
    vault.set_secret(tok, 'K1', 'VALUE-1')
    vault.set_secret(tok, 'K2', 'VALUE-2')
    rot = vault.rotate_secret(tok, 'K1', 'VALUE-1-NEW')     # 生成 rotated_backups
    with __import__('sqlite3').connect(vault.db_path) as con:
        seed_before = con.execute("SELECT seed_key FROM identities WHERE id=?",
                                  (ident,)).fetchone()[0]
        enc_before = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                      (ident,)).fetchall())
        backups_before = con.execute("SELECT COUNT(*) FROM rotated_backups WHERE identity_id=?",
                                     (ident,)).fetchone()[0]
    check('0) 前置：rotate_secret 产生了备份', rot.get('status') == 'ok' and backups_before >= 1,
          'backups=%d' % backups_before)

    # ══ 1) 轮换后 secrets 可读、seed 变了 ══
    res = vault.rotate_seed_key(tok)
    check('1) 轮换返回 ok', res.get('status') == 'ok', str(res.get('message', ''))[:80])
    with __import__('sqlite3').connect(vault.db_path) as con:
        seed_after = con.execute("SELECT seed_key FROM identities WHERE id=?",
                                 (ident,)).fetchone()[0]
        enc_after = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                     (ident,)).fetchall())
    check('1) seed_key 变了', seed_after != seed_before)
    check('1) 所有密文都被重写', enc_after != enc_before,
          'changed=%d/%d' % (sum(1 for k in enc_before if enc_before[k] != enc_after.get(k)),
                             len(enc_before)))
    # 旧会话已被失效（master 过期）→ 换窗口重新 auth 读回
    a2 = reauth(v2mod, otp, vault, ident, machine, '123456', 1)
    got = {n: (vault.get_secret(a2['session_token'], n) or {}).get('value')
           for n in ('K1', 'K2')}
    check('1) 轮换后 secrets 仍可读', got == {'K1': 'VALUE-1-NEW', 'K2': 'VALUE-2'}, str(got))
    check('1) 旧会话确实被失效', (vault.get_secret(tok, 'K1') or {}).get('status') != 'ok')

    # ══ 2) rotated_backups 仍能 rollback（关键：备份也依赖 seed）══
    rb = vault.rollback_secret(a2['session_token'], 'K1')
    check('2) 轮换后 rollback 仍可用（备份被一起重加密）',
          rb.get('status') == 'ok', str(rb.get('message', ''))[:80])
    got_after_rb = (vault.get_secret(a2['session_token'], 'K1') or {}).get('value')
    check('2) rollback 后值回到旧值', got_after_rb == 'VALUE-1', repr(got_after_rb))

    # ══ 4) 连续两次轮换都成功 ══
    a3 = reauth(v2mod, otp, vault, ident, machine, '123456', 2)
    r1 = vault.rotate_seed_key(a3['session_token'])
    a4 = reauth(v2mod, otp, vault, ident, machine, '123456', 3)
    r2 = vault.rotate_seed_key(a4['session_token'])
    check('4) 连续两次轮换都成功', r1.get('status') == 'ok' and r2.get('status') == 'ok',
          '%s / %s' % (r1.get('status'), r2.get('status')))

    # ══ 6) 跨窗口仍可读（P0 未回归）══
    a5 = reauth(v2mod, otp, vault, ident, machine, '123456', 4)
    with Shift([v2mod, otp], 600):
        a6 = vault.auth(ident, machine, '123456')
        across = (vault.get_secret(a6['session_token'], 'K2') or {}).get('value')
    check('6) 轮换后跨窗口仍可读（P0 未回归）', across == 'VALUE-2', repr(across))

    # ══ 5) 读路径零写 ══
    a7 = reauth(v2mod, otp, vault, ident, machine, '123456', 9)
    h_before = db_hash(vault)
    for _ in range(3):
        vault.get_secret(a7['session_token'], 'K2')
    vault.list_secrets(a7['session_token'])
    check('5) get_secret / list_secrets 不改 db', db_hash(vault) == h_before)

    # ══ 3) 中途失败注入 → 全回滚 ══
    v2mod2, otp2, vault2i = fresh()
    reg2 = vault2i.register('bob', '654321', security_level='L2')
    ident2, machine2 = reg2['identity_id'], reg2['machine_id']
    a8 = vault2i.auth(ident2, machine2, '654321')
    vault2i.set_secret(a8['session_token'], 'X', 'XVALUE')
    vault2i.rotate_secret(a8['session_token'], 'X', 'XVALUE2')   # 造备份
    with __import__('sqlite3').connect(vault2i.db_path) as con:
        seed_b = con.execute("SELECT seed_key FROM identities WHERE id=?", (ident2,)).fetchone()[0]
        sec_b = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                 (ident2,)).fetchall())
        bak_b = dict(con.execute("SELECT id, value FROM rotated_backups WHERE identity_id=?",
                                 (ident2,)).fetchall())
    # 注入点：写阶段的 seam —— 先写一部分再抛错，验证事务**整体回滚**
    real_apply = v2mod2.Vault2._apply_seed_rotation
    state = {'n': 0}

    def flaky_apply(self, conn, identity_id, new_envelope, secret_updates, backup_updates):
        # 先真正写一条 secrets，再炸 —— 若没有事务，就会留下"半新半旧"
        if secret_updates:
            conn.execute("UPDATE secrets SET value=? WHERE id=?",
                         (secret_updates[0][1], secret_updates[0][0]))
        raise RuntimeError('模拟轮换写阶段失败')

    v2mod2.Vault2._apply_seed_rotation = flaky_apply
    try:
        bad = vault2i.rotate_seed_key(a8['session_token'])
    except Exception as exc:                       # noqa: BLE001
        bad = {'status': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        v2mod2.Vault2._apply_seed_rotation = real_apply
    with __import__('sqlite3').connect(vault2i.db_path) as con:
        seed_c = con.execute("SELECT seed_key FROM identities WHERE id=?", (ident2,)).fetchone()[0]
        sec_c = dict(con.execute("SELECT name, value FROM secrets WHERE identity_id=?",
                                 (ident2,)).fetchall())
        bak_c = dict(con.execute("SELECT id, value FROM rotated_backups WHERE identity_id=?",
                                 (ident2,)).fetchall())
    check('3) 失败被显式报告', bad.get('status') == 'error', str(bad.get('message', ''))[:70])
    check('3) seed 未变', seed_c == seed_b)
    check('3) secrets 密文全未变', sec_c == sec_b)
    check('3) rotated_backups 密文全未变（无半截状态）', bak_c == bak_b)
    after_fail = vault2i.get_secret(a8['session_token'], 'X') or {}
    check('3) 旧会话 master 仍可解数据（数据完好）', after_fail.get('value') == 'XVALUE2',
          repr(after_fail.get('value')))

    print()
    failed = [l for l, ok in RESULTS if not ok]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
