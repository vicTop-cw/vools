# -*- coding: utf-8 -*-
"""actus/tests/test_probe.py — 环境探测器（probe 包）验收测试。

覆盖 analysis/PROBE_PLAN.md 的九类探测维度与本轮修的两个真缺陷：
1. 缓存往返丢失：save_cache 原先只落盘 timestamp/elapsed_ms/summary/items，
   而 probe() 从缓存重建 Report 时按 platform/permissions/environment/resources
   回填 —— 命中缓存后这四个维度恒为空 dict（实测复现）。
2. py3.6 包探测假阴性：_get_pkg_version 整条链路吊在 `import importlib.metadata`
   上，而该模块 py3.8+ 才有（py3.6 实测抛 ImportError），异常被外层 except 吞掉
   后恒返回 "" —— py3.6 下所有 Python 包一律被判「未安装」。

测试不依赖机器上真装了哪些工具（那会让断言随环境漂移）：只断言报告结构完整、
维度非空、以及"已知存在的包能拿到版本号"这类确定性事实。

py3.6 兼容：无 capture_output/text 之外的新语法依赖，无 walrus，f-string 限于 py3.6 支持形态。
"""

import json
import os
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.probe import ProbeReport, format_summary, probe
from vools.actus.probe.base import ProbeItem, Prober
from vools.actus.probe import cache as cache_mod
from vools.actus.probe.platform import get_platform_info
from vools.actus.probe.permissions import get_permissions_info
from vools.actus.probe.environment import get_environment_info
from vools.actus.probe.resources import get_resources_info
from vools.actus.probe.python_pkgs import _get_pkg_version


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

def test_probeitem_to_dict_roundtrip():
    item = ProbeItem(name="git", category="system_tools", available=True,
                     path="C:\\git.exe", version="git version 2.43.0")
    d = item.to_dict()
    assert d["name"] == "git"
    assert d["category"] == "system_tools"
    assert d["available"] is True
    assert d["path"] == "C:\\git.exe"
    assert d["version"] == "git version 2.43.0"
    # 重建（缓存反序列化路径）
    item2 = ProbeItem(**d)
    assert item2.name == "git" and item2.available is True


def test_probeitem_unavailable_carries_error():
    item = ProbeItem(name="nosuch", category="system_tools", available=False,
                     error="not found")
    d = item.to_dict()
    assert d["available"] is False
    assert d["error"] == "not found"


def test_prober_swallows_probe_exception():
    """探测器炸掉时不能把异常抛穿整份报告，要降级成 available=False 的条目。"""
    class Boom(Prober):
        def probe(self):
            raise RuntimeError('boom')

    results = Boom().run()
    assert len(results) == 1
    assert results[0].available is False
    assert 'boom' in (results[0].error or '')


# ---------------------------------------------------------------------------
# 四个维度采集器
# ---------------------------------------------------------------------------

def test_platform_info_fields():
    info = get_platform_info()
    assert info["os"] in ("Windows", "Linux", "Darwin")
    assert info["python_version"]
    assert info["python_executable"]
    assert isinstance(info["path_dirs"], list) and info["path_dirs"]
    # 平台标志位互斥且与 sys.platform 一致
    flags = [info["is_windows"], info["is_linux"], info["is_macos"]]
    assert sum(1 for f in flags if f) == 1


def test_platform_windows_specific_fields():
    info = get_platform_info()
    if info["is_windows"]:
        assert "program_files" in info
        assert "local_app_data" in info


def test_permissions_info_shape():
    info = get_permissions_info()
    assert info["user"]["name"]
    # is_admin / 能力标志必须是 bool，不能是 None（下游要做动作门禁判断）
    for key in ("is_admin", "is_elevated", "can_install_system_wide",
                "can_create_startups"):
        assert isinstance(info[key], bool), key
    # 关键目录权限：home/temp 一定存在且可写（否则本机能跑 pytest 这件事就不成立）
    assert info["effective_permissions"]["home"]["exists"] is True
    assert info["effective_permissions"]["home"]["write"] is True


def test_environment_info_shape():
    info = get_environment_info()
    assert info["path_count"] == len(info["path_dirs"])
    # PATH 必须脱敏成条目数，不原样回显整串（计划的安全约束）
    assert info["env_vars"].get("PATH", "").startswith("[REDACTED:")
    # venv/conda 结构存在
    assert "active" in info["virtual_env"]
    assert "active" in info["conda_env"]


def test_environment_no_secret_values():
    """敏感 key 只记名不记值 —— 报告里绝不能出现值本身。"""
    secret_name = 'PROBE_TEST_API_KEY'
    secret_value = 'sk-DO-NOT-LEAK-12345'
    os.environ[secret_name] = secret_value
    try:
        info = get_environment_info()
        assert info["secret_keys_found"].get(secret_name) is True
        blob = json.dumps(info, ensure_ascii=False)
        assert secret_value not in blob, '敏感值泄进了探测报告'
    finally:
        del os.environ[secret_name]


def test_resources_info_shape():
    info = get_resources_info()
    assert "cpu" in info and "memory" in info and "disk" in info and "network" in info
    # CPU 逻辑核数必须为正整数（os.cpu_count 兜底也在）
    assert info["cpu"]["count_logical"] >= 1


# ---------------------------------------------------------------------------
# 包版本探测（钉死 py3.6 假阴性）
# ---------------------------------------------------------------------------

def test_pkg_version_reads_real_metadata():
    """pip 一定装了：必须拿到版本号，而不是空串。

    旧实现在 py3.6 走 `import importlib.metadata`（py3.8+ 才有）抛 ImportError，
    被外层 except 吞掉 → 恒返回 ""，于是 py3.6 上所有包都被判成未安装。
    """
    ver = _get_pkg_version('pip')
    assert ver, 'pip 已安装却探不到版本号（py3.6 假阴性回归）'
    assert ver[0].isdigit(), ver


def test_pkg_version_missing_pkg_is_empty():
    assert _get_pkg_version('no_such_package_xyz_123') == ''


def test_python_packages_prober_reports_versions(tmp_path):
    from vools.actus.probe.python_pkgs import PythonPackagesProber

    items = PythonPackagesProber().run()
    assert items, '包探测器未产出任何条目'
    by_name = {i.name: i for i in items}
    pip_item = by_name.get('pip')
    if pip_item is not None:
        # 装了就必须 available=True 且带版本
        assert pip_item.available is True
        assert pip_item.version


# ---------------------------------------------------------------------------
# 缓存往返（钉死维度丢失）
# ---------------------------------------------------------------------------

def test_cache_roundtrip_keeps_all_dimensions(tmp_path, monkeypatch):
    """缓存命中后 platform/permissions/environment/resources 不能变空。

    旧 save_cache 只落盘 timestamp/elapsed_ms/summary/items，四个维度不落盘，
    probe() 从缓存重建时按这四个键回填 → 全部为空 dict（实测 keys=0）。
    """
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))

    report = probe(force_refresh=True)
    fresh = report.to_dict()
    assert len(fresh["platform"]) > 0 and len(fresh["permissions"]) > 0
    assert len(fresh["environment"]) > 0 and len(fresh["resources"]) > 0

    # 走缓存路径重建
    cached = probe(force_refresh=False, max_age=999999)
    got = cached.to_dict()
    # 具体维度必须与真探测完全一致（不是"非空"就行：被换成 {"stub": 1} 也会非空）
    assert got["platform"] == fresh["platform"], '缓存命中后 platform 维度内容变了'
    assert got["permissions"] == fresh["permissions"], '缓存命中后 permissions 维度内容变了'
    assert got["environment"] == fresh["environment"], '缓存命中后 environment 维度内容变了'
    assert got["resources"] == fresh["resources"], '缓存命中后 resources 维度内容变了'
    # 条目不是"数量相同"就行：名称序列必须与真探测一致（数量相同但内容全错也算失败）
    assert [item["name"] for item in got["items"]] == \
        [item["name"] for item in fresh["items"]], '缓存命中后 items 名称/顺序变了'
    assert got["report_source"] == "cache", "缓存命中必须标记 report_source=cache"
    assert fresh["report_source"] == "probe"


def test_cache_force_refresh_bypasses(tmp_path, monkeypatch):
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    assert cache_mod.load_cache(force_refresh=True) is None


def test_cache_invalidate(tmp_path, monkeypatch):
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    cache_file.write_text('{"timestamp": 1}', encoding='utf-8')
    cache_mod.invalidate_cache()
    assert not cache_file.exists()


def test_cache_expired_returns_none(tmp_path, monkeypatch):
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    cache_file.write_text('{"timestamp": 1}', encoding='utf-8')
    assert cache_mod.load_cache(max_age=10) is None


def test_cache_corrupt_file_is_not_fatal(tmp_path, monkeypatch):
    """缓存坏掉必须降级为"没缓存"，不能让 probe() 整条炸。"""
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    cache_file.write_text('{ not valid json', encoding='utf-8')
    assert cache_mod.load_cache() is None


# ---------------------------------------------------------------------------
# 集成：完整报告
# ---------------------------------------------------------------------------

@pytest.mark.timeout(180)
def test_probe_returns_full_report(tmp_path, monkeypatch):
    """probe() 一次跑完，报告结构完整、九类信息齐备、summary 计数自洽。"""
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))

    report = probe(force_refresh=True)
    assert isinstance(report, ProbeReport)
    d = report.to_dict()

    for key in ("platform", "permissions", "environment", "resources",
                "items", "summary", "timestamp", "elapsed_ms"):
        assert key in d, key

    s = d["summary"]
    assert s["total_items"] == len(d["items"])
    assert s["available_items"] + s["unavailable_items"] == s["total_items"]

    # 九类维度在 items 的分类计数里都要有落点
    cats = set(s["by_category"].keys())
    for expected in ("platform", "permissions", "environment", "resources",
                     "system_tools", "runtimes", "compilers", "actions"):
        assert expected in cats, '缺维度: %s（已得 %s）' % (expected, sorted(cats))

    # 报告必须能 JSON 序列化（要落缓存/给 LLM 消费）
    json.dumps(d, ensure_ascii=False)


@pytest.mark.timeout(180)
def test_probe_detects_a_known_tool(tmp_path, monkeypatch):
    """机器上必然有 python（正在跑它），探针必须探到它 —— 全表恒 False 说明探测逻辑坏了。"""
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))

    report = probe(force_refresh=True)
    d = report.to_dict()
    found = [i for i in d["items"]
             if i["name"] in ("python", "py", "python3") and i["available"]]
    assert found, '探针没探到 python（正在执行它的解释器）'
    assert found[0]["path"]


@pytest.mark.timeout(180)
def test_format_summary_renders(tmp_path, monkeypatch):
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))

    text = format_summary(probe(force_refresh=True))
    assert "vools probe report" in text
    assert "[Platform]" in text
    assert "[Summary]" in text
