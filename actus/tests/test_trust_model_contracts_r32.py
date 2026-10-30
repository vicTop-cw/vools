"""trust_model 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- ScopeEnforcer 权限判定错误 → 越权或误拒
- KeyManager 密钥管理损坏 → 签名验证失败
- SignatureVerifier 签名/验证错误 → 伪造内容被接受或合法内容被拒
"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_keys_dir(tmp_path, monkeypatch):
    """隔离：KEYS_DIR 指向 tmp，不碰真实 ~/.actus/keys。"""
    d = tmp_path / "keys"
    d.mkdir()
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path))
    return str(d)


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    return str(f)


# ── ScopeEnforcer ──

class TestScopeEnforcer:
    def test_invalid_scope_defaults_to_community(self):
        """退步了会怎样：未知 scope 不应崩溃，应默认 community。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("invalid_scope")
        assert se.scope == "community"

    def test_trusted_has_all_permissions(self):
        """退步了会怎样：trusted scope 应有全部权限。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("trusted")
        assert se.check_permission("files:read")
        assert se.check_permission("files:write")
        assert se.check_permission("net:connect")
        assert se.check_permission("process:spawn")

    def test_unverified_is_readonly(self):
        """退步了会怎样：unverified scope 应只读，不应有写权限。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("unverified")
        assert se.is_readonly()
        assert se.check_permission("files:read")
        assert not se.check_permission("files:write")
        assert not se.check_permission("net:connect")

    def test_sandbox_is_readonly_with_notify(self):
        """退步了会怎样：sandbox scope 只读 + 通知，不应有写/网络。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("sandbox")
        assert se.is_readonly()
        assert se.check_permission("files:read")
        assert se.check_permission("ui:notify")
        assert not se.check_permission("files:write")
        assert not se.check_permission("net:connect")

    def test_check_permissions_returns_missing(self):
        """退步了会怎样：check_permissions 应返回缺失列表。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("community")
        ok, missing = se.check_permissions(["files:read", "files:write", "net:connect"])
        assert ok is True
        assert missing == []

    def test_check_permissions_with_missing(self):
        """退步了会怎样：community 不应有 trusted 专属权限。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("community")
        ok, missing = se.check_permissions(["files:read", "admin:grant"])
        assert ok is False
        assert "admin:grant" in missing

    def test_enforce_returns_none_when_ok(self):
        """退步了会怎样：enforce 权限满足时应返回 None。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("trusted")
        assert se.enforce(["files:read", "files:write"]) is None

    def test_enforce_returns_error_when_missing(self):
        """退步了会怎样：enforce 权限缺失时应返回错误信息。"""
        from vools.actus.trust_model import ScopeEnforcer
        se = ScopeEnforcer("unverified")
        err = se.enforce(["files:write"])
        assert err is not None
        assert "unverified" in err
        assert "files:write" in err

    def test_requires_confirmation_for_low_trust(self):
        """退步了会怎样：unverified/sandbox/community 应要求确认，trusted 不应。"""
        from vools.actus.trust_model import ScopeEnforcer
        assert ScopeEnforcer("unverified").requires_confirmation()
        assert ScopeEnforcer("sandbox").requires_confirmation()
        assert ScopeEnforcer("community").requires_confirmation()
        assert not ScopeEnforcer("trusted").requires_confirmation()


# ── KeyManager ──

class TestKeyManager:
    def test_generate_keypair_creates_keys(self, tmp_keys_dir):
        """退步了会怎样：generate_keypair 应创建密钥对。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        pub, priv = km.generate_keypair("test")
        assert pub is not None
        assert priv is not None
        assert len(pub) > 0

    def test_list_keys_shows_generated(self, tmp_keys_dir):
        """退步了会怎样：list_keys 应列出已生成的密钥。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("mykey")
        keys = km.list_keys()
        assert "mykey" in keys

    def test_list_keys_empty_initially(self, tmp_keys_dir):
        """退步了会怎样：空 KEYS_DIR 应返回空列表。"""
        from vools.actus.trust_model import KeyManager
        km = KeyManager(keys_dir=tmp_keys_dir)
        assert km.list_keys() == []


# ── SignatureVerifier ──

class TestSignatureVerifier:
    def test_sign_and_verify_file(self, tmp_keys_dir, tmp_file):
        """退步了会怎样：签名的文件应通过验证。"""
        from vools.actus.trust_model import KeyManager, SignatureVerifier
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("default")
        sv = SignatureVerifier(km)
        sig_path = tmp_file + ".sig"
        sv.sign_file(tmp_file, key_name="default", output=sig_path)
        result = sv.verify_file(tmp_file, sig_path=sig_path)
        assert result["status"] == "ok"

    def test_verify_tampered_file_fails(self, tmp_keys_dir, tmp_file):
        """退步了会怎样：被篡改的文件应验证失败。"""
        from vools.actus.trust_model import KeyManager, SignatureVerifier
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("default")
        sv = SignatureVerifier(km)
        sig_path = tmp_file + ".sig"
        sv.sign_file(tmp_file, key_name="default", output=sig_path)
        # 篡改文件内容
        with open(tmp_file, "a", encoding="utf-8") as f:
            f.write(" TAMPERED")
        result = sv.verify_file(tmp_file, sig_path=sig_path)
        assert result["status"] == "error"

    def test_sign_and_verify_roundtrip(self, tmp_keys_dir, tmp_file):
        """退步了会怎样：签名 → 验证 应往返一致。"""
        from vools.actus.trust_model import KeyManager, SignatureVerifier
        km = KeyManager(keys_dir=tmp_keys_dir)
        km.generate_keypair("default")
        sv = SignatureVerifier(km)
        sig_path = tmp_file + ".sig"
        sv.sign_file(tmp_file, key_name="default", output=sig_path)
        result = sv.verify_file(tmp_file, sig_path=sig_path)
        assert result["status"] == "ok"
        assert result.get("algorithm") is not None
