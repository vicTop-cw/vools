"""KEK 轮换**第 1 步**验收：passphrase 模式单事务轮换。

1) 轮换成功：`kek_gen` 0 → 1、salt 变了、信封变了、**seed 与 secrets 密文未变**
2) 轮换后数据仍可读；**新进程式重开**（重新实例化）也能解
3) `status().kek_gen` 反映新代数（`kek_gen_max` 同步）
4) `kek_retired` 仍 0 行（passphrase 无外部条目）
5) 失败注入（写阶段抛错）→ **全回滚**：seed 信封 / key_meta / kek_gen 全不变、数据可读
6) keyring / file-key 模式 → **明确拒绝**（`kek_rotation_unsupported`），且零写
7) 传新 passphrase → 轮换后**旧口令**解不开、新口令可解
8) 连续两次轮换 → 代数 1 → 2

跑法：`python tools/audit/verify_vault2_kek_step1.py`（全 tmp 隔离）
"""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok))
    print('%s %s%s' % ('PASS' if ok else 'FAIL', label, (': ' + detail) if detail else ''))


def fresh(tag, protection='passphrase'):
    sandbox = tempfile.mkdtemp(prefix='kek1-%s-' % tag)
    vdir = os.path.join(sandbox, 'vault2')
    os.environ['ACTUS_VAULT2_DIR'] = vdir
    os.environ['HOME'] = sandbox
    os.environ['USERPROFILE'] = sandbox
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    if protection == 'passphrase':
        os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'old-passphrase'
    elif protection == 'file-key':
        os.environ.pop('ACTUS_VAULT2_PASSPHRASE', None)
    import importlib
    import vools.actus.vault2 as v2mod
    importlib.reload(v2mod)
    return v2mod, vdir, sandbox


def snap(root):
    rows = []
    for dirpath, _d, files in os.walk(root):
        for n in sorted(files):
            full = os.path.join(dirpath, n)
            st = os.stat(full)
            rows.append((os.path.relpath(full, root), st.st_size, st.st_mtime_ns))
    return sorted(rows)


def ident_row(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT seed_key, key_meta FROM identities").fetchone()
    finally:
        con.close()


def secret_hashes(db):
    con = sqlite3.connect(db)
    try:
        return {r[0]: r[1] for r in con.execute("SELECT name, value FROM secrets")}
    finally:
        con.close()


def retired_count(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT COUNT(*) FROM kek_retired").fetchone()[0]
    finally:
        con.close()


def reauth_window(v2mod, delta=120):
    """换窗口再 auth（同窗口 TOTP 已被消费，防重放会拦）。"""
    import types
    import vools.security.otp as otp
    saved = (v2mod.time, otp.time)
    for mod, real in ((v2mod, saved[0]), (otp, saved[1])):
        shim = types.SimpleNamespace()
        for attr in dir(real):
            if not attr.startswith('__'):
                try:
                    setattr(shim, attr, getattr(real, attr))
                except Exception:              # noqa: BLE001
                    pass
        shim.time = (lambda real=real: real.time() + delta)
        mod.time = shim
    return saved


def main():
    # ── 1) 轮换成功 ──
    v2mod, vdir, sandbox = fresh('ok')
    v = v2mod.Vault2()
    reg = v.register('kek-u', '123456', security_level='L2')
    a = v.auth(reg['identity_id'], reg['machine_id'], '123456')
    tok = a['session_token']
    v.set_secret(tok, 'K1', 'V1')
    v.set_secret(tok, 'K2', 'V2')
    seed_before, meta_before = ident_row(v.db_path)
    secrets_before = secret_hashes(v.db_path)
    check('0) 轮换前 kek_gen == 0', v.status().get('kek_gen') == 0, str(v.status().get('kek_gen')))

    res = v.rotate_kek(tok, caller='test')
    check('1) 轮换返回 ok', res.get('status') == 'ok', str(res.get('message'))[:80])
    check('1) kek_gen 0 → 1', res.get('kek_gen_old') == 0 and res.get('kek_gen') == 1,
          '%s → %s' % (res.get('kek_gen_old'), res.get('kek_gen')))
    seed_after, meta_after = ident_row(v.db_path)
    check('1) 信封变了', seed_after != seed_before)
    check('1) key_meta 里有 kek_gen=1',
          json.loads(meta_after).get('kek_gen') == 1, meta_after[:60])
    check('1) salt 变了', json.loads(meta_after).get('salt') != json.loads(meta_before).get('salt'))
    check('1) **secrets 密文完全未变**', secret_hashes(v.db_path) == secrets_before)
    check('1) kek_retired 未写入（仍 0 行）', retired_count(v.db_path) == 0)

    # ── 2) 数据仍可读 + 新实例重开也能解 ──
    check('2) 轮换后 secret 仍可读', (v.get_secret(tok, 'K1') or {}).get('value') == 'V1')
    import importlib
    import vools.actus.vault2 as v2b
    importlib.reload(v2b)
    reopened = v2b.Vault2()
    saved = reauth_window(v2b)
    try:
        a2 = reopened.auth(reg['identity_id'], reg['machine_id'], '123456')
    finally:
        v2b.time, otp_time = saved
        import vools.security.otp as _otp
        _otp.time = otp_time
    check('2) 新实例能 auth（新 salt 可解信封）', a2.get('status') == 'ok', str(a2.get('message'))[:60])
    check('2) 新实例能读数据', (reopened.get_secret(a2['session_token'], 'K2') or {})
          .get('value') == 'V2')

    # ── 3) status().kek_gen 反映新代数 ──
    st = reopened.status()
    check('3) status().kek_gen == 1', st.get('kek_gen') == 1, str(st.get('kek_gen')))
    check('3) status().kek_gen_max == 1', st.get('kek_gen_max') == 1, str(st.get('kek_gen_max')))

    # ── 8) 连续两次轮换 ──
    r2 = reopened.rotate_kek(a2['session_token'])
    check('8) 连续两次轮换：1 → 2', r2.get('status') == 'ok' and r2.get('kek_gen') == 2,
          '%s → %s' % (r2.get('kek_gen_old'), r2.get('kek_gen')))
    check('8) 两次轮换后数据仍可读', (reopened.get_secret(a2['session_token'], 'K1') or {})
          .get('value') == 'V1')

    # ── 5) 失败注入 → 全回滚 ──
    v2mod3, vdir3, sb3 = fresh('rollback')
    v3 = v2mod3.Vault2()
    reg3 = v3.register('rb-u', '654321', security_level='L2')
    a3 = v3.auth(reg3['identity_id'], reg3['machine_id'], '654321')
    tok3 = a3['session_token']
    v3.set_secret(tok3, 'X', 'XV')
    seed_pre, meta_pre = ident_row(v3.db_path)
    secrets_pre = secret_hashes(v3.db_path)
    real_apply = v2mod3.Vault2._apply_kek_rotation

    def boom(self, conn, identity_id, new_envelope, new_meta):
        conn.execute("UPDATE identities SET seed_key=?, key_meta=? WHERE id=?",
                     (new_envelope, new_meta, identity_id))     # 先写，再炸
        raise RuntimeError('模拟 KEK 写阶段失败')

    v2mod3.Vault2._apply_kek_rotation = boom
    try:
        bad = v3.rotate_kek(tok3)
    except Exception as exc:                       # noqa: BLE001
        bad = {'status': 'error', 'message': '%s: %s' % (type(exc).__name__, exc)}
    finally:
        v2mod3.Vault2._apply_kek_rotation = real_apply
    seed_post, meta_post = ident_row(v3.db_path)
    check('5) 失败被显式报告', bad.get('status') == 'error', str(bad.get('message'))[:60])
    check('5) 事务回滚：信封未变', seed_post == seed_pre)
    check('5) 事务回滚：key_meta 未变（kek_gen 仍 0）',
          json.loads(meta_post).get('kek_gen', 0) == 0)
    check('5) 事务回滚：secrets 未变', secret_hashes(v3.db_path) == secrets_pre)
    check('5) 回滚后数据仍可读', (v3.get_secret(tok3, 'X') or {}).get('value') == 'XV')
    check('5) 回滚后 status().kek_gen 仍 0', v3.status().get('kek_gen') == 0)

    # ── 6) **不可用模式** → 明确拒绝 + 零写 ──
    # 第 22 轮 keyring 落地、第 23 轮 file-key 落地 ⇒ 三种真实模式都支持轮换了。
    # 仍然存在的拒绝分支是"没有可用 KEK"（unavailable / legacy-plaintext）。
    # 这里直接把实例的 key_protection 改成 unavailable 来验该分支 ——
    # 既保住了"拒绝路径"的覆盖，又不再与某个具体模式绑定（原断言已随实现失效）。
    v2m, vd, sb = fresh('unsupported')
    vm = v2m.Vault2()
    regm = vm.register('un-u', '111111', security_level='L2')
    am = vm.auth(regm['identity_id'], regm['machine_id'], '111111')
    before = snap(sb)
    vm.key_protection = 'unavailable'
    rej = vm.rotate_kek(am['session_token'])
    after = snap(sb)
    check('6) unavailable 模式 → kek_rotation_unsupported',
          rej.get('code') == 'kek_rotation_unsupported', str(rej.get('code')))
    check('6) 拒绝时**零写**', before == after)
    check('6) 拒绝消息说明该模式无可用 KEK', '没有可用 KEK' in (rej.get('message') or ''),
          (rej.get('message') or '')[:70])

    # ── 7) 新 passphrase ──
    v2p, vdp, sbp = fresh('newpass')
    vp = v2p.Vault2()
    regp = vp.register('np-u', '222222', security_level='L2')
    ap = vp.auth(regp['identity_id'], regp['machine_id'], '222222')
    vp.set_secret(ap['session_token'], 'P', 'PV')
    rp = vp.rotate_kek(ap['session_token'], new_passphrase='brand-new-passphrase')
    check('7) 换口令轮换成功', rp.get('status') == 'ok', str(rp.get('message'))[:60])
    check('7) 有"必须同步环境变量"警告',
          any('ACTUS_VAULT2_PASSPHRASE' in w for w in (rp.get('warnings') or [])))
    # 旧口令：新实例 → 应解不开
    os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'old-passphrase'
    importlib.reload(v2p)
    old_inst = v2p.Vault2()
    try:
        old_ok = old_inst.auth(regp['identity_id'], regp['machine_id'], '222222')
    except Exception as exc:                       # noqa: BLE001
        old_ok = {'status': 'error', 'message': str(exc)}
    check('7) 旧口令解不开（明确报错，不静默）', old_ok.get('status') != 'ok',
          str(old_ok.get('message'))[:60])
    os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'brand-new-passphrase'
    importlib.reload(v2p)
    new_inst = v2p.Vault2()
    saved2 = reauth_window(v2p, 240)
    try:
        anew = new_inst.auth(regp['identity_id'], regp['machine_id'], '222222')
    finally:
        v2p.time, otp_time2 = saved2
        import vools.security.otp as _otp2
        _otp2.time = otp_time2
    check('7) 新口令可正常 auth', anew.get('status') == 'ok', str(anew.get('message'))[:60])
    check('7) 新口令下数据可读', (new_inst.get_secret(anew['session_token'], 'P') or {})
          .get('value') == 'PV')

    print()
    failed = [l for l, ok_ in RESULTS if not ok_]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
