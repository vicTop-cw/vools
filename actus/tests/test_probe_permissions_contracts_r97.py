# -*- coding: utf-8 -*-
"""probe/permissions.py 契约测试 r97 — 补齐 r50 未覆盖分支。

覆盖目标（基线 71%，missed 20-21, 60, 70-77, 89-94）：
- _check_windows_admin: ctypes 异常分支（20-21）
- get_permissions_info: pwd 导入失败回退（60）、grp 补充组（70-77）、
  Unix euid==0 / 非 root 分支（89-94）
- 隔离红线：全部走 tmp / monkeypatch，不真跑需要提权的探测；
  patch 一律对象寻址（绑定文件级 import 的模块对象），禁字符串寻址。

每条断言都能真失败；变异验证见文末注释。
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

import vools.actus.probe.permissions as perms  # noqa: E402
from vools.actus.probe.permissions import (  # noqa: E402
    _check_windows_admin,
    _get_windows_startup_dir,
    get_permissions_info,
    PermissionsProber,
)


# ---------------------------------------------------------------------------
# _check_windows_admin — ctypes 异常分支
# ---------------------------------------------------------------------------

def test_check_windows_admin_ctypes_failure_returns_false(monkeypatch):
    """IsUserAnAdmin 抛异常（如 AttributeError/AccessError）→ False。

    变异验证：把 20-21 的 except 分支删掉（让异常抛穿）→ 本用例红。
    """
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "ctypes":
            raise ImportError("stub: no ctypes")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(sys, "platform", "win32")
    assert _check_windows_admin() is False


def test_check_windows_admin_real_windows_true(monkeypatch):
    """ctypes.windll.shell32.IsUserAnAdmin() 返回非零 → True（真打 19 行返回值）。"""
    fake_ctypes = types.ModuleType("ctypes")
    fake_ctypes.windll = types.SimpleNamespace(
        shell32=types.SimpleNamespace(IsUserAnAdmin=lambda: 1))
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") \
        else __builtins__["__import__"]

    def fake_import(name, *a, **kw):
        if name == "ctypes":
            return fake_ctypes
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", fake_import, raising=False)
    import builtins as b
    monkeypatch.setattr(b, "__import__", fake_import)
    monkeypatch.setattr(sys, "platform", "win32")
    assert _check_windows_admin() is True


# ---------------------------------------------------------------------------
# _get_windows_startup_dir — 已在 r50 覆盖，此处只补 can_create_startups 联动
# ---------------------------------------------------------------------------

def test_windows_path_startup_dir_writable(monkeypatch, tmp_path):
    """win32 分支：startup 目录可写 → can_create_startups=True 即便非 admin。"""
    startup = tmp_path / "startup"
    startup.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(perms.os.path, "join",
                        lambda *parts: os.path.join(*parts), raising=False)
    # startup 目录推导走 APPDATA；把 startup 目录指到 tmp 下可写位置
    monkeypatch.setattr(perms, "_get_windows_startup_dir", lambda: str(startup))
    monkeypatch.setattr(sys, "platform", "win32")
    # 打桩 windows admin 检测：非管理员
    monkeypatch.setattr(perms, "_check_windows_admin", lambda: False)

    info = get_permissions_info()
    assert info["can_create_startups"] is True, \
        "startup 目录可写且非 admin 时仍应可创建开机自启"
    assert info["is_admin"] is False
    assert info["is_elevated"] is False
    assert info["can_install_system_wide"] is False


# ---------------------------------------------------------------------------
# get_permissions_info — 用户名回退 / 补充组 / Unix 分支
# ---------------------------------------------------------------------------

def test_user_name_fallback_without_pwd(monkeypatch):
    """pwd 导入失败 → 用 USERNAME/USER 环境变量回退（覆盖 60-62 except 分支）。

    只桩 import 边界（pwd/grp 假装缺失），平台走本机真实分支 ——
    用户名回退这条契约与平台无关。
    """
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name in ("pwd", "grp"):
            raise ImportError("stub: unix only")
        return real_import(name, *a, **kw)

    monkeypatch.setenv("USERNAME", "fallback-user")
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    info = get_permissions_info()
    assert info["user"]["name"] == "fallback-user", \
        "pwd 不可用时应回退到 USERNAME 环境变量"


def test_unix_branch_root(monkeypatch):
    """posix 分支 euid==0 → is_admin/is_elevated/can_install/can_create 全 True（覆盖 89-97）。

    Windows 上 os.geteuid/getegid/getgroups 原本不存在 —— monkeypatch.setattr
    的 raising=False 恰好会把它们造出来，posix 分支由此在 win32 上也可执行。
    """

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "getegid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "getgroups", lambda: [], raising=False)

    info = get_permissions_info()
    assert info["is_admin"] is True
    assert info["is_elevated"] is True
    assert info["elevation_possible"] is True
    assert info["can_install_system_wide"] is True
    assert info["can_create_startups"] is True


def test_unix_branch_non_root_groups(monkeypatch):
    """posix 分支 euid!=0 + 补充组解析：grp 命中与异常吞掉都要走到（覆盖 70-77, 89-94）。

    Windows 上 os.geteuid/getegid/getgroups 原本不存在 —— raising=False 造出来。
    """

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(os, "getegid", lambda: 1000, raising=False)

    # grp 模块：getgrgid 命中第一个 gid、第二个 gid 抛 KeyError（两条路径都覆盖）
    fake_grp = types.ModuleType("grp")
    calls = []
    def getgrgid(gid):
        calls.append(gid)
        if gid == 999:
            raise KeyError(gid)
        return types.SimpleNamespace(gr_name="grp-%d" % gid)
    fake_grp.getgrgid = getgrgid
    monkeypatch.setattr(os, "getgroups", lambda: [20, 999], raising=False)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "grp":
            return fake_grp
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    info = get_permissions_info()
    assert calls == [20, 999], "补充组循环必须对每个 gid 都调 getgrgid"
    assert info["user"]["groups"] == ["grp-20"], \
        "命中的 gid 出名字、抛异常的 gid 被跳过"
    assert info["is_admin"] is False
    assert info["is_elevated"] is False
    assert info["elevation_possible"] in (True, False)  # 取决于 /etc/sudoers 可读性
    assert info["can_install_system_wide"] == info["elevation_possible"]
    assert isinstance(info["can_create_startups"], bool)


def test_unix_branch_pwd_user_name(monkeypatch):
    """pwd 命中时用户名来自 getpwuid（覆盖 58-60 正常路径）。

    Windows 上 os.geteuid/getegid/getgroups 原本不存在 —— raising=False 造出来。
    """

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(os, "getegid", lambda: 1000, raising=False)
    monkeypatch.setattr(os, "getgroups", lambda: [], raising=False)

    fake_pwd = types.ModuleType("pwd")
    fake_pwd.getpwuid = lambda uid: types.SimpleNamespace(pw_name="pwd-user")

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "pwd":
            return fake_pwd
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    info = get_permissions_info()
    assert info["user"]["name"] == "pwd-user"


# ---------------------------------------------------------------------------
# effective_permissions — TEMP/SYSTEMROOT/ProgramFiles 环境变量注入
# ---------------------------------------------------------------------------

def test_effective_permissions_env_dirs(monkeypatch, tmp_path):
    """TEMP/ProgramFiles 环境变量生效且目录状态如实（覆盖 100-109 的变量读取）。"""
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "sys"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))

    info = get_permissions_info()
    ep = info["effective_permissions"]
    assert os.path.normcase(ep["temp"]["path"]) == os.path.normcase(str(temp_dir))
    assert ep["temp"]["exists"] is True
    assert ep["temp"]["write"] is True
    assert ep["program_files"]["exists"] is False  # 没建这个目录
    assert set(ep) == {"home", "temp", "system", "program_files"}


# ---------------------------------------------------------------------------
# Prober 接口
# ---------------------------------------------------------------------------

def test_prober_returns_item_with_extra(monkeypatch, tmp_path):
    """PermissionsProber.probe() 返回的 ProbeItem.extra 即 get_permissions_info() 结果。"""
    monkeypatch.setenv("TEMP", str(tmp_path))
    prober = PermissionsProber()
    items = prober.probe()
    assert len(items) == 1
    item = items[0]
    assert item.name == "permissions"
    assert item.category == "permissions"
    assert item.available is True
    assert "user" in item.extra and "effective_permissions" in item.extra


# ---------------------------------------------------------------------------
# 变异验证记录（人工执行后还原，不留在测试运行里）
# ---------------------------------------------------------------------------
# MV-1: 删掉 permissions.py:20-21 的 `except Exception: return False` →
#       test_check_windows_admin_ctypes_failure_returns_false 红（异常抛穿）。
# MV-2: 把 permissions.py:84 `info["can_create_startups"] = info["is_admin"] or (...)`
#       改成 `= info["is_admin"]`（去掉 startup 目录可写那条腿）→
#       test_windows_path_startup_dir_writable 红。
