"""probe/permissions.py 契约测试 — 权限探测。

覆盖目标：
- _check_windows_admin(): Windows 管理员检测
- _check_dir_permissions(): 目录权限检查
- _get_windows_startup_dir(): 开机自启目录
- get_permissions_info(): 完整权限信息
- PermissionsProber.probe(): 探测器接口
"""
import os
import sys

import pytest

from vools.actus.probe.permissions import (
    _check_windows_admin,
    _check_dir_permissions,
    _get_windows_startup_dir,
    get_permissions_info,
    PermissionsProber,
)
from vools.actus.probe.base import ProbeItem


class TestCheckWindowsAdmin:
    """_check_windows_admin() 测试。"""

    def test_returns_bool(self):
        """返回值应为 bool。"""
        result = _check_windows_admin()
        assert isinstance(result, bool)

    def test_non_windows_returns_false(self, monkeypatch):
        """非 Windows 平台返回 False。"""
        monkeypatch.setattr(sys, "platform", "linux")
        assert _check_windows_admin() is False


class TestCheckDirPermissions:
    """_check_dir_permissions() 测试。"""

    def test_existing_dir(self, tmp_path):
        """存在的目录应返回完整权限信息。"""
        info = _check_dir_permissions(str(tmp_path))
        assert info["exists"] is True
        assert info["path"] == str(tmp_path)
        assert "read" in info
        assert "write" in info
        assert "exec" in info

    def test_non_existing_dir(self, tmp_path):
        """不存在的目录应返回 exists=False。"""
        info = _check_dir_permissions(str(tmp_path / "nonexistent"))
        assert info["exists"] is False
        assert info["path"] == str(tmp_path / "nonexistent")


class TestGetWindowsStartupDir:
    """_get_windows_startup_dir() 测试。"""

    def test_with_appdata(self, monkeypatch):
        """有 APPDATA 环境变量时应返回完整路径。"""
        monkeypatch.setenv("APPDATA", "C:\\Fake\\AppData")
        result = _get_windows_startup_dir()
        assert result == "C:\\Fake\\AppData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"

    def test_without_appdata(self, monkeypatch):
        """无 APPDATA 环境变量时应返回空字符串。"""
        monkeypatch.delenv("APPDATA", raising=False)
        result = _get_windows_startup_dir()
        assert result == ""


class TestGetPermissionsInfo:
    """get_permissions_info() 测试。"""

    def test_returns_dict_with_required_keys(self):
        """返回值应包含所有必需键。"""
        info = get_permissions_info()
        assert "user" in info
        assert "is_admin" in info
        assert "is_elevated" in info
        assert "elevation_possible" in info
        assert "effective_permissions" in info
        assert "can_install_system_wide" in info
        assert "can_create_startups" in info

    def test_user_info_has_name(self):
        """用户信息应包含用户名。"""
        info = get_permissions_info()
        assert "name" in info["user"]

    def test_effective_permissions_has_all_dirs(self):
        """有效权限应包含 home/temp/system/program_files。"""
        info = get_permissions_info()
        ep = info["effective_permissions"]
        assert "home" in ep
        assert "temp" in ep
        assert "system" in ep
        assert "program_files" in ep

    def test_effective_permissions_dir_info(self):
        """目录权限信息应包含 exists/read/write/exec。"""
        info = get_permissions_info()
        ep = info["effective_permissions"]
        for key, dir_info in ep.items():
            assert "exists" in dir_info
            if dir_info["exists"]:
                assert "read" in dir_info
                assert "write" in dir_info
                assert "exec" in dir_info


class TestPermissionsProber:
    """PermissionsProber 测试。"""

    def test_probe_returns_list(self):
        """probe() 应返回列表。"""
        prober = PermissionsProber()
        result = prober.probe()
        assert isinstance(result, list)

    def test_probe_returns_probe_item(self):
        """probe() 应返回 ProbeItem。"""
        prober = PermissionsProber()
        result = prober.probe()
        assert len(result) >= 1
        assert isinstance(result[0], ProbeItem)

    def test_probe_item_properties(self):
        """probe() 返回的 ProbeItem 属性应正确。"""
        prober = PermissionsProber()
        result = prober.probe()
        item = result[0]
        assert item.name == "permissions"
        assert item.category == "permissions"
        assert item.available is True
        assert "user" in item.extra
