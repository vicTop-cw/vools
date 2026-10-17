# -*- coding: utf-8 -*-
"""测试 vools.sys.env。"""

import pytest
import vools.sys.env as env

__all__ = ["TestGetEnv", "TestGetEnvWithDefault", "TestBridges",
           "TestPlatformFlags", "TestFallback", "TestImport"]


class TestGetEnv:
    """get_env 测试。"""

    def test_os_environ(self, monkeypatch):
        monkeypatch.setenv("V_TEST_MY_VAR", "hello")
        assert env.get_env("V_TEST_MY_VAR") == "hello"

    def test_missing(self):
        assert env.get_env("V_NO_SUCH_VAR_XYZ") is None


class TestGetEnvWithDefault:
    """get_env_with_default 测试。"""

    def test_found(self, monkeypatch):
        monkeypatch.setenv("V_TEST_MY_VAR2", "hello")
        assert env.get_env_with_default("V_TEST_MY_VAR2", "def") == "hello"

    def test_not_found(self):
        assert env.get_env_with_default("V_NO_SUCH_VAR_XYZ", "def") == "def"


class TestBridges:
    """桥接加载测试。"""

    def test_powershell_bridge_none(self, monkeypatch):
        import sys as _sys
        # 强制 ImportError
        monkeypatch.setitem(_sys.modules, "vools.bridge.powershell", None)
        env._powershell_bridge = None
        assert env._get_powershell_bridge() is None

    def test_shell_bridge_none(self, monkeypatch):
        import sys as _sys
        monkeypatch.setitem(_sys.modules, "vools.bridge.shell", None)
        env._shell_bridge = None
        assert env._get_shell_bridge() is None

    def test_get_env_powershell_no_bridge(self, monkeypatch):
        env._powershell_bridge = None
        monkeypatch.setattr(env, "_get_powershell_bridge", lambda: None)
        assert env._get_env_powershell("PATH") is None

    def test_get_env_shell_no_bridge(self, monkeypatch):
        env._shell_bridge = None
        monkeypatch.setattr(env, "_get_shell_bridge", lambda: None)
        assert env._get_env_shell("PATH") is None

    def test_get_env_powershell_bridge_result(self, monkeypatch):
        class FakeBridge:
            def compile_and_run(self, **kw):
                return "PS_VALUE"
        monkeypatch.setattr(env, "_get_powershell_bridge", lambda: FakeBridge())
        assert env._get_env_powershell("PATH") == "PS_VALUE"

    def test_get_env_shell_bridge_result(self, monkeypatch):
        class FakeBridge:
            def compile_and_run(self, **kw):
                return "SH_VALUE"
        monkeypatch.setattr(env, "_get_shell_bridge", lambda: FakeBridge())
        assert env._get_env_shell("PATH") == "SH_VALUE"


class TestPlatformFlags:
    """平台标志测试。"""

    def test_flags_are_bool(self):
        assert isinstance(env._IS_WINDOWS, bool)
        assert isinstance(env._IS_LINUX, bool)
        assert isinstance(env._IS_MACOS, bool)


class TestFallback:
    """fallback 测试。"""

    def test_fallback(self, monkeypatch):
        monkeypatch.setenv("V_TEST_FB", "val")
        assert env._get_env_fallback("V_TEST_FB") == "val"

    def test_fallback_none(self):
        assert env._get_env_fallback("V_NO_SUCH") is None


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        assert "get_env" in env.__all__
        assert "get_env_with_default" in env.__all__
