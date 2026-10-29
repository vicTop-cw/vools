# -*- coding: utf-8 -*-
"""阶段1/§六.3：远程动作源的指纹校验。

计划 §六.3：远程 URL 动作「下载即执行」的供应链风险，建议默认 audit +
指纹校验 + 白名单域名。白名单只挡主机、SSL 只挡传输层——白名单域名内被
替换的内容仍会执行，所以必须有内容指纹校验。
"""
import hashlib

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

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


def test_cli_refuses_unverified_remote_by_contract(monkeypatch, capsys):
    """行为契约（第 20 轮替换源码断言）：默认拒绝未校验远程、两个出路可用。

    - 默认：run 一个 digest_verified=False 的 URL → rc=1 + code=remote_unverified
      （守卫被删 → 会直接进 execute，rc=0，立刻红）；
    - `--allow-unverified-remote`：放行到执行层（execute 被打桩，不联网）；
    - `--expect-digest`：值必须真的传给 resolver（守卫在但透传被删 → 红）。
      URL 的所有网络/下载行为都用 monkeypatch 消除。
    """
    import json
    from vools.actus import cli
    from vools.actus import resolver as resolver_mod
    import vools.actus as actuscore

    calls = []

    class _Resolved:
        source = "url"
        url = URL
        path = None
        action_id = None
        ambiguous = []
        digest_verified = False
        sha256 = "deadbeef"

    def fake_resolve(target, **kwargs):
        calls.append(kwargs)
        return _Resolved()

    executed = []
    monkeypatch.setattr(resolver_mod, "resolve_target", fake_resolve)
    monkeypatch.setattr(actuscore, "execute",
                        lambda *a, **kw: executed.append(a) or {"status": "ok"})

    def run(argv):
        capsys.readouterr()
        rc = cli.main(argv)
        out = capsys.readouterr().out
        payload = json.loads(out[out.index("{"):]) if "{" in out else {}
        return rc, payload

    rc, payload = run(["run", URL])
    assert rc == 1, (rc, payload)
    assert payload["error"]["code"] == "remote_unverified", payload
    assert executed == [], "默认拒绝时不应进入执行层"

    rc, _payload = run(["run", URL, "--allow-unverified-remote"])
    assert rc == 0 and executed, "显式 --allow-unverified-remote 应放行到执行层"

    run(["run", URL, "--expect-digest", "a" * 64])
    assert calls and calls[-1].get("expect_digest") == "a" * 64, calls
