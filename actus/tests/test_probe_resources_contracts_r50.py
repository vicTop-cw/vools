"""probe/resources.py 契约测试 — 系统资源探测。

覆盖目标：
- _get_cpu_info(): CPU 信息（有/无 psutil）
- _detect_cpu_count(): 无 psutil 时的 CPU 数检测
- _get_memory_info(): 内存信息
- _get_disk_info(): 磁盘信息
- get_resources_info(): 完整资源信息
- ResourcesProber.probe(): 探测器接口
"""
import sys

import pytest

from vools.actus.probe.resources import (
    _get_cpu_info,
    _detect_cpu_count,
    _get_memory_info,
    _get_disk_info,
    get_resources_info,
    ResourcesProber,
)
from vools.actus.probe.base import ProbeItem


class TestDetectCpuCount:
    """_detect_cpu_count() 测试。"""

    def test_returns_positive_int(self):
        """返回值应为正整数。"""
        result = _detect_cpu_count()
        assert isinstance(result, int)
        assert result >= 1


class TestGetCpuInfo:
    """_get_cpu_info() 测试。"""

    def test_returns_dict_with_platform(self):
        """应包含 platform 和 platform_release。"""
        info = _get_cpu_info()
        assert "platform" in info
        assert "platform_release" in info

    def test_has_cpu_count(self):
        """应包含 CPU 数量信息。"""
        info = _get_cpu_info()
        assert "count_logical" in info

    def test_with_psutil(self):
        """有 psutil 时应返回更详细的信息（如果平台支持）。"""
        try:
            import psutil  # noqa: F401
        except ImportError:
            pytest.skip("psutil not available")
        info = _get_cpu_info()
        assert "count_logical" in info
        # 某些平台 psutil 不支持 cpu_info()，但至少 count_logical 应存在
        assert info["count_logical"] >= 1


class TestGetMemoryInfo:
    """_get_memory_info() 测试。"""

    def test_returns_dict(self):
        """返回值应为 dict。"""
        result = _get_memory_info()
        assert isinstance(result, dict)

    def test_with_psutil(self):
        """有 psutil 时应返回 total/available/used_percent。"""
        try:
            import psutil  # noqa: F401
        except ImportError:
            pytest.skip("psutil not available")
        result = _get_memory_info()
        assert "total_mb" in result
        assert "available_mb" in result
        assert "used_percent" in result
        assert result["total_mb"] > 0

    def test_without_psutil(self, monkeypatch):
        """无 psutil 时应返回空 dict。"""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No psutil")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        result = _get_memory_info()
        assert result == {}


class TestGetDiskInfo:
    """_get_disk_info() 测试。"""

    def test_returns_list(self):
        """返回值应为列表。"""
        result = _get_disk_info()
        assert isinstance(result, list)

    def test_with_psutil(self):
        """有 psutil 时应返回磁盘分区信息。"""
        try:
            import psutil  # noqa: F401
        except ImportError:
            pytest.skip("psutil not available")
        result = _get_disk_info()
        assert len(result) >= 1
        part = result[0]
        assert "device" in part
        assert "mountpoint" in part
        assert "fstype" in part
        assert "total_mb" in part
        assert "free_mb" in part


class TestGetResourcesInfo:
    """get_resources_info() 测试。"""

    def test_returns_dict_with_required_keys(self):
        """应包含 cpu/memory/disk/network。"""
        info = get_resources_info()
        assert "cpu" in info
        assert "memory" in info
        assert "disk" in info
        assert "network" in info

    def test_cpu_info_present(self):
        """cpu 信息应包含 platform。"""
        info = get_resources_info()
        assert "platform" in info["cpu"]

    def test_network_info_is_dict(self):
        """network 信息应为 dict。"""
        info = get_resources_info()
        assert isinstance(info["network"], dict)


class TestResourcesProber:
    """ResourcesProber 测试。"""

    def test_probe_returns_list(self):
        """probe() 应返回列表。"""
        prober = ResourcesProber()
        result = prober.probe()
        assert isinstance(result, list)

    def test_probe_returns_probe_item(self):
        """probe() 应返回 ProbeItem。"""
        prober = ResourcesProber()
        result = prober.probe()
        assert len(result) >= 1
        assert isinstance(result[0], ProbeItem)

    def test_probe_item_properties(self):
        """probe() 返回的 ProbeItem 属性应正确。"""
        prober = ResourcesProber()
        result = prober.probe()
        item = result[0]
        assert item.name == "resources"
        assert item.category == "resources"
        assert item.available is True
        assert "cpu" in item.extra
        assert "memory" in item.extra
