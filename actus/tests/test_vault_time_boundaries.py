# -*- coding: utf-8 -*-
"""actus/tests/test_vault_time_boundaries.py — vault 会话 TTL / used_codes 清理边界。

背景（第 18 轮审计 #4/#5）：
  * `test_expired_token_rejected` 只手动把 `expires_at=0` 再断言 error —— 只测了
    "epoch 0 < now"这个极端点；`SESSION_TTL` 在测试里 grep = 0，边界（TTL-1 /
    TTL+1）完全没测。TTL 判断写成 `>=` 或单位错（秒/毫秒）都不会被发现。
  * `used_codes` 清理是 `DELETE ... WHERE used_at < now-86400`，边界"刚好一天"
    也没有测试 —— 早删（重放窗口变小）或晚删（表无限增长）都不会被发现。

时间控制：用 conftest 的 `advance_totp_window`（同时 patch `vault2.time` 与
`vools.security.otp.time`），其 `advance.seconds(n)` 提供**秒级**推进，不 sleep。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import vault2 as vault2_mod  # noqa: E402
from vools.actus.vault2 import SESSION_TTL, Vault2  # noqa: E402

_PIN = "123456"


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

    vault2_mod._vault2_singleton = None
    w = _World()
    w.vault = Vault2(vault_dir=str(v2dir))
    w.db_path = w.vault.db_path
    w.advance = advance_totp_window
    return w


def _register_auth(world, identity="alice", level="L1"):
    reg = world.vault.register(identity, _PIN, security_level=level)
    assert reg["status"] == "ok", reg
    auth = world.vault.auth(reg["identity_id"], reg["machine_id"], _PIN)
    assert auth["status"] == "ok", auth
    return reg, auth


# ===========================================================================
# ① 会话 TTL 边界：TTL-1 仍有效，TTL+1 失效
# ===========================================================================

def test_session_ttl_boundary(world):
    """退步了会怎样：TTL 判断写成 `>=`（提前 1 秒失效）或单位错（秒当毫秒）——
    用户会话在临界点被意外踢掉/永不过期。只测 `expires_at=0` 这个极端点抓不到。

    断言：写入后 `advance.seconds(TTL-1)` → 读取仍成功；再
    `advance.seconds(2)`（已越过 TTL）→ 明确报"会话无效或已过期"。
    """
    _reg, auth = _register_auth(world, "alice", "L1")
    token = auth["session_token"]
    ttl = SESSION_TTL["L1"]
    assert world.vault.set_secret(token, "k", "V")["status"] == "ok"

    world.advance.seconds(ttl - 1)          # 距过期还有 1 秒
    ok = world.vault.get_secret(token, "k")
    assert ok["status"] == "ok" and ok["value"] == "V", ok

    world.advance.seconds(2)                # 已超过 TTL
    expired = world.vault.get_secret(token, "k")
    assert expired["status"] == "error", expired
    assert "会话无效或已过期" in (expired.get("message") or ""), expired


# ===========================================================================
# ② used_codes 清理边界：used_at < now-86400 才删
# ===========================================================================

def test_used_codes_cleanup_boundary(world):
    """退步了会怎样：清理条件写成 `<=`（多删一条还没过重放窗口的记录 → 防重放变弱）
    或漏删（表无限增长，长期进程内存/磁盘膨胀）。

    断言：手动放两条 used_codes —— 86401 秒前（严格早于一天，应删）、
    86399 秒前（严格晚于一天，应保留）；一次新 auth 后：
    旧码消失、临界保留的码还在（且 auth 自己新插入的码也在）。
    """
    reg, _auth0 = _register_auth(world, "bob", "L2")
    identity_id = reg["identity_id"]
    machine_id = reg["machine_id"]

    # 先推进时间，再以「最终 auth 时刻」为基准放两条临界记录，
    # 保证清理阈值（now-86400）恰好夹在 86401 与 86399 之间。
    world.advance.seconds(120)               # 跨窗口，auth 会生成新动态码
    now = int(world.advance.clock.now)
    with world.vault._db() as conn:
        conn.execute(
            "INSERT INTO used_codes (identity_id, machine_id, code, used_at)"
            " VALUES (?,?,?,?)", (identity_id, machine_id, "old-code", now - 86401))
        conn.execute(
            "INSERT INTO used_codes (identity_id, machine_id, code, used_at)"
            " VALUES (?,?,?,?)", (identity_id, machine_id, "keep-code", now - 86399))

    auth_next = world.vault.auth(identity_id, machine_id, _PIN)
    assert auth_next["status"] == "ok", auth_next

    with world.vault._db() as conn:
        codes = {row[0] for row in conn.execute(
            "SELECT code FROM used_codes WHERE identity_id=? AND machine_id=?",
            (identity_id, machine_id)).fetchall()}

    assert "old-code" not in codes, "used_at 严格早于一天前应被清理: %r" % codes
    assert "keep-code" in codes, "used_at 严格晚于一天前不应被清理: %r" % codes
    assert auth_next["dynamic_code"] in codes, "本次 auth 的动态码应已入防重放表"
