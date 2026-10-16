# -*- coding: utf-8 -*-
"""actus/tests/test_desktop_import.py — `actus desktop` 的桌面依赖导入路径回归锁。

BUG-61：cli._cmd_desktop 曾写 `from desktop.app import start`。本模块迁移进
vools.actus 后（独立成包 + 引擎根按包位置推导两次改动）：
  - 根本没有 top-level `desktop` 包；
  - 即使有，`app` 也只是 FastAPI 实例、不是装着 start 的子模块。
所以该 import 恒抛 ModuleNotFoundError('desktop')，落进下面 except 后打印
"pip install fastapi uvicorn jinja2" 并 return 1——即使桌面依赖已装也起不来，
且把用户往错误的方向（装 fastapi）引。正确模块是 vools.actus.desktop（顶层 start）。

本锁不依赖真装 fastapi/uvicorn：用 stub 证明"桌面依赖在场时 import 路径能解析"，
用无 stub 证明"依赖缺席时报的是真实根因（fastapi）而非 stale 的 desktop"。
"""

import argparse
import io
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cli  # noqa: E402


_STUBS = ['fastapi', 'fastapi.responses', 'fastapi.staticfiles',
          'fastapi.templating', 'uvicorn', 'jinja2']


def _args():
    return argparse.Namespace(host='127.0.0.1', port=18765, no_browser=True)


def _purge_desktop():
    for k in [m for m in list(sys.modules) if m.endswith('actus.desktop')]:
        del sys.modules[k]


def test_desktop_start_importable_when_deps_present():
    """桌面依赖 stub 在场时，正确模块路径必须能解析出 start（证明 stale 路径已改对）。"""
    _purge_desktop()
    saved = {m: sys.modules.get(m) for m in _STUBS}
    try:
        for m in _STUBS:
            sys.modules[m] = mock.MagicMock()
        from vools.actus.desktop import start
        assert callable(start)
    finally:
        for m, v in saved.items():
            if v is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = v
        _purge_desktop()


def test_cmd_desktop_blames_fastapi_not_desktop(capsys):
    """fastapi 真缺席时，提示的 ImportError 根因必须是 fastapi，不能再是 'desktop'。"""
    pytest.importorskip('vools.actus')
    _purge_desktop()
    try:
        import fastapi  # noqa: F401
        pytest.skip('fastapi 已安装，无法在此环境复现缺席分支')
    except ImportError:
        pass
    rc = cli._cmd_desktop(_args())
    assert rc == 1
    out = capsys.readouterr().out
    assert 'No module named' in out
    assert 'desktop' not in out, '仍在把失败怪到 stale 的 desktop 包上（修复未生效）'


def test_cmd_desktop_success_path_reached(monkeypatch, capsys):
    """依赖 stub 齐备时 _cmd_desktop 走成功分支并 return 0（曾恒因 import 失败 return 1）。"""
    _purge_desktop()
    saved = {m: sys.modules.get(m) for m in _STUBS}
    try:
        for m in _STUBS:
            sys.modules[m] = mock.MagicMock()
        monkeypatch.setitem(sys.modules, 'uvicorn', mock.MagicMock())
        monkeypatch.setattr('vools.actus.desktop.start', lambda **kw: None, raising=False)
        rc = cli._cmd_desktop(_args())
        assert rc == 0, 'stub 齐备仍返回 1 —— 说明 import 路径还没修对'
    finally:
        for m, v in saved.items():
            if v is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = v
        _purge_desktop()
