"""probe/platform.py — 平台信息采集。"""


__all__ = [
    "get_platform_info",
    "PlatformProber",
]

import os
import platform
import sys

from .base import Prober, ProbeItem


def _get_windows_version() -> str:
    """获取 Windows 版本字符串。"""
    try:
        import ctypes
        result = ctypes.windll.rtlGetVersion()
        return f"{platform.release()}"
    except Exception:
        return platform.release()


def _get_linux_distro() -> dict:
    """获取 Linux 发行版信息。"""
    try:
        import distro
        return {
            "id": distro.id(),
            "name": distro.name(),
            "version": distro.version(),
            "like": " ".join(distro.like()),
        }
    except ImportError:
        # 回退：读 /etc/os-release
        try:
            info = {}
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip('"')
            return info
        except Exception:
            return {"id": "unknown"}


def _get_sip_status() -> bool:
    """macOS SIP 状态检测。"""
    try:
        import subprocess
        r = subprocess.run(["csrutil", "status"], capture_output=True, text=True, errors='replace', timeout=5)
        return "enabled" in r.stdout.lower()
    except Exception:
        return None


def get_platform_info() -> dict:
    """采集平台信息，返回 dict。"""
    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform_tag": sys.platform,
        "is_windows": sys.platform == "win32",
        "is_linux": sys.platform == "linux",
        "is_macos": sys.platform == "darwin",
        "path_dirs": os.environ.get("PATH", "").split(os.pathsep),
    }

    if info["is_windows"]:
        info["windows_version"] = _get_windows_version()
        info["program_files"] = os.environ.get("ProgramFiles", "")
        info["program_files_x86"] = os.environ.get("ProgramFiles(x86)", "")
        info["local_app_data"] = os.environ.get("LOCALAPPDATA", "")
        info["app_data"] = os.environ.get("APPDATA", "")
        info["program_data"] = os.environ.get("ProgramData", "")

    if info["is_linux"]:
        info["linux_distro"] = _get_linux_distro()

    if info["is_macos"]:
        info["sip_enabled"] = _get_sip_status()

    return info


class PlatformProber(Prober):
    """平台信息探测器。"""

    def probe(self) -> list:
        info = get_platform_info()
        return [ProbeItem(
            name="platform",
            category="platform",
            available=True,
            extra=info,
        )]
