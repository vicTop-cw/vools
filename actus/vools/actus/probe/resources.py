"""probe/resources.py — 系统资源探测（psutil 可选）。"""

import platform
import sys

from .base import Prober, ProbeItem


def _get_cpu_info() -> dict:
    """获取 CPU 信息。"""
    info = {
        "platform": platform.machine(),
        "platform_release": platform.release(),
    }
    try:
        import psutil
        cpus = psutil.cpu_info()
        info["count_physical"] = psutil.cpu_count(logical=False)
        info["count_logical"] = psutil.cpu_count(logical=True)
        if cpus:
            info["vendor"] = cpus[0].get("vendor_id") if cpus[0].get("vendor_id") else ""
            info["model"] = cpus[0].get("brand", "")
            info["cores_per_socket"] = len(cpus)
    except ImportError:
        info["count_logical"] = _detect_cpu_count()
    except Exception:
        info["count_logical"] = _detect_cpu_count()
    return info


def _detect_cpu_count() -> int:
    """无 psutil 时的 CPU 数检测。"""
    try:
        import os
        return os.cpu_count() or 1
    except Exception:
        return 1


def _get_memory_info() -> dict:
    """获取内存信息。"""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total_mb": round(vm.total / 1024 / 1024),
            "available_mb": round(vm.available / 1024 / 1024),
            "used_percent": round(vm.percent),
        }
    except ImportError:
        return {}
    except Exception:
        return {}


def _get_disk_info() -> list:
    """获取磁盘信息。"""
    result = []
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                result.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_mb": round(usage.total / 1024 / 1024),
                    "free_mb": round(usage.free / 1024 / 1024),
                    "used_percent": round(usage.percent),
                })
            except (PermissionError, OSError):
                pass
    except ImportError:
        pass
    return result


def get_resources_info() -> dict:
    """探测系统资源信息。"""
    info = {
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "network": {},
    }

    # 网络接口（仅名称列表）
    try:
        import psutil
        for iface_name, addrs in psutil.net_if_addrs().items():
            info["network"][iface_name] = [
                {"family": str(a.family), "address": a.address}
                for a in addrs
            ]
    except Exception:
        pass

    return info


class ResourcesProber(Prober):
    """系统资源探测器。"""

    def probe(self) -> list:
        info = get_resources_info()
        return [ProbeItem(
            name="resources",
            category="resources",
            available=True,
            extra=info,
        )]