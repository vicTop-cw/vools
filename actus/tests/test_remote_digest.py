# -*- coding: utf-8 -*-
"""阶段1/§六.3：远程动作源的指纹校验。

计划 §六.3：远程 URL 动作「下载即执行」的供应链风险，建议默认 audit +
指纹校验 + 白名单域名。白名单只挡主机、SSL 只挡传输层——白名单域名内被
替换的内容仍会执行，所以必须有内容指纹校验。
"""
import hashlib

import pytest

from vools.actus import resolver as r

URL = "https://example.invalid/a.actus.schema.md"
CONTENT = "---\nid: myapp.remote\nname: Remote\n---\n"


def _patch_download(monkeypatch, tmp_path, content=CONTENT):
    f = tmp_path / "remote.actus.schema.md"
    f.write_text(content, encoding="utf-8")
    monkeypatch.setattr(r, "_download_url",
                        lambda url, allow_hosts=None: str(f))
    # 用文件**实际字节**算指纹：Windows 上 write_text 会把 \n 翻译成 \r\n，
    # 拿原始 content 的哈希会与文件内容不一致。
    return f, hashlib.sha256(f.read_bytes()).hexdigest()


def test_remote_digest_match_marks_verified(monkeypatch, tmp_path):
    _, digest = _patch_download(monkeypatch, tmp_path)
    res = r.resolve_target(URL, allow_hosts=["example.invalid"], expect_digest=digest)
    assert res.source == "url"
    assert res.digest_verified is True
    assert res.sha256 == digest


def test_remote_digest_mismatch_is_rejected(monkeypatch, tmp_path):
    _patch_download(monkeypatch, tmp_path)
    with pytest.raises(Exception) as exc:
        r.resolve_target(URL, allow_hosts=["example.invalid"],
                         expect_digest="deadbeef" * 8)
    assert getattr(exc.value, "code", "") == "remote_digest_mismatch", exc.value


def test_remote_without_digest_is_unverified(monkeypatch, tmp_path):
    """不给指纹时 sha256 仍算出来，但 digest_verified 保持 False——
    CLI 据此默认拒绝执行（--allow-unverified-remote 才放行）。"""
    _, digest = _patch_download(monkeypatch, tmp_path)
    res = r.resolve_target(URL, allow_hosts=["example.invalid"])
    assert res.digest_verified is False
    assert res.sha256 == digest


def test_remote_digest_case_insensitive(monkeypatch, tmp_path):
    _, digest = _patch_download(monkeypatch, tmp_path)
    res = r.resolve_target(URL, allow_hosts=["example.invalid"],
                           expect_digest=digest.upper())
    assert res.digest_verified is True


def test_cli_refuses_unverified_remote_by_contract():
    """源码级契约：CLI 必须默认拒绝未校验远程，并给出两个出路参数。"""
    import inspect
    from vools.actus import cli
    src = inspect.getsource(cli)
    assert "remote_unverified" in src
    assert "--expect-digest" in src or "expect_digest" in src
    assert "allow_unverified_remote" in src
