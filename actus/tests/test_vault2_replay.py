"""Vault2 动态码防重放 + 加密往返回归。

回归点（2026-10-13）：auth 的 L2/L3 动态码 TOTP 只写 used_codes 却从不查重，
INSERT OR IGNORE 的 rowcount 也被忽略 -> 同一动态码在其 60s+window TTL 内
可被无限重放换 session_token（窃到一次 TOTP 即可重复登录）。与
security/otp BUG-147 同型。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()


@pytest.fixture
def vault(tmp_path):
    from vools.actus.vault2 import Vault2
    return Vault2(vault_dir=str(tmp_path / "vault"))


def _register_and_auth(vault, level):
    reg = vault.register("alice", "123456", security_level=level)
    assert reg["status"] == "ok", reg
    iid, mid = reg["identity_id"], reg["machine_id"]
    res = vault.auth(iid, mid, "123456")
    return iid, mid, res


def test_l2_dynamic_code_cannot_be_replayed(vault):
    iid, mid, first = _register_and_auth(vault, "L2")
    assert first["status"] == "ok", first
    assert first["session_token"]

    # 同一时间步内立即再次用同一 PIN 登录 -> 动态码相同 -> 必须按重放拒绝
    second = vault.auth(iid, mid, "123456")
    assert second["status"] == "error"
    assert "动态码" in second["message"]
    assert "session_token" not in second


def test_l1_has_no_dynamic_code_and_skips_replay_table(vault):
    # L1 不产生动态码，登录不应因 used_codes 被拦（两次都应成功，各发新 token）
    iid, mid, first = _register_and_auth(vault, "L1")
    assert first["status"] == "ok"
    again = vault.auth(iid, mid, "123456")
    assert again["status"] == "ok", again
    assert again["session_token"] != first["session_token"]


def test_secret_roundtrip_default_fernet(vault):
    iid, mid, res = _register_and_auth(vault, "L1")  # L1 免去动态码时序依赖
    token = res["session_token"]
    w = vault.set_secret(token, "db_pw", "s3cr3t!", metadata={"env": "prod"})
    assert w["status"] == "ok" and w["cipher_alg"] == "fernet"
    got = vault.get_secret(token, "db_pw")
    assert got["status"] == "ok"
    assert got["value"] == "s3cr3t!"
    assert got["metadata"] == {"env": "prod"}


def test_secret_ciphertext_is_not_plaintext(vault):
    iid, mid, res = _register_and_auth(vault, "L1")
    token = res["session_token"]
    vault.set_secret(token, "tok", "PLAINVALUE123")
    import sqlite3
    with sqlite3.connect(vault.db_path) as conn:
        stored = conn.execute("SELECT value FROM secrets WHERE name=?", ("tok",)).fetchone()[0]
    assert "PLAINVALUE123" not in stored


def test_expired_token_rejected(vault, monkeypatch):
    iid, mid, res = _register_and_auth(vault, "L1")
    token = res["session_token"]
    # 把该会话过期时间拨到过去
    vault._sessions[token]["expires_at"] = 0
    assert vault.get_secret(token, "x")["status"] == "error"
