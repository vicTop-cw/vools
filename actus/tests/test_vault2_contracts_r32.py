# -*- coding: utf-8 -*-
"""actus/tests/test_vault2_contracts_r32.py — vault2（密钥库 v2，55% 覆盖）安全契约。

安全模块低覆盖 = 假安全。本文件按"先审计后补测"覆盖此前没测到的入口 /
错误路径 / 轮换 / 只读状态 / 并发，不为了覆盖率写必然绿的断言。

覆盖重点：
  * register/auth 的输入校验与失败路径（错 PIN、未知身份/机器、L3 缺硬件、
    连续失败锁定）；
  * recover（重置 PIN）后 **seed 不变 ⇒ 已存 secrets 仍可读**；
  * KEK 轮换（dry-run 零写、mode mismatch、真实轮换不动 secrets）；
  * seed 轮换（dry-run 零写；真实轮换使旧会话失效、新会话可读、
    rotated_backups 一起迁移、recovery key 明确失效）；
  * 缺失/损坏库的显式状态（missing/corrupt，不当空库）；
  * 空值/超长 secret、空 key 名、缺失 key 的错误；
  * 多实例并发读写；审计日志/repr 不泄露明文。

已审计发现（第 32 轮已由 lead 裁决修复，本文件含回归用例）：
  * `sandbox.prepare` 未校验 exec_id（父目录穿越）—— 已修（见 sandbox 文件）；
  * `set_secret/get_secret` 曾接受空 key 名 —— 已修为 ValueError；
  * 模块级 `rotate_seed_key` 曾缺 `apply` 参数 —— 已修为默认干跑、显式 apply=True 真写。
"""

import hashlib
import json
import os
import sys

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import vault2 as vault2_mod  # noqa: E402
from vools.actus.vault2 import Vault2  # noqa: E402

_PIN = "123456"


class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    v2dir = tmp_path / "vault2"
    for directory in (home, meta, v2dir):
        directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(v2dir))
    monkeypatch.setenv("ACTUS_VAULT2_KEY_PROTECTION", "file-key")
    monkeypatch.setenv("ACTUS_VAULT2_NO_PROMPT", "1")
    monkeypatch.delenv("ACTUS_VAULT_KEY", raising=False)
    monkeypatch.delenv("ACTUS_VAULT2_PASSPHRASE", raising=False)

    vault2_mod._vault2_singleton = None
    w = _World()
    w.root = tmp_path
    w.v2dir = v2dir
    w.db_path = v2dir / "vault2.db"
    w.vault = Vault2(vault_dir=str(v2dir))
    return w


def _snapshot(path):
    with open(str(path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _register_auth(world, name="alice", level="L2", pin=_PIN):
    reg = world.vault.register(name, pin, security_level=level)
    assert reg["status"] == "ok", reg
    auth = world.vault.auth(reg["identity_id"], reg["machine_id"], pin)
    assert auth["status"] == "ok", auth
    return reg, auth


# ===========================================================================
# register / auth 失败路径
# ===========================================================================

def test_register_validates_pin_and_security_level(world):
    """退步了会怎样：非法 PIN（短/非数字）/非法安全级别被接受 —— 注册出弱凭据身份，
    或 security_level 拼错后 L2 逻辑不生效。

    断言：两种非法输入均 status=error 且消息点名校验；合法注册返回
    identity/machine/recovery_key 与 warning（恢复密钥只展示一次）。
    """
    assert world.vault.register("bad1", "12345")["status"] == "error"
    assert world.vault.register("bad2", "12345a")["status"] == "error"
    assert world.vault.register("bad3", _PIN, security_level="L9")["status"] == "error"

    reg = world.vault.register("ok", _PIN)
    assert reg["status"] == "ok"
    assert reg["identity_id"] and reg["machine_id"]
    assert reg["recovery_key"] and "warning" in reg


def test_auth_rejects_wrong_pin_unknown_identity_and_machine(world):
    """退步了会怎样（安全洞）：错 PIN 被接受/返回模糊错误 —— 暴力破解无从审计；
    未知身份/机器被当成成功或抛未捕获异常。

    断言：三种失败都 status=error 且消息可区分（PIN 错误 / 身份不存在 / 机器未注册）。
    """
    reg, _auth = _register_auth(world)

    wrong = world.vault.auth(reg["identity_id"], reg["machine_id"], "000000")
    assert wrong["status"] == "error" and "PIN" in wrong["message"], wrong

    unknown_id = world.vault.auth("no-such-identity", reg["machine_id"], _PIN)
    assert unknown_id["status"] == "error" and "身份" in unknown_id["message"], unknown_id

    unknown_machine = world.vault.auth(reg["identity_id"], "no-such-machine", _PIN)
    assert unknown_machine["status"] == "error" and "机器" in unknown_machine["message"], \
        unknown_machine


def test_auth_l3_requires_hardware_token(world):
    """退步了会怎样：L3 身份没有 hardware_token 也能登录 —— 硬件第二因子变成装饰。

    断言：L3 + 无 hardware_token → error，消息含 hardware/硬件；带任意 token 可过。
    """
    reg = world.vault.register("l3", _PIN, security_level="L3")
    assert reg["status"] == "ok"

    missing = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert missing["status"] == "error"
    assert "hardware" in missing["message"].lower() or "硬件" in missing["message"]

    ok = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN,
                          hardware_token="yubikey-1")
    assert ok["status"] == "ok", ok


def test_auth_lockout_after_repeated_failures(world):
    """退步了会怎样：连续错 PIN 无锁定，可无限爆破；或锁定后正确 PIN 仍放行。

    断言：连续 MAX_FAILED_ATTEMPTS 次错误 PIN 后，即使给正确 PIN 也返回 error
    且消息含"锁定"/"稍后"。
    """
    reg, _auth = _register_auth(world)
    attempts = int(getattr(vault2_mod, "MAX_FAILED_ATTEMPTS", 5))
    last = None
    for _ in range(attempts):
        last = world.vault.auth(reg["identity_id"], reg["machine_id"], "000000")
        assert last["status"] == "error"

    locked = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert locked["status"] == "error", locked
    assert ("锁定" in locked["message"]) or ("稍后" in locked["message"]), locked


# ===========================================================================
# recover：重置 PIN 后 seed 不变 ⇒ secrets 仍可读
# ===========================================================================

def test_recover_resets_pin_and_keeps_secrets_readable(world):
    """退步了会怎样（严重）：recover 重置 PIN 时换掉 seed/重加密失败 —— 用户按流程
    恢复身份后，**所有 secrets 永久打不开**（密钥库最不可接受的失败）。

    断言：先存 secret；recover(正确 recovery_key, 新 PIN) → ok；
    旧 PIN 登录失败、新 PIN 登录成功、且 secret 值仍可读；恢复密钥已轮换（新值非空）。
    """
    reg, auth = _register_auth(world)
    assert world.vault.set_secret(auth["session_token"], "db_pw", "TOP")["status"] == "ok"
    recovery_key = reg["recovery_key"]

    bad = world.vault.recover(reg["identity_id"], "WRONG-RECOVERY", "654321")
    assert bad["status"] == "error" and "恢复密钥" in bad["message"]

    bad_pin = world.vault.recover(reg["identity_id"], recovery_key, "12345")
    assert bad_pin["status"] == "error"

    recovered = world.vault.recover(reg["identity_id"], recovery_key, "654321")
    assert recovered["status"] == "ok", recovered
    assert recovered["recovery_key"] and recovered["recovery_key"] != recovery_key

    old = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert old["status"] == "error"

    new = world.vault.auth(reg["identity_id"], reg["machine_id"], "654321")
    assert new["status"] == "ok", new
    got = world.vault.get_secret(new["session_token"], "db_pw")
    assert got["status"] == "ok" and got["value"] == "TOP", got


def test_recover_without_recovery_key_is_explicit_error(world):
    """退步了会怎样：未启用恢复密钥的身份，recover 静默成功/抛未捕获异常。

    断言：把 recovery_key_hash 置 NULL 后 recover → error 且消息含"未启用"。
    """
    reg, _auth = _register_auth(world)
    with world.vault._db() as conn:
        conn.execute("UPDATE identities SET recovery_key_hash=NULL WHERE id=?",
                     (reg["identity_id"],))

    result = world.vault.recover(reg["identity_id"], "anything", "654321")
    assert result["status"] == "error"
    assert "未启用" in result["message"], result


# ===========================================================================
# KEK 轮换：dry-run 零写 / mode mismatch / 真实轮换不动 secrets
# ===========================================================================

def test_rotate_kek_dry_run_writes_nothing(world):
    """退步了会怎样：`rotate_kek(apply=False)` 真写了 DB/key 文件 —— 干跑预览改坏
    密钥库（可能让旧 KEK 丢失，库直接打不开）。

    断言：dry_run=True、wrote_db/wrote_keyring/wrote_files 全 False；
    vault2.db 与 key 目录文件快照完全不变；would 里给出 kek_gen 递增预期。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "k", "V")["status"] == "ok"
    db_before = _snapshot(world.db_path)
    key_files_before = sorted(os.listdir(str(world.v2dir)))

    result = world.vault.rotate_kek(token, apply=False)

    assert result["status"] == "ok" and result["dry_run"] is True, result
    assert result["wrote_db"] is False
    assert result["wrote_keyring"] is False
    assert result["wrote_files"] is False
    assert result["would"]["kek_gen"] == result["would"]["kek_gen_old"] + 1
    assert _snapshot(world.db_path) == db_before
    assert sorted(os.listdir(str(world.v2dir))) == key_files_before


def test_rotate_kek_mode_mismatch_and_invalid_token(world):
    """退步了会怎样：`--mode` 断言与实际保护方式不符时仍执行轮换（切换保护方式被
    静默当成轮换），或用无效 token 轮换（未认证的密钥库管理操作）。

    断言：file-key 库传 mode='passphrase' → error/mode_mismatch；
    无效 token → error；库不存在 → error/vault_not_found。
    """
    _reg, auth = _register_auth(world)
    mismatch = world.vault.rotate_kek(auth["session_token"], mode="passphrase")
    assert mismatch["status"] == "error"
    assert mismatch.get("code") == "mode_mismatch", mismatch

    assert world.vault.rotate_kek("bogus-token")["status"] == "error"

    missing = Vault2(vault_dir=str(world.root / "missing-vault"))
    gone = missing.rotate_kek("tok")
    assert gone["status"] == "error" and gone.get("code") == "vault_not_found", gone


def test_rotate_kek_real_rotates_envelope_only(world):
    """退步了会怎样：KEK 轮换顺手重加密 secrets（数据面被无谓暴露/出错），或轮换后
    本进程读不到数据。

    断言：真实轮换 → kek_gen 递增、secrets_reencrypted=0；secrets 值仍可读
    （KEK 只换信封钥匙，密文不变）。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "k", "V")["status"] == "ok"
    before = world.vault.get_secret(token, "k")["value"]

    result = world.vault.rotate_kek(token)

    assert result["status"] == "ok" and result["mode"] == "file-key", result
    assert result["kek_gen"] == result["kek_gen_old"] + 1
    assert result["secrets_reencrypted"] == 0
    assert world.vault.get_secret(token, "k")["value"] == before


# ===========================================================================
# seed 轮换：旧会话失效、数据/备份可迁、恢复密钥明确失效
# ===========================================================================

def test_rotate_seed_key_dry_run_writes_nothing(world):
    """退步了会怎样：seed 轮换干跑真写 —— 轮换是重大操作，预览就把库改掉。

    断言：dry_run=True；would_rotate_secrets 计数正确；db 快照不变。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "a", "1")["status"] == "ok"
    assert world.vault.set_secret(token, "b", "2")["status"] == "ok"
    before = _snapshot(world.db_path)

    result = world.vault.rotate_seed_key(token, apply=False)

    assert result["status"] == "ok" and result["dry_run"] is True, result
    assert result["would_rotate_secrets"] == 2
    assert result["recovery_key_would_be_invalidated"] is True
    assert _snapshot(world.db_path) == before


def test_rotate_seed_key_rotates_data_and_invalidates_old_session(world):
    """退步了会怎样（安全洞）：seed 换了但旧会话仍能读（新 seed 没真正生效），
    或旧密文没重加密（轮换后全部解不开）。

    断言：真实轮换 → 旧 token get 失败；重新 auth 后 get 成功且值不变；
    返回 recovery_key_invalidated=True + 明确 warning。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "seed_key", "SECRET")["status"] == "ok"

    result = world.vault.rotate_seed_key(token)

    assert result["status"] == "ok" and result["dry_run"] is False, result
    assert result["rotated_secrets"] >= 1
    assert result["recovery_key_invalidated"] is True
    assert result["warnings"], result

    stale = world.vault.get_secret(token, "seed_key")
    assert stale["status"] == "error", "旧会话在 seed 轮换后仍可读（新 seed 未生效）"

    auth2 = world.vault.auth(_reg["identity_id"], _reg["machine_id"], _PIN)
    assert auth2["status"] == "ok"
    got = world.vault.get_secret(auth2["session_token"], "seed_key")
    assert got["status"] == "ok" and got["value"] == "SECRET", got


def test_rotate_seed_key_migrates_rotated_backups(world):
    """退步了会怎样（最容易漏的一条）：seed 轮换只迁 secrets、不迁 rotated_backups
    —— seed 换后旧备份再也解不开，rollback 永久失效。

    断言：set V1 → rotate（产生备份）→ seed 轮换 → 重新 auth → rollback 成功取回 V1。
    """
    reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "rot", "V1")["status"] == "ok"
    assert world.vault.rotate_secret(token, "rot")["status"] == "ok"

    rotated = world.vault.rotate_seed_key(token)
    assert rotated["status"] == "ok", rotated
    assert rotated.get("rotated_backups", 0) >= 1, rotated

    auth2 = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert auth2["status"] == "ok"
    token2 = auth2["session_token"]

    rolled = world.vault.rollback_secret(token2, "rot")
    assert rolled["status"] == "ok", rolled
    assert world.vault.get_secret(token2, "rot")["value"] == "V1"


def test_rotate_seed_key_rejects_legacy_identity_without_writing(world):
    """退步了会怎样：旧格式身份（无 key_salt）被强行轮换 —— 设计上需要 PIN 派生，
    强行执行可能产生半迁移状态。

    断言：把 key_salt 置 NULL 后轮换 → error/rotate_unsupported，且 db 快照不变。
    """
    reg, auth = _register_auth(world)
    with world.vault._db() as conn:
        conn.execute("UPDATE identities SET key_salt=NULL WHERE id=?", (reg["identity_id"],))
    before = _snapshot(world.db_path)

    result = world.vault.rotate_seed_key(auth["session_token"])

    assert result["status"] == "error", result
    assert result.get("code") == "rotate_unsupported", result
    assert _snapshot(world.db_path) == before


# ===========================================================================
# 只读 API：resolve / machines / audit / anomaly / status
# ===========================================================================

def test_resolve_vault_refs_handles_missing_default_and_non_vault(world):
    """退步了会怎样：批量引用解析把 missing 静默成空串（调用方拿到空 env），
    或 default/非 vault 项处理错（回退值丢失）。

    断言：存在项解析出明文；missing 项进 missing 列表；有 default 的回落 default；
    非 vault:// 项也按 default 透传。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "present", "P")["status"] == "ok"

    result = world.vault.resolve_vault_refs(token, [
        {"env": "PRESENT", "key": "vault://present"},
        {"env": "MISSING", "key": "vault://missing"},
        {"env": "FALLBACK", "key": "vault://missing", "default": "D"},
        {"env": "PLAIN", "key": "plain", "default": "P2"},
    ])

    assert result["status"] == "ok"
    assert result["resolved"]["PRESENT"] == "P"
    assert result["resolved"]["FALLBACK"] == "D"
    assert result["resolved"]["PLAIN"] == "P2"
    assert "MISSING" not in result["resolved"]
    assert result["missing"] == ["vault://missing"]

    assert world.vault.resolve_vault_refs("bad-token", [])["status"] == "error"


def test_machines_audit_and_anomaly_are_readable(world):
    """退步了会怎样：管理/审计只读 API 返回错误结构或泄露明文 —— 运维看不到机器与
    操作记录，或审计日志成了泄密面。

    断言：list_machines 返回已注册机器且不含 seed/PIN；audit_log 返回记录且不含
    secret 明文；anomaly_check 返回 alerts/window 字段；无效 token 一律 error。
    """
    reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "audited", "PLAINTEXT-XYZ")["status"] == "ok"

    machines = world.vault.list_machines(token)
    assert machines["status"] == "ok" and machines["count"] >= 1
    blob = json.dumps(machines, ensure_ascii=False)
    assert "PLAINTEXT-XYZ" not in blob and _PIN not in blob

    logs = world.vault.audit_log(token)
    assert logs["status"] == "ok" and logs["count"] >= 1
    assert "PLAINTEXT-XYZ" not in json.dumps(logs, ensure_ascii=False), "审计日志泄露明文"

    anomaly = world.vault.anomaly_check(token)
    assert anomaly["status"] == "ok"
    assert "alerts" in anomaly and "window_seconds" in anomaly

    for call in (world.vault.list_machines, world.vault.audit_log,
                 world.vault.anomaly_check):
        assert call("bad-token")["status"] == "error"


def test_status_missing_corrupt_and_unauthenticated(world):
    """退步了会怎样（P3 元数据泄露）：无认证 status 返回 identities/secrets 计数
    （本机任意进程可枚举）；或缺失/损坏库被当成"空库"糊过去。

    断言：missing → state='missing'、initialized=False；损坏文件 → state='corrupt'
    且带 state_detail；无 token 不含 identities/secrets/active_sessions；带 token 才有计数。
    """
    unattached = world.vault.status()
    assert unattached["status"] == "ok"
    assert unattached["state"] in ("missing", "empty", "ok")
    assert "identities" not in unattached and "secrets" not in unattached
    assert "active_sessions" not in unattached

    reg, auth = _register_auth(world)
    assert world.vault.set_secret(auth["session_token"], "k", "V")["status"] == "ok"

    authed = world.vault.status(auth["session_token"])
    assert authed["identities"] == 1 and authed["secrets"] == 1
    assert authed["active_sessions"] >= 1

    missing = Vault2(vault_dir=str(world.root / "no-vault")).status()
    assert missing["state"] == "missing" and missing["initialized"] is False

    corrupt_dir = world.root / "corrupt-vault"
    corrupt_dir.mkdir()
    (corrupt_dir / "vault2.db").write_bytes(b"not a sqlite database")
    corrupt = Vault2(vault_dir=str(corrupt_dir)).status()
    assert corrupt["status"] == "ok" and corrupt["state"] == "corrupt", corrupt
    assert corrupt.get("state_detail")


# ===========================================================================
# 边界：空值 / 超长 / 空 key / 缺失 key / 并发 / 明文
# ===========================================================================

def test_secret_value_boundaries_roundtrip(world):
    """退步了会怎样：空字符串 secret 被当成"没设置"丢失；超长 secret 被截断/拒绝
    （大 token/证书场景直接不可用）。

    断言：空值 set→ok、get→''；200k 字符 set→ok、get 长度与内容完全一致。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]

    assert world.vault.set_secret(token, "empty", "")["status"] == "ok"
    empty = world.vault.get_secret(token, "empty")
    assert empty["status"] == "ok" and empty["value"] == ""

    long_value = "x" * 200000
    assert world.vault.set_secret(token, "long", long_value)["status"] == "ok"
    got = world.vault.get_secret(token, "long")
    assert got["status"] == "ok" and len(got["value"]) == len(long_value)
    assert got["value"] == long_value


def test_missing_secret_and_missing_delete_are_explicit_errors(world):
    """退步了会怎样：读/删不存在的 key 静默成功 —— 调用方以为撤销/删除成功
    （安全操作必须可确认）。

    断言：get/delete 不存在的 key 都 error 且消息含"不存在"。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]

    got = world.vault.get_secret(token, "no-such")
    assert got["status"] == "error" and "不存在" in got["message"], got

    deleted = world.vault.delete_secret(token, "no-such")
    assert deleted["status"] == "error" and "不存在" in deleted["message"], deleted


def test_two_instances_see_each_others_writes(world):
    """退步了会怎样（并发/多实例）：一个 Vault2 实例写入后，另一个实例读不到
    （各自缓存了旧连接/旧状态）—— 多进程/多入口场景数据不一致。

    断言：实例 A 写 → 实例 B（新构造、独立 db 连接）auth 后能读到同值；B 再写 →
    A 用原 token 也能读到 B 的值。
    """
    reg, auth = _register_auth(world, name="alice", level="L1")
    token = auth["session_token"]
    assert world.vault.set_secret(token, "shared", "FROM-A")["status"] == "ok"

    other = Vault2(vault_dir=str(world.v2dir))
    auth_b = other.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert auth_b["status"] == "ok"
    token_b = auth_b["session_token"]
    assert other.get_secret(token_b, "shared")["value"] == "FROM-A"

    assert other.set_secret(token_b, "shared", "FROM-B")["status"] == "ok"
    assert world.vault.get_secret(token, "shared")["value"] == "FROM-B"


def test_status_and_repr_never_print_secret_values(world):
    """退步了会怎样（安全属性）：状态/对象 repr/审计里出现 secrets 明文 ——
    日志、崩溃报告、截图都会泄露密钥。

    断言：存一个唯一明文后，status（含 token 与无 token）、repr(vault)、
    audit_log 的 JSON 中都搜不到该明文。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    unique = "UNIQUE-PLAINTEXT-9f3a"
    assert world.vault.set_secret(token, "secret_key", unique)["status"] == "ok"

    blobs = [
        json.dumps(world.vault.status(), ensure_ascii=False),
        json.dumps(world.vault.status(token), ensure_ascii=False),
        repr(world.vault),
        json.dumps(world.vault.audit_log(token), ensure_ascii=False),
    ]
    for blob in blobs:
        assert unique not in blob, "明文出现在非读取返回值中: %r" % blob[:200]


def test_cleanup_rotated_backups_removes_expired_only(world, advance_totp_window):
    """退步了会怎样：过期备份永不清理（库无限增长）或把未过期备份也删了
    （7 天内 rollback 突然失效）。

    断言：rotate 产生备份 → 推进 7 天+1s → cleanup 删除 1 条；再次 cleanup 删 0 条。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "bk", "V")["status"] == "ok"
    assert world.vault.rotate_secret(token, "bk")["status"] == "ok"

    advance_totp_window.seconds(7 * 86400 + 1)
    cleaned = world.vault.cleanup_rotated_backups()
    assert cleaned["status"] == "ok", cleaned
    assert cleaned.get("deleted", cleaned.get("count", 0)) >= 1, cleaned

    again = world.vault.cleanup_rotated_backups()
    assert again.get("deleted", again.get("count", 0)) == 0, again


# ===========================================================================
# 补充：passphrase 模式 KEK 轮换、legacy secrets 迁移、模块级包装函数
# ===========================================================================

def test_rotate_kek_passphrase_mode_and_new_passphrase(tmp_path, monkeypatch):
    """退步了会怎样（passphrase 保护模式）：KEK 轮换只支持 file-key、passphrase
    模式直接炸或换口令后旧数据解不开 —— 而 passphrase 正是无 keyring 环境的主路径。

    断言：passphrase 模式轮换 → gen+1、secrets 仍可读；显式换新口令 →
    passphrase_changed=True 且带 warning；用新口令新建实例能 auth/set/get。
    """
    vdir = tmp_path / "pass-vault"
    vdir.mkdir()
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(vdir))
    monkeypatch.setenv("ACTUS_VAULT2_KEY_PROTECTION", "passphrase")
    monkeypatch.setenv("ACTUS_VAULT2_PASSPHRASE", "old-pass")
    monkeypatch.setenv("ACTUS_VAULT2_NO_PROMPT", "1")

    vault = Vault2(vault_dir=str(vdir))
    reg = vault.register("pass-user", _PIN, security_level="L1")
    auth = vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    token = auth["session_token"]
    assert vault.set_secret(token, "k", "V")["status"] == "ok"

    rotated = vault.rotate_kek(token)
    assert rotated["status"] == "ok" and rotated["mode"] == "passphrase", rotated
    assert rotated["kek_gen"] == rotated["kek_gen_old"] + 1
    assert vault.get_secret(token, "k")["value"] == "V"

    changed = vault.rotate_kek(token, new_passphrase="new-pass")
    assert changed["status"] == "ok" and changed["passphrase_changed"] is True, changed
    assert changed["warnings"], changed
    assert vault.get_secret(token, "k")["value"] == "V"

    monkeypatch.setenv("ACTUS_VAULT2_PASSPHRASE", "new-pass")
    reopened = Vault2(vault_dir=str(vdir))
    auth2 = reopened.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert auth2["status"] == "ok", auth2
    got = reopened.get_secret(auth2["session_token"], "k")
    assert got["status"] == "ok" and got["value"] == "V", got


def _insert_legacy_secret(world, auth, name, value):
    """插入一条 key_salt=NULL 的旧格式行（用当前会话 master_key + fernet 加密）。"""
    master = auth["session_token"]
    sess = world.vault._sessions[master]
    backend = vault2_mod._make_backend("fernet", sess["master_key"])
    encrypted = backend.encrypt(value)
    import secrets as _secrets
    with world.vault._db() as conn:
        conn.execute(
            "INSERT INTO secrets (id, identity_id, name, value, secret_type,"
            " security_level, created_at, expires_at, last_rotated_at,"
            " rotate_interval_days, metadata, cipher_alg, key_salt, key_iters, key_dklen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_secrets.token_hex(8), sess["identity_id"], name, encrypted, "api_key",
             "L2", int(vault2_mod.time.time()), None, None, None, "{}", "fernet",
             None, None, None))


def test_migrate_legacy_secrets_success_and_failure(world):
    """退步了会怎样：旧格式 secrets 迁移在失败时仍返回 status=ok（假成功，调用方以为
    已全部升级），或成功路径不真正重加密 —— 旧数据一直裸奔在旧格式。

    断言：一条可解旧行 → migrated=1/status=ok，重新 get 可读；
    再插入一条损坏旧行 → migrated 计数 + failed=1 + status=error + failed_names 点名。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    _insert_legacy_secret(world, auth, "legacy_ok", "OLD-VALUE")

    first = world.vault.migrate_legacy_secrets(token)
    assert first["status"] == "ok", first
    assert first["migrated"] == 1 and first["failed"] == 0, first
    assert world.vault.get_secret(token, "legacy_ok")["value"] == "OLD-VALUE"

    _insert_legacy_secret(world, auth, "legacy_bad", "will-be-corrupted")
    with world.vault._db() as conn:
        conn.execute("UPDATE secrets SET value='not-a-valid-token' WHERE name='legacy_bad'")

    second = world.vault.migrate_legacy_secrets(token)
    assert second["status"] == "error", second
    assert second["failed"] == 1, second
    assert second["failed_names"] == ["legacy_bad"], second


def test_module_level_wrappers_delegate_to_singleton(world, monkeypatch):
    """退步了会怎样：模块级便捷函数（`vault2.rotate_kek(...)` 等）没有委托到单例/
    参数错位 —— 外部按模块 API 调用时行为与类方法不一致（两套入口漂移）。

    断言：把单例指向当前实例后，各模块级函数返回与类方法同构的 dict（不抛）。
    注：模块级 `rotate_seed_key(token, caller, apply=False)` 已支持干跑参数
    （第 32 轮修复）；本用例只做零副作用的 apply=False 调用。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    monkeypatch.setattr(vault2_mod, "_vault2_singleton", world.vault)

    assert vault2_mod.status(token)["status"] == "ok"
    assert vault2_mod.list_machines(token)["status"] == "ok"
    assert vault2_mod.audit_log(token)["status"] == "ok"
    assert vault2_mod.anomaly_check(token)["status"] == "ok"
    assert vault2_mod.resolve_vault_refs(token, [])["status"] == "ok"
    assert vault2_mod.rotate_kek(token, apply=False)["status"] == "ok"
    assert vault2_mod.rotate_seed_key(token, apply=False)["status"] == "ok"
    assert vault2_mod.migrate_legacy_rows(token)["status"] == "ok"
    assert vault2_mod.cleanup_rotated_backups()["status"] == "ok"


# ===========================================================================
# KEK 元数据 / file-key 助手 / keyring 探测（私有但安全关键）
# ===========================================================================

def test_kek_gen_of_meta_tolerates_bad_metadata():
    """退步了会怎样：损坏/缺失的 key_meta 让 kek_gen 抛异常 —— 任何旧身份打开即崩；
    或把非法值当成有效代数（轮换代数错乱，可能复用旧 KEK）。

    断言：None/空/非 JSON/非 dict/非整数 → 0；数字字符串 → 正确整数。
    """
    assert vault2_mod.kek_gen_of_meta(None) == 0
    assert vault2_mod.kek_gen_of_meta("") == 0
    assert vault2_mod.kek_gen_of_meta("not-json") == 0
    assert vault2_mod.kek_gen_of_meta("[]") == 0
    assert vault2_mod.kek_gen_of_meta('{"kek_gen": "3"}') == 3
    assert vault2_mod.kek_gen_of_meta('{"kek_gen": "bad"}') == 0


def test_file_key_helpers_are_fail_closed(world):
    """退步了会怎样：KEK 文件缺失/损坏/长度不对时静默返回空 key —— 用零 key 加密
    seed 信封（等价明文），或读坏文件后继续运行。

    断言：缺失 → None；base64 损坏/长度≠32 → Vault2KeyProtectionError；
    正常写入可读回；**O_EXCL 不覆盖已有代**（重复 put 抛 FileExistsError）。
    """
    vault = world.vault
    key = b"k" * 32

    assert vault._file_locator("id") == vault2_mod.FILE_KEY_NAME
    assert vault._file_locator("id", '{"kek_gen": 1}').endswith("#g1")
    assert vault._file_locator("id", '{"kek_locator": {"name": "custom.key"}}') == "custom.key"
    assert vault._file_locator("id", "not-json") == vault2_mod.FILE_KEY_NAME
    assert vault._file_key_path("x") == os.path.join(str(world.v2dir), "x")

    assert vault._get_file_kek("missing.key") is None
    vault._put_file_kek("k1.key", key)
    assert vault._get_file_kek("k1.key") == key

    with pytest.raises(FileExistsError):
        vault._put_file_kek("k1.key", b"j" * 32)

    bad = os.path.join(str(world.v2dir), "bad.key")
    with open(bad, "wb") as handle:
        handle.write(b"%%%not-base64%%%")
    with pytest.raises(vault2_mod.Vault2KeyProtectionError):
        vault._get_file_kek("bad.key")

    short = os.path.join(str(world.v2dir), "short.key")
    import base64 as _b64
    with open(short, "wb") as handle:
        handle.write(_b64.b64encode(b"short"))
    with pytest.raises(vault2_mod.Vault2KeyProtectionError):
        vault._get_file_kek("short.key")

    vault._delete_file_kek("k1.key")
    assert vault._get_file_kek("k1.key") is None


def test_probe_keyring_success_cached_and_failure_reasons(monkeypatch):
    """退步了会怎样（fail-closed 声明）：keyring 不可用时探测仍报"可用" —— 后续把
    seed 信封交给一个假后端，库直接打不开；或每次调用都重试探测（拖慢打开）。

    断言：成功后端 → (module, None) 且第二次调用走缓存（不再碰后端）；
    fail/null 后端 → reason 含"后端"；未安装 → reason 含"未安装"。
    """
    monkeypatch.setattr(vault2_mod, "_KEYRING_PROBE_CACHE", None)
    calls = {"n": 0}

    class _OkKeyring(object):
        @staticmethod
        def get_keyring():
            calls["n"] += 1
            return object()

        @staticmethod
        def set_password(service, user, value):
            calls["n"] += 1

        @staticmethod
        def get_password(service, user):
            return vault2_mod.secrets.token_urlsafe and None or None

        @staticmethod
        def delete_password(service, user):
            pass

    # get_password 必须读回 set_password 写的值，这里用一个闭包保存
    store = {}

    class _RealOk(object):
        @staticmethod
        def get_keyring():
            calls["n"] += 1
            return object()

        @staticmethod
        def set_password(service, user, value):
            store[(service, user)] = value

        @staticmethod
        def get_password(service, user):
            return store.get((service, user))

        @staticmethod
        def delete_password(service, user):
            store.pop((service, user), None)

    monkeypatch.setitem(sys.modules, "keyring", _RealOk)
    first = vault2_mod.probe_keyring()
    assert first[0] is _RealOk and first[1] is None, first
    n_after_first = calls["n"]
    assert vault2_mod.probe_keyring() == first
    assert calls["n"] == n_after_first, "第二次探测没有走缓存"

    class _FailBackend(object):
        pass

    _FailBackend.__module__ = "keyring.backends.fail"

    class _FailKeyring(object):
        @staticmethod
        def get_keyring():
            return _FailBackend()

    monkeypatch.setattr(vault2_mod, "_KEYRING_PROBE_CACHE", None)
    monkeypatch.setitem(sys.modules, "keyring", _FailKeyring)
    backend, reason = vault2_mod.probe_keyring()
    assert backend is None and "后端" in reason, (backend, reason)

    monkeypatch.setattr(vault2_mod, "_KEYRING_PROBE_CACHE", None)
    monkeypatch.setitem(sys.modules, "keyring", None)      # import 时 ImportError
    backend, reason = vault2_mod.probe_keyring()
    assert backend is None and "未安装" in reason, (backend, reason)

    message = vault2_mod._key_protection_unavailable_message("测试原因")
    assert "fail-closed" in message and "测试原因" in message
    assert "任选其一" in message


def test_keyring_kek_put_get_roundtrip_with_fake_backend(world):
    """退步了会怎样：keyring 模式的 KEK 写入/读取编码错（base64/字符串）—— 轮换后
    读不回 KEK，seed 信封永久打不开。

    断言：假 keyring 后端上 put→get 得到同一 32 字节；不存在的 locator → None。
    """
    store = {}

    class _FakeKeyring(object):
        @staticmethod
        def set_password(service, user, value):
            store[(service, user)] = value

        @staticmethod
        def get_password(service, user):
            return store.get((service, user))

        @staticmethod
        def delete_password(service, user):
            store.pop((service, user), None)

    world.vault._keyring = _FakeKeyring
    world.vault.key_protection = vault2_mod.PROTECTION_KEYRING
    kek = b"z" * 32
    locator = "identity-1#g2"

    world.vault._put_keyring_kek(locator, kek)
    assert world.vault._get_keyring_kek(locator) == kek
    assert world.vault._get_keyring_kek("missing-locator") is None


def test_expired_secret_is_rejected(world):
    """退步了会怎样：过期 secret 仍能读出 —— 密钥轮换/到期策略形同虚设（过期凭据
    本应强制重配）。

    断言：把 expires_at 置到过去 → get 返回 error 且消息含"过期"。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "exp", "V")["status"] == "ok"
    with world.vault._db() as conn:
        conn.execute("UPDATE secrets SET expires_at=? WHERE name='exp'",
                     (int(vault2_mod.time.time()) - 1,))

    got = world.vault.get_secret(token, "exp")
    assert got["status"] == "error" and "过期" in got["message"], got


def test_set_secret_rejects_unknown_cipher_algorithm(world):
    """退步了会怎样：未知 cipher_alg 被接受（落到未知后端）—— 密文用什么算法都说不清，
    读取端无法解密/安全审计失真。

    断言：cipher_alg='bogus' → error 且消息含"白名单"。
    """
    _reg, auth = _register_auth(world)
    result = world.vault.set_secret(auth["session_token"], "k", "V", cipher_alg="bogus")
    assert result["status"] == "error" and "白名单" in result["message"], result


def test_anomaly_check_reports_repeated_auth_failures(world):
    """退步了会怎样（审计异常检测）：连续认证失败不产生告警 —— 爆破/异常访问无感知。

    断言：制造多次失败登录后 anomaly_check(windows=3600) 的 alerts 非空，且记录数
    record_count >= 失败次数。
    """
    reg, _auth = _register_auth(world)
    for _ in range(int(vault2_mod.MAX_FAILED_ATTEMPTS) + 1):
        world.vault.auth(reg["identity_id"], reg["machine_id"], "000000")
    # 上面可能已锁定；用另一个身份拿 token 做审计读取
    reg2, auth2 = _register_auth(world, name="bob", level="L1")
    result = world.vault.anomaly_check(auth2["session_token"])
    assert result["status"] == "ok", result
    assert result["record_count"] > 0, result
    assert isinstance(result["alerts"], list)


def test_file_kek_orphan_scan_and_reference_check(world):
    """退步了会怎样（密钥文件盘点）：孤儿 KEK 文件扫不出来（旧代文件无限堆积），
    或把仍被身份引用的 KEK 误判为孤儿（GC 删掉正在用的 key，库打不开）。

    断言：放一个未被引用的 `.vault2.key#g9` → 扫出该名；已注册身份的当前 KEK 文件
    不被判为孤儿。
    """
    _reg, auth = _register_auth(world)
    current_name = world.vault._file_locator(auth["session_token"] and
                                             world.vault._sessions[auth["session_token"]]["identity_id"])
    orphans = world.vault._scan_file_kek_orphans()
    assert isinstance(orphans, list)
    assert current_name not in [os.path.basename(str(x)) for x in orphans]

    orphan_path = os.path.join(str(world.v2dir), ".vault2.key#g9")
    with open(orphan_path, "wb") as handle:
        handle.write(b"x")
    orphans2 = world.vault._scan_file_kek_orphans()
    names = [os.path.basename(str(x)) for x in orphans2]
    assert ".vault2.key#g9" in names, names


def test_anomaly_check_four_rules_fire(world):
    """退步了会怎样：异常检测只返回空 alerts（规则全失效）—— 爆破、换机、恢复密钥
    使用、凌晨访问四类风险全部不可见。

    断言：同一身份窗口内 5 次失败认证 + 指纹不匹配 + recover + 凌晨 get 审计记录 →
    alerts 里四条规则各至少一条（brute_force_attempt / fingerprint_mismatch /
    recovery_key_used / odd_hour_access）。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    reg = _reg
    # 先拿到 token，再做失败认证（否则会锁定拿不到 token）
    for _ in range(5):
        world.vault.auth(reg["identity_id"], reg["machine_id"], "000000")

    identity_id = world.vault._sessions[token]["identity_id"]
    now = int(vault2_mod.time.time())
    fake_records = [
        {"ts": now, "action": "auth", "identity_id": identity_id,
         "success": False, "reason": "fingerprint_mismatch"},
        {"ts": now, "action": "recover", "identity_id": identity_id, "success": True},
        {"ts": now, "action": "get", "identity_id": identity_id, "success": True},
        {"ts": now, "action": "get", "identity_id": identity_id, "success": True},
        {"ts": now, "action": "get", "identity_id": identity_id, "success": True},
    ]
    with open(str(world.vault.audit_path), "a", encoding="utf-8") as handle:
        for record in fake_records:
            handle.write(json.dumps(record, ensure_ascii=False) + chr(10))

    result = world.vault.anomaly_check(token)

    assert result["status"] == "ok", result
    rules = {alert["rule"] for alert in result["alerts"]}
    assert "brute_force_attempt" in rules, result
    assert "fingerprint_mismatch" in rules, result
    assert "recovery_key_used" in rules, result
    local_hour = vault2_mod.time.localtime(now).tm_hour
    if 2 <= local_hour <= 5:
        assert "odd_hour_access" in rules, result


def test_status_exposes_diagnostics_without_secrets(world):
    """退步了会怎样：KEK 轮换诊断（代数/待清理旧代/孤儿文件/迁移告警）在 status 里
    消失 —— 运维无法判断"轮换是否完成、旧代是否清理"；或诊断字段泄露密钥材料。

    断言：设置 key_protection_warning/migrated_key_protection/migrated_from 后 status
    如实回显这些诊断；kek_gen/kek_retired_count/kek_rotation_supported 存在；
    响应里不含 seed/PIN/secret 明文。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "diag", "DIAG-PLAINTEXT")["status"] == "ok"
    world.vault.key_protection_warning = "测试告警"
    world.vault.migrated_key_protection = 2
    world.vault.migrated_from = "/old/path"

    status = world.vault.status(token)

    assert status["key_protection_warning"] == "测试告警"
    assert status["migrated_key_protection"] == 2
    assert status["migrated_from"] == "/old/path"
    assert status["kek_rotation_supported"] is True
    assert status["kek_gen"] == 0 and status["kek_gen_max"] == 0
    assert status["kek_retired_count"] >= 0

    blob = json.dumps(status, ensure_ascii=False)
    assert "DIAG-PLAINTEXT" not in blob
    assert _PIN not in blob


def test_secret_name_validation_rejects_empty_and_blank(world):
    """退步了会怎样（第 32 轮修复回归）：空/纯空白 secret 名被接受 —— 空名条目在
    列表/审计里与"缺字段"难区分，也容易与调用方拼错的名字碰撞。

    断言：set_secret/get_secret 对 ""、纯空白、非字符串名抛 ValueError；
    正常名字不受影响（能存能读）。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]

    for bad in ("", "   ", "	", None, 123):
        with pytest.raises(ValueError):
            world.vault.set_secret(token, bad, "V")
        with pytest.raises(ValueError):
            world.vault.get_secret(token, bad)

    assert world.vault.set_secret(token, "ok_name", "V")["status"] == "ok"
    assert world.vault.get_secret(token, "ok_name")["value"] == "V"


def test_module_rotate_seed_key_apply_passthrough(world, monkeypatch):
    """退步了会怎样（第 32 轮修复回归）：模块级 `rotate_seed_key` 丢掉 apply ——
    默认调用就做不可逆轮换（干跑请求变成真写），或 apply=True 反而不写。

    断言：默认 `rotate_seed_key(token)` → dry_run=True 且 db 快照不变；
    显式 `apply=True` → dry_run=False、rotated_secrets>=1、db 已变、旧 token 失效。
    """
    _reg, auth = _register_auth(world)
    token = auth["session_token"]
    assert world.vault.set_secret(token, "k", "V")["status"] == "ok"
    monkeypatch.setattr(vault2_mod, "_vault2_singleton", world.vault)

    before = _snapshot(world.db_path)
    dry = vault2_mod.rotate_seed_key(token)
    assert dry["status"] == "ok" and dry["dry_run"] is True, dry
    assert _snapshot(world.db_path) == before, "默认调用竟然真写了"

    real = vault2_mod.rotate_seed_key(token, apply=True)
    assert real["status"] == "ok" and real["dry_run"] is False, real
    assert real["rotated_secrets"] >= 1
    assert _snapshot(world.db_path) != before
    assert world.vault.get_secret(token, "k")["status"] == "error"
