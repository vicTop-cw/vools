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
@pytest.mark.xfail(strict=True, reason=(
    "待实现（第 2 步）：keyring 模式需要双代并存 + 轮换日志 + GC。"
    "实现正确后本用例 XPASS —— strict 会让它变红，提示把本标记删掉。"))
def test_vault2_rotate_kek_keyring_mode(tmp_path, monkeypatch):
    """退步了会怎样：keyring 模式实现了但只过 happy path —— 崩溃矩阵（上面 1/2/3）
    才是真正验收；本用例只锁"入口 + 代数 + seed 仍可解"。

    当前状态：`rotate_kek` 对非 passphrase 模式返回 `kek_rotation_unsupported`
    → 断言失败 → xfail（预期）。
    """
    store = fk.FakeKeyring()
    monkeypatch.setattr(vault2, 'probe_keyring', lambda: (fk.FakeKeyringModule(store), 'ok'))
    monkeypatch.setenv(vault2.PROTECTION_ENV, vault2.PROTECTION_KEYRING)
    monkeypatch.delenv(vault2.PASSPHRASE_ENV, raising=False)

    v = vault2.Vault2(vault_dir=str(tmp_path / 'v2'))
    reg = v.register('kek-u', '123456', security_level='L2')
    auth = v.auth(reg['identity_id'], reg['machine_id'], '123456')
    assert auth['status'] == 'ok', auth
    v.set_secret(auth['session_token'], 'K', 'V')

    res = v.rotate_kek(auth['session_token'])
    assert res['status'] == 'ok', 'keyring 轮换尚未实现：%s' % res
    assert res['kek_gen'] == 1
    assert v.status()['kek_gen'] == 1
    # 新 KEK 写入后，原会话读数据仍应正常（KEK 只换信封，不换 master）
    assert v.get_secret(auth['session_token'], 'K')['value'] == 'V'
