# -*- coding: utf-8 -*-
"""actus/tests/test_platform_sip_r103.py — macOS SIP 探测判据回归（统帅轮-10时）。

测什么 / 为什么
---------------
`probe/platform.py::_get_sip_status()` 原判据 `"enabled" in stdout.lower()`
存在子串误判：SIP **disabled** 时的 csrutil 输出
「System Integrity Protection status: disabled.」同样包含 "enabled" 子串
（disabled ⊃ enabled）→ 关闭态被误报成开启态（安全语义反转，静默错值）。

修复为 `"status: enabled" in stdout.lower()`。本文件用**假 subprocess 世界**
验证三种输出形态的判据行为（本机无 csrutil / 非 darwin 也能全跑）：
  * status: enabled  → True
  * status: disabled → False（关键回归点：旧判据在此误报 True）
  * csrutil 不存在/异常 → None

py3.8+ 口径（pyproject requires-python>=3.8，24ea2d53 升级）：只用标准库，% 格式化（保持文件间一致风格）。
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe import platform as plat  # noqa: E402


def _fake_run(stdout_text):
    """构造 capture_output 形态的假 subprocess.run。"""
    def fake_run(*_args, **_kwargs):
        return types.SimpleNamespace(stdout=stdout_text, returncode=0)
    return fake_run


def _patch_and_call(monkeypatch, stdout_text):
    fake = types.ModuleType("subprocess")
    fake.run = _fake_run(stdout_text)
    monkeypatch.setitem(sys.modules, "subprocess", fake)
    return plat._get_sip_status()


def test_sip_enabled_detected(monkeypatch):
    """status: enabled → True。"""
    out = "System Integrity Protection status: enabled.\n"
    assert _patch_and_call(monkeypatch, out) is True


def test_sip_disabled_not_misreported(monkeypatch):
    """关键回归：status: disabled → False（旧判据 "enabled" in stdout 误报 True）。"""
    out = "System Integrity Protection status: disabled.\n"
    assert _patch_and_call(monkeypatch, out) is False


def test_sip_unrecognized_output_is_false(monkeypatch):
    """无 status 行的输出 → False（不猜）。"""
    assert _patch_and_call(monkeypatch, "csrutil: unknown output\n") is False


def test_sip_command_missing_returns_none(monkeypatch):
    """csrutil 不存在（FileNotFoundError）→ None（不伪造状态）。"""
    fake = types.ModuleType("subprocess")

    def raise_fnf(*_a, **_k):
        raise FileNotFoundError("csrutil")
    fake.run = raise_fnf
    monkeypatch.setitem(sys.modules, "subprocess", fake)
    assert plat._get_sip_status() is None
