# -*- coding: utf-8 -*-
r"""actus/tests/test_runtimes_wsl_bash_r106.py — WSL bash 转发器特判回归（统帅轮-12时）。

测什么 / 为什么
---------------
`probe/runtimes.py::_probe_one_runtime` 原实现对 shell runtime 找到的
`C:\Windows\system32\bash.EXE`（WSL 网关）照常发 `bash --version`——该命令要
拉起 WSL VM：热态 ~2.3s、冷态 >5s 撞满 per-tool timeout。实测把 runtimes
探测器拖成 5.1s 恒定尾巴（probe 并行墙钟 2.5-5.4s 的真凶手；CHANGELOG 记载的
「system_tools 尖峰」另有归因，本尾巴与其并存且更硬）。

修复：version 探测前特判 system32\bash.exe——跳过 version、available 语义
不变、extra["wsl_forwarder"]=True 标注网关身份（真 git-bash 在 Git\\bin\\，
候选链后续命中，不丢信号）。

怎么测（不依赖 WSL 真跑）
------------------------
* monkeypatch `_find_runtime_path` 直接返回 WSL 转发器路径 → 断言 version
  为空、extra 标注、**且 _get_version_detail 未被调用**（跳过实锤）；
* 对照：非 WSL 路径（正常 bash）→ version 探测照常发起；
* SystemRoot 环境变量兜底路径也走特判。

py3.8+（pyproject requires-python），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe import runtimes as R  # noqa: E402


def _runtime():
    from vools.actus.runtimes import RuntimeRegistry
    return RuntimeRegistry()._runtimes.get("shell")


def _patch_path(monkeypatch, path):
    monkeypatch.setattr(R, "_find_runtime_path", lambda rt, idx: path)
    return path


def test_wsl_forwarder_skips_version_probe(monkeypatch):
    """system32\bash.EXE → version 探测被跳过，extra 标注 wsl_forwarder。"""
    calls = []

    def fake_version_detail(*a, **kw):
        calls.append(a)
        return ("GNU bash, version 5.1", None, {})
    monkeypatch.setattr(R, "_get_version_detail", fake_version_detail)

    wsl_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                            "system32", "bash.EXE")
    _patch_path(monkeypatch, wsl_path)

    result = R._probe_one_runtime(_runtime(), None, 5)

    assert result["available"] is True
    assert result["version"] == ""
    assert result["error"] is None
    assert result["extra"] == {"wsl_forwarder": True}
    assert calls == [], "version 探测不应发起（WSL 网关跳过）"


def test_normal_bash_still_probes_version(monkeypatch):
    """对照：非 WSL 路径（git-bash）→ version 探测照常发起。"""
    seen = []

    def fake_version_detail(path, args, timeout):
        seen.append((path, args, timeout))
        return ("GNU bash, version 5.2", None, {"foo": 1})
    monkeypatch.setattr(R, "_get_version_detail", fake_version_detail)

    _patch_path(monkeypatch, r"D:\Git\bin\bash.exe")
    result = R._probe_one_runtime(_runtime(), None, 5)

    assert result["version"] == "GNU bash, version 5.2"
    assert result["extra"] == {"foo": 1}
    assert len(seen) == 1
    assert seen[0][0] == r"D:\Git\bin\bash.exe"


def test_wsl_forwarder_case_insensitive(monkeypatch):
    """路径大小写/斜杠形态不敏感（normcase 归一）。"""
    monkeypatch.setattr(R, "_get_version_detail",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError(
                            "不应发起 version 探测")))
    lower = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                         "System32", "bash.exe")
    _patch_path(monkeypatch, lower)
    result = R._probe_one_runtime(_runtime(), None, 5)
    assert result["extra"] == {"wsl_forwarder": True}


def test_runtimes_probe_wall_clock_improved(monkeypatch):
    """集成口径：RuntimesProber.probe() 在本机（bash=WSL 转发器）下墙钟
    不再被 5s timeout 拖住——上限 3s（修复前实测 5.1s 恒定）。"""
    prober = R.RuntimesProber()
    import time as _time
    t0 = _time.monotonic()
    items = prober.probe()
    elapsed = (_time.monotonic() - t0) * 1000
    assert items, "runtimes 探测应产出条目"
    assert elapsed < 3000, (
        "runtimes 探测 %.0f ms ≥3s：WSL bash 转发器尾巴未消除？" % elapsed)
    # shell 条目存在且带 wsl_forwarder 标注（本机实况锚定）
    shell_items = [i for i in items
                   if getattr(i, "name", "") == "shell"
                   or "shell" in str(getattr(i, "meta", ""))]
    assert shell_items, "shell runtime 条目应存在"
