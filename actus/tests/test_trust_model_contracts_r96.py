# -*- coding: utf-8 -*-
"""r96 — vools.actus.trust_model 契约测试（只读补测，产品零改动）。

覆盖本轮缺口（结合合跑 70% / missed 91 的未覆盖行）：
* KeyManager 全生命周期：PEM 生成往返、裸 32 字节退化路径、cryptography
  ImportError 退化（sys.modules 置 None 强制 ImportError）、公钥裸格式/
  非法 base64、list_keys 空目录早退、keys_dir 属性；
* SignatureVerifier 错误矩阵：文件缺失/私钥缺失/签名文件缺失/文件不匹配/
  内容篡改/公钥缺失/公钥格式非法/签名不匹配 + HMAC 退化双向（sign 侧
  bytes 私钥、verify 侧 ImportError 分支）；
* ApprovalManager：list_pending 目录缺失早退 + 非 .json 跳过；
* TrustEvaluator.evaluate 全分支矩阵（假 installer，禁真跑）：
  未安装 / 被拒 / 需审批未批 / 已批通过 / .actus.scope 覆盖 / 权限不足；
* evaluate_trust() 已知产品 bug（trust_model.py:623-624 调用裸 evaluate
  而非 evaluator.evaluate → NameError）：负向契约 pytest.raises(NameError)
  —— 【待裁决】产品侧修与否则由人类指挥官裁决，本测试只钉住现状。

基建红线：
* 全部隔离：conftest._pin_isolated_dirs 已把 HOME/ACTUS_META_DIR/
  ACTUS_VAULT2_DIR 钉到 session tmp，本文件不写工作区 _meta/；
* 跨文件收集期 sys.modules['vools.actus.<mod>'] 可能被置换为 namespace
  stub —— patch 一律对象寻址（模块对象属性 / 实例属性），禁止字符串寻址；
* 产品代码零修改。
"""

import base64
import hashlib
import json
import os
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导（幂等），再导入 vools.actus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.trust_model as tm  # noqa: E402  对象寻址：绑定模块对象


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def keys_dir(tmp_path):
    d = tmp_path / "keys"
    d.mkdir()
    return str(d)


@pytest.fixture
def km(keys_dir):
    return tm.KeyManager(keys_dir=keys_dir)


_ED25519_MOD = "cryptography.hazmat.primitives.asymmetric.ed25519"


# ---------------------------------------------------------------------------
# KeyManager 全生命周期
# ---------------------------------------------------------------------------

class TestKeyManagerLifecycle:
    def test_keys_dir_property(self, km, keys_dir):
        """keys_dir 属性回显构造参数。"""
        assert km.keys_dir == keys_dir

    def test_default_keys_dir_under_home(self):
        """不传 keys_dir 时默认 ~/.actus/keys（conftest 已把 HOME 钉到 tmp）。"""
        m = tm.KeyManager()
        expected = os.path.join(os.path.expanduser("~"), ".actus", "keys")
        assert m.keys_dir == expected

    def test_constructor_does_not_create_dir(self, tmp_path):
        """第 16 轮契约：构造不建目录（只读用途不在 HOME 留目录）。"""
        d = tmp_path / "never_created"
        m = tm.KeyManager(keys_dir=str(d))
        m.list_keys()
        assert not d.exists()

    def test_list_keys_missing_dir_returns_empty(self, tmp_path):
        """目录不存在 = 空列表（不为此建目录）。"""
        m = tm.KeyManager(keys_dir=str(tmp_path / "nope"))
        assert m.list_keys() == []
        assert not (tmp_path / "nope").exists()

    def test_generate_keypair_pem_roundtrip(self, km):
        """生成 → PEM 文件落盘 → load_private_key 往返 Ed25519 对象。"""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives import serialization

        priv_path, pub_path = km.generate_keypair("pem")
        assert os.path.isfile(priv_path) and os.path.isfile(pub_path)
        with open(priv_path, "rb") as f:
            assert f.read().startswith(b"-----BEGIN")
        with open(pub_path, "rb") as f:
            assert f.read().startswith(b"-----BEGIN PUBLIC KEY")
        loaded = km.load_private_key("pem")
        assert isinstance(loaded, Ed25519PrivateKey)
        pub = km.load_public_key("pem")
        assert pub.startswith(b"-----BEGIN")
        # PEM 私钥可解析回原始字节
        raw = loaded.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        assert len(raw) == 32

    def test_load_private_key_missing_returns_none(self, km):
        assert km.load_private_key("no_such_key") is None

    def test_load_public_key_missing_returns_none(self, km):
        assert km.load_public_key("no_such_key") is None

    def test_load_private_key_raw32_bytes(self, km):
        """裸 32 字节 base64 私钥 → 返回解码字节（退化格式往返）。"""
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        assert km.load_private_key("raw") == raw

    def test_load_private_key_valid_base64_non32_returns_none(self, km):
        """PEM 解析失败 + base64 合法但不是 32 字节 → None（不猜格式）。

        注意：base64 本身非法（长度非 4 倍数等）会抛 binascii.Error ——
        那是产品现状的另一条契约，这里只测「合法 base64 / 非 32 字节」支路。
        """
        with open(os.path.join(km.keys_dir, "junk.key"), "wb") as f:
            f.write(base64.b64encode(os.urandom(16)))  # 合法 base64，16 字节
        assert km.load_private_key("junk") is None

    def test_load_private_key_importerror_fallback(self, km, monkeypatch):
        """cryptography 缺失（ImportError）→ 直接 base64 解码返回。"""
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)  # None → import 抛 ImportError
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        assert km.load_private_key("raw") == raw

    def test_generate_keypair_importerror_fallback(self, km, monkeypatch):
        """cryptography 缺失 → 退化方案：urandom 32 字节 base64 落盘。"""
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)
        priv_path, pub_path = km.generate_keypair("degraded")
        with open(priv_path, "rb") as f:
            decoded = base64.b64decode(f.read())
        assert len(decoded) == 32
        with open(pub_path, "rb") as f:
            assert len(base64.b64decode(f.read())) == 32

    def test_load_public_key_bare_base64(self, km):
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "bare.pub"), "wb") as f:
            f.write(base64.b64encode(raw))
        assert km.load_public_key("bare") == raw

    def test_load_public_key_invalid_base64_returns_raw(self, km):
        """非 PEM、非合法 base64 → 原样返回字节（最后兜底）。"""
        blob = b"!!! not base64 at all !!!"
        with open(os.path.join(km.keys_dir, "bad.pub"), "wb") as f:
            f.write(blob)
        assert km.load_public_key("bad") == blob

    def test_list_keys_filters_key_suffix(self, km):
        km.generate_keypair("a")
        km.generate_keypair("b")
        with open(os.path.join(km.keys_dir, "c.pub"), "wb") as f:
            f.write(b"x")
        assert sorted(km.list_keys()) == ["a", "b"]


# ---------------------------------------------------------------------------
# SignatureVerifier 错误矩阵 + HMAC 退化
# ---------------------------------------------------------------------------

class TestSignatureVerifierErrors:
    def test_sign_file_missing_file(self, km, tmp_path):
        sv = tm.SignatureVerifier(km)
        result = sv.sign_file(str(tmp_path / "ghost.txt"))
        assert result["status"] == "error"
        assert "File not found" in result["message"]

    def test_sign_file_missing_private_key(self, km, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        result = sv.sign_file(str(f), key_name="no_key")
        assert result["status"] == "error"
        assert "Private key not found" in result["message"]

    def test_sign_with_raw_bytes_key_uses_hmac(self, km, tmp_path):
        """裸 32 字节私钥（cryptography 可用但非 Ed25519 对象）→ HMAC-SHA256 签名。"""
        import hmac as hmac_mod
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        f = tmp_path / "doc.txt"
        f.write_text("payload", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        result = sv.sign_file(str(f), key_name="raw")
        assert result["status"] == "ok"
        with open(str(f) + ".sig", "r", encoding="utf-8") as fh:
            sig = json.load(fh)
        message = sig["message"].encode("utf-8")
        expected = hmac_mod.new(raw, message, hashlib.sha256).digest()
        assert base64.b64decode(sig["signature"]) == expected

    def test_sign_importerror_fallback_hmac(self, km, tmp_path, monkeypatch):
        """bytes 私钥 + cryptography 导入失败 → except 分支 HMAC 签名。"""
        import hmac as hmac_mod
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        f = tmp_path / "doc.txt"
        f.write_text("payload", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        result = sv.sign_file(str(f), key_name="raw")
        assert result["status"] == "ok"
        with open(str(f) + ".sig", "r", encoding="utf-8") as fh:
            sig = json.load(fh)
        expected = hmac_mod.new(raw, sig["message"].encode("utf-8"),
                                hashlib.sha256).digest()
        assert base64.b64decode(sig["signature"]) == expected

    def test_verify_file_missing_file(self, km, tmp_path):
        sv = tm.SignatureVerifier(km)
        assert sv.verify_file(str(tmp_path / "ghost.txt"))["status"] == "error"

    def test_verify_file_missing_sig(self, km, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        assert sv.verify_file(str(f))["status"] == "error"

    def test_verify_file_basename_mismatch(self, km, tmp_path):
        """签名里的 file 字段与目标文件名不同 → 拒绝。"""
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        sig_path = tmp_path / "other.txt.sig"
        sig_path.write_text(json.dumps({"file": "other.txt"}), encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        result = sv.verify_file(str(f), sig_path=str(sig_path))
        assert result["status"] == "error"
        assert "mismatch" in result["message"]

    def test_verify_tampered_content(self, km, tmp_path):
        km.generate_keypair("default")
        f = tmp_path / "a.txt"
        f.write_text("hello", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        sv.sign_file(str(f))
        f.write_text("hello tampered", encoding="utf-8")
        result = sv.verify_file(str(f))
        assert result["status"] == "error"
        assert "tampered" in result["message"]

    def test_verify_missing_public_key(self, km, tmp_path):
        """没有 .pub 文件、也没传 public_key → 公钥缺失错误。"""
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        content_hash = tm.SignatureVerifier._compute_hash(str(f))
        message = "actus-sig:%s:0" % content_hash
        import hmac as hmac_mod
        sig_path = str(f) + ".sig"
        with open(sig_path, "w", encoding="utf-8") as fh:
            json.dump({"file": "a.txt", "message": message,
                       "signature": base64.b64encode(
                           hmac_mod.new(raw, message.encode("utf-8"),
                                        hashlib.sha256).digest()).decode("utf-8")},
                      fh)
        sv = tm.SignatureVerifier(km)
        result = sv.verify_file(str(f), sig_path=sig_path, key_name="no_key")
        # 退化分支前置检查在主 try 之外：public_key None 且 load_public_key
        # 也拿不到（无 raw.pub）→ 提前 "Public key not found"（270 行），到不了
        # ImportError 分支。
        assert result["status"] == "error"
        assert result["message"] == "Public key not found"

    def test_verify_invalid_pubkey_format(self, km, tmp_path):
        """公钥既非 PEM 也非 32 字节 → Invalid public key format。"""
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        with open(os.path.join(km.keys_dir, "raw.pub"), "wb") as f:
            f.write(base64.b64encode(os.urandom(10)))  # 10 字节裸公钥
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        content_hash = tm.SignatureVerifier._compute_hash(str(f))
        message = "actus-sig:%s:0" % content_hash
        import hmac as hmac_mod
        sig_path = str(f) + ".sig"
        with open(sig_path, "w", encoding="utf-8") as fh:
            json.dump({"file": "a.txt", "message": message,
                       "signature": base64.b64encode(
                           hmac_mod.new(raw, message.encode("utf-8"),
                                        hashlib.sha256).digest()).decode("utf-8")},
                      fh)
        sv = tm.SignatureVerifier(km)
        result = sv.verify_file(str(f), sig_path=sig_path, key_name="raw")
        assert result["status"] == "error"
        assert result["message"] == "Invalid public key format"

    def test_verify_bad_signature_ed25519(self, km, tmp_path):
        """Ed25519 全链路：真签名被篡改 → Signature verification failed。"""
        km.generate_keypair("default")
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        sv.sign_file(str(f))
        with open(str(f) + ".sig", "r", encoding="utf-8") as fh:
            sig = json.load(fh)
        sig["signature"] = base64.b64encode(os.urandom(64)).decode("utf-8")
        with open(str(f) + ".sig", "w", encoding="utf-8") as fh:
            json.dump(sig, fh)
        result = sv.verify_file(str(f))
        assert result["status"] == "error"
        assert result["message"] == "Signature verification failed"

    def test_verify_with_pubkey_object(self, km, tmp_path):
        """public_key 传公钥对象（非 bytes）→ 走对象 verify 分支。"""
        from cryptography.hazmat.primitives import serialization
        km.generate_keypair("default")
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        sv.sign_file(str(f))
        with open(os.path.join(km.keys_dir, "default.pub"), "rb") as fh:
            pub_obj = serialization.load_pem_public_key(fh.read())
        result = sv.verify_file(str(f), public_key=pub_obj)
        assert result["status"] == "ok"
        assert result["algorithm"] == "ed25519"

    def test_verify_importerror_hmac_fallback_roundtrip(self, km, tmp_path,
                                                        monkeypatch):
        """cryptography 缺失 + 裸私钥：sign(退化) → verify(HMAC 退化) 往返。"""
        import hmac as hmac_mod
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)
        raw = os.urandom(32)
        with open(os.path.join(km.keys_dir, "raw.key"), "wb") as f:
            f.write(base64.b64encode(raw))
        with open(os.path.join(km.keys_dir, "raw.pub"), "wb") as f:
            f.write(base64.b64encode(os.urandom(32)))
        f = tmp_path / "doc.txt"
        f.write_text("payload", encoding="utf-8")
        sv = tm.SignatureVerifier(km)
        assert sv.sign_file(str(f), key_name="raw")["status"] == "ok"
        result = sv.verify_file(str(f), key_name="raw")
        assert result["status"] == "ok"
        assert result["algorithm"] == "hmac-sha256-fallback"

    def test_verify_importerror_shared_secret_path(self, km, tmp_path,
                                                   monkeypatch):
        """退化分支 + 传入的 public_key 实为共享密钥 → hmac-sha256 老行为。"""
        import hmac as hmac_mod
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)
        secret = os.urandom(32)
        f = tmp_path / "doc.txt"
        f.write_text("payload", encoding="utf-8")
        content_hash = tm.SignatureVerifier._compute_hash(str(f))
        message = "actus-sig:%s:123" % content_hash
        sig_path = str(f) + ".sig"
        with open(sig_path, "w", encoding="utf-8") as fh:
            json.dump({"file": "doc.txt", "message": message,
                       "signature": base64.b64encode(
                           hmac_mod.new(secret, message.encode("utf-8"),
                                        hashlib.sha256).digest()).decode("utf-8")},
                      fh)
        sv = tm.SignatureVerifier(km)
        result = sv.verify_file(str(f), sig_path=sig_path, public_key=secret,
                                key_name="no_key")
        assert result["status"] == "ok"
        assert result["algorithm"] == "hmac-sha256"

    def test_verify_importerror_total_failure(self, km, tmp_path, monkeypatch):
        """退化分支：无私钥、共享密钥也不匹配 → 显式失败。"""
        import hmac as hmac_mod
        monkeypatch.setitem(sys.modules, _ED25519_MOD, None)
        f = tmp_path / "doc.txt"
        f.write_text("payload", encoding="utf-8")
        content_hash = tm.SignatureVerifier._compute_hash(str(f))
        message = "actus-sig:%s:123" % content_hash
        sig_path = str(f) + ".sig"
        with open(sig_path, "w", encoding="utf-8") as fh:
            json.dump({"file": "doc.txt", "message": message,
                       "signature": base64.b64encode(os.urandom(32)).decode("utf-8")},
                      fh)
        # 必须有 .pub 文件才能越过 270 行 "Public key not found" 前置检查，
        # 进入 ImportError 分支；32 字节 pub 但与签名不匹配 → 最终失败。
        with open(os.path.join(km.keys_dir, "no_key.pub"), "wb") as pf:
            pf.write(base64.b64encode(os.urandom(32)))
        sv = tm.SignatureVerifier(km)
        result = sv.verify_file(str(f), sig_path=sig_path, key_name="no_key")
        assert result["status"] == "error"
        assert result["message"] == "Signature verification failed (fallback)"


# ---------------------------------------------------------------------------
# ApprovalManager 边界
# ---------------------------------------------------------------------------

class TestApprovalManagerBoundaries:
    def test_list_pending_missing_dir(self, tmp_path):
        am = tm.ApprovalManager(approvals_dir=str(tmp_path / "nope"))
        assert am.list_pending() == []
        assert not (tmp_path / "nope").exists()

    def test_list_pending_skips_non_json(self, tmp_path):
        d = tmp_path / "approvals"
        d.mkdir()
        (d / "notes.txt").write_text("junk", encoding="utf-8")
        am = tm.ApprovalManager(approvals_dir=str(d))
        rec = am.request_approval("act.x", "https://e", ["files:read"], "c0")
        assert rec["status"] == "pending"
        pending = am.list_pending()
        assert len(pending) == 1
        assert pending[0]["action_id"] == "act.x"

    def test_private_action_auto_approved(self, tmp_path):
        """私有动作作者自动批准：status="auto_approved"（注意 436-439 行：
        is_approved 只认 "approved" —— auto_approved 记录 is_approved=False，
        这是产品现状契约，钉住它）。"""
        am = tm.ApprovalManager(approvals_dir=str(tmp_path / "approvals"))
        rec = am.request_approval("act.p", "https://e", [], "c0",
                                  visibility="private", author="me")
        assert rec["status"] == "auto_approved"
        assert "auto_approve_reason" in rec
        assert am.is_approved("act.p") is False
        assert am.is_rejected("act.p") is False

    def test_reject_roundtrip_and_unknown_id(self, tmp_path):
        am = tm.ApprovalManager(approvals_dir=str(tmp_path / "approvals"))
        am.request_approval("act.r", "https://e", [], "c0")
        rec = am.reject("act.r", reason="bad")
        assert rec["status"] == "rejected" and rec["reason"] == "bad"
        assert am.is_rejected("act.r") is True
        assert am.is_approved("act.r") is False
        assert am.approve("never_seen") is None
        assert am.is_approved("never_seen") is False


# ---------------------------------------------------------------------------
# TrustEvaluator.evaluate 全分支矩阵（假 installer，禁真跑）
# ---------------------------------------------------------------------------

class _FakeInstaller:
    """对象寻址替身：只实现 evaluate() 用到的 list_installed()。"""

    def __init__(self, manifests):
        self._manifests = manifests

    def list_installed(self):
        return self._manifests


@pytest.fixture
def evaluator(tmp_path):
    ev = tm.TrustEvaluator(install_dir=str(tmp_path / "install_root"))
    return ev


def _manifest(action_id, local_path):
    return {"actions": [{"id": action_id}], "local_path": local_path}


class TestTrustEvaluatorEvaluate:
    def test_action_not_installed(self, evaluator):
        result = evaluator.evaluate("ghost.action")
        assert result["can_execute"] is False
        assert result["error"] == "Action not installed: ghost.action"
        assert result["trust_level"] == "unverified"

    def test_rejected_action_blocked(self, evaluator, tmp_path):
        aid = "rejected.action"
        local = tmp_path / "repo_rejected"
        local.mkdir()
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        evaluator._approval.request_approval(aid, "https://e", [], "c0")
        evaluator._approval.reject(aid)
        result = evaluator.evaluate(aid)
        assert result["error"] == "Action has been rejected by user"
        assert result["can_execute"] is False

    def test_community_requires_approval(self, evaluator, tmp_path):
        aid = "community.action"
        local = tmp_path / "repo_community"
        local.mkdir()  # 无 .actus.scope → 默认 community
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        result = evaluator.evaluate(aid)
        assert result["trust_level"] == "community"
        assert result["can_execute"] is False
        assert result["requires_confirmation"] is True
        assert "requires approval" in result["error"]
        assert "actus approve" in result["error"]

    def test_approved_community_executes_with_confirmation(self, evaluator,
                                                           tmp_path):
        aid = "approved.action"
        local = tmp_path / "repo_approved"
        local.mkdir()
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        evaluator._approval.request_approval(aid, "https://e", [], "c0")
        evaluator._approval.approve(aid)
        result = evaluator.evaluate(aid)
        assert result["trust_level"] == "community"
        assert result["can_execute"] is True
        assert result["requires_confirmation"] is True
        assert result["error"] is None

    def test_scope_file_overrides(self, evaluator, tmp_path):
        """.actus.scope 文件存在 → 读取并 strip（trusted 无需审批）。"""
        aid = "trusted.action"
        local = tmp_path / "repo_trusted"
        local.mkdir()
        (local / ".actus.scope").write_text("trusted\n", encoding="utf-8")
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        result = evaluator.evaluate(aid)
        assert result["trust_level"] == "trusted"
        assert result["can_execute"] is True
        assert result["requires_confirmation"] is False

    def test_insufficient_permissions(self, evaluator, tmp_path):
        """community scope 默认含 files:write（constants.py:82）——
        所以 files:write 实际放行；files:delete 不在白名单 → enforce 失败。"""
        aid = "perm.action"
        local = tmp_path / "repo_perm"
        local.mkdir()
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        evaluator._approval.request_approval(aid, "https://e", [], "c0")
        evaluator._approval.approve(aid)
        result = evaluator.evaluate(aid, action_permissions=["files:delete"])
        assert result["can_execute"] is False
        assert "lacks permissions" in result["error"]
        assert "files:delete" in result["error"]

    def test_community_permission_allowed(self, evaluator, tmp_path):
        """community 白名单内的权限（files:write）→ 通过。"""
        aid = "perm.ok"
        local = tmp_path / "repo_perm_ok"
        local.mkdir()
        evaluator._installer = _FakeInstaller([_manifest(aid, str(local))])
        evaluator._approval.request_approval(aid, "https://e", [], "c0")
        evaluator._approval.approve(aid)
        result = evaluator.evaluate(aid, action_permissions=["files:write"])
        assert result["can_execute"] is True
        # scope_permissions 回显整个 scope 白名单（community 5 项），非过滤后的
        assert "files:write" in result["scope_permissions"]
        assert "net:connect" in result["scope_permissions"]

    def test_find_manifest_skips_empty_actions(self, evaluator, tmp_path):
        """多 manifest 遍历：第一个无 actions、第二个命中（587-589 循环分支）。"""
        aid = "second.action"
        local = tmp_path / "repo_second"
        local.mkdir()
        evaluator._installer = _FakeInstaller(
            [{"actions": []}, _manifest(aid, str(local))])
        result = evaluator.evaluate(aid)
        assert result["trust_level"] == "community"
        assert result["can_execute"] is False  # community 未审批
        assert "requires approval" in result["error"]

    def test_get_scope_defaults_community(self, evaluator, tmp_path):
        assert evaluator._get_scope(str(tmp_path)) == "community"


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    def test_generate_keys_writes_pair(self, tmp_path):
        priv, pub = tm.generate_keys("conv", keys_dir=str(tmp_path / "kd"))
        assert os.path.isfile(priv) and os.path.isfile(pub)

    def test_evaluate_trust_known_bug_raises_nameerror(self):
        """【待裁决】已知产品 bug：evaluate_trust() (trust_model.py:623-624)
        调用裸 evaluate(action_id) 而非 evaluator.evaluate(action_id)
        → NameError。本测试钉住现状（负向契约）；产品修复后本断言应改写为
        正向契约（见 trust_model.py:624 `return evaluate(...)`）。
        """
        with pytest.raises(NameError):
            tm.evaluate_trust("any.action")
