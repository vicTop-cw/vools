# -*- coding: utf-8 -*-
"""E1 统一检索入口与输出一致性测试（提升计划 P0）。

覆盖三入口（registry.search / search_params / MCP actus_search 参数口径）
共用同一内核后的行为契约：
- 空查询语义：query 为空 → 按 limit 返回**最近注册**动作（非报错、非全量）；
- 硬过滤：category/author/tags/kind/purpose/industry 全部收敛到 `_filter_entry`；
- 分页：offset+limit 截断一致、不越界；
- 数据源：`load_from_index` 从 indexer 的 actions.index.json（brief）填充，
  保持 schema v2.0.0 结构不破坏（本测试不触碰真实仓库索引）。
"""

import io
import json
from dataclasses import asdict
import os
from types import SimpleNamespace

import pytest

from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, RegistryEntry, SearchParams


@pytest.fixture(autouse=True)
def _repo_root_to_tmp(tmp_path, monkeypatch):
    """测试卫生：`scan_actions` 的 mtime 缓存只认 `_repo_root()`，
    不隔离会把缓存写进真实仓库 `_meta/`。指到 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))


ACTIONS = [
    # (aid, name, kind, purpose, industry, author, tags, desc)
    ("test.unified.alpha", "Alpha Compute", "exec", "compute", "general",
     "alice", ["alpha", "math"], "统一检索测试：计算类动作"),
    ("test.unified.beta", "Beta File Ops", "exec", "automation", "general",
     "alice", ["beta", "file"], "统一检索测试：文件操作动作"),
    ("test.unified.gamma", "Gamma Demo", "demo", "compute", "finance",
     "bob", ["gamma", "demo"], "统一检索测试：演示动作"),
    ("test.unified.delta", "Delta Template", "template", "control", "health",
     "bob", ["delta", "template"], "统一检索测试：模板动作"),
]


def _action_md(aid, name, kind, purpose, industry, author, tags, desc):
    tag_str = ", ".join(tags)
    return f"""---
id: {aid}
name: {name}
version: 1.0.0
trust: sandbox
kind: {kind}
purpose: [{purpose}]
industry: [{industry}]
trigger: [manual]
context_applies: []
entry: main
description: {desc}
author: {author}
platform: desktop
tags: [{tag_str}]
license: mit
pricing: free
declared_features: []
deprecated: false
---

# {name}

## Implementation

```python #!run tag=main
def main():
    return "ok"
```
"""


@pytest.fixture
def indexed_registry(tmp_path):
    """在 tmp 建一个 4 动作仓库并生成索引，返回 (registry, index, actions_dir)。"""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid, name, kind, purpose, industry, author, tags, desc in ACTIONS:
        (actions_dir / f"{aid}.actus.schema.md").write_text(
            _action_md(aid, name, kind, purpose, industry, author, tags, desc),
            encoding="utf-8")
    meta_dir = str(tmp_path / "meta")
    idx = build_index(actions_dir=str(actions_dir), meta_dir=meta_dir, write=True)
    # 索引键序 = 注册序（空查询"最近注册在前"依赖插入序）。
    # 真实索引的 actions 键序来自扫描顺序（文件系统不保证），
    # 测试固定为 ACTIONS 定义序以保证断言确定性。
    ordered = {}
    for aid, *_rest in ACTIONS:
        if aid in idx.get("actions", {}):
            ordered[aid] = idx["actions"][aid]
    for aid in idx.get("actions", {}):
        if aid not in ordered:
            ordered[aid] = idx["actions"][aid]
    idx["actions"] = ordered
    reg = ActionRegistry()
    reg.load_from_index(idx)
    return reg, idx, actions_dir


def _ids(entries):
    return [e.id for e in entries]


class TestLoadFromIndex:
    def test_populates_entries_from_brief(self, indexed_registry):
        reg, idx, _ = indexed_registry
        assert len(reg._entries) == 4
        for aid, _, kind, purpose, industry, author, tags, _ in ACTIONS:
            e = reg._entries[aid]
            assert e.id == aid
            assert e.kind == kind
            assert purpose in (e.purpose or [])
            assert industry in (e.industry or [])
            assert e.author == author
            assert set(e.tags) == set(tags)

    def test_skips_invalid_entries(self):
        reg = ActionRegistry()
        reg.load_from_index({
            "schema_version": "2.0.0",
            "actions": {
                "good.action": {"name": "Good", "kind": "exec"},
                "_invalid:bad/path.actus.md": {"path": "bad"},
            },
        })
        assert list(reg._entries.keys()) == ["good.action"]


class TestEmptyQuerySemantics:
    def test_empty_query_returns_latest_registered(self, indexed_registry):
        reg, _, _ = indexed_registry
        # 注册序 = ACTIONS 顺序；空查询返回最近注册在前（delta 最后注册）
        assert _ids(reg.search("")) == ["test.unified.delta",
                                         "test.unified.gamma",
                                         "test.unified.beta",
                                         "test.unified.alpha"]
        assert _ids(reg.search(None)) == _ids(reg.search(""))

    def test_empty_query_respects_limit(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert len(reg.search("", limit=2)) == 2
        assert _ids(reg.search("", limit=2)) == ["test.unified.delta",
                                                 "test.unified.gamma"]

    def test_empty_query_with_offset(self, indexed_registry):
        reg, _, _ = indexed_registry
        page1 = _ids(reg.search("", limit=2, offset=0))
        page2 = _ids(reg.search("", limit=2, offset=2))
        assert page1 + page2 == _ids(reg.search(""))
        # 越界 offset 返回空
        assert reg.search("", limit=2, offset=99) == []


class TestSearchParamsEquivalence:
    def test_search_delegates_to_search_params(self, indexed_registry):
        reg, _, _ = indexed_registry
        kw = dict(query="compute", tags=["alpha"], kind="exec", limit=3)
        assert _ids(reg.search(**kw)) == _ids(reg.search_params(SearchParams(**kw)))

    def test_search_params_filtered_args(self):
        p = SearchParams(query="x", category=None, limit=10, offset=0)
        assert p.filtered_args() == {"query": "x", "limit": 10, "offset": 0}


class TestDimensionFilters:
    def test_kind_filter(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert _ids(reg.search("", kind="exec")) == ["test.unified.beta",
                                                     "test.unified.alpha"]
        assert _ids(reg.search("", kind="demo")) == ["test.unified.gamma"]

    def test_purpose_filter(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert _ids(reg.search("", purpose="automation")) == ["test.unified.beta"]

    def test_industry_filter(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert _ids(reg.search("", industry="finance")) == ["test.unified.gamma"]

    def test_author_and_tag_filter(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert _ids(reg.search("", author="alice")) == ["test.unified.beta",
                                                        "test.unified.alpha"]
        assert _ids(reg.search("", tags=["demo"])) == ["test.unified.gamma"]

    def test_combined_filters(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert reg.search("", kind="exec", purpose="automation",
                          author="alice") == [reg._entries["test.unified.beta"]]


class TestUnifiedEntryConsistency:
    """三入口（registry.search / search_params / MCP 参数口径）一致性。"""

    def test_query_search_consistent_across_entries(self, indexed_registry):
        reg, _, _ = indexed_registry
        for q in ["alpha", "compute", "demo", "no_such_word_xyz"]:
            by_search = _ids(reg.search(q))
            by_params = _ids(reg.search_params(SearchParams(query=q)))
            assert by_search == by_params
            # MCP 口径 = 同一 search()（actus_search 已委托内核）
            by_mcp = _ids(reg.search(query=q))
            assert by_mcp == by_search

    def test_empty_query_consistent_across_entries(self, indexed_registry):
        reg, _, _ = indexed_registry
        assert _ids(reg.search("")) == _ids(reg.search_params(SearchParams(query="")))
        assert _ids(reg.search("")) == _ids(reg.search(None))

    def test_legacy_registry_entry_still_searchable(self):
        """旧 .actus.registry.json 条目（无 kind/purpose/industry）不受影响。"""
        reg = ActionRegistry()
        reg._entries["old.action"] = RegistryEntry(
            id="old.action", name="Old", version="1.0.0",
            description="旧条目", category="system", path="old.actus.md",
            author="tester", tags=["legacy"], checksum="abc")
        assert _ids(reg.search("old")) == ["old.action"]
        assert _ids(reg.search("")) == ["old.action"]  # 空查询：最近注册（唯一）
        assert reg.search("", kind="system") == [reg._entries["old.action"]]
        assert reg.search("", purpose="utility") == []


def _brief(aid, name="N", kind="exec", purpose="utility", industry="general",
           author="tester", tags=None, desc="d"):
    return {"name": name, "version": "1.0.0", "trust": "sandbox",
            "kind": kind, "purpose": purpose, "industry": industry,
            "description": desc, "author": author, "tags": tags or []}


class TestCliDelegation:
    """CLI search 子命令：维度参数透传 + local 数据源走 load_from_index。"""

    @staticmethod
    def _fake_cli(monkeypatch, idx):
        calls = []

        class FakeReg:
            def load_from_index(self, i):
                calls.append(("load_from_index", i))

            def search(self, **kw):
                calls.append(("search", kw))
                return []

            def search_explain(self, **kw):
                calls.append(("search_explain", kw))
                return []

            def search_params_with_total(self, params):
                # E4：CLI --json 委托分页变体；记录 asdict 兼容旧断言。
                calls.append(("search_params_with_total", asdict(params)))
                return [], 0

        monkeypatch.setattr("vools.actus.registry.ActionRegistry",
                            lambda: FakeReg())
        monkeypatch.setattr("vools.actus.indexer.load_index",
                            lambda build=False: idx)
        return calls

    def test_cmd_search_local_uses_load_from_index(self, monkeypatch):
        from vools.actus import cli as actus_cli
        idx = {"actions": {"a": _brief("a")}}
        calls = self._fake_cli(monkeypatch, idx)
        ns = SimpleNamespace(source="local", url=None, query="alpha",
                             category=None, author=None, tag="t1,t2",
                             limit=5, json_output=True,
                             kind="exec", purpose="automation",
                             industry="general", offset=2)
        assert actus_cli._cmd_search(ns) == 0
        assert calls[0][0] == "load_from_index"  # local 数据源统一为索引 brief
        assert calls[0][1] is idx

    def test_cmd_search_passes_dimension_params(self, monkeypatch):
        from vools.actus import cli as actus_cli
        calls = self._fake_cli(monkeypatch, {"actions": {}})
        ns = SimpleNamespace(source="local", url=None, query="alpha",
                             category=None, author=None, tag="t1,t2",
                             limit=5, json_output=True,
                             kind="exec", purpose="automation",
                             industry="general", offset=2)
        assert actus_cli._cmd_search(ns) == 0
        search_kw = calls[-1][1]
        assert search_kw["query"] == "alpha"
        assert search_kw["tags"] == ["t1", "t2"]
        assert search_kw["kind"] == "exec"
        assert search_kw["purpose"] == "automation"
        assert search_kw["industry"] == "general"
        assert search_kw["offset"] == 2
        assert search_kw["limit"] == 5

    def test_cmd_search_getattr_defaults(self, monkeypatch):
        """旧调用方未传新维度参数时（如测试 NS 缺字段）不报错、默认 None/0。"""
        from vools.actus import cli as actus_cli
        calls = self._fake_cli(monkeypatch, {"actions": {}})
        ns = SimpleNamespace(source="local", url=None, query="a",
                             category=None, author=None, tag=None,
                             limit=20, json_output=False)
        assert actus_cli._cmd_search(ns) == 0
        search_kw = calls[-1][1]
        assert search_kw["kind"] is None
        assert search_kw["purpose"] is None
        assert search_kw["industry"] is None
        assert search_kw["offset"] == 0


class TestMCPDelegation:
    """MCP actus_search：委托 registry.search（→ search_params 内核），
    输出保持 {status, data:{actions,total}} 结构。"""

    def test_actus_search_delegates_to_registry(self, monkeypatch):
        from vools.actus import mcp_server
        idx = {"actions": {"a": _brief("a", kind="exec", purpose="automation")}}
        calls = []

        class FakeReg:
            def load_from_index(self, i):
                calls.append(("load_from_index", i))

            def search(self, **kw):
                calls.append(("search", kw))
                return [SimpleNamespace(
                    id="a", name="A", version="1.0.0", trust_level="sandbox",
                    kind="exec", purpose=["automation"], industry=["general"],
                    tags=[], description="d")]

            def search_explain(self, **kw):
                # E2：MCP actus_search 委托 search_explain，返回带解释条目。
                calls.append(("search_explain", kw))
                return [{'entry': SimpleNamespace(
                    id="a", name="A", version="1.0.0", trust_level="sandbox",
                    kind="exec", purpose=["automation"], industry=["general"],
                    tags=[], description="d"),
                    'score': 0.6, 'match_fields': ['name'],
                    'reason': '命中 name'}]

            def search_explain_params_with_total(self, params):
                # E4：MCP actus_search 委托解释版分页变体。
                calls.append(("search_explain_params_with_total",
                              asdict(params)))
                rows = [{'entry': SimpleNamespace(
                    id="a", name="A", version="1.0.0", trust_level="sandbox",
                    kind="exec", purpose=["automation"], industry=["general"],
                    tags=[], description="d"),
                    'score': 0.6, 'match_fields': ['name'],
                    'reason': '命中 name'}]
                return rows, len(rows)

        monkeypatch.setattr("vools.actus.registry.ActionRegistry",
                            lambda: FakeReg())
        monkeypatch.setattr("vools.actus.indexer.load_index",
                            lambda: idx)
        server = mcp_server.MCPServer(stdout=io.BytesIO())
        resp = server._call_tool({"name": "actus_search", "arguments": {
            "query": "alpha", "kind": "exec", "purpose": "automation",
            "limit": 3}})
        assert resp.get("isError") is False
        payload = json.loads(resp["content"][0]["text"])
        assert payload.get("status") == "ok"
        assert payload["data"]["total"] == 1
        assert payload["data"]["actions"][0]["id"] == "a"
        search_kw = calls[-1][1]
        assert search_kw["query"] == "alpha"
        assert search_kw["kind"] == "exec"
        assert search_kw["purpose"] == "automation"
        assert search_kw["industry"] is None
        assert search_kw["limit"] == 3

    def test_actus_search_empty_query_via_registry(self, monkeypatch):
        """空查询不再由 MCP 自行全量返回，委托内核的 limit 语义。"""
        from vools.actus import mcp_server
        idx = {"actions": {}}
        calls = []

        class FakeReg:
            def load_from_index(self, i):
                calls.append(("load_from_index", i))

            def search(self, **kw):
                calls.append(("search", kw))
                return []

            def search_explain(self, **kw):
                calls.append(("search_explain", kw))
                return []

            def search_explain_params_with_total(self, params):
                # E4：空查询同样走解释版分页变体，total=实际匹配数（0）。
                calls.append(("search_explain_params_with_total",
                              asdict(params)))
                return [], 0

        monkeypatch.setattr("vools.actus.registry.ActionRegistry",
                            lambda: FakeReg())
        monkeypatch.setattr("vools.actus.indexer.load_index",
                            lambda: idx)
        server = mcp_server.MCPServer(stdout=io.BytesIO())
        resp = server._call_tool({"name": "actus_search",
                                  "arguments": {"query": ""}})
        assert resp.get("isError") is False
        payload = json.loads(resp["content"][0]["text"])
        assert payload.get("status") == "ok"
        assert payload["data"]["total"] == 0
        assert calls[-1][0] == "search_explain_params_with_total"
        assert calls[-1][1]["query"] == ""
        assert calls[-1][1]["limit"] == 20  # MCP 默认 limit 仍生效
