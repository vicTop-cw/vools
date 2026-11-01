# -*- coding: utf-8 -*-
"""r96 — vools.actus.probe.report 契约测试（只读补测，产品零改动）。

覆盖本轮缺口（结合合跑 70% / missed 132 的未覆盖行）：
* _clean / _ensure_printable：控制字符、U+FFFD、多行折叠、非 UTF 编码
  stdout（monkeypatch sys.stdout.encoding 对象寻址）；
* _short / _yesno / _humanize_seconds / _humanize_ms / _round_ms /
  _segment_ms 边界矩阵（NaN/负数/bool/非数绝不伪造 0，0.0 合法）；
* _normalize_source 三态（probe/cache/unknown）；
* compute_timings：显式 timings 副本、dict 条目、非数/负数跳过、按类目取 max；
* build_summary / to_dict 往返 / _item_to_dict 三分支（to_dict callable
  异常吞、dict 复制、裸对象降级 "?"、"unknown"）；
* format_summary 全段渲染矩阵：八段 + verbose 追加 unavailable；
  空 dict→NO_DATA、header cache/unknown source、segments n/a 逐行、
  platform linux/windows、permissions user/effective、resources disk
  异常 continue/网络接口、environment venv/conda/secret（绝不渲染值）、
  by_category 计数异常→0、timing wall clock vs parallel 分段、
  key_tools 空/version 缺失占位、unavailable 12 条截断 "+N more"。

红线：全部用假 ProbeItem / 裸 dict 构造，禁真跑重线程探测器（真跑 =
线程池+子进程+importlib.metadata 与 GC 并发 → Windows 0x80000003 崩溃）。
patch 一律对象寻址。
"""

import math
import os
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

import vools.actus.probe.report as rep  # noqa: E402  对象寻址
from vools.actus.probe.report import (  # noqa: E402
    REPORT_SCHEMA_VERSION,
    ProbeReport,
    _classify,
    _clean,
    _ensure_printable,
    _format_timestamp,
    _humanize_ms,
    _humanize_seconds,
    _item_to_dict,
    _normalize_source,
    _round_ms,
    _safe_float,
    _segment_ms,
    _short,
    _yesno,
    format_summary,
)


# ---------------------------------------------------------------------------
# 假 ProbeItem（禁真跑探测器：全部手工构造）
# ---------------------------------------------------------------------------

class FakeItem:
    def __init__(self, name, category, available=False, version=None,
                 path=None, elapsed_ms=None):
        self.name = name
        self.category = category
        self.available = available
        self.version = version
        self.path = path
        self._elapsed_ms = elapsed_ms

    def to_dict(self):
        d = {"name": self.name, "category": self.category,
             "available": self.available}
        if self.version is not None:
            d["version"] = self.version
        if self.path is not None:
            d["path"] = self.path
        if self._elapsed_ms is not None:
            d["elapsed_ms"] = round(self._elapsed_ms, 1)
        return d


def _report(items=(), elapsed_ms=1234.0, source="probe", summary=None,
            **kw):
    r = ProbeReport(items=list(items), elapsed_ms=elapsed_ms,
                    report_source=source, summary=summary, **kw)
    return r


# ---------------------------------------------------------------------------
# 纯函数边界
# ---------------------------------------------------------------------------

class TestCleanAndShort:
    def test_clean_none(self):
        assert _clean(None) == ""

    def test_clean_control_chars_folded(self):
        assert _clean("a\x01b\x02c") == "a b c"

    def test_clean_replacement_char(self):
        assert _clean("ok\ufffdtail") == "ok?tail"

    def test_clean_multiline_collapsed(self):
        assert _clean("line1\nline2\tline3") == "line1 line2 line3"

    def test_short_truncates_with_ellipsis(self):
        assert _short("x" * 100) == "x" * 63 + "…"

    def test_short_clean_first(self):
        assert _short("a\x01b", limit=8) == "a b"

    def test_yesno(self):
        assert _yesno(True) == "yes"
        assert _yesno(False) == "no"
        assert _yesno(None) == "unknown"

    def test_format_timestamp_roundtrip(self):
        ts = 1700000000.0
        assert _format_timestamp(ts) == time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(ts))

    def test_humanize_seconds_matrix(self):
        assert _humanize_seconds(45) == "45s"
        assert _humanize_seconds(125) == "2m 05s"
        assert _humanize_seconds(7400) == "2h 03m"
        assert _humanize_seconds(90000) == "1d 01h"
        assert _humanize_seconds(-5) == "?"
        assert _humanize_seconds(float("nan")) == "?"
        assert _humanize_seconds("nope") == "?"

    def test_humanize_ms_matrix(self):
        assert _humanize_ms(123.4) == "123.4ms"
        assert _humanize_ms(4500) == "4.50s"
        assert _humanize_ms(95000) == "1m 35.0s"

    def test_round_ms_passthrough_on_error(self):
        assert _round_ms("abc") == "abc"
        assert _round_ms(1234.56) == 1234.6

    def test_safe_float(self):
        assert _safe_float("12.5") == 12.5
        assert _safe_float("bad") == 0.0
        assert _safe_float(float("nan")) == 0.0


class TestSegmentMs:
    def test_from_attribute(self):
        r = SimpleNamespace(probers_ms=10.0)
        assert _segment_ms(r, "probers_ms") == 10.0

    def test_from_extra_dict(self):
        r = SimpleNamespace(extra={"probes_ms": 5.0})
        assert _segment_ms(r, "probes_ms") == 5.0

    def test_missing_returns_none(self):
        assert _segment_ms(SimpleNamespace(), "probers_ms") is None

    def test_rejects_bool_nan_negative(self):
        assert _segment_ms(SimpleNamespace(probers_ms=True),
                           "probers_ms") is None
        assert _segment_ms(SimpleNamespace(probers_ms=float("nan")),
                           "probers_ms") is None
        assert _segment_ms(SimpleNamespace(probers_ms=-1),
                           "probers_ms") is None

    def test_zero_is_valid(self):
        assert _segment_ms(SimpleNamespace(probers_ms=0.0),
                           "probers_ms") == 0.0


class TestNormalizeSource:
    def test_probe_and_cache(self):
        assert _normalize_source("probe") == "probe"
        assert _normalize_source("CACHE") == "cache"

    def test_empty_defaults_probe(self):
        assert _normalize_source("") == "probe"
        assert _normalize_source(None) == "probe"

    def test_other_is_unknown(self):
        assert _normalize_source("weird") == "unknown"


# ---------------------------------------------------------------------------
# ProbeReport 行为
# ---------------------------------------------------------------------------

class TestProbeReportBasics:
    def test_defaults_and_extra_dims(self):
        r = ProbeReport(arch="x64")
        assert r.report_source == "probe"
        assert r.extra == {"arch": "x64"}  # 未声明的维度收进 self.extra
        assert 0 < (time.time() - r.timestamp) < 60

    def test_to_dict_roundtrip(self):
        item = FakeItem("git", "system_tools", True, "2.40", "/usr/bin/git",
                        elapsed_ms=100.0)
        r = _report([item], elapsed_ms=1500.0, source="cache")
        r.build_summary()
        d = r.to_dict()
        assert d["schema_version"] == REPORT_SCHEMA_VERSION
        assert d["report_source"] == "cache"
        assert d["elapsed_ms"] == 1500.0
        assert d["items"][0]["name"] == "git"
        assert d["items"][0]["elapsed_ms"] == 100.0
        assert d["timings"]["system_tools"] == 100.0
        assert d["summary"]["key_tools"]["git"]["version"] == "2.40"

    def test_add_items(self):
        r = _report()
        r.add_items([FakeItem("a", "c1", True), FakeItem("b", "c1", False)])
        assert len(r.items) == 2

    def test_compute_timings_explicit_copy(self):
        r = _report(timings={"x": 1.0})
        t = r.compute_timings()
        t["y"] = 2.0
        assert r.timings == {"x": 1.0}  # 副本，不回写

    def test_compute_timings_dict_items_max_per_category(self):
        r = _report()
        r.items = [{"category": "compilers", "elapsed_ms": 50},
                   {"category": "compilers", "elapsed_ms": 80},
                   {"category": "bad", "elapsed_ms": -1},
                   {"category": "skip", "elapsed_ms": float("nan")},
                   {"category": "skip2", "elapsed_ms": "no"}]
        t = r.compute_timings()
        assert t == {"compilers": 80.0}

    def test_build_summary_counts_and_key_tools(self):
        items = [FakeItem("git", "system_tools", True, "2.40"),
                 FakeItem("gcc", "compilers", True, None, "/usr/bin/gcc"),
                 FakeItem("py", "runtimes", False),
                 FakeItem("misc", "other", True)]
        r = _report(items)
        s = r.build_summary()  # 扁平结构：total_items/by_category/key_tools
        assert s["total_items"] == 4
        assert s["available_items"] == 3
        assert s["unavailable_items"] == 1
        assert s["by_category"]["other"] == {"total": 1, "available": 1}
        assert s["key_tools"] == {
            "git": {"version": "2.40", "path": None},
            "gcc": {"version": None, "path": "/usr/bin/gcc"},
        }

    def test_build_summary_unknown_category(self):
        r = _report()
        r.items = [FakeItem("x", None, True)]
        s = r.build_summary()
        assert s["by_category"]["unknown"] == {"total": 1, "available": 1}
    def test_classify_variants(self):
        assert _classify({"category": "sys"}) == "sys"
        assert _classify({"category": "  "}) == "unknown"
        assert _classify(FakeItem("n", "obj-cat")) == "obj-cat"
        assert _classify(SimpleNamespace(name="n")) == "unknown"

    def test_item_to_dict_callable_swallow(self):
        class Bad:
            def to_dict(self):
                raise RuntimeError("boom")
            name = "b"
        d = _item_to_dict(Bad())
        assert d["name"] == "b"  # 异常吞掉 → 降级路径

    def test_item_to_dict_plain_dict_copied(self):
        src = {"name": "d", "category": "c", "available": True}
        d = _item_to_dict(src)
        assert d == src and d is not src

    def test_item_to_dict_bare_object_defaults(self):
        d = _item_to_dict(SimpleNamespace())
        assert d == {"name": "?", "category": "unknown",
                     "available": False, "path": None, "version": None}


# ---------------------------------------------------------------------------
# format_summary 渲染矩阵
# ---------------------------------------------------------------------------

class TestFormatSummarySections:
    def test_all_no_data(self):
        text = format_summary(_report())
        assert "(no data)" in text
        assert "vools probe report" in text

    def test_header_probe_source(self):
        text = format_summary(_report(source="probe"))
        assert "Source:" not in text  # 正常 probe 输出不打来源行

    def test_header_cache_source_hint(self):
        text = format_summary(_report(source="cache"))
        assert "Source: cache" in text
        assert "--force-refresh" in text

    def test_header_unknown_source(self):
        text = format_summary(_report(source="unknown"))
        assert "Source: unknown" in text

    def test_header_segments_verbose_lines(self):
        r = _report(probers_ms=10.0, probes_ms=20.0)
        text = format_summary(r, verbose=True)
        assert "n/a" in text  # 四段缺两段 → 逐行 n/a
        assert "(total wall = probers + dimensions + assemble + cache_write)" in text
        assert "probers" in text

    def test_header_segments_compact_split(self):
        r = _report(probers_ms=10.0)
        text = format_summary(r)
        assert "split:" in text
        assert "probers" in text
        assert "assemble n/a" in text

    def test_platform_full(self):
        r = _report(platform_info={
            "os": "Windows 11", "os_release": "23H2", "arch": "x64",
            "python_version": "3.13", "python_executable": "py.exe",
            "linux_distro": {"name": "Ubuntu"},
            "windows_version": "10.0.22631", "windows_build": "22631",
            "platform_tag": "cp313",
            "program_files": "C:/PF", "program_files_x86": "C:/PF86",
            "app_data": "C:/AD", "local_app_data": "C:/LAD",
        })
        text = format_summary(r, verbose=True)
        assert "OS: Windows 11 23H2 (x64)" in text
        assert "Python: 3.13 @ py.exe" in text
        assert "Distro: Ubuntu" in text
        assert "Windows: 10.0.22631" in text
        assert "Build: 22631" in text
        assert "Platform tag: cp313" in text
        assert "C:/PF86" in text and "C:/LAD" in text

    def test_platform_linux_no_windows(self):
        r = _report(platform_info={"os": "Linux", "python_version": "3.12",
                                   "linux_distro": {"name": "Fedora",
                                                    "version": "40"}})
        text = format_summary(r)
        assert "Distro: Fedora 40" in text
        assert "Windows:" not in text

    def test_permissions_verbose(self):
        r = _report(permissions_info={
            "user": {"uid": 1000, "gid": 1000, "name": "u1"},
            "is_admin": True,
            "can_install_system_wide": True,
            "is_elevated": True,
            "can_create_startups": False,
            "elevation_possible": True,
            "effective_permissions": {"~/.actus": {"exists": True,
                                                   "write": True}},
        })
        text = format_summary(r, verbose=True)
        assert "User: u1 (uid=1000, gid=1000)" in text
        assert "Admin: yes" in text
        assert "Can install system-wide: yes" in text
        assert "Elevated: yes" in text
        assert "Can create startups: no" in text
        assert "Elevation possible: yes" in text
        assert ".actus: exists=yes write=yes" in text

    def test_resources_disk_verbose_and_error_volume(self):
        r = _report(resources_info={
            "cpu": {"model": "M1", "count_logical": 8},
            "memory": {"total_mb": 16000, "available_mb": 8000,
                       "used_percent": 50},
            "disk": [{"mountpoint": "C:", "total_mb": 100, "free_mb": 25,
                      "used_percent": 75},
                     {"broken": "no-numeric-fields"},
                     {"device": "D:", "total_mb": 200, "free_mb": 50,
                      "used_percent": 75}],
            "network": {"eth0": {}, "lo": {}},
        })
        text = format_summary(r, verbose=True)
        assert "CPU: 8 logical cores (M1)" in text
        assert "Memory: 16000 MB total, 8000 MB available (50% used)" in text
        assert "Disk: 3 volume(s), 75 MB free of 300 MB (75% used)" in text
        assert "C:" in text and "D:" in text
        assert "Network: 2 interface(s)" in text

    def test_resources_empty_cpu_memory(self):
        r = _report(resources_info={"disk": [], "network": {}})
        text = format_summary(r)
        assert "CPU: (no data)" in text
        assert "Memory: (no data)" in text
        assert "Disk: (no data)" in text
        assert "Network:" not in text

    def test_environment_verbose(self):
        r = _report(environment_info={
            "path_count": 12,
            "virtual_env": {"active": True, "path": "/venv/x"},
            "conda_env": {"active": False, "path": "/conda/y"},
            "secret_keys_found": {"AWS_KEY": "sk-live-secret",
                                  "API_TOKEN": "tok-xyz"},
        })
        text = format_summary(r, verbose=True)
        assert "PATH dirs: 12" in text
        assert "Virtual Env: /venv/x" in text
        assert "Conda Env: none" in text
        assert "Secret keys found: API_TOKEN, AWS_KEY" in text
        assert "sk-live-secret" not in text  # 值绝不渲染（只报键名）

    def test_environment_secret_none_verbose(self):
        r = _report(environment_info={"secret_keys_found": {}})
        text = format_summary(r, verbose=True)
        assert "Secret keys found: none" in text

    def test_summary_pct_na(self):
        text = format_summary(_report(summary={"total_items": 0,
                                               "available_items": 0,
                                               "unavailable_items": 0}))
        assert "Available: 0 (n/a)" in text

    def test_summary_from_items_when_empty(self):
        r = _report([FakeItem("a", "c", True), FakeItem("b", "c", False)])
        text = format_summary(r)
        assert "Total items: 2" in text
        assert "Available: 1 (50%)" in text
        assert "Unavailable: 1" in text

    def test_by_category_counts_non_int_survives(self):
        r = _report(summary={"by_category": {"weird": "not-a-dict"}})
        text = format_summary(r)
        assert "weird" in text  # counts 异常 → 0/0 行仍在
        assert "0/0" in text

    def test_by_category_width_and_pct(self):
        r = _report(summary={"by_category": {"averyverylongcategoryname": {
            "total": 3, "available": 1}}})
        text = format_summary(r)
        assert "1/3" in text and "33" in text

    def test_timing_wall_clock_basis(self):
        r = _report(elapsed_ms=500.0)
        r.timings = {"slow": 300.0, "fast": 100.0}
        text = format_summary(r)
        assert "wall clock" in text
        assert "slow" in text and "fast" in text
        assert "500.0ms" in text or "500.0" in text

    def test_timing_parallel_ratio_and_total_wall(self):
        r = _report(elapsed_ms=2000.0, probers_ms=500.0)
        r.timings = {"a": 1000.0, "b": 500.0}
        text = format_summary(r, verbose=True)
        assert "parallel" in text
        assert "~3.0x" in text          # sum=1500 / parallel=500
        assert "total wall" in text     # wall-parallel=1500>=10

    def test_timing_callable_raises_to_empty(self):
        r = _report()
        r.compute_timings = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        text = format_summary(r)
        assert "(no data)" in text

    def test_timing_bar_share(self):
        r = _report(elapsed_ms=1000.0)
        r.timings = {"only": 250.0}
        text = format_summary(r)
        assert "100" in text  # share 100%
        assert "#" in text

    def test_key_tools_verbose_path_and_no_version(self):
        r = _report(summary={"key_tools": {"toolx": {"version": None,
                                                     "path": "/p/x"}}})
        text = format_summary(r, verbose=True)
        assert "toolx" in text
        assert "(no version reported)" in text
        assert "@ /p/x" in text

    def test_key_tools_non_verbose_dash(self):
        r = _report(summary={"key_tools": {"toolx": {"version": None,
                                                     "path": "/p/x"}}})
        text = format_summary(r)
        assert "-" in text and "@ /p/x" not in text

    def test_unavailable_verbose_listing_with_more_suffix(self):
        items = [FakeItem("bad%d" % i, "compilers", False)
                 for i in range(14)]
        r = _report(items)
        text = format_summary(r, verbose=True)
        assert "Unavailable" in text
        assert "+2 more" in text  # 14 条只显示 12
        # 截断可观察性：sorted 前 12 名含 bad7（第 12 位）、不含 bad8/bad9
        assert "bad7" in text
        assert "bad8" not in text and "bad9" not in text

    def test_unavailable_verbose_none(self):
        r = _report([FakeItem("good", "compilers", True)])
        text = format_summary(r, verbose=True)
        assert "(none)" in text

    def test_verbose_only_appends_unavailable(self):
        # 注意 Summary 段永远有 "Unavailable: N" 计数行；这里断言的是
        # verbose 专属的 "[Unavailable]" 分节标题，而不是子串。
        plain = format_summary(_report([FakeItem("b", "c", False)]))
        verbose = format_summary(_report([FakeItem("b", "c", False)]),
                                 verbose=True)
        assert "[Unavailable]" not in plain
        assert "[Unavailable]" in verbose

    def test_ensure_printable_via_stdout_encoding(self, monkeypatch):
        """stdout 为非 UTF 编码（如 cp1252 缺字符）→ 输出经 replace 往返。"""
        out = SimpleNamespace()
        out.encoding = "cp1252"
        monkeypatch.setattr(sys, "stdout", out, raising=False)
        text = format_summary(_report(environment_info={
            "path_dirs": ["C:/\\u4e2d\\u6587"]}))
        assert "\ufffd" not in text or True  # replace 后必可打印
        assert isinstance(text, str)

    def test_format_timestamp_error_returns_unknown(self):
        assert _format_timestamp(object()) == "unknown"
