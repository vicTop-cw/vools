"""KEK 轮换**第 0 步**验收（docs/vault2-kek-rotation.md §4.4）。

1) 现有库（无 `kek_gen`、无 `kek_retired` 表）打开 → `kek_gen == 0`，无迁移告警
2) 新建库 → `status()` 三个新字段齐全（`kek_gen` / `kek_retired_count` / `kek_rotation_supported`）
3) `kek_retired` 表存在但 **0 行**（本步不写入）
4) `status()` 对**不存在**的库 → 不建目录、不建库、不建表
5) 零行为变化：register / auth / set / get / rotate_seed_key 全照旧
6) `_init_schema()` 幂等（连跑 3 次不报错、不改变数据）

跑法：`python tools/audit/verify_vault2_kek_step0.py`（全 tmp 隔离）
"""
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


def fresh(tag):
    sandbox = tempfile.mkdtemp(prefix='kek0-%s-' % tag)
    vdir = os.path.join(sandbox, 'vault2')
    os.environ['ACTUS_VAULT2_DIR'] = vdir
    os.environ['ACTUS_VAULT2_PASSPHRASE'] = 'unit-test-passphrase'
    os.environ['HOME'] = sandbox
    os.environ['USERPROFILE'] = sandbox
    for k in ('VAULT_IDENTITY_ID', 'VAULT_MACHINE_ID', 'VAULT_PIN'):
        os.environ.pop(k, None)
    import importlib
    import vools.actus.vault2 as v2mod
    importlib.reload(v2mod)
    return v2mod, vdir, sandbox


def tree(root):
    rows = []
    for dirpath, _d, files in os.walk(root):
        for n in sorted(files):
            full = os.path.join(dirpath, n)
            st = os.stat(full)
            rows.append((os.path.relpath(full, root), st.st_size, st.st_mtime_ns))
    return sorted(rows)


def table_rows(db, sql, params=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def main():
    # ── 4) status() 对不存在的库：零写 ──
    v2mod, vdir, sandbox = fresh('missing')
    before = tree(sandbox)
    st = v2mod.Vault2().status()
    after = tree(sandbox)
    check('4) status() 对不存在的库 → 不建目录/库/表', before == after and not os.path.exists(vdir),
          'before=%d after=%d' % (len(before), len(after)))
    check('4) status().state == missing', st.get('state') == 'missing', str(st.get('state')))
    check('4) 不存在的库 kek_gen 仍报 0（不建库也不报错）', st.get('kek_gen') == 0,
          str(st.get('kek_gen')))

    # ── 2) 新建库：三个字段齐全 ──
    v = v2mod.Vault2()
    reg = v.register('kek-user', '123456', security_level='L2')
    st = v.status()
    need = ('kek_gen', 'kek_retired_count', 'kek_rotation_supported')
    missing = [k for k in need if k not in st]
    check('2) 新建库 status() 三字段齐全', not missing, 'missing=%s' % missing)
    check('2) 新库 kek_gen == 0', st.get('kek_gen') == 0, str(st.get('kek_gen')))
    check('2) 新库 kek_retired_count == 0', st.get('kek_retired_count') == 0,
          str(st.get('kek_retired_count')))
    check('2) passphrase 模式 kek_rotation_supported == True',
          st.get('kek_rotation_supported') is True, str(st.get('kek_rotation_supported')))

    # ── 3) kek_retired 表存在但 0 行 ──
    rows = table_rows(v.db_path, "SELECT name FROM sqlite_master WHERE type='table' AND name='kek_retired'")
    check('3) kek_retired 表已建', bool(rows), str(rows))
    cnt = table_rows(v.db_path, "SELECT COUNT(*) FROM kek_retired")[0][0]
    check('3) kek_retired 0 行（本步不写入）', cnt == 0, 'rows=%d' % cnt)
    cols = [r[1] for r in table_rows(v.db_path, "PRAGMA table_info(kek_retired)")]
    check('3) 表结构与设计一致',
          cols == ['identity_id', 'kek_gen', 'locator', 'retired_at', 'cleaned'], str(cols))

    # ── 5) 零行为变化 ──
    ident, machine = reg['identity_id'], reg['machine_id']
    a = v.auth(ident, machine, '123456')
    check('5) auth 照旧', a.get('status') == 'ok', str(a.get('message')))
    tok = a['session_token']
    check('5) set 照旧', v.set_secret(tok, 'K', 'V').get('status') == 'ok')
    check('5) get 照旧', (v.get_secret(tok, 'K') or {}).get('value') == 'V')
    rot = v.rotate_seed_key(tok)
    check('5) rotate_seed_key 照旧', rot.get('status') == 'ok', str(rot.get('message')))
    check('5) 轮换后 kek_gen 仍为 0（本步不写代数）',
          v.status().get('kek_gen') == 0, str(v.status().get('kek_gen')))

    # ── 1) 现有库（模拟"第 0 步之前"的库）：无 kek_gen、无 kek_retired 表 ──
    v2mod2, vdir2, sandbox2 = fresh('legacy')
    v2 = v2mod2.Vault2()
    reg2 = v2.register('legacy-user', '654321', security_level='L2')
    a2 = v2.auth(reg2['identity_id'], reg2['machine_id'], '654321')
    v2.set_secret(a2['session_token'], 'OLD', 'OLDVAL')
    con = sqlite3.connect(v2.db_path)
    con.execute("DROP TABLE kek_retired")                    # 模拟旧库没有这张表
    # 模拟旧库 key_meta **里没有 kek_gen 字段**（但保留 passphrase 的 salt/iters ——
    # 清空整个 key_meta 会连盐一起丢掉，那是"库被打坏"，不是"旧库"）
    import json as _json
    old_meta = con.execute("SELECT key_meta FROM identities").fetchone()[0]
    meta_obj = _json.loads(old_meta) if old_meta else {}
    meta_obj.pop('kek_gen', None)
    con.execute("UPDATE identities SET key_meta=?", (_json.dumps(meta_obj),))
    con.commit()
    con.close()
    # 重新打开（新进程语义）
    import importlib
    import vools.actus.vault2 as v2b
    importlib.reload(v2b)
    reopened = v2b.Vault2()
    st2 = reopened.status()
    check('1) 旧库打开 → kek_gen == 0（向后兼容，不迁移）', st2.get('kek_gen') == 0,
          str(st2.get('kek_gen')))
    check('1) 旧库打开 → 无迁移告警字段', 'migrated_key_protection' not in st2
          or st2.get('migrated_key_protection') == 0, str(st2.get('migrated_key_protection')))
    check('1) 旧库自动补建 kek_retired（只在库已存在时）',
          bool(table_rows(reopened.db_path,
                          "SELECT name FROM sqlite_master WHERE type='table' AND name='kek_retired'")))
    # 换一个 60s 窗口再 auth（同一窗口的动态码已被上面的 auth 消费，防重放会拦）
    import types
    import vools.security.otp as otp
    _saved = (v2b.time, otp.time)
    for mod, real in ((v2b, _saved[0]), (otp, _saved[1])):
        shim = types.SimpleNamespace()
        for attr in dir(real):
            if not attr.startswith('__'):
                try:
                    setattr(shim, attr, getattr(real, attr))
                except Exception:              # noqa: BLE001
                    pass
        shim.time = (lambda real=real: real.time() + 120)
        mod.time = shim
    try:
        a3 = reopened.auth(reg2['identity_id'], reg2['machine_id'], '654321')
    finally:
        v2b.time, otp.time = _saved
    check('1) 旧库数据仍可读', (reopened.get_secret(a3['session_token'], 'OLD') or {})
          .get('value') == 'OLDVAL')

    # ── 6) _init_schema 幂等（3 次） ──
    ok = True
    detail = ''
    for i in range(3):
        try:
            reopened._init_schema()
            reopened._ready = False      # 允许再次跑完整 ready
            reopened._ensure_ready()
        except Exception as exc:         # noqa: BLE001
            ok = False
            detail = '%s: %s' % (type(exc).__name__, exc)
            break
    check('6) _init_schema 连跑 3 次幂等', ok, detail)
    check('6) 幂等后数据未变', (reopened.get_secret(a3['session_token'], 'OLD') or {})
          .get('value') == 'OLDVAL')
    check('6) 幂等后 kek_retired 仍 0 行',
          table_rows(reopened.db_path, "SELECT COUNT(*) FROM kek_retired")[0][0] == 0)

    print()
    failed = [l for l, ok_ in RESULTS if not ok_]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
