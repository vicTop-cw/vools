# -*- coding: utf-8 -*-
"""actus/tests/test_vault_master_migration.py — P0 修复（稳定派生 + 迁移）的正式回归。

P0 背景：L2/L3 的 `master_key` 曾把**每 60 秒变一次的 TOTP 动态码**掺进 PBKDF2，
默认级别 L2 ⇒ 今天写的密钥明天解不开（不可逆数据损失）。修复：
  * `derive_master_key_stable(seed, salt)` —— master 只由 seed + key_salt 决定；
  * `migrate_master_derivation()` —— 把旧派生时期的密文迁到新派生：
      - 读阶段全部试解密/试重加密到内存，**任何一条失败整批放弃（磁盘零写）**；
      - 写阶段单事务，抛错回滚；
      - 幂等（新派生能解开 = already，不重复写）；
      - 无 `key_salt` 的旧身份进 `skipped_legacy`（需 PIN，如实报告不静默）；
      - `auth` 天生是升级点：失败不阻断登录，但响应带 `master_migration` 错误。

时间控制：统一使用 `tests/conftest.py` 的 `advance_totp_window(n)`
（同时 patch `vault2.time` 与 `vools.security.otp.time`，不 sleep）——
14 轮全绿却漏掉 P0 的根因就是"测试时间跨度不够"，这个夹具就是为此存在的。
"""

import contextlib
import hashlib
import os
import secrets
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import vault2 as vault2_mod  # noqa: E402
from vools.actus.vault2 import DEFAULT_TIME_STEP, Vault2  # noqa: E402

_PIN = "123456"
_ROW_ITERS = vault2_mod.DEFAULT_ROW_ITERS
_ROW_DKLEN = vault2_mod.DEFAULT_ROW_DKLEN


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch, advance_totp_window):
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
    monkeypatch.delenv("ACTUS_VAULT_LAZY_MIGRATE", raising=False)

    vault2_mod._vault2_singleton = None
    w = _World()
    w.root = tmp_path
    w.vault = Vault2(vault_dir=str(v2dir))
    w.db_path = w.vault.db_path
    w.advance = advance_totp_window          # 共用夹具：推进 n 个 TOTP 窗口
    w.clock = advance_totp_window.clock
    return w


def _auth(world, reg):
    return world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)


def _register_and_auth(world, identity, level):
    reg = world.vault.register(identity, _PIN, security_level=level)
    assert reg["status"] == "ok", reg
    auth = _auth(world, reg)
    assert auth["status"] == "ok", auth
    return reg, auth


def _identity_material(vault, identity_id):
    """(seed_hex, key_salt 或 None)；用于造"旧派生时期"的密文。"""
    with vault._db() as conn:
        row = conn.execute(
            "SELECT seed_key, key_protection, key_meta, key_salt FROM identities WHERE id=?",
            (identity_id,)).fetchone()
    seed_hex = vault._decode_seed_hex(identity_id, row[0], row[1], row[2])
    key_salt = bytes.fromhex(row[3]) if row[3] else None
    return seed_hex, key_salt


def _insert_legacy_secret(vault, identity_id, name, value, created_at):
    """插入一条**旧派生时期**的密文行（master 掺了该行写入窗口的 TOTP）。"""
    seed_hex, key_salt = _identity_material(vault, identity_id)
    assert key_salt, "该身份没有 key_salt，不能模拟旧行"
    window = int(created_at) // DEFAULT_TIME_STEP
    old_master = vault2_mod.derive_master_key_windowed(seed_hex, window, key_salt)
    row_salt = secrets.token_bytes(16)
    row_key = vault2_mod._derive_row_key(old_master, row_salt, _ROW_ITERS, _ROW_DKLEN)
    encrypted = vault2_mod._make_backend("fernet", row_key).encrypt(value)
    with vault._db() as conn:
        conn.execute(
            "INSERT INTO secrets (id, identity_id, name, value, secret_type,"
            " security_level, created_at, expires_at, last_rotated_at,"
            " rotate_interval_days, metadata, cipher_alg, key_salt, key_iters, key_dklen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (secrets.token_hex(8), identity_id, name, encrypted, "api_key", "L1",
             int(created_at), None, int(created_at), None, "{}", "fernet",
             row_salt.hex(), _ROW_ITERS, _ROW_DKLEN))
    return name


def _legacy_plaintext(vault, identity_id, name):
    """按旧派生（created_at 窗口）解密一行 —— 用于断言"回滚后旧派生仍可解"。"""
    seed_hex, key_salt = _identity_material(vault, identity_id)
    with vault._db() as conn:
        row = conn.execute(
            "SELECT value, created_at, key_salt, key_iters, key_dklen FROM secrets"
            " WHERE identity_id=? AND name=?", (identity_id, name)).fetchone()
    enc, created_at, row_salt_hex, iters, dklen = row
    window = int(created_at or 0) // DEFAULT_TIME_STEP
    old_master = vault2_mod.derive_master_key_windowed(seed_hex, window, key_salt)
    row_key = vault2_mod._derive_row_key(old_master, bytes.fromhex(row_salt_hex),
                                         iters or _ROW_ITERS, dklen or _ROW_DKLEN)
    return vault2_mod._make_backend("fernet", row_key).decrypt(enc)


def _snapshot(path):
    stat = os.stat(str(path))
    with open(str(path), "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "sha256": digest}


# ===========================================================================
# 1) 稳定派生的核心契约：跨窗口可读（P0 本体）
# ===========================================================================

def test_master_derivation_stable_across_windows(world):
    """退步了会怎样（P0 复活）：master 重新掺入 TOTP → 窗口 N 写的密钥在窗口 N+1
    重新 auth 后「凭证解密失败（密钥错误？）」，默认级别 L2 的用户数据一天内必丢。

    断言：窗口 N 写入 → `advance_totp_window(1)` → 重新 auth → get 成功且值一致。
    """
    _reg, auth_n = _register_and_auth(world, "alice", "L2")
    assert world.vault.set_secret(auth_n["session_token"], "db_pw", "TOP-SECRET")["status"] == "ok"

    world.advance(1)
    auth_next = _auth(world, _reg)
    assert auth_next["status"] == "ok", auth_next

    got = world.vault.get_secret(auth_next["session_token"], "db_pw")

    assert got["status"] == "ok", got
    assert got["value"] == "TOP-SECRET"


# ===========================================================================
# 2) L1 派生必须逐字不变（防修复误伤）
# ===========================================================================

def test_l1_derivation_unchanged(world):
    """退步了会怎样：修复时改了 L1 的派生（L1 本就没有动态码，应为空串）——
    L1 用户升级后旧密钥全部解不开（这次修复只应影响 L2/L3 的旧密文）。

    断言：L1 跨窗口读成功；且 `derive_master_key_stable(seed, salt)` 与旧 L1 口径
    `derive_master_key(seed, "", salt)` **逐字节相等**。
    """
    reg, auth_n = _register_and_auth(world, "bob", "L1")
    assert world.vault.set_secret(auth_n["session_token"], "l1_key", "L1-VALUE")["status"] == "ok"

    seed_hex, key_salt = _identity_material(world.vault, reg["identity_id"])
    assert vault2_mod.derive_master_key_stable(seed_hex, key_salt) == \
        vault2_mod.derive_master_key(seed_hex, "", key_salt), \
        "L1 派生被修复意外改变（旧 L1 密文将解不开）"

    world.advance(1)
    auth_next = _auth(world, reg)
    got = world.vault.get_secret(auth_next["session_token"], "l1_key")
    assert got["status"] == "ok" and got["value"] == "L1-VALUE", got


# ===========================================================================
# 3) auth 自动迁移旧密文 → 可读
# ===========================================================================

def test_legacy_ciphertext_migrated_on_auth(world):
    """退步了会怎样：旧派生时期的密文不迁移 —— 升级后老用户每次读都是
    「凭证解密失败」，只能靠人工脚本救。

    断言：造一条旧窗口密文 → 推进窗口后 auth → 响应 `master_migration.status=ok`
    且 `migrated>=1`；用新会话 get 能读到原值。
    """
    reg, auth_n = _register_and_auth(world, "carol", "L2")
    now = int(world.clock.now)
    _insert_legacy_secret(world.vault, reg["identity_id"], "legacy_pw", "OLD-VALUE", now)

    world.advance(1)
    auth_next = _auth(world, reg)

    assert auth_next["status"] == "ok", auth_next
    migration = auth_next.get("master_migration") or {}
    assert migration.get("status") == "ok", migration
    assert migration.get("migrated", 0) >= 1, migration

    got = world.vault.get_secret(auth_next["session_token"], "legacy_pw")
    assert got["status"] == "ok" and got["value"] == "OLD-VALUE", got


# ===========================================================================
# 4) 迁移原子性：写阶段异常 → 全部回滚（旧派生仍可解）
# ===========================================================================

def test_migration_atomic_rollback(world, monkeypatch):
    """退步了会怎样（非原子迁移）：写阶段中途失败却已 commit 了部分行 ——
    一部分密文变成新派生、一部分还是旧派生，且调用方以为整批失败；用户数据永久
    半迁移（新会话读旧行失败、旧脚本读新行失败）。

    断言：注入写阶段异常 → 抛错且 **db 逐字节不变**、seed 不变、两行旧密文仍可用
    旧派生解开（= 一行都没写成）。
    """
    reg, _auth_n = _register_and_auth(world, "dave", "L2")
    now = int(world.clock.now)
    _insert_legacy_secret(world.vault, reg["identity_id"], "old_a", "A", now)
    _insert_legacy_secret(world.vault, reg["identity_id"], "old_b", "B", now)

    before = _snapshot(world.db_path)
    seed_before, _salt = _identity_material(world.vault, reg["identity_id"])

    # 注入**写阶段**异常：第 2 条 UPDATE 时抛错（第 1 条已在同一事务里执行）。
    # 不能直接 patch sqlite3.Connection（C 类型不可改），改用代理连接 + 代理 `_db`。
    state = {"updates": 0}

    class FlakyConn(object):
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *params):
            if "UPDATE secrets SET value" in sql:
                state["updates"] += 1
                if state["updates"] == 2:
                    raise RuntimeError("模拟写阶段崩溃（单事务应回滚）")
            return self._conn.execute(sql, *params)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    @contextlib.contextmanager
    def flaky_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield FlakyConn(conn)
            conn.commit()
        finally:
            conn.close()

    monkeypatch.setattr(vault2_mod.Vault2, "_db", flaky_db)
    with pytest.raises(RuntimeError):
        world.vault.migrate_master_derivation(reg["identity_id"])

    assert _snapshot(world.db_path) == before, "写阶段失败后 db 被部分修改（非原子）"
    seed_after, _salt = _identity_material(world.vault, reg["identity_id"])
    assert seed_after == seed_before, "迁移失败不应改动 seed_key"
    assert _legacy_plaintext(world.vault, reg["identity_id"], "old_a") == "A"
    assert _legacy_plaintext(world.vault, reg["identity_id"], "old_b") == "B"


# ===========================================================================
# 5) 迁移幂等：第二遍 migrated=0 / already=N
# ===========================================================================

def test_migration_idempotent(world):
    """退步了会怎样：重复 auth（长驻进程很常见）时反复重加密 —— 每次写库、每次换 salt，
    轻则抖动，重则把"已迁移"误报成新迁移。

    断言：第一遍迁移后（新派生行 already 计数），第二遍 `migrated == 0` 且
    `already >= 1`，且不报错。
    """
    reg, auth_n = _register_and_auth(world, "erin", "L2")
    assert world.vault.set_secret(auth_n["session_token"], "k1", "v1")["status"] == "ok"

    first = world.vault.migrate_master_derivation(reg["identity_id"])
    assert first["status"] == "ok", first
    assert first["migrated"] == 0, first          # 刚写的就是新派生
    assert first["already"] >= 1, first

    second = world.vault.migrate_master_derivation(reg["identity_id"])
    assert second["status"] == "ok"
    assert second["migrated"] == 0 and second["already"] >= 1, second


# ===========================================================================
# 6) 无 key_salt 的旧身份 → skipped_legacy（如实报告，不静默）
# ===========================================================================

def test_migration_reports_legacy_no_key_salt(world):
    """退步了会怎样：无 `key_salt` 的旧身份被静默当成"已迁移"—— 用户以为升级完成，
    实际老密文一条都没救。

    断言：把身份的 key_salt 置 NULL 后迁移 → status=ok，该身份出现在
    `skipped_legacy`（需 PIN 才能重建旧 master，不能静默跳）。
    """
    reg = world.vault.register("frank", _PIN, security_level="L1")
    assert reg["status"] == "ok"
    with world.vault._db() as conn:
        conn.execute("UPDATE identities SET key_salt=NULL WHERE id=?", (reg["identity_id"],))

    result = world.vault.migrate_master_derivation()

    assert result["status"] == "ok", result
    assert reg["identity_id"] in result.get("skipped_legacy", []), result


# ===========================================================================
# 7) 自动迁移失败 → auth 仍成功，但显式回报 error（不静默）
# ===========================================================================

def test_auth_surfaces_migration_failure(world, monkeypatch):
    """退步了会怎样：迁移失败被吞掉，auth 只回"登录成功"——用户之后读旧密钥才
    发现解不开，而且没有任何线索指向"迁移没做完"。

    断言：monkeypatch 迁移返回 error → auth.status 仍 ok（登录不被阻断），但响应里
    `master_migration.status == 'error'` 且带原因。
    """
    reg = world.vault.register("gina", _PIN, security_level="L1")

    monkeypatch.setattr(
        vault2_mod.Vault2, "migrate_master_derivation",
        lambda self, identity_id=None: {
            "status": "error", "code": "migration_failed",
            "message": "simulated migration failure"})

    result = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)

    assert result["status"] == "ok", result
    migration = result.get("master_migration") or {}
    assert migration.get("status") == "error", migration
    assert "simulated" in (migration.get("message") or ""), migration


# ===========================================================================
# 8) 读路径零写（get / list 不改 db 文件）
# ===========================================================================

def test_read_path_zero_write(world):
    """退步了会怎样：`get_secret`/`list_secrets` 又变成"读时写"（审计/懒迁移）——
    只读 FS 上直接失败，且并发/备份校验被破坏。

    断言：读成功后 db 的 sha256 + mtime_ns + size 三件套与读前完全一致。
    """
    _reg, auth_n = _register_and_auth(world, "helen", "L2")
    token = auth_n["session_token"]
    assert world.vault.set_secret(token, "read_key", "READ-VALUE")["status"] == "ok"
    before = _snapshot(world.db_path)

    got = world.vault.get_secret(token, "read_key")
    listed = world.vault.list_secrets(token)

    assert got["status"] == "ok" and got["value"] == "READ-VALUE"
    assert listed["status"] == "ok"
    assert listed["count"] >= 1
    assert _snapshot(world.db_path) == before, "读路径改动了 vault2.db"


# ===========================================================================
# 9) rotated_backups 不迁移、迁移后仍可回滚
# ===========================================================================

def test_rotated_backups_survive_migration(world):
    """退步了会怎样：迁移把 `rotated_backups` 一起重加密（或用 master 加密备份）——
    回滚时旧值解不开；实际上备份由 `_derive_backup_key(seed)` 加密，只依赖 seed，
    迁移不应碰它。

    断言：写 V1 → rotate → 迁移 → rollback 成功且取回 V1。
    """
    reg, auth_n = _register_and_auth(world, "ivan", "L2")
    token = auth_n["session_token"]
    assert world.vault.set_secret(token, "rot_key", "V1")["status"] == "ok"

    rotated = world.vault.rotate_secret(token, "rot_key")
    assert rotated["status"] == "ok", rotated

    migration = world.vault.migrate_master_derivation(reg["identity_id"])
    assert migration["status"] == "ok", migration

    rolled = world.vault.rollback_secret(token, "rot_key")
    assert rolled["status"] == "ok", rolled

    got = world.vault.get_secret(token, "rot_key")
    assert got["status"] == "ok", got
    assert got["value"] == "V1", got
