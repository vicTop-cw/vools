# -*- coding: utf-8 -*-
"""打开库恢复扫描（docs/vault2-kek-rotation.md L133：方案 C 的「进程启动/下次
打开库时扫未完成记录并补齐」）—— 真实实现测试。

背景：rotate 内部 GC 失败（delete_lag / fail_delete / shared）或进程在 C5 窗口
崩溃（旧代已删但未标 cleaned=1）都会在 `kek_retired` 留下 cleaned=0 行。此前
只有 rotate 内部的即时 GC，崩溃残留不会被自动补齐 —— 本测试覆盖新增的
`Vault2._recover_pending_kek_gc()`（挂在 `_ensure_ready()` 末尾，即每次打开库
都会执行）：

1. keyring C5 残留（旧代已删但未标 cleaned=1）→ 打开库补标 cleaned=1；
2. keyring delete_lag（旧代仍在）→ 打开库保持 pending；关掉 lag 后再打开即补齐；
3. file-key C5 残留（旧代文件被外部恢复）→ 打开库删除旧文件并补标；
4. file-key 共享旧代 → 打开库不删（shared 保护）保持 pending；
5. 干净库无 pending → 打开库零副作用（scanned=0、条目/文件数不变）。

一致性约定与 rotate 内部 GC 完全一致（I3：只有回读确认不在才标 cleaned=1）。
"""
import os
import sys

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

sys.path.insert(0, os.path.join(_ACTUS_ROOT, 'tools', 'audit'))
import fake_keyring as fk          # noqa: E402

from vools.actus import vault2     # noqa: E402


def _keyring_vault(tmp_path, monkeypatch, store):
    monkeypatch.setattr(vault2, 'probe_keyring',
                        lambda: (fk.FakeKeyringModule(store), 'ok'))
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_KEYRING)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)
    return vault2.Vault2(vault_dir=str(tmp_path / 'v2'))


def _filekey_vault(tmp_path, monkeypatch):
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_FILE)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)
    return vault2.Vault2(vault_dir=str(tmp_path / 'v2'))


def _prime(tmp_path, monkeypatch, store=None, filekey=False):
    """建库 + 注册 + 登录 + 写一个 secret，返回 (v, ident, tok)。"""
    v = (_filekey_vault(tmp_path, monkeypatch) if filekey
         else _keyring_vault(tmp_path, monkeypatch, store))
    reg = v.register('rec-u', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    assert auth['status'] == 'ok', auth
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')
    return v, ident, tok


def _open_again(tmp_path, monkeypatch, store=None, filekey=False):
    """模拟「进程重启 / 下次打开库」：新实例 + status() 触发 _ensure_ready。"""
    v2 = (_filekey_vault(tmp_path, monkeypatch) if filekey
          else _keyring_vault(tmp_path, monkeypatch, store))
    st = v2.status()
    assert st['status'] == 'ok', st
    return v2, st


def _reopen_read(v, tok, key='K'):
    """用仍有效的会话读 secret —— 验证恢复扫描未破坏库、数据仍可读。
    注：跨实例复用旧 token 无效（会话是实例内的），重新 auth 又需要新动态码，
    所以这里用**同一实例**的会话验证"库数据完整"即可（恢复发生在 v2 上）。"""
    return v.get_secret(tok, key)['value']


def _mark_row_pending(v, identity_id, kek_gen):
    """把某代已清理日志行手工改回 cleaned=0（模拟 C5 崩溃：删了但没来得及标）。"""
    with v._db() as conn:
        conn.execute("UPDATE kek_retired SET cleaned=0 "
                     "WHERE identity_id=? AND kek_gen=?", (identity_id, kek_gen))


# ---------------------------------------------------------------------------
# 1) keyring：C5 残留 —— 旧代条目已不在但未标 cleaned=1
# ---------------------------------------------------------------------------
def test_keyring_c5_pending_is_cleaned_on_open(tmp_path, monkeypatch):
    """rotate 成功后把日志行改回 cleaned=0（旧代条目确已不在）→ 下次打开库补标。"""
    store = fk.FakeKeyring()
    v, ident, tok = _prime(tmp_path, monkeypatch, store=store)

    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert not store.has(ident), 'rotate 正常时应已删旧代'
    assert v.status()['kek_retired_count'] == 0

    # 模拟 C5 崩溃：旧代删了但 cleaned 没来得及写 1（日志行被改回 0）
    _mark_row_pending(v, ident, 0)

    v2, st = _open_again(tmp_path, monkeypatch, store=store)
    assert st['kek_retired_count'] == 0, '打开库应补齐 C5 残留'
    gc = st.get('kek_gc_recovery', {})
    assert gc.get('scanned') == 1, gc
    assert gc.get('recovered') == 1, gc
    assert gc.get('deferred') == [], gc
    # 旧代本来就该不在；新代不受影响；数据可读
    assert not store.has(ident)
    assert store.has('%s#g1' % ident)
    assert _reopen_read(v, tok) == 'V'


# ---------------------------------------------------------------------------
# 2) keyring：delete_lag —— 旧代仍在 → 打开库保持 pending；lag 消失后补齐
# ---------------------------------------------------------------------------
def test_keyring_delete_lag_stays_pending_then_recovers(tmp_path, monkeypatch):
    """delete_lag：删除"成功"但条目仍在 → 打开库**绝不**标 cleaned=1（I3）；
    后端 lag 消失后再打开 → 删除旧代并补齐。"""
    store = fk.FakeKeyring()
    v, ident, tok = _prime(tmp_path, monkeypatch, store=store)

    store.delete_lag = True                      # 删除"成功"但条目仍在
    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['gc']['delete'] == 'lagged', res['gc']
    assert res['gc']['cleaned'] == 0, res['gc']
    assert store.has(ident), 'lag 场景旧代确实还在'

    # 第一次重开（lag 仍生效）→ 保持 pending，不谎报
    v2a, st_a = _open_again(tmp_path, monkeypatch, store=store)
    assert st_a['kek_retired_count'] == 1, st_a
    gc_a = st_a.get('kek_gc_recovery', {})
    assert gc_a.get('recovered') == 0, gc_a
    assert len(gc_a.get('deferred', [])) == 1, gc_a
    assert 'delete_lag' in gc_a['deferred'][0]['reason'], gc_a
    assert store.has(ident), 'lag 未消失时旧代必须仍在'

    # lag 消失（后端恢复）→ 再次打开库 → 删除旧代 + 回读确认 + 补标
    store.delete_lag = False
    v2b, st_b = _open_again(tmp_path, monkeypatch, store=store)
    assert st_b['kek_retired_count'] == 0, st_b
    gc_b = st_b.get('kek_gc_recovery', {})
    assert gc_b.get('recovered') == 1, gc_b
    assert gc_b.get('deferred') == [], gc_b
    assert not store.has(ident), 'lag 消失后旧代应被删除'
    assert store.has('%s#g1' % ident), '新代必须仍在'
    assert _reopen_read(v, tok) == 'V'


def test_keyring_fail_delete_stays_pending_on_open(tmp_path, monkeypatch):
    """fail_delete：删除被后端拒绝 → 打开库保持 pending；拒绝解除后补齐。"""
    store = fk.FakeKeyring()
    v, ident, tok = _prime(tmp_path, monkeypatch, store=store)

    store.fail_delete = True
    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['gc']['cleaned'] == 0, res['gc']
    assert store.has(ident)

    v2a, st_a = _open_again(tmp_path, monkeypatch, store=store)
    assert st_a['kek_retired_count'] == 1, st_a
    assert 'delete_failed' in st_a['kek_gc_recovery']['deferred'][0]['reason'], st_a

    store.fail_delete = False
    v2b, st_b = _open_again(tmp_path, monkeypatch, store=store)
    assert st_b['kek_retired_count'] == 0, st_b
    assert not store.has(ident)


# ---------------------------------------------------------------------------
# 3) file-key：C5 残留 —— 旧代文件被外部恢复且未标 cleaned=1
# ---------------------------------------------------------------------------
def test_filekey_c5_pending_file_removed_on_open(tmp_path, monkeypatch):
    """rotate 后旧代文件被"外部恢复"（模拟同步/AV 回滚）且日志行 cleaned=0 →
    打开库应删除旧文件并补标，orphans 不再报告它。"""
    v, ident, tok = _prime(tmp_path, monkeypatch, filekey=True)

    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    old_name = vault2.FILE_KEY_NAME                    # 第 0 代文件名
    old_path = os.path.join(v.vault_dir, old_name)
    assert not os.path.exists(old_path), 'rotate 正常时应已删旧代文件'
    assert v.status()['kek_retired_count'] == 0

    # 模拟 C5 崩溃 + 文件被外部恢复：重建旧代文件，日志行改回 cleaned=0
    with open(old_path, 'wb') as fh:
        fh.write(b'RESTORED-OLD-KEK')
    _mark_row_pending(v, ident, 0)

    v2, st = _open_again(tmp_path, monkeypatch, filekey=True)
    assert st['kek_retired_count'] == 0, '打开库应补齐 file-key C5 残留'
    gc = st.get('kek_gc_recovery', {})
    assert gc.get('scanned') == 1, gc
    assert gc.get('recovered') == 1, gc
    assert not os.path.exists(old_path), '恢复扫描应删除旧代文件'
    # orphans 只报"既不被引用也不在日志里"的文件 —— 该文件已在日志里被清理
    assert old_name not in st.get('kek_file_orphans', []), st
    assert _reopen_read(v, tok) == 'V'


# ---------------------------------------------------------------------------
# 4) file-key：共享旧代 → 打开库不删（shared 保护）保持 pending
# ---------------------------------------------------------------------------
def test_filekey_shared_pending_not_deleted_on_open(tmp_path, monkeypatch):
    """两个身份共享第 0 代文件：A 轮换后 pending（shared）；打开库时因 B 仍引用
    → 不删文件、保持 pending，绝不误删 B 的钥匙。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    reg_a = v.register('fk-a', '123456', security_level='L2')
    ident_a = reg_a['identity_id']
    auth_a = v.auth(ident_a, reg_a['machine_id'], '123456')
    tok_a = auth_a['session_token']
    v.set_secret(tok_a, 'K', 'VA')
    # 第二个身份：file-key 第 0 代是"随库"共享的单一 .vault2.key
    reg_b = v.register('fk-b', '654321', security_level='L2')
    ident_b = reg_b['identity_id']
    auth_b = v.auth(ident_b, reg_b['machine_id'], '654321')
    tok_b = auth_b['session_token']
    v.set_secret(tok_b, 'K', 'VB')

    old_path = os.path.join(v.vault_dir, vault2.FILE_KEY_NAME)
    assert os.path.exists(old_path)

    res = v.rotate_kek(tok_a)
    assert res['status'] == 'ok', res
    assert res['gc']['delete'] == 'shared', res['gc']
    assert res['gc']['cleaned'] == 0, res['gc']
    assert os.path.exists(old_path), '共享旧代不能被 A 的轮换删掉'

    # 下次打开库：shared 保护依然生效
    v2, st = _open_again(tmp_path, monkeypatch, filekey=True)
    assert st['kek_retired_count'] == 1, st
    gc = st.get('kek_gc_recovery', {})
    assert gc.get('recovered') == 0, gc
    assert len(gc.get('deferred', [])) == 1, gc
    assert 'shared' in gc['deferred'][0]['reason'], gc
    assert os.path.exists(old_path), 'shared 场景绝不能删共享文件'
    # 两个身份的数据都仍可读
    assert _reopen_read(v, tok_a) == 'VA'
    assert _reopen_read(v, tok_b) == 'VB'


# ---------------------------------------------------------------------------
# 5) 干净库：无 pending → 打开库零副作用
# ---------------------------------------------------------------------------
def test_clean_vault_open_has_no_side_effect(tmp_path, monkeypatch):
    """无 cleaned=0 残留时：恢复扫描 scanned=0、不删任何条目/文件。"""
    store = fk.FakeKeyring()
    v, ident, tok = _prime(tmp_path, monkeypatch, store=store)
    before = sorted(store.snapshot().keys())
    vdir = v.vault_dir
    files_before = sorted(os.listdir(vdir))

    v2, st = _open_again(tmp_path, monkeypatch, store=store)
    gc = st.get('kek_gc_recovery', {})
    assert gc.get('scanned') == 0, gc
    assert gc.get('recovered') == 0, gc
    assert st['kek_retired_count'] == 0, st
    assert sorted(store.snapshot().keys()) == before, 'keyring 条目数必须不变'
    assert sorted(os.listdir(vdir)) == files_before, '目录文件数必须不变'
    assert _reopen_read(v, tok) == 'V'


def test_open_recovery_never_raises(tmp_path, monkeypatch):
    """恢复扫描绝不抛异常：即使是脏库（pending 行指向不存在的身份）打开也稳定。"""
    store = fk.FakeKeyring()
    v, ident, tok = _prime(tmp_path, monkeypatch, store=store)
    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    # 人为制造一条"指向不存在身份"的 pending 行（脏数据），打开库不应崩
    with v._db() as conn:
        conn.execute("INSERT OR REPLACE INTO kek_retired "
                     "(identity_id, kek_gen, locator, retired_at, cleaned) "
                     "VALUES (?, ?, ?, ?, 0)",
                     ('ghost-identity', 3, '%s#g3' % 'ghost-identity', 1))
    v2, st = _open_again(tmp_path, monkeypatch, store=store)
    assert st['status'] == 'ok', st
    gc = st.get('kek_gc_recovery', {})
    assert gc.get('scanned') == 1, gc
    assert gc.get('skipped') == 0, gc
    assert gc.get('deferred') == [], gc
    # 脏行指向的条目本来就不存在 → already gone 路径：补标 cleaned=1 不误删任何东西
    assert gc.get('recovered') == 1, gc
    assert st['kek_retired_count'] == 0, st
