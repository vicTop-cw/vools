# -*- coding: utf-8 -*-
"""测试 vools.sys.env_cmd — EnvCommands。"""

import os
import sys
import pytest

from vools.sys.env_cmd import EnvCommands

__all__ = ["TestEnvCommands", "TestNimBranch", "TestPythonBranch", "TestImport"]


class TestEnvCommands:
    """EnvCommands 行为测试。"""

    def test_path(self, capsys):
        EnvCommands().path()
        out = capsys.readouterr().out
        assert "PATH 环境变量" in out
        assert "共" in out

    def test_python(self, capsys):
        EnvCommands().python()
        out = capsys.readouterr().out
        assert "Python 环境信息" in out
        assert "版本" in out
        assert "可执行文件" in out
        assert "已安装的相关包" in out


class TestNimBranch:
    """nim 子命令分支覆盖。"""

    def test_nim_success(self, capsys, monkeypatch):
        # 模拟 nim 编译器返回 0
        fake_result = type("R", (), {"returncode": 0, "stdout": "Nim 2.0", "stderr": ""})()
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "Nim 环境信息" in out

    def test_nim_nonzero(self, capsys, monkeypatch):
        fake_result = type("R", (), {"returncode": 1, "stdout": "", "stderr": "err"})()
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "非零" in out

    def test_nim_not_found(self, capsys, monkeypatch):
        def _raise(*a, **kw):
            raise FileNotFoundError("nim not found")
        monkeypatch.setattr("subprocess.run", _raise)
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "未找到" in out

    def test_nim_lib_dir_with_dlls(self, capsys, monkeypatch, tmp_path):
        # 伪造一个 _LIB_DIR 目录，内有 .dll
        import vools.bridge.core.loader as loader_mod
        dll = tmp_path / "fake.dll"
        dll.write_bytes(b"x")
        monkeypatch.setattr(loader_mod, "_LIB_DIR", str(tmp_path))
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "找到" in out
        assert "fake.dll" in out

    def test_nim_lib_dir_empty(self, capsys, monkeypatch, tmp_path):
        import vools.bridge.core.loader as loader_mod
        monkeypatch.setattr(loader_mod, "_LIB_DIR", str(tmp_path))
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "目录为空" in out

    def test_nim_lib_dir_missing(self, capsys, monkeypatch):
        import vools.bridge.core.loader as loader_mod
        monkeypatch.setattr(loader_mod, "_LIB_DIR", "Z:/definitely/missing")
        EnvCommands().nim()
        out = capsys.readouterr().out
        assert "目录不存在" in out


class TestPythonBranch:
    """python 子命令分支覆盖。"""

    def test_python_site_ok(self, capsys):
        EnvCommands().python()
        out = capsys.readouterr().out
        assert "site-packages" in out

    def test_python_packages(self, capsys):
        EnvCommands().python()
        out = capsys.readouterr().out
        assert "ctypes" in out
        assert "subprocess" in out


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.env_cmd import __all__
        assert "EnvCommands" in __all__


class TestBug187Regression:
    """BUG-187 回归：可选子包 vools.bridge 缺席时 nim() 不得崩溃。"""

    def test_nim_without_bridge_graceful(self, capsys, monkeypatch):
        """模拟 vools.bridge 不可导入：nim() 应优雅提示而非抛异常。"""
        # 若 vools.bridge 已被导入缓存，builtins.__import__ 拦截会被绕过，
        # 因此直接把相关模块在 sys.modules 里置 None，from-import 即抛 ImportError。
        monkeypatch.setitem(sys.modules, "vools.bridge.core.loader", None)
        monkeypatch.setitem(sys.modules, "vools.bridge.core", None)
        monkeypatch.setitem(sys.modules, "vools.bridge", None)
        EnvCommands().nim()  # 修复前此处抛 ModuleNotFoundError
        out = capsys.readouterr().out
        assert "Nim 环境信息" in out
        assert "vools-bridges" in out
