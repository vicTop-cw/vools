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
    """获取 Windows 版本字符串（如 "11"）。

    旧实现调用的 `ctypes.windll.rtlGetVersion()` 在 Windows 上并不存在
    （必然抛 AttributeError 再掉进 except 回退成 platform.release()），这里去掉
    那次无效调用，直接用 platform 的版本源。
    """
    try:
        return platform.win32_ver()[0] or platform.release()
    except Exception:
        return platform.release()


def _get_windows_build() -> str:
    """获取 Windows build 版本串（如 "10.0.26200"），比 release 更精确。"""
    try:
        return platform.version()
    except Exception:
        return ""


def _get_linux_kernel() -> str:
    """获取 Linux 内核版本（如 "6.6.87.2-1"）。"""
    try:
        return os.uname().release
    except (AttributeError, OSError):
        return ""


def _is_wsl() -> bool:
    """是否跑在 WSL 里（Linux 侧平台判据：环境变量 + 内核版本含 microsoft）。"""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/sys/kernel/osrelease", "r", errors="replace") as handle:
            release = handle.read(128).lower()
    except OSError:
        return False
    return "microsoft" in release or "wsl" in release


def _get_macos_version() -> str:
    """获取 macOS 版本（如 "14.5"）。"""
    try:
        return platform.mac_ver()[0]
    except Exception:
        return ""


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
        info["windows_build"] = _get_windows_build()
        info["program_files"] = os.environ.get("ProgramFiles", "")
        info["program_files_x86"] = os.environ.get("ProgramFiles(x86)", "")
        info["local_app_data"] = os.environ.get("LOCALAPPDATA", "")
        info["app_data"] = os.environ.get("APPDATA", "")
        info["program_data"] = os.environ.get("ProgramData", "")

    if info["is_linux"]:
        info["linux_distro"] = _get_linux_distro()
        info["kernel_version"] = _get_linux_kernel()
        info["is_wsl"] = _is_wsl()

    if info["is_macos"]:
        info["sip_enabled"] = _get_sip_status()
        info["macos_version"] = _get_macos_version()

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
