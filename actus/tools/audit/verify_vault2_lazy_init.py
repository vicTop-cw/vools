"""验收：`Vault2` 懒创建（构造零 FS）+ 读路径不建库 + dry-run 零写。

1) 构造 `Vault2()`（库不存在）→ **零文件系统副作用**
2) 读路径（get_secret / list_secrets / status）→ 明确"没有密钥"，**不建库**
3) 写路径（register → set_secret）→ 自动建库并成功
4) `_get_vault2()` → 不建库；`_get_vault2(create=True)` → 才建
5) `rotate_seed_key(apply=False)` → 零写 + 返回统计
6) `status()` 能区分 missing / empty / ok（corrupt 单独判定）

跑法：`python tools/audit/verify_vault2_lazy_init.py`（全 tmp 隔离）
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


def fresh(tag):
    sandbox = tempfile.mkdtemp(prefix='v2lazy-%s-' % tag)
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


def tree_snapshot(root):
    """目录树快照（相对路径 + size + mtime_ns）——用于证明"零 FS 副作用"。"""
    rows = []
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            st = os.stat(full)
            rows.append((os.path.relpath(full, root), st.st_size, st.st_mtime_ns))
    return sorted(rows)


def main():
    # ── 1) 构造零 FS ──
    v2mod, vdir, sandbox = fresh('ctor')
    before = tree_snapshot(sandbox)
    v = v2mod.Vault2()
    after = tree_snapshot(sandbox)
    check('1) 构造 Vault2() 零 FS 副作用', before == after, 'before=%d after=%d'
          % (len(before), len(after)))
    check('1) 构造后库文件仍不存在', not os.path.isfile(v.db_path))
    check('1) 构造后目录都未创建', not os.path.isdir(vdir))

    # ── 2) 读路径不建库 ──
    r_get = v.get_secret('no-such-token', 'K')
    r_list = v.list_secrets('no-such-token')
    r_status = v.status()
    check('2) get_secret → 与"查不到"同形', r_get.get('message') == '凭证不存在', str(r_get))
    check('2) list_secrets → 空列表 + vault_exists=False',
          r_list.get('count') == 0 and r_list.get('secrets') == []
          and r_list.get('vault_exists') is False, str(r_list))
    check('2) status → state=missing', r_status.get('state') == 'missing', str(r_status.get('state')))
    check('2) 三个读路径都**未建库**', not os.path.isfile(v.db_path))
    check('2) 连目录都没建', not os.path.isdir(vdir))

    # ── 4) _get_vault2() 不建库 ──
    v2mod._vault2_singleton = None
    got = v2mod._get_vault2()
    check('4) _get_vault2() 不建库', not os.path.isfile(got.db_path))
    check('4) 返回的是可用实例（路径已算好）', got.db_path.endswith('vault2.db'))

    # ── 3) 写路径自动建库 ──
    reg = got.register('lazy-user', '123456', security_level='L2')
    check('3) register 建库成功', reg.get('status') == 'ok', str(reg.get('message')))
    check('3) 库文件已创建', os.path.isfile(got.db_path))
    check('3) status → state=ok', got.status().get('state') == 'ok', got.status().get('state'))
    a = got.auth(reg['identity_id'], reg['machine_id'], '123456')
    st = got.set_secret(a['session_token'], 'K', 'V')
    check('3) set_secret 成功', st.get('status') == 'ok', str(st.get('message')))
    check('3) 读回一致', (got.get_secret(a['session_token'], 'K') or {}).get('value') == 'V')

    # ── 3b) 空库态（有文件、零身份）──
    empty_sandbox = tempfile.mkdtemp(prefix='v2lazy-empty-')
    empty_vdir = os.path.join(empty_sandbox, 'vault2')
    os.environ['ACTUS_VAULT2_DIR'] = empty_vdir
    os.environ['HOME'] = empty_sandbox
    os.environ['USERPROFILE'] = empty_sandbox
    import importlib
    import vools.actus.vault2 as v2b
    importlib.reload(v2b)
    ev = v2b.Vault2()._ensure_ready()          # 显式 ready → 建空库
    check('3b) status → state=empty（库在但零身份）',
          ev.status().get('state') == 'empty', ev.status().get('state'))

    # ── 5) rotate_seed_key(apply=False) 零写 ──
    v2mod, vdir, sandbox = fresh('dryrun')
    vault = v2mod.Vault2()
    reg = vault.register('dry-user', '123456', security_level='L2')
    a = vault.auth(reg['identity_id'], reg['machine_id'], '123456')
    tok = a['session_token']
    vault.set_secret(tok, 'K1', 'V1')
    vault.set_secret(tok, 'K2', 'V2')
    vault.rotate_secret(tok, 'K1', 'V1B')      # 造一条备份
    with open(vault.db_path, 'rb') as f:
        db_hash = hashlib.sha256(f.read()).hexdigest()
    dry = vault.rotate_seed_key(tok, apply=False)
    with open(vault.db_path, 'rb') as f:
        db_hash2 = hashlib.sha256(f.read()).hexdigest()
    check('5) dry-run 返回 ok + dry_run=True',
          dry.get('status') == 'ok' and dry.get('dry_run') is True, str(dry)[:80])
    check('5) dry-run 给出统计', dry.get('would_rotate_secrets') == 2
          and dry.get('would_rotate_backups', 0) >= 1, str(dry.get('would_rotate_secrets')))
    check('5) dry-run **零写**（db 哈希不变）', db_hash == db_hash2)
    check('5) dry-run 后数据仍可读',
          (vault.get_secret(tok, 'K2') or {}).get('value') == 'V2')
    real = vault.rotate_seed_key(tok)          # 真跑仍可用
    check('5) apply=True 仍正常', real.get('status') == 'ok' and real.get('dry_run') is False,
          str(real.get('status')))

    print()
    failed = [l for l, ok in RESULTS if not ok]
    print('SUMMARY: %d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    for l in failed:
        print('  FAILED: ' + l)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
