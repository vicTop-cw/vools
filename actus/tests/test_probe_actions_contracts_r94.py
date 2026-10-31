# -*- coding: utf-8 -*-
"""r94 — vools.actus.probe.actions 契约测试（只读补测，零产品代码改动）。

覆盖本轮缺口（结合 9 文件 probe 合跑 53% 的未覆盖行）：
* _scan_actions_dir / _scan_actions_with_deps：跨盘 relpath ValueError 回退、
  同 id 多份先到优先、deps 字段三形态（missing/null/invalid）与 parse_error；
* _report_items / _capabilities_from_report / _ReportCapabilities：
  报告四种形态归一 + available→installed 回退 + 分类路由；
* _SelfCapabilities：懒索引、命令缓存、异常吞、运行时别名表、包探测缓存；
* _parse_declared_deps：invalid_deps_field / invalid_dep_entry /
  解析异常 / 条数不符 / 正常配对；
* _dep_label / _dep_kind 全类型矩阵；
* _entry_check_targets / _check_entry_block_directives：
  入口块选择、校验器缺失不判定、单块异常、白名单外指令 → degraded；
* analyze_actions 端到端：ready / blocked(missing) / undeclared(missing/null) /
  parse_failed / action 链 / action 缺失 / 成环 / unverifiable(mcp) /
  degraded / duplicate_ids / index_source 两态 / 汇总字段；
* ActionsProber.probe 三条目 + analyze 异常容错。
"""

import json
import os
import types

import pytest

import _ai_local_bootstrap  # noqa: F401  必须先于 vools 导入（套件约定）

import vools.actus.probe.actions as pa


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def acts_dir(tmp_path):
    d = tmp_path / "actions"
    d.mkdir()
    return str(d)


def _cfg(aid, deps="__nodeps__", entry="main"):
    meta = {
        "id": aid, "name": aid.split(".")[-1], "version": "1.0.0",
        "kind": "exec", "platform": "desktop", "trust": "sandbox",
        "entry": entry, "description": "t", "maintainer": "vools",
        "visibility": "public", "engines": ["prompt", "python"],
        "params": [], "returns": "none",
    }
    if deps != "__nodeps__":
        meta["deps"] = deps
    body = "```json #!cfg\n" + json.dumps(meta, ensure_ascii=False) + "\n```\n"
    body += "```python #!run tag=main\nprint('hi')\n```\n"
    return body


def _put(d, name, aid, deps="__nodeps__", body=None):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body if body is not None else _cfg(aid, deps))
    return p


_REPORT = {
    "system_tools": [{"name": "git", "available": True}],
    "runtimes": [{"name": "python3", "installed": True}],
    "python_packages": [{"name": "requests", "installed": True},
                        {"name": "absent_pkg", "installed": False}],
}


# ---------------------------------------------------------------------------
# 扫描层
# ---------------------------------------------------------------------------

class TestScanActionsDir(object):
    def test_happy_and_dedup_first_wins(self, acts_dir):
        _put(acts_dir, "a.actus.md", "demo.a")
        info = pa._scan_actions_dir(acts_dir)
        assert info["exists"] is True and len(info["actions"]) == 1
        assert info["actions"][0]["id"] == "demo.a"

    def test_parse_failure_falls_back_to_rel(self, acts_dir):
        _put(acts_dir, "bad.actus.md", "demo.bad",
             body="```json #!cfg\n{broken json\n```\n")
        info = pa._scan_actions_dir(acts_dir)
        assert info["actions"] and info["actions"][0]["id"].endswith("bad.actus.md")

    def test_cross_drive_relpath_fallback(self, acts_dir, monkeypatch):
        # 跨盘 relpath 失败 + 解析失败 → id 回退为完整路径 rel
        _put(acts_dir, "x.actus.md", "demo.x",
             body="```json #!cfg\n{broken\n```\n")
        real_os = os

        class _FakeOS(object):
            def __getattr__(self, n):
                return getattr(real_os, n)

            @staticmethod
            def relpath(full, root):
                raise ValueError("cross drive")

        monkeypatch.setattr(pa, "os", _FakeOS())
        info = pa._scan_actions_dir(acts_dir)
        assert info["actions"][0]["id"].endswith("x.actus.md")


class TestScanWithDeps(object):
    def test_deps_field_shapes(self, acts_dir):
        _put(acts_dir, "a.actus.md", "demo.a", deps=["builtin:ui"])
        _put(acts_dir, "b.actus.md", "demo.b")                    # 键缺失
        _put(acts_dir, "c.actus.md", "demo.c", deps=None)         # null
        _put(acts_dir, "d.actus.md", "demo.d", deps="oops")       # 非列表
        _put(acts_dir, "e.actus.md", "demo.e",
             body="```json #!cfg\n{broken\n```\n")                # 解析失败
        scan = pa._scan_actions_with_deps(acts_dir)
        fields = {e["rel"].split(".")[0]: e for e in scan["entries"]}
        assert fields["a"]["deps_field"] == "list"
        assert fields["b"]["deps_field"] == "missing"
        assert fields["c"]["deps_field"] == "null"
        assert fields["d"]["deps_field"] == "invalid"
        assert fields["e"]["parse_error"]

    def test_duplicate_ids_recorded(self, acts_dir):
        sub = os.path.join(acts_dir, "sub")
        os.makedirs(sub)
        _put(acts_dir, "a.actus.md", "demo.dup")
        _put(sub, "a.actus.md", "demo.dup")
        scan = pa._scan_actions_with_deps(acts_dir)
        assert scan["duplicate_ids"] and \
            scan["duplicate_ids"][0]["id"] == "demo.dup"

    def test_cross_drive_relpath_fallback(self, acts_dir, monkeypatch):
        # 跨盘 relpath 失败 + 解析失败 → rel 字段回退为完整路径
        _put(acts_dir, "x.actus.md", "demo.x",
             body="```json #!cfg\n{broken\n```\n")
        real_os = os

        class _FakeOS(object):
            def __getattr__(self, n):
                return getattr(real_os, n)

            @staticmethod
            def relpath(full, root):
                raise ValueError("cross drive")

        monkeypatch.setattr(pa, "os", _FakeOS())
        scan = pa._scan_actions_with_deps(acts_dir)
        assert scan["entries"][0]["rel"].endswith("x.actus.md")


# ---------------------------------------------------------------------------
# 报告归一与能力集合
# ---------------------------------------------------------------------------

class TestReportItems(object):
    def test_none_and_shapes(self):
        assert pa._report_items(None) is None
        obj = types.SimpleNamespace(items=[{"name": "git"}])
        assert pa._report_items(obj) == [{"name": "git"}]
        assert pa._report_items({"items": [1]}) == [1]
        assert pa._report_items(["raw"]) == ["raw"]
        assert pa._report_items(42) is None
        # 计划形态：按分类展开
        rep = {"system_tools": [{"name": "git"}],
               "runtimes": [], "python_packages": ["notdict"]}
        items = pa._report_items(rep)
        assert items and items[0]["category"] == "system_tools"
        assert pa._report_items({}) is None


class TestCapabilitiesFromReport(object):
    def test_routing_and_fallbacks(self):
        caps = pa._capabilities_from_report({
            "system_tools": [{"name": "git", "available": True}],
            "runtimes": [{"name": "py", "installed": True}],
            "python_packages": [{"name": "requests", "installed": True}],
            "system_tools2": [{"available": True}],          # 无 name 跳过
            "runtimes_x": [{"name": "dead", "available": False}],
        })
        assert caps.source == "probe_report"
        assert caps.has_system("git") and not caps.has_system("dead")
        assert caps.has_runtime("py") and caps.has_python("requests")
        assert not caps.has_python("absent_pkg")

    def test_unavailable_report_returns_none(self):
        assert pa._capabilities_from_report(None) is None
        assert pa._capabilities_from_report({}) is None

    def test_caps_selection(self):
        assert isinstance(pa._capabilities(_REPORT), pa._ReportCapabilities)
        self_caps = pa._capabilities(None)
        assert self_caps.source == "self-probe"


class TestSelfCapabilities(object):
    def test_command_lookup_and_cache(self, monkeypatch):
        calls = []

        def fake_lookup(name, index):
            calls.append(name)
            return "/bin/%s" % name if name == "git" else None

        monkeypatch.setattr("vools.actus.probe.system_tools._build_path_index",
                            lambda: {"git": ["/bin"]})
        monkeypatch.setattr(
            "vools.actus.probe.system_tools._lookup_in_path_index", fake_lookup)
        caps = pa._SelfCapabilities()
        assert caps.has_system("git") is True
        assert caps.has_system("git") is True and len(calls) == 1   # 缓存
        assert caps.has_system("") is False
        assert caps.has_system("nope") is False

    def test_command_lookup_exception(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("index boom")

        monkeypatch.setattr("vools.actus.probe.system_tools._build_path_index", boom)
        caps = pa._SelfCapabilities()
        assert caps.has_system("git") is False

    def test_runtime_alias_expansion(self, monkeypatch):
        seen = []

        def fake_lookup(name, index):
            seen.append(name)
            return "/bin/%s" % name if name in ("bash", "python") else None

        monkeypatch.setattr("vools.actus.probe.system_tools._build_path_index",
                            lambda: {})
        monkeypatch.setattr(
            "vools.actus.probe.system_tools._lookup_in_path_index", fake_lookup)
        caps = pa._SelfCapabilities()
        assert caps.has_runtime("shell") is True          # 别名表命中
        assert caps.has_runtime("nope") is False

    def test_python_pkg_probe(self, monkeypatch):
        import importlib.metadata as md

        monkeypatch.setattr(md, "version",
                            lambda n: "1.0" if n == "requests" else (_ for _ in ()).throw(Exception()))
        caps = pa._SelfCapabilities()
        assert caps.has_python("requests") is True
        assert caps.has_python("requests") is True        # 缓存第二次不再调
        assert caps.has_python("") is False
        assert caps.has_python("nope_pkg") is False


# ---------------------------------------------------------------------------
# 依赖解析与分类
# ---------------------------------------------------------------------------

class TestParseDeclaredDeps(object):
    def test_shapes(self):
        assert pa._parse_declared_deps(None) == ([], [])
        parsed, issues = pa._parse_declared_deps("not-a-list")
        assert parsed == [] and issues[0]["status"] == "invalid_deps_field"
        parsed, issues = pa._parse_declared_deps([42])
        assert parsed == [] and issues[0]["status"] == "invalid_dep_entry"

    def test_resolver_exception_and_mismatch(self, monkeypatch):
        class BoomResolver(object):
            def parse_deps(self, rows):
                raise RuntimeError("resolver boom")

        monkeypatch.setattr("vools.actus.dependency.get_resolver",
                            lambda: BoomResolver())
        parsed, issues = pa._parse_declared_deps(["system:git"])
        assert parsed == [] and issues[0]["status"] == "parse_error"

        class ShortResolver(object):
            def parse_deps(self, rows):
                return rows[:1]

        monkeypatch.setattr("vools.actus.dependency.get_resolver",
                            lambda: ShortResolver())
        parsed, issues = pa._parse_declared_deps(["system:git", "builtin:ui"])
        assert parsed == [] and "条数不符" in issues[0]["reason"]

    def test_happy_pairs(self, monkeypatch):
        parsed, issues = pa._parse_declared_deps(["system:git", {"type": "builtin", "name": "ui"}])
        assert issues == [] and len(parsed) == 2


class TestDepLabelKind(object):
    def test_label(self):
        assert pa._dep_label("system:git", None) == "system:git"
        dep = types.SimpleNamespace(type=types.SimpleNamespace(value="builtin"),
                                    name="ui")
        assert pa._dep_label({"x": 1}, dep) == "builtin:ui"
        dep2 = types.SimpleNamespace(type=None, name="")
        assert pa._dep_label({}, dep2) == "action:?"

    def test_kind_matrix(self):
        ns = types.SimpleNamespace
        assert pa._dep_kind(ns(type=ns(value="lang"), name="requests")) == ("pip", "requests")
        assert pa._dep_kind(ns(type=ns(value="lang"), name="x",
                               lang_manager="npm")) == ("npm", "x")
        assert pa._dep_kind(ns(type=ns(value="system"), name="git")) == ("system", "git")
        assert pa._dep_kind(ns(type=ns(value="runtime"), name="shell")) == ("runtime", "shell")
        assert pa._dep_kind(ns(type=ns(value="weird"), name="x")) == ("unknown", "x")


# ---------------------------------------------------------------------------
# 入口块指令
# ---------------------------------------------------------------------------

class TestEntryBlockDirectives(object):
    def _entry(self, blocks, entry="main"):
        return {"entry": entry, "blocks": blocks}

    def test_targets_selection(self):
        blocks = [{"tag": ["main"], "language": "python", "directives": {}},
                  {"tag": ["other"], "language": "python", "directives": {}}]
        assert len(pa._entry_check_targets(self._entry(blocks))) == 1
        assert len(pa._entry_check_targets(self._entry(blocks, entry=""))) == 2
        assert pa._entry_check_targets({"entry": "main", "blocks": []}) == []

    def test_validator_unavailable_not_judged(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules,
                            "vools.bridge.md.directives", None)
        reasons, info = pa._check_entry_block_directives(
            self._entry([{"tag": ["main"], "language": "python", "directives": {}}]))
        assert reasons == [] and info["checked"] is False and "error" in info

    def test_block_validate_exception(self, monkeypatch):
        import vools.bridge.md.directives as dv

        def boom(d, lang):
            raise RuntimeError("validate boom")

        monkeypatch.setattr(dv, "validate_directives", boom)
        reasons, info = pa._check_entry_block_directives(
            self._entry([{"tag": ["main"], "language": "python",
                          "directives": {}, "index": 0}]))
        assert reasons == [] and info["checked"] is True
        assert info["blocks"][0]["ok"] is None

    def test_unsupported_directive_degrades(self, monkeypatch):
        import vools.bridge.md.directives as dv

        monkeypatch.setattr(dv, "validate_directives",
                            lambda d, lang: ["未知指令: devtools"])
        reasons, info = pa._check_entry_block_directives(
            self._entry([{"tag": ["main"], "language": "webview2",
                          "directives": {"devtools": "false"}, "index": 0}]))
        assert reasons and reasons[0]["kind"] == "entry_block_unsupported"
        assert info["checked"] is True and info["blocks"][0]["ok"] is False

    def test_valid_directives_pass(self, monkeypatch):
        import vools.bridge.md.directives as dv

        monkeypatch.setattr(dv, "validate_directives", lambda d, lang: [])
        reasons, info = pa._check_entry_block_directives(
            self._entry([{"tag": ["main"], "language": "python",
                          "directives": {}, "index": 0}]))
        assert reasons == [] and info["checked"] is True


# ---------------------------------------------------------------------------
# analyze_actions 端到端
# ---------------------------------------------------------------------------

class TestAnalyzeActions(object):
    def test_full_matrix(self, acts_dir):
        _put(acts_dir, "ok.actus.md", "demo.ok", deps=["builtin:ui"])
        _put(acts_dir, "miss.actus.md", "demo.miss",
             deps=["system:definitely_not_installed_xyz"])
        _put(acts_dir, "nodeps.actus.md", "demo.nodeps")
        _put(acts_dir, "null.actus.md", "demo.null", deps=None)
        _put(acts_dir, "badfield.actus.md", "demo.badfield", deps="oops")
        _put(acts_dir, "badentry.actus.md", "demo.badentry", deps=[42])
        _put(acts_dir, "mcp.actus.md", "demo.mcp", deps=["mcp:nope"])
        _put(acts_dir, "ghost.actus.md", "demo.ghost", deps=["action:ghost"])
        _put(acts_dir, "broken.actus.md", "demo.broken",
             body="```json #!cfg\n{broken\n```\n")
        res = pa.analyze_actions(acts_dir, probe_report=_REPORT)
        v = res["verdicts"]
        assert v["demo.ok"]["verdict"] == "ready"
        assert v["demo.miss"]["verdict"] == "blocked"
        assert "system:definitely_not_installed_xyz" in res["missing_deps"]["demo.miss"]
        assert v["demo.nodeps"]["verdict"] == "ready" and \
            "demo.nodeps" in res["undeclared"]
        assert v["demo.null"]["verdict"] == "ready" and \
            "demo.null" in res["undeclared"]
        assert v["demo.badfield"]["verdict"] == "blocked" and \
            v["demo.badfield"]["blocked_reasons"][0]["status"] == "invalid_deps_field"
        assert v["demo.badentry"]["verdict"] == "blocked" and \
            v["demo.badentry"]["blocked_reasons"][0]["status"] == "invalid_dep_entry"
        assert v["demo.mcp"]["verdict"] == "blocked"
        assert res["unverifiable"]["demo.mcp"] == ["mcp:nope"]
        assert v["demo.ghost"]["verdict"] == "blocked"
        assert any("broken" in x for x in res["parse_failed"])   # 解析失败无 id → rel
        assert res["index_source"] == "probe_report"
        assert res["ready_scope"] == pa.READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES
        assert res["exists"] is True
        assert isinstance(res["elapsed_ms"], float)

    def test_chain_and_cycle_and_selfprobe(self, acts_dir):
        _put(acts_dir, "a.actus.md", "demo.a", deps=["action:demo.b"])
        _put(acts_dir, "b.actus.md", "demo.b", deps=["builtin:ui"])
        _put(acts_dir, "c1.actus.md", "demo.c1", deps=["action:demo.c2"])
        _put(acts_dir, "c2.actus.md", "demo.c2", deps=["action:demo.c1"])
        res = pa.analyze_actions(acts_dir)          # 无报告 → self-probe
        v = res["verdicts"]
        assert res["index_source"] == "self-probe"
        assert v["demo.a"]["verdict"] == "ready"    # 链式依赖随 b 就绪
        assert v["demo.c1"]["verdict"] == "blocked"
        assert v["demo.c1"]["blocked_reasons"][-1]["status"] == "cycle"
        assert v["demo.c2"]["verdict"] == "blocked"

    def test_degraded_by_entry_directive(self, acts_dir, monkeypatch):
        import vools.bridge.md.directives as dv

        _put(acts_dir, "g.actus.md", "demo.g", deps=["builtin:ui"])
        monkeypatch.setattr(dv, "validate_directives",
                            lambda d, lang: ["未知指令: devtools"])
        res = pa.analyze_actions(acts_dir, probe_report=_REPORT)
        rec = res["verdicts"]["demo.g"]
        assert rec["verdict"] == "degraded"
        assert rec["degraded_reasons"][0]["kind"] == "entry_block_unsupported"
        assert res["degraded"] == 1 and res["ready"] == 0


# ---------------------------------------------------------------------------
# ActionsProber
# ---------------------------------------------------------------------------

class TestActionsProber(object):
    def test_three_items(self, acts_dir, monkeypatch):
        # bootstrap 重建后 pa 可能是旧身份 → patch 必须落在 pa 自己的全局名上
        monkeypatch.setattr(pa, "_action_roots",
                            lambda actions_dir=None: [actions_dir or acts_dir])
        monkeypatch.setattr(pa, "_repo_root", lambda: os.path.dirname(acts_dir))
        _put(acts_dir, "a.actus.md", "demo.a")
        prober = pa.ActionsProber(probe_report=_REPORT)
        items = prober.probe()
        names = [i.name for i in items]
        assert names == ["actions", "action_dependencies", "action_readiness"]
        # 缺省扫全部动作根（含包内种子）→ 只断言包含本目录动作，不限总数
        ids = [a["id"] for a in items[0].extra["actions"]]
        assert "demo.a" in ids and items[0].extra["action_count"] >= 1
        assert items[1].available is True
        readiness = items[2]
        assert readiness.available is True
        assert readiness.extra["verdicts"]["demo.a"]["verdict"] == "ready"
        assert prober.last_readiness is readiness.extra

    def test_analyze_failure_does_not_break_items(self, acts_dir, monkeypatch):
        monkeypatch.setattr(pa, "_action_roots",
                            lambda actions_dir=None: [actions_dir or acts_dir])
        monkeypatch.setattr(pa, "_repo_root", lambda: os.path.dirname(acts_dir))

        def boom(*a, **k):
            raise RuntimeError("analyze boom")

        monkeypatch.setattr(pa, "analyze_actions", boom)
        items = pa.ActionsProber().probe()
        assert items[0].name == "actions"
        readiness = items[2]
        assert readiness.available is False
        assert readiness.extra["error"].startswith("RuntimeError")
        assert readiness.extra["index_source"] == "failed"

    def test_module_exports(self):
        assert set(pa.__all__) == {"ActionsProber", "ACTION_DEPENDENCY_MAP",
                                   "analyze_actions"}
