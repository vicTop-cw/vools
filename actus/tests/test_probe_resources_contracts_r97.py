# -*- coding: utf-8 -*-
"""probe/resources.py 契约测试 r97 — 补齐 r50 未覆盖分支。

覆盖目标（基线 72%，missed 24-29, 31, 42-43, 58-59, 78-81, 102-103）：
- _get_cpu_info: psutil 命中路径（24-29）、异常回退（32-33）
- _detect_cpu_count: os.cpu_count 异常回退（42-43）
- _get_memory_info: psutil 异常回退（58-59）
- _get_disk_info: disk_usage PermissionError 跳过（78-79）、ImportError 空表（80-81）
- get_resources_info 网络分支: psutil 异常吞掉（102-103）
- 隔离红线：psutil 用假模块注入（sys.modules / builtins.__import__ 桩），
  不真跑重探测器；patch 一律对象寻址。

每条断言都能真失败；变异验证见文末注释。
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

import vools.actus.probe.resources as res  # noqa: E402
from vools.actus.probe.resources import (  # noqa: E402
    _detect_cpu_count,
    _get_cpu_info,
    _get_disk_info,
    _get_memory_info,
    get_resources_info,
    ResourcesProber,
)


def _install_fake_psutil(monkeypatch, **funcs):
    """把假 psutil 同时注入两个边界：

    1. import 边界：`import psutil` 拿到假模块（覆盖 ImportError 腿的对手面）；
    2. sys.modules 边界：解释器已缓存真 psutil 时，函数内 `import psutil`
       直接命中 sys.modules —— 必须一并置换才桩得住（对象寻址，可还原）。
    """
    fake = types.ModuleType("psutil")
    # 安全默认：get_resources_info 一次调用会依次碰 cpu/memory/disk/network 四个
    # 探测函数，只注入单一属性时其余路径会 AttributeError 抛穿 —— 补齐全接口。
    def _boom():
        raise RuntimeError("stub psutil failure")
    fake.cpu_info = []
    fake.cpu_count = lambda logical=True: 1
    fake.virtual_memory = _boom   # 走 except Exception → {}
    fake.disk_partitions = lambda all=False: []
    fake.disk_usage = lambda path: None
    fake.net_if_addrs = lambda: {}
    for name, fn in funcs.items():
        setattr(fake, name, fn)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            return fake
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setitem(sys.modules, "psutil", fake)
    return fake


# ---------------------------------------------------------------------------
# _get_cpu_info
# ---------------------------------------------------------------------------

def test_cpu_info_with_psutil_full(monkeypatch):
    """psutil.cpu_info 命中 → vendor/model/cores_per_socket 来自 psutil（覆盖 22-29）。"""
    cpu_rows = [{"vendor_id": "GenuineIntel", "brand": "Stub CPU 9000"}]
    _install_fake_psutil(
        monkeypatch,
        cpu_info=lambda: cpu_rows,
        cpu_count=lambda logical=True: 4 if logical else 2,
    )
    info = _get_cpu_info()
    assert info["count_physical"] == 2
    assert info["count_logical"] == 4
    assert info["vendor"] == "GenuineIntel"
    assert info["model"] == "Stub CPU 9000"
    assert info["cores_per_socket"] == 1
    assert "platform" in info and "platform_release" in info


def test_cpu_info_psutil_empty_cpu_rows(monkeypatch):
    """psutil.cpu_info() 返回空列表 → vendor/model 键不被写入，计数仍在（覆盖 26 if 边界）。"""
    _install_fake_psutil(
        monkeypatch,
        cpu_info=lambda: [],
        cpu_count=lambda logical=True: 8 if logical else 4,
    )
    info = _get_cpu_info()
    assert "vendor" not in info
    assert "model" not in info
    assert info["count_logical"] == 8
    assert info["count_physical"] == 4


def test_cpu_info_psutil_empty_vendor_string(monkeypatch):
    """vendor_id 为空串 → vendor 落空串（覆盖 27 行三元 False 腿）。"""
    _install_fake_psutil(
        monkeypatch,
        cpu_info=lambda: [{"vendor_id": "", "brand": "B"}],
        cpu_count=lambda logical=True: 1,
    )
    info = _get_cpu_info()
    assert info["vendor"] == ""
    assert info["model"] == "B"


def test_cpu_info_psutil_raises_falls_back(monkeypatch):
    """psutil 在场但 cpu_info 抛异常 → 回退 _detect_cpu_count（覆盖 32-33 except Exception）。"""
    def boom(*a, **kw):
        raise RuntimeError("stub psutil failure")

    _install_fake_psutil(
        monkeypatch,
        cpu_info=boom,
        cpu_count=boom,
    )
    info = _get_cpu_info()
    assert info["count_logical"] == os.cpu_count() or info["count_logical"] == 1
    assert "count_physical" not in info


def test_cpu_info_no_psutil(monkeypatch):
    """psutil 缺失 → ImportError 腿回退 _detect_cpu_count（覆盖 30-31）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("stub: no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    info = _get_cpu_info()
    assert info["count_logical"] >= 1
    assert "count_physical" not in info


def test_detect_cpu_count_exception_returns_one(monkeypatch):
    """os.cpu_count 本身炸 → 返回 1（覆盖 42-43）。"""
    def boom():
        raise RuntimeError("stub cpu_count failure")

    # _detect_cpu_count 内部 `import os` → 就是全局 os 模块对象，对象寻址打桩
    monkeypatch.setattr(os, "cpu_count", boom)
    assert _detect_cpu_count() == 1


# ---------------------------------------------------------------------------
# _get_memory_info
# ---------------------------------------------------------------------------

def test_memory_info_with_psutil(monkeypatch):
    """psutil.virtual_memory 命中 → total/available/used_percent（覆盖 50-55）。"""
    class VM(object):
        total = 16 * 1024 * 1024 * 1024  # 16 GB
        available = 8 * 1024 * 1024 * 1024
        percent = 50.0

    _install_fake_psutil(monkeypatch, virtual_memory=lambda: VM())
    info = _get_memory_info()
    assert info == {"total_mb": 16384, "available_mb": 8192, "used_percent": 50}


def test_memory_info_psutil_raises(monkeypatch):
    """psutil 在场但 virtual_memory 抛异常 → 空 dict（覆盖 58-59）。"""
    def boom():
        raise RuntimeError("stub memory failure")

    _install_fake_psutil(monkeypatch, virtual_memory=boom)
    assert _get_memory_info() == {}


# ---------------------------------------------------------------------------
# _get_disk_info
# ---------------------------------------------------------------------------

class _Part(object):
    def __init__(self, device, mountpoint, fstype):
        self.device = device
        self.mountpoint = mountpoint
        self.fstype = fstype


class _Usage(object):
    def __init__(self):
        self.total = 100 * 1024 * 1024 * 1024
        self.free = 40 * 1024 * 1024 * 1024
        self.percent = 60.0


def test_disk_info_with_psutil(monkeypatch):
    """psutil.disk_partitions + disk_usage 命中 → 逐分区完整字段（覆盖 67-77）。"""
    parts = [_Part("C:\\", "C:\\", "NTFS")]
    _install_fake_psutil(
        monkeypatch,
        disk_partitions=lambda all=False: parts,
        disk_usage=lambda mp: _Usage(),
    )
    result = _get_disk_info()
    assert len(result) == 1
    d = result[0]
    assert d["device"] == "C:\\"
    assert d["mountpoint"] == "C:\\"
    assert d["fstype"] == "NTFS"
    assert d["total_mb"] == 102400
    assert d["free_mb"] == 40960
    assert d["used_percent"] == 60


def test_disk_info_permission_error_skipped(monkeypatch):
    """disk_usage 抛 PermissionError → 该分区跳过、其它照常（覆盖 78-79）。"""
    parts = [_Part("C:\\", "C:\\", "NTFS"), _Part("D:\\", "D:\\", "NTFS")]
    calls = []

    def fake_usage(mp):
        calls.append(mp)
        if mp == "C:\\":
            raise PermissionError("stub: locked")
        return _Usage()

    _install_fake_psutil(
        monkeypatch,
        disk_partitions=lambda all=False: parts,
        disk_usage=fake_usage,
    )
    result = _get_disk_info()
    assert calls == ["C:\\", "D:\\"], "异常分区也必须真实调过 disk_usage"
    assert [d["device"] for d in result] == ["D:\\"], \
        "PermissionError 分区被跳过、可用分区保留"


def test_disk_info_no_psutil(monkeypatch):
    """psutil 缺失 → 空列表（覆盖 80-81）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("stub: no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _get_disk_info() == []


# ---------------------------------------------------------------------------
# get_resources_info — 网络分支
# ---------------------------------------------------------------------------

class _Addr(object):
    def __init__(self, family, address):
        self.family = family
        self.address = address


def test_network_interfaces_with_psutil(monkeypatch):
    """net_if_addrs 命中 → network dict 逐接口逐地址（覆盖 97-101）。"""
    addrs = {
        "lo": [_Addr(2, "127.0.0.1")],
        "eth0": [_Addr(2, "10.0.0.2"), _Addr(23, "fe80::1")],
    }
    _install_fake_psutil(monkeypatch, net_if_addrs=lambda: addrs)
    info = get_resources_info()
    assert info["network"]["lo"] == [{"family": "2", "address": "127.0.0.1"}]
    assert len(info["network"]["eth0"]) == 2
    assert info["network"]["eth0"][1] == {"family": "23", "address": "fe80::1"}


def test_network_interfaces_raises_swallowed(monkeypatch):
    """net_if_addrs 抛异常 → network 保持空 dict，不炸整体（覆盖 102-103）。"""
    def boom():
        raise RuntimeError("stub net failure")

    _install_fake_psutil(monkeypatch, net_if_addrs=boom)
    info = get_resources_info()
    assert info["network"] == {}
    assert "cpu" in info and "memory" in info and "disk" in info


def test_network_no_psutil(monkeypatch):
    """psutil 缺失 → network 空 dict（同 except 兜底，一石二鸟）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("stub: no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    info = get_resources_info()
    assert info["network"] == {}
    assert info["cpu"]["count_logical"] >= 1
    assert info["memory"] == {}
    assert info["disk"] == []


# ---------------------------------------------------------------------------
# Prober 接口
# ---------------------------------------------------------------------------

def test_prober_returns_item_with_extra(monkeypatch):
    """ResourcesProber.probe() 返回带 extra 的 ProbeItem。"""
    _install_fake_psutil(monkeypatch, net_if_addrs=lambda: {})
    items = ResourcesProber().probe()
    assert len(items) == 1
    item = items[0]
    assert item.name == "resources"
    assert item.category == "resources"
    assert item.available is True
    assert "cpu" in item.extra and "network" in item.extra


# ---------------------------------------------------------------------------
# 变异验证记录（人工执行后还原，不留在测试运行里）
# ---------------------------------------------------------------------------
# MV-1: 删掉 resources.py:78-79 的 `except (PermissionError, OSError): pass` →
#       test_disk_info_permission_error_skipped 红（PermissionError 抛穿）。
# MV-2: 把 resources.py:31 `info["count_logical"] = _detect_cpu_count()` 改成
#       `pass`（ImportError 腿不回退）→ test_cpu_info_no_psutil 红（KeyError）。
# MV-3: 把 resources.py:102-103 的 `except Exception: pass` 改成只 `pass` 前半段
#       （即不吞异常）→ test_network_interfaces_raises_swallowed 红。
