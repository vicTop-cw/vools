"""probe/permissions.py — 权限与身份探测。"""


__all__ = [
    "get_permissions_info",
    "PermissionsProber",
]

import os
import sys

from .base import Prober, ProbeItem


def _check_windows_admin() -> bool:
    """Windows 管理员检测（ctypes，零依赖）。"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _check_dir_permissions(path: str) -> dict:
    """检查目录的读写执行权限。"""
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    return {
        "path": path,
        "exists": True,
        "read": os.access(path, os.R_OK),
        "write": os.access(path, os.W_OK),
        "exec": os.access(path, os.X_OK),
    }


def _get_windows_startup_dir() -> str:
    """Windows 开机自启目录。"""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    return ""


def get_permissions_info() -> dict:
    """探测当前用户的权限信息。"""
    info = {
        "user": {},
        "is_admin": False,
        "is_elevated": False,
        "elevation_possible": False,
        "effective_permissions": {},
        "can_install_system_wide": False,
        "can_create_startups": False,
    }

    # ── 用户身份 ──
    try:
        import pwd
        user_name = pwd.getpwuid(os.geteuid()).pw_name
    except (ImportError, KeyError):
        user_name = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))

    info["user"]["name"] = user_name
    info["user"]["uid"] = os.geteuid() if hasattr(os, "geteuid") else None
    info["user"]["gid"] = os.getegid() if hasattr(os, "getegid") else None

    # ── 补充组（Unix only） ──
    if hasattr(os, "getgroups"):
        group_names = []
        for gid in os.getgroups():
            try:
                import grp
                group_names.append(grp.getgrgid(gid).gr_name)
            except Exception:
                pass
        info["user"]["groups"] = group_names

    # ── 管理员/root 检测 ──
    if sys.platform == "win32":
        info["is_admin"] = _check_windows_admin()
        info["is_elevated"] = info["is_admin"]
        info["can_install_system_wide"] = info["is_admin"]
        info["can_create_startups"] = info["is_admin"] or (
            bool(_get_windows_startup_dir()) and
            os.access(_get_windows_startup_dir(), os.W_OK)
        )
    else:
        euid = os.geteuid()
        info["is_admin"] = (euid == 0)
        info["is_elevated"] = (euid == 0)
        info["elevation_possible"] = os.access("/etc/sudoers", os.R_OK) or (euid == 0)
        info["can_install_system_wide"] = (euid == 0) or info["elevation_possible"]
        info["can_create_startups"] = (
            os.access(os.path.expanduser("~/.config/autostart"), os.W_OK) or
            (euid == 0)
        )

    # ── 关键目录权限 ──
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    system_dir = os.environ.get("SYSTEMROOT", "C:\\Windows") if sys.platform == "win32" else "/usr"
    pf_dir = os.environ.get("ProgramFiles", "C:\\Program Files") if sys.platform == "win32" else "/usr/local"

    info["effective_permissions"] = {
        "home": _check_dir_permissions(os.path.expanduser("~")),
        "temp": _check_dir_permissions(temp_dir),
        "system": _check_dir_permissions(system_dir),
        "program_files": _check_dir_permissions(pf_dir),
    }

    return info


class PermissionsProber(Prober):
    """权限探测器。"""

    def probe(self) -> list:
        info = get_permissions_info()
        return [ProbeItem(
            name="permissions",
            category="permissions",
            available=True,
            extra=info,
        )]
