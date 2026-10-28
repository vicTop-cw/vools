"""P0 的 **A/B 对照**：动态码掺进 KDF（旧） vs 不掺（新）。

第 15 轮发现：`master_key = PBKDF2(seed_key_hex + TOTP(60s), key_salt)` ⇒
L2/L3 的 secrets 在**下一个时间窗口**就解不开（`register()` 默认 L2）。
第 16 轮修复：master 只由 `seed_key + key_salt` 决定，动态码只做认证挑战。

本脚本用同一段流程跑两遍，证明修复确实有效：
  A) **修复后**（当前代码）：窗口1 写入 → 窗口2 读 → **成功**
  B) **旧行为**（把派生 monkeypatch 回"掺 TOTP"，并关掉登录自动迁移）：
     窗口1 写入 → 窗口2 读 → **失败**（事故复现）

更完整的迁移验收（中途失败回滚 / 幂等 / L1 不变 / 读路径零写）见
`tools/audit/verify_vault2_master_migration.py`。

跑法：`python tools/audit/prove_vault2_window_master.py`（tmp 隔离）
"""
import os
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def _fresh():
    sandbox = tempfile.mkdtemp(prefix='v2ab-')
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
    """把 time 模块的 time() 推后 delta 秒（vault2 与 otp 两个模块都要推）。"""

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
        for mod, real in zip(self.mods, self.saved):
            mod.time = real
        return False


def run_case(old_behavior: bool):
    v2mod, otp, vault = _fresh()
    real_stable = v2mod.derive_master_key_stable
    real_migrate = v2mod.Vault2.migrate_master_derivation
    if old_behavior:
        # 复刻事故：派生掺入当前窗口的 TOTP；并关掉登录自动迁移
        v2mod.derive_master_key_stable = lambda seed, salt: v2mod.derive_master_key_windowed(
            seed, int(v2mod.time.time()) // 60, salt)
        v2mod.Vault2.migrate_master_derivation = lambda self, identity_id=None: {'status': 'skipped'}
    try:
        reg = vault.register('u', '123456', security_level='L2')
        ident, machine = reg['identity_id'], reg['machine_id']
        a1 = vault.auth(ident, machine, '123456')
        vault.set_secret(a1['session_token'], 'K', 'SECRET')
        with Shift([v2mod, otp], 300):
            a2 = vault.auth(ident, machine, '123456')
            got = vault.get_secret(a2['session_token'], 'K') if a2.get('session_token') else {}
        return (got or {}).get('status') == 'ok', (got or {}).get('value')
    finally:
        v2mod.derive_master_key_stable = real_stable
        v2mod.Vault2.migrate_master_derivation = real_migrate


def main():
    ok_new, val_new = run_case(old_behavior=False)
    ok_old, val_old = run_case(old_behavior=True)
    print('A) 修复后（当前代码）  ：窗口1 写 → 窗口2 读 =',
          '成功' if ok_new else '失败', '| value =', repr(val_new))
    print('B) 旧行为（派生怕 TOTP）：窗口1 写 → 窗口2 读 =',
          '成功' if ok_old else '失败', '| value =', repr(val_old))
    print()
    passed = ok_new and not ok_old and val_new == 'SECRET'
    print('结论：修复有效 =', passed, '（A 必须成功、B 必须失败）')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
