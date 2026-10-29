# -*- coding: utf-8 -*-
"""KEK 轮换第 2 步（keyring 双代 + 日志 + GC）—— **崩溃矩阵测试骨架**。

本轮（第 21 轮）**只做骨架，不改 `vault2.py`**。骨架的作用有三：
  1. 把设计文档 §2/§4.3 的 **6 个崩溃点 × 4 条不变式**变成可执行断言（骨架即规格）；
  2. 用**故意错误的实现**（`delete_old_first`：先删旧 KEK 再写新代）证明断言**真会红**；
  3. 给将来的 `vault2.rotate_kek(mode='keyring')` 留一个 `xfail(strict=True)` 的落地位：
     实现正确 → 变 XPASS → **strict 使测试红**，提示把这行标记删掉。

## 矩阵（6 崩溃点 × 4 不变式）

| 崩溃点 | 含义 | I1 seed可解 | I2 旧KEK后删 | I3 不谎报cleaned | I4 孤儿不阻塞 |
|---|---|---|---|---|---|
| C1 | 写新 KEK 前 | ✅ | ✅ | ✅ | ✅ |
| C2 | 写新 KEK 后、DB 提交前 | ✅ | ✅ | ✅ | ✅ |
| C3 | DB 提交后、GC 前 | ✅ | ✅ | ✅ | ✅ |
| C4 | GC 中、删旧 KEK 前 | ✅ | ✅ | ✅ | ✅ |
| C5 | GC 中、删旧 KEK 后（未标 cleaned） | ✅ | ✅ | ✅ | ✅ |
| C6 | GC 后 | ✅ | ✅ | ✅ | ✅ |

**错误实现**（先删旧 KEK）在 **C1/C2** 违反 I1（DB 仍引用旧代、旧 KEK 已没了 → seed 永久
不可解）—— 这正是骨架要能抓住的东西；C3-C6 对它是通过的（窗口已越过危险区），
所以矩阵并不"全绿就代表实现正确"，而是**每个窗口各自负责**。

## 外部 store 故障模式（`fake_keyring.FakeKeyring`）

| 模式 | 模拟 | 期望 |
|---|---|---|
| `fail_write` | 凭据库拒绝写入 | 绝不提交 DB，I1 保持 |
| `stale_read_once` | 刚写完读回**旧值** | 写后自检必须中止，I1 保持 |
| `fail_delete` | 删除被拒绝 | 留 `cleaned=0` 待重试，I1 保持 |
| `delete_lag` | 删除"成功"但条目仍在 | **绝不能标 `cleaned=1`**（I3），I1 保持 |
| `restart_drop_volatile` | 重启后条目丢失（云同步回滚） | **已记录局限**：若丢的是 DB 引用的新代 → I1 无法保持 |

最后一条是**诚实的边界**：它不靠 DB 侧设计解决（只能靠备份/多副本），所以测试里
断言的是"这条确实是 I1 违反"，而不是假装它通过。
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
import kek_crash_matrix as kcm     # noqa: E402

from vools.actus import vault2     # noqa: E402

CRASH_POINTS = kcm.CRASH_POINTS
INVARIANTS = ('I1', 'I2', 'I3', 'I4')


def _assert_invariants(res, point):
    """**唯一**的不变式断言体（正确实现与灵敏度自检共用同一份，避免"两套判据"）。"""
    inv = res['invariants']
    bad = {k: v[1] for k, v in inv.items() if not v[0]}
    assert not bad, '崩溃点 %s 后不变式被违反: %s' % (point, bad)


# ---------------------------------------------------------------------------
# 1) 正确参考实现：6 个崩溃点都必须守住全部不变式
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('point', CRASH_POINTS)
def test_correct_impl_survives_every_crash_point(point):
    """退步了会怎样：正确实现（先写新代→提交→GC）在某个窗口崩溃后 seed 不可解。

    断言：崩溃 + "进程重启"（keyring 重启、DB 重连）后 I1/I2/I3/I4 全部成立。
    """
    res, _db = kcm.run_case(crash=point, variant='correct')
    _assert_invariants(res, point)


# ---------------------------------------------------------------------------
# 1b) **灵敏度自检**：同一份断言喂给错误实现 → 必须 AssertionError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('point', ('C1', 'C2'))
def test_harness_reds_on_wrong_impl(point):
    """退步了会怎样：**断言恒真** —— 9 个用例全绿，但实现错了也全绿（假保护）。

    断言：把 `_assert_invariants`（正确实现用的那一份，逐字相同）喂给
    `delete_old_first` 错误实现的结果 → **必须抛 AssertionError**。
    这是"骨架能红"的可执行证据，不依赖任何人工观察。
    """
    res, _db = kcm.run_case(crash=point, variant='delete_old_first')
    with pytest.raises(AssertionError):
        _assert_invariants(res, point)


# ---------------------------------------------------------------------------
# 2) 故意错误的实现：骨架必须抓到（证明断言不是恒真）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('point', ('C1', 'C2'))
def test_wrong_delete_old_first_is_caught(point):
    """退步了会怎样：**骨架失效**（错误实现也全绿）—— 那这套测试就是摆设。

    断言：错误实现"先删旧 KEK"在 C1/C2 崩溃后 **I1 必须被判定为违反**。
    如果这个用例红了，说明要么错误实现被改对了（好事），要么骨架抓不住错（坏事）。
    """
    res, _db = kcm.run_case(crash=point, variant='delete_old_first')
    assert res['invariants']['I1'][0] is False, (
        '骨架失效：错误实现在 %s 崩溃后仍被认为 seed 可解' % point)


@pytest.mark.parametrize('point', ('C3', 'C4', 'C5', 'C6'))
def test_wrong_impl_passes_after_danger_window(point):
    """记录一个**诚实的事实**：错误实现只在 C1/C2 露出马脚，C3-C6 已经越过危险区。

    这条用例不是"认可错误实现"，而是防止有人误以为矩阵任意一格绿就等于实现正确。
    """
    res, _db = kcm.run_case(crash=point, variant='delete_old_first')
    assert res['invariants']['I1'][0] is True, (
        '%s 处错误实现本应"看起来没问题"（危险窗口已过），现在却失败了 —— '
        '说明矩阵语义或参考实现变了，需要重新审视' % point)


# ---------------------------------------------------------------------------
# 3) 外部 store 故障模式：期望与实测一致（含"已记录局限"）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('name,faults,crash,expected_i1,why', kcm.FAULT_MATRIX)
def test_fault_matrix_matches_expectation(name, faults, crash, expected_i1, why):
    """退步了会怎样：外部 store 异常时不变式悄悄失效（例如 delete_lag 被标 cleaned）。

    断言：实测 I1 与期望一致；`expected_i1 is None` 表示**已记录局限**（只记录不假装）。
    """
    rows = {r['name']: r for r in kcm.fault_matrix(verbose=False)}
    row = rows[name]
    if expected_i1 is None:
        # 已记录局限：不要求 I1 成立，但要求"失败是可见的"
        assert row['inv']['I1'][0] is False, (
            '%s 被标为"已记录局限"（keyring 丢弃被引用条目 → seed 不可解），'
            '现在却解开了？请复核这条局限是否仍然成立' % name)
        return
    assert row['inv']['I1'][0] is expected_i1, (
        '%s 的 I1 与期望不符：%s' % (name, row['inv']['I1'][1]))


# ---------------------------------------------------------------------------
# 4) 规格完整性：6 × 4 一格不少（防"悄悄删掉一个崩溃点"）
# ---------------------------------------------------------------------------
def test_matrix_spec_is_complete():
    """退步了会怎样：有人删掉某个崩溃点/不变式，矩阵看起来仍然"全绿"。

    断言：崩溃点恰为 C1..C6、不变式恰为 I1..I4、每个点都有明确的含义说明。
    """
    assert tuple(CRASH_POINTS) == ('C1', 'C2', 'C3', 'C4', 'C5', 'C6')
    assert set(kcm.CRASH_MEANING) == set(CRASH_POINTS)
    assert all(kcm.CRASH_MEANING[p] for p in CRASH_POINTS)
    res, _db = kcm.run_case(crash=None)
    assert set(res['invariants']) == set(INVARIANTS), res['invariants'].keys()
    assert len(kcm.FAULT_MATRIX) >= 5, '故障模式至少覆盖 5 类'


# ---------------------------------------------------------------------------
# 5) 落地位：真实 API 的 keyring 轮换（**待实现**）
# ---------------------------------------------------------------------------
def test_vault2_rotate_kek_keyring_mode(tmp_path, monkeypatch):
    """真实实现的 keyring KEK 轮换（第 2 步）：入口 + 双代 + GC + 代数 + 数据可读。

    **不再 xfail**（第 22 轮落地）。骨架的价值不因落地而消失：上面 6×4 矩阵、
    灵敏度自检、`test_wrong_impl_passes_after_danger_window` 全部保留 ——
    它们是"骨架本身没坏"的证明（lead 明确要求不许删）。
    """
    store = fk.FakeKeyring()
    monkeypatch.setattr(vault2, 'probe_keyring', lambda: (fk.FakeKeyringModule(store), 'ok'))
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_KEYRING)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)

    v = vault2.Vault2(vault_dir=str(tmp_path / 'v2'))
    reg = v.register('kek-u', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    assert auth['status'] == 'ok', auth
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    old_locator = ident          # 第 0 代 locator = 旧规则的 identity_id（向后兼容）
    assert store.has(old_locator), '注册时应按旧规则写入第 0 代 KEK'

    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['mode'] == 'keyring'
    assert (res['kek_gen_old'], res['kek_gen']) == (0, 1), res
    # 新代写入且被 DB 引用
    assert store.has('%s#g1' % ident), '新代 KEK 必须写进 keyring'
    assert res['locator_new'] == '%s#g1' % ident
    # GC：旧代真的删掉 + 日志置 cleaned=1（I2/I3）
    assert not store.has(old_locator), 'GC 后旧代 KEK 必须不在'
    assert res['gc']['cleaned'] == 1, res['gc']
    assert res['kek_retired_written'] is True
    # status 诊断：清理完的旧代不该算 pending
    st = v.status()
    assert st['kek_gen'] == 1, st
    assert st['kek_retired_count'] == 0, st
    # KEK 只换信封：seed 未变 ⇒ 原会话仍可读
    assert v.get_secret(tok, 'K')['value'] == 'V'

    # 连续第二次：1 → 2，且上一代被清理
    res2 = v.rotate_kek(tok)
    assert res2['status'] == 'ok', res2
    assert res2['kek_gen'] == 2
    assert store.has('%s#g2' % ident) and not store.has('%s#g1' % ident)
    assert v.get_secret(tok, 'K')['value'] == 'V'


def test_vault2_rotate_kek_keyring_delete_lag_keeps_pending(tmp_path, monkeypatch):
    """**delete_lag**：`delete_password` 没抛异常但条目仍在 → 绝不许标 cleaned=1（I3）。

    这是 lead 附加要求 ① 的可执行断言：只判"没抛异常"的实现会在这里红。
    """
    store = fk.FakeKeyring()
    monkeypatch.setattr(vault2, 'probe_keyring', lambda: (fk.FakeKeyringModule(store), 'ok'))
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_KEYRING)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)

    v = vault2.Vault2(vault_dir=str(tmp_path / 'v2'))
    reg = v.register('lag-u', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    store.delete_lag = True                       # 删除"成功"但条目仍在
    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['gc']['delete'] == 'lagged', res['gc']
    assert res['gc']['cleaned'] == 0, 'delete_lag 下绝不能标 cleaned=1'
    assert store.has(ident), 'lag 场景旧代确实还在'
    # 日志保留 pending，等下次 GC 重试
    assert v.status()['kek_retired_count'] == 1, v.status()
    # 数据仍可读（DB 已指向新代）
    assert v.get_secret(tok, 'K')['value'] == 'V'


def test_vault2_rotate_kek_keyring_stale_read_aborts_without_commit(tmp_path, monkeypatch):
    """**stale_read_once**：写后回读拿到旧值 → 必须中止、不提交 DB（旧代与信封不变）。

    这是 lead 附加要求 ② 的可执行断言："我刚写成功了" ≠ "后端真的存了"。
    """
    store = fk.FakeKeyring()
    monkeypatch.setattr(vault2, 'probe_keyring', lambda: (fk.FakeKeyringModule(store), 'ok'))
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_KEYRING)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)

    v = vault2.Vault2(vault_dir=str(tmp_path / 'v2'))
    reg = v.register('stale-u', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    # 定点到**新代 locator**：否则这个"一次性 stale"会被前面"读旧代 KEK"那一步消耗掉
    # （那是测试替身的语义细节，不是实现问题）
    store.stale_read_once = True
    store.stale_targets = {'%s#g1' % ident}
    res = v.rotate_kek(tok)
    assert res['status'] == 'error', res
    assert res['code'] == 'kek_readback_mismatch', res
    # DB 未提交：代数仍是 0，旧代仍在，数据可读
    assert v.status()['kek_gen'] == 0, v.status()
    assert store.has(ident), '旧代 KEK 必须还在'
    assert v.get_secret(tok, 'K')['value'] == 'V'


# ---------------------------------------------------------------------------
# 6) 第 3 步：file-key 模式的真实实现
# ---------------------------------------------------------------------------
def _filekey_vault(tmp_path, monkeypatch, passphrase_free=True):
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_FILE)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)
    v = vault2.Vault2(vault_dir=str(tmp_path / 'v2'))
    return v


def test_vault2_rotate_kek_filekey_mode(tmp_path, monkeypatch):
    """file-key 轮换：O_EXCL 写新代 → 回读 → 提交 → 删旧代（回读确认）→ 代数 0→1。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    reg = v.register('fk-u', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    vdir = v.vault_dir
    old_name = vault2.FILE_KEY_NAME
    new_name = '%s#g1' % vault2.FILE_KEY_NAME
    assert os.path.isfile(os.path.join(vdir, old_name)), '注册时应创建第 0 代 KEK 文件'

    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['mode'] == 'file-key'
    assert (res['kek_gen_old'], res['kek_gen']) == (0, 1), res
    assert os.path.isfile(os.path.join(vdir, new_name)), '新代 KEK 文件必须存在'
    assert not os.path.exists(os.path.join(vdir, old_name)), 'GC 后旧代文件必须删除'
    assert res['gc']['cleaned'] == 1, res['gc']
    # POSIX 权限：0600（Windows 上只切只读位，故这里不硬断言 mode）
    if os.name == 'posix':
        assert (os.stat(os.path.join(vdir, new_name)).st_mode & 0o777) == 0o600
    # 数据仍可读（KEK 只换信封）+ 代数 + 无孤儿
    assert v.get_secret(tok, 'K')['value'] == 'V'
    st = v.status()
    assert st['kek_gen'] == 1 and st['kek_retired_count'] == 0, st
    assert st.get('kek_file_orphans') == [], st
    # 第二次轮换 1 → 2
    res2 = v.rotate_kek(tok)
    assert res2['status'] == 'ok' and res2['kek_gen'] == 2, res2
    assert os.path.isfile(os.path.join(vdir, '%s#g2' % vault2.FILE_KEY_NAME))
    assert not os.path.exists(os.path.join(vdir, '%s#g1' % vault2.FILE_KEY_NAME))


def test_vault2_rotate_kek_filekey_o_excl_refuses_existing(tmp_path, monkeypatch):
    """**O_EXCL**：目标代文件已存在 → 绝不覆盖、不提交（TOCTOU 的反面）。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    reg = v.register('fk2', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    target = os.path.join(v.vault_dir, '%s#g1' % vault2.FILE_KEY_NAME)
    with open(target, 'wb') as handle:            # 预先占位（模拟残留/并发）
        handle.write(b'occupied')

    res = v.rotate_kek(tok)
    assert res['status'] == 'error', res
    assert res['code'] == 'kek_file_exists', res
    assert v.status()['kek_gen'] == 0, '拒绝时必须仍停在旧代'
    with open(target, 'rb') as handle:
        assert handle.read() == b'occupied', 'O_EXCL 绝不许覆盖已有文件'
    assert v.get_secret(tok, 'K')['value'] == 'V'


def test_vault2_rotate_kek_filekey_unlink_lag_keeps_pending(tmp_path, monkeypatch):
    """**删后回读确认**：unlink"成功"但文件还在 → cleaned 必须保持 0（I3）。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    reg = v.register('fk3', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    monkeypatch.setattr(vault2.Vault2, '_delete_file_kek', lambda self, name: None)
    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert res['gc']['delete'] == 'lagged', res['gc']
    assert res['gc']['cleaned'] == 0, '文件仍在时绝不能标 cleaned=1'
    assert os.path.exists(os.path.join(v.vault_dir, vault2.FILE_KEY_NAME)), 'lag 场景文件确实还在'
    assert v.status()['kek_retired_count'] == 1, v.status()
    assert v.get_secret(tok, 'K')['value'] == 'V'


def test_vault2_rotate_kek_filekey_orphan_reported_not_deleted(tmp_path, monkeypatch):
    """**保守孤儿策略**：既不被引用也不在日志里的 KEK 文件 → 只报告，**不删除**。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    reg = v.register('fk4', '123456', security_level='L2')
    ident = reg['identity_id']
    auth = v.auth(ident, reg['machine_id'], '123456')
    tok = auth['session_token']
    v.set_secret(tok, 'K', 'V')

    orphan = os.path.join(v.vault_dir, '%s#g9' % vault2.FILE_KEY_NAME)
    with open(orphan, 'wb') as handle:
        handle.write(b'stray')

    res = v.rotate_kek(tok)
    assert res['status'] == 'ok', res
    assert '%s#g9' % vault2.FILE_KEY_NAME in (res.get('orphans') or []), res.get('orphans')
    assert os.path.exists(orphan), '保守策略下孤儿文件**不得被删除**'
    assert any('孤儿' in w for w in (res.get('warnings') or [])), res.get('warnings')


def test_vault2_rotate_kek_filekey_shared_gen0_not_deleted(tmp_path, monkeypatch):
    """两个身份共用第 0 代 KEK 文件 → 轮换其中一个时**不得删**该文件（另一个还要用）。"""
    v = _filekey_vault(tmp_path, monkeypatch)
    r1 = v.register('fk5a', '123456', security_level='L2')
    r2 = v.register('fk5b', '654321', security_level='L2')
    a1 = v.auth(r1['identity_id'], r1['machine_id'], '123456')
    a2 = v.auth(r2['identity_id'], r2['machine_id'], '654321')
    v.set_secret(a1['session_token'], 'K1', 'V1')
    v.set_secret(a2['session_token'], 'K2', 'V2')

    res = v.rotate_kek(a1['session_token'])
    assert res['status'] == 'ok', res
    assert res['gc']['delete'] == 'shared', res['gc']
    assert res['gc']['cleaned'] == 0
    assert os.path.exists(os.path.join(v.vault_dir, vault2.FILE_KEY_NAME)), \
        '其它身份仍引用旧代文件，不能删'
    # 两个身份都仍可读
    assert v.get_secret(a1['session_token'], 'K1')['value'] == 'V1'
    assert v.get_secret(a2['session_token'], 'K2')['value'] == 'V2'
