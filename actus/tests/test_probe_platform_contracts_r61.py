# -*- coding: utf-8 -*-
"""probe/platform.py 契约测试 (Round 55)。

只测公开契约，零产品代码改动。隔离：环境变量用 monkeypatch。
"""

import types

import pytest

from vools.actus.probe import platform as pmod
from vools.actus.probe.base import ProbeItem


# ---------------------------------------------------------------- helpers

def test_all_exports():
    assert set(pmod.__all__) == {"get_platform_info", "PlatformProber"}


# ---------------------------------------------------------------- windows

class TestWindowsVersion:
    def test_win32_ver_primary(self, monkeypatch):
        monkeypatch.setattr(pmod.platform, "win32_ver",
                            lambda: ("11", "10.0.26200", "SP0", "Multiprocessor"))
        assert pmod._get_windows_version() == "11"

    def test_win32_ver_empty_falls_to_release(self, monkeypatch):
        monkeypatch.setattr(pmod.platform, "win32_ver", lambda: ("", "", "", ""))
        monkeypatch.setattr(pmod.platform, "release", lambda: "10")
        assert pmod._get_windows_version() == "10"

    def test_win32_ver_raises_falls_to_release(self, monkeypatch):
        def boom():
            raise RuntimeError("x")
        monkeypatch.setattr(pmod.platform, "win32_ver", boom)
        monkeypatch.setattr(pmod.platform, "release", lambda: "7")
        assert pmod._get_windows_version() == "7"

    def test_build_is_platform_version(self, monkeypatch):
        monkeypatch.setattr(pmod.platform, "version", lambda: "10.0.26200")
        assert pmod._get_windows_build() == "10.0.26200"

    def test_build_exception_returns_empty(self, monkeypatch):
        def boom():
            raise RuntimeError("x")
        monkeypatch.setattr(pmod.platform, "version", boom)
        assert pmod._get_windows_build() == ""


# ---------------------------------------------------------------- linux

class TestLinuxKernel:
    def test_no_uname_attr(self, monkeypatch):
        # Windows 无 os.uname → AttributeError → ""
        monkeypatch.delattr(pmod.os, "uname", raising=False)
        assert pmod._get_linux_kernel() == ""

    def test_uname_oserror(self, monkeypatch):
        def boom():
            raise OSError("no")
        monkeypatch.setattr(pmod.os, "uname", boom, raising=False)
        assert pmod._get_linux_kernel() == ""

    def test_uname_ok(self, monkeypatch):
        fake = types.SimpleNamespace(release="6.6.87.2-1")
        monkeypatch.setattr(pmod.os, "uname", lambda: fake, raising=False)
        assert pmod._get_linux_kernel() == "6.6.87.2-1"


class TestIsWsl:
    def test_env_distro_name(self, monkeypatch):
        monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
        assert pmod._is_wsl() is True

    def test_env_interop(self, monkeypatch):
        monkeypatch.setenv("WSL_INTEROP", "/run/WSL")
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        assert pmod._is_wsl() is True

    def test_proc_file_microsoft(self, tmp_path, monkeypatch):
        import builtins
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.delenv("WSL_INTEROP", raising=False)
        fake = tmp_path / "osrelease"
        fake.write_text("5.15.90.1-microsoft-standard-WSL2\n", encoding="utf-8")
        real_open = builtins.open
        monkeypatch.setattr(
            builtins, "open",
            lambda p, *a, **k: real_open(fake, *a, **k) if str(p).endswith("osrelease")
            else real_open(p, *a, **k))
        assert pmod._is_wsl() is True

    def test_proc_file_wsl_keyword(self, tmp_path, monkeypatch):
        import builtins
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.delenv("WSL_INTEROP", raising=False)
        fake = tmp_path / "osrelease"
        fake.write_text("4.19-wsl-kernel\n", encoding="utf-8")
        real_open = builtins.open
        monkeypatch.setattr(
            builtins, "open",
            lambda p, *a, **k: real_open(fake, *a, **k) if str(p).endswith("osrelease")
            else real_open(p, *a, **k))
        assert pmod._is_wsl() is True

    def test_proc_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.delenv("WSL_INTEROP", raising=False)
        # 真实 /proc 在 Windows 上不存在 → OSError → False
        assert pmod._is_wsl() is False

    def test_proc_file_normal_kernel(self, tmp_path, monkeypatch):
        import builtins
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        monkeypatch.delenv("WSL_INTEROP", raising=False)
        fake = tmp_path / "osrelease"
        fake.write_text("6.1.0-18-amd64\n", encoding="utf-8")
        real_open = builtins.open
        monkeypatch.setattr(
            builtins, "open",
            lambda p, *a, **k: real_open(fake, *a, **k) if str(p).endswith("osrelease")
            else real_open(p, *a, **k))
        assert pmod._is_wsl() is False


class TestLinuxDistro:
    def test_distro_module_present(self):
        # distro 库若已安装则走第一分支；返回四个键
        d = pmod._get_linux_distro()
        assert set(d) == {"id", "name", "version", "like"}

    def test_distro_missing_fallback_osrelease(self, tmp_path, monkeypatch):
        # 屏蔽 distro 导入 → 读 /etc/os-release 替身
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "distro":
                raise ImportError("no distro")
            return real_import(name, *a, **k)

        fake_file = tmp_path / "os-release"
        fake_file.write_text(
            '# comment line\nID="ubuntu"\nNAME=Debian\nVERSION_ID="22.04"\n'
            'ID_LIKE="debian"\nNOEQ_LINE\n', encoding="utf-8")
        monkeypatch.setattr(builtins, "__import__", fake_import)
        real_open = builtins.open
        monkeypatch.setattr(
            builtins, "open",
            lambda p, *a, **k: real_open(fake_file, *a, **k)
            if str(p).endswith("os-release") else real_open(p, *a, **k))
        d = pmod._get_linux_distro()
        assert d == {"ID": "ubuntu", "NAME": "Debian",
                     "VERSION_ID": "22.04", "ID_LIKE": "debian"}

    def test_distro_missing_and_no_osrelease(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "distro":
                raise ImportError("no distro")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # Windows 上 /etc/os-release 不存在 → Exception → unknown
        assert pmod._get_linux_distro() == {"id": "unknown"}


# ---------------------------------------------------------------- macos

class TestMacos:
    def test_mac_ver_ok(self, monkeypatch):
        monkeypatch.setattr(pmod.platform, "mac_ver", lambda: ("14.5", "", ""))
        assert pmod._get_macos_version() == "14.5"

    def test_mac_ver_raises(self, monkeypatch):
        def boom():
            raise RuntimeError("x")
        monkeypatch.setattr(pmod.platform, "mac_ver", boom)
        assert pmod._get_macos_version() == ""

    def test_sip_csrutil_missing_returns_none(self, monkeypatch):
        # Windows 上 csrutil 不存在 → subprocess 异常 → None
        assert pmod._get_sip_status() is None

    def test_sip_enabled(self, monkeypatch):
        import subprocess as sp
        monkeypatch.setattr(sp, "run", lambda *a, **k:
                            types.SimpleNamespace(stdout="status: enabled."))
        assert pmod._get_sip_status() is True

    def test_sip_disabled(self, monkeypatch):
        import subprocess as sp
        monkeypatch.setattr(sp, "run", lambda *a, **k:
                            types.SimpleNamespace(stdout="status: disabled"))
        assert pmod._get_sip_status() is False


# ---------------------------------------------------------------- aggregate

class TestGetPlatformInfo:
    def test_windows_branch_keys(self, monkeypatch):
        monkeypatch.setenv("ProgramFiles", "C:/Program Files")
        monkeypatch.setenv("LOCALAPPDATA", "C:/Users/x/AppData/Local")
        info = pmod.get_platform_info()
        assert info["is_windows"] is True
        assert info["is_linux"] is False and info["is_macos"] is False
        assert info["windows_version"] == pmod._get_windows_version()
        assert info["windows_build"] == pmod._get_windows_build()
        assert info["program_files"] == "C:/Program Files"
        assert info["program_files_x86"] == pmod.os.environ.get("ProgramFiles(x86)", "")
        assert info["local_app_data"] == "C:/Users/x/AppData/Local"
        assert info["app_data"] == pmod.os.environ.get("APPDATA", "")
        assert info["program_data"] == pmod.os.environ.get("ProgramData", "")
        assert isinstance(info["path_dirs"], list)

    def test_linux_branch_via_sys_stub(self, monkeypatch):
        # 用 sys 命名空间替身驱动 linux 分支（模块以 `sys.platform` 读取）
        stub = types.SimpleNamespace(platform="linux", executable="py3")
        monkeypatch.setattr(pmod, "sys", stub)
        monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
        info = pmod.get_platform_info()
        assert info["is_windows"] is False and info["is_linux"] is True
        assert "linux_distro" in info
        assert "kernel_version" in info
        assert info["is_wsl"] is False
        # windows 键不应存在
        assert "windows_version" not in info

    def test_macos_branch_via_sys_stub(self, monkeypatch):
        stub = types.SimpleNamespace(platform="darwin", executable="py3")
        monkeypatch.setattr(pmod, "sys", stub)
        info = pmod.get_platform_info()
        assert info["is_macos"] is True
        assert "sip_enabled" in info
        assert "macos_version" in info
        assert "windows_version" not in info and "linux_distro" not in info

    def test_base_fields(self):
        info = pmod.get_platform_info()
        assert info["os"] == pmod.platform.system()
        assert info["os_release"] == pmod.platform.release()
        assert info["arch"] == pmod.platform.machine()
        assert info["python_executable"] == pmod.sys.executable
        assert info["platform_tag"] == pmod.sys.platform


# ---------------------------------------------------------------- prober

class TestPlatformProber:
    def test_probe_returns_single_item(self):
        items = pmod.PlatformProber().probe()
        assert len(items) == 1
        it = items[0]
        assert isinstance(it, ProbeItem)
        assert it.name == "platform"
        assert it.category == "platform"
        assert it.available is True
        assert it.extra["os"] == pmod.platform.system()

    def test_prober_is_prober_subclass(self):
        # identity-proof：经 pmod 的 MRO 验证基类，而不是在测试体里重新 import
        # Prober（bootstrap 重建后旧类与测试时 import 的新 Prober 身份不同，
        # issubclass 假阴性——与 panel/cost 跨文件族同根因）。
        assert issubclass(pmod.PlatformProber, pmod.Prober)
