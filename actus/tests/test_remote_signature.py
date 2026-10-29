# -*- coding: utf-8 -*-
"""阶段1/§六.3：远程动作的签名校验。

指纹（sha256）只能证明「内容没变」，**不能证明「谁发的」**——白名单域名被
攻破时，攻击者可以连指纹一起换掉。签名校验复用种子动作已有的 ed25519 .sig
机制：下载同名 `<url>.sig`，用本地可信公钥验签，失败即拒绝。
"""
import hashlib

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import pytest

from vools.actus import resolver as r
from vools.actus import trust_model

URL = "https://example.invalid/a.actus.schema.md"
CONTENT = "---\nid: myapp.remote\nname: Remote\n---\n"


def _patch_downloads(monkeypatch, tmp_path, with_sig=True, sig_text='{"version":"1.0"}'):
    action = tmp_path / "remote.actus.schema.md"
    action.write_text(CONTENT, encoding="utf-8")
    sig = tmp_path / "remote.actus.schema.md.sig"
    if with_sig:
        sig.write_text(sig_text, encoding="utf-8")

    def fake_download(url, allow_hosts=None):
        if url.endswith(".sig"):
            if not with_sig:
                raise RuntimeError("404 not found")
            return str(sig)
        return str(action)

    monkeypatch.setattr(r, "_download_url", fake_download)
    return action, sig, hashlib.sha256(action.read_bytes()).hexdigest()


def test_signature_verified_marks_flag(monkeypatch, tmp_path):
    _patch_downloads(monkeypatch, tmp_path)

    class _V:
        def verify_file(self, fpath, sig_path=None, public_key=None, key_name="default"):
            return {"status": "ok", "signer": key_name, "algorithm": "ed25519"}

    monkeypatch.setattr(trust_model, "SignatureVerifier", _V)
    res = r.resolve_target(URL, allow_hosts=["example.invalid"],
                           expect_signature_key="default")
    assert res.source == "url"
    assert res.signature_verified is True


def test_signature_missing_is_rejected(monkeypatch, tmp_path):
    _patch_downloads(monkeypatch, tmp_path, with_sig=False)
    with pytest.raises(Exception) as exc:
        r.resolve_target(URL, allow_hosts=["example.invalid"],
                         expect_signature_key="default")
    assert getattr(exc.value, "code", "") == "remote_signature_missing", exc.value


def test_signature_invalid_is_rejected(monkeypatch, tmp_path):
    _patch_downloads(monkeypatch, tmp_path)

    class _V:
        def verify_file(self, *a, **kw):
            return {"status": "error", "message": "Signature verification failed"}

    monkeypatch.setattr(trust_model, "SignatureVerifier", _V)
    with pytest.raises(Exception) as exc:
        r.resolve_target(URL, allow_hosts=["example.invalid"],
                         expect_signature_key="default")
    assert getattr(exc.value, "code", "") == "remote_signature_invalid", exc.value


def test_without_signature_key_flag_stays_false(monkeypatch, tmp_path):
    """不给 --require-signature 时不验签，flag 保持 False（不假装验过）。"""
    _patch_downloads(monkeypatch, tmp_path)
    res = r.resolve_target(URL, allow_hosts=["example.invalid"])
    assert res.signature_verified is False


def test_cli_exposes_require_signature_flag(monkeypatch):
    """行为契约（第 20 轮替换源码断言）：`--require-signature` 必须真的传给 resolver。

    做法：resolver 打桩记录 kwargs 并抛错（让 CLI 走"解析失败不阻断"的旧路径），
    execute 打桩避免联网/执行。守卫被删（参数不再透传）→ 记录到 None → 红。
    """
    import vools.actus as actuscore
    from vools.actus import cli
    from vools.actus import resolver as resolver_mod
    from vools.actus.errors import ActionError

    calls = []

    def fake_resolve(target, **kwargs):
        calls.append(kwargs)
        raise ActionError("remote_unverified", "simulated")

    executed = []
    monkeypatch.setattr(resolver_mod, "resolve_target", fake_resolve)
    monkeypatch.setattr(actuscore, "execute",
                        lambda *a, **kw: executed.append(a) or {"status": "ok"})

    rc = cli.main(["run", URL, "--require-signature", "default"])
    assert rc == 0, rc
    assert calls and calls[-1].get("expect_signature_key") == "default", calls
    assert executed, "解析失败应回退旧路径（零回归），不能中断"

    rc = cli.main(["run", URL])
    assert rc == 0 and calls[-1].get("expect_signature_key") is None, calls
