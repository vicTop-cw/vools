"""E2 结果可读性与上下文解释测试（提升计划 E2）。

覆盖：
- `registry.search_explain`：结果集与 `search` 一致，携带 score /
  match_fields / reason（含"命中 name"、"命中 tag=record"式理由）；
- 空查询：score=0、match_fields=[]、reason=''；
- score 与 `_score_entry` 打分口径一致（同源）；
- CLI 人类输出：单条 ≤4 行、含匹配理由与 kind/purpose/usage 摘要列、
  高信任（trusted / verification=verified）动作带 ★ 视觉标记；
- MCP actus_search：返回行含 score 与 match_fields 字段。
"""

import io
import json
from types import SimpleNamespace

import pytest

from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, SearchParams

# ── 与 test_search_unified_entry.py 同源的 4 动作测试库 ──

ACTIONS = [
    # (aid, name, kind, purpose, industry, author, tags, desc)
    ("test.e2.alpha", "Alpha Compute", "exec", "compute", "general",
     "alice", ["alpha", "math"], "统一检索测试：计算类动作"),
    ("test.e2.beta", "Beta Record Ops", "exec", "automation", "general",
     "alice", ["beta", "record"], "统一检索测试：记录操作动作"),
    ("test.e2.gamma", "Gamma Demo", "demo", "compute", "finance",
     "bob", ["gamma", "demo"], "统一检索测试：演示动作"),
    ("test.e2.delta", "Delta Template", "template", "control", "health",
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


@pytest.fixture(autouse=True)
def _repo_root_to_tmp(tmp_path, monkeypatch):
    """测试卫生：scan_actions 的 mtime 缓存只认 `_repo_root()`。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))


@pytest.fixture
def indexed_registry(tmp_path):
    """在 tmp 建一个 4 动作仓库并生成索引，返回 (registry, index)。"""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid, name, kind, purpose, industry, author, tags, desc in ACTIONS:
        (actions_dir / f"{aid}.actus.schema.md").write_text(
            _action_md(aid, name, kind, purpose, industry, author, tags, desc),
            encoding="utf-8")
    idx = build_index(actions_dir=str(actions_dir),
                      meta_dir=str(tmp_path / "meta"), write=True)
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
    return reg, idx


def _ids(scored):
    return [item['entry'].id for item in scored]


class TestSearchExplain:
    """registry.search_explain 字段与口径。"""

    def test_name_hit_fields(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.search_explain(query="alpha")
        assert _ids(items) == ["test.e2.alpha"]
        assert items[0]['score'] > 0
        assert 'name' in items[0]['match_fields']
        assert items[0]['reason'].startswith('命中')
        assert '命中 name' in items[0]['reason']

    def test_tag_hit_fields(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.search_explain(query="record")
        assert _ids(items) == ["test.e2.beta"]
        assert any(f == 'tag=record' for f in items[0]['match_fields'])
        assert '命中 tag=record' in items[0]['reason']

    def test_id_hit_fields(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.search_explain(query="test.e2.gamma")
        assert _ids(items) == ["test.e2.gamma"]
        assert 'id' in items[0]['match_fields']

    def test_description_hit_fields(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.search_explain(query="记录操作")
        assert _ids(items) == ["test.e2.beta"]
        assert 'description' in items[0]['match_fields']

    def test_empty_query_no_explain(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.search_explain(query="")
        assert len(items) == 4
        for it in items:
            assert it['score'] == 0.0
            assert it['match_fields'] == []
            assert it['reason'] == ''

    def test_results_same_as_search(self, indexed_registry):
        reg, _ = indexed_registry
        for q in ["alpha", "record", "demo", "no_such_word_xyz"]:
            by_search = [e.id for e in reg.search(q)]
            assert _ids(reg.search_explain(query=q)) == by_search

    def test_score_consistent_with_score_entry(self, indexed_registry):
        reg, _ = indexed_registry
        for q in ["alpha", "record ops", "demo", "计算"]:
            items = reg.search_explain(query=q)
            for it in items:
                entry = it['entry']
                ql = q.lower().strip()
                words = set(ql.split())
                expect = round(reg._score_entry(entry, ql, words), 3)
                assert it['score'] == expect

    def test_search_explain_params_alias(self, indexed_registry):
        reg, _ = indexed_registry
        by_kw = reg.search_explain(query="alpha")
        by_params = reg.search_explain_params(SearchParams(query="alpha"))
        assert _ids(by_kw) == _ids(by_params)
        assert by_kw[0]['score'] == by_params[0]['score']


def _make_cli_reg(monkeypatch, idx, scored):
    """monkeypatch ActionRegistry / load_index，返回 (calls, reg)。"""
    calls = []

    class FakeReg:
        def load_from_index(self, i):
            calls.append(("load_from_index", i))

        def search(self, **kw):
            calls.append(("search", kw))
            return []

        def search_explain(self, **kw):
            calls.append(("search_explain", kw))
            return scored

    monkeypatch.setattr("vools.actus.registry.ActionRegistry",
                        lambda: FakeReg())
    monkeypatch.setattr("vools.actus.indexer.load_index",
                        lambda build=False: idx)
    return calls


class TestCliHumanOutput:
    """CLI 人类输出：单条 ≤4 行、含匹配理由与摘要列、高信任 ★ 标记。"""

    @staticmethod
    def _entry():
        return SimpleNamespace(
            id="a.b.record", name="Record Ops", version="1.0.0",
            trust_level="trusted", description="记录操作动作",
            author="alice", category="cat", tags=["record", "beta"],
            kind="exec", purpose=["automation"], industry=["general"])

    def test_single_hit_four_lines(self, monkeypatch, capsys):
        from vools.actus import cli as actus_cli
        idx = {"actions": {"a.b.record": {
            "name": "Record Ops", "trust": "trusted", "status": "valid",
            "usage": "actus_a_b_record({'op': 'upsert'})"}}}
        scored = [{'entry': self._entry(), 'score': 0.8,
                   'match_fields': ['name', 'tag=record'],
                   'reason': '命中 name、命中 tag=record'}]
        _make_cli_reg(monkeypatch, idx, scored)
        ns = SimpleNamespace(source="local", url=None, query="record",
                             category=None, author=None, tag=None,
                             limit=20, json_output=False,
                             kind=None, purpose=None, industry=None,
                             offset=0)
        assert actus_cli._cmd_search(ns) == 0
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if l.strip()]
        # 头部 1 行 + 单条 4 行（末尾空行被过滤）
        assert len(lines) == 5
        assert '找到 1 个动作' in lines[0]
        body = lines[1:]
        assert len(body) == 4
        assert '★' in body[0]            # trusted → 视觉标记
        assert '类别=exec' in body[0]
        assert '用途=automation' in body[0]
        assert '得分=0.80' in body[0]
        assert '用法:' in body[2]          # usage 摘要列
        assert 'actus_a_b_record' in body[2]
        assert '命中 name、命中 tag=record' in body[3]
        assert '标签:' in body[3]

    def test_low_trust_no_mark(self, monkeypatch, capsys):
        from vools.actus import cli as actus_cli
        entry = self._entry()
        entry.trust_level = "community"
        idx = {"actions": {"a.b.record": {"trust": "community"}}}
        scored = [{'entry': entry, 'score': 0.4,
                   'match_fields': ['name'], 'reason': '命中 name'}]
        _make_cli_reg(monkeypatch, idx, scored)
        ns = SimpleNamespace(source="local", url=None, query="record",
                             category=None, author=None, tag=None,
                             limit=20, json_output=False,
                             kind=None, purpose=None, industry=None,
                             offset=0)
        assert actus_cli._cmd_search(ns) == 0
        out = capsys.readouterr().out
        body = [l for l in out.splitlines() if l.strip()][1:]
        assert len(body) == 4
        assert '★' not in body[0]

    def test_verified_index_mark(self, monkeypatch, capsys):
        """索引 verification=verified 但 trust 非 trusted 也加 ★。"""
        from vools.actus import cli as actus_cli
        entry = self._entry()
        entry.trust_level = "community"
        idx = {"actions": {"a.b.record": {
            "trust": "community", "verification": "verified"}}}
        scored = [{'entry': entry, 'score': 0.4,
                   'match_fields': ['name'], 'reason': '命中 name'}]
        _make_cli_reg(monkeypatch, idx, scored)
        ns = SimpleNamespace(source="local", url=None, query="record",
                             category=None, author=None, tag=None,
                             limit=20, json_output=False,
                             kind=None, purpose=None, industry=None,
                             offset=0)
        assert actus_cli._cmd_search(ns) == 0
        body = [l for l in capsys.readouterr().out.splitlines() if l.strip()][1:]
        assert '★' in body[0]

    def test_empty_result(self, monkeypatch, capsys):
        from vools.actus import cli as actus_cli
        _make_cli_reg(monkeypatch, {"actions": {}}, [])
        ns = SimpleNamespace(source="local", url=None, query="zzz",
                             category=None, author=None, tag=None,
                             limit=20, json_output=False,
                             kind=None, purpose=None, industry=None,
                             offset=0)
        assert actus_cli._cmd_search(ns) == 0
        assert '未找到' in capsys.readouterr().out


class TestMcpSearchExplainFields:
    """MCP actus_search：返回行含 score 与 match_fields。"""

    @staticmethod
    def _entry():
        return SimpleNamespace(
            id="a.b.record", name="Record Ops", version="1.0.0",
            trust_level="sandbox", kind="exec", purpose=["automation"],
            industry=["general"], tags=["record"], description="记录操作",
            category="cat", author="alice")

    def _server_reg(self, monkeypatch, idx, scored):
        calls = []

        class FakeReg:
            def load_from_index(self, i):
                calls.append(("load_from_index", i))

            def search_explain(self, **kw):
                calls.append(("search_explain", kw))
                return scored

            def search_explain_params_with_total(self, params):
                # E4：MCP actus_search 委托解释版分页变体。
                calls.append(("search_explain_params_with_total", params))
                return scored, len(scored)

        monkeypatch.setattr("vools.actus.registry.ActionRegistry",
                            lambda: FakeReg())
        monkeypatch.setattr("vools.actus.indexer.load_index",
                            lambda: idx)
        return calls

    def test_rows_carry_score_and_match_fields(self, monkeypatch):
        from vools.actus import mcp_server
        idx = {"actions": {"a.b.record": {
            "name": "Record Ops", "trust": "sandbox", "status": "valid"}}}
        scored = [{'entry': self._entry(), 'score': 0.7,
                   'match_fields': ['name', 'tag=record'],
                   'reason': '命中 name、命中 tag=record'}]
        self._server_reg(monkeypatch, idx, scored)
        server = mcp_server.MCPServer(stdout=io.BytesIO())
        resp = server._call_tool({"name": "actus_search", "arguments": {
            "query": "record", "limit": 5}})
        assert resp.get("isError") is False
        payload = json.loads(resp["content"][0]["text"])
        assert payload.get("status") == "ok"
        assert payload["data"]["total"] == 1
        row = payload["data"]["actions"][0]
        assert row["id"] == "a.b.record"
        assert row["score"] == 0.7
        assert row["match_fields"] == ["name", "tag=record"]

    def test_empty_query_rows_have_zero_fields(self, monkeypatch):
        from vools.actus import mcp_server
        idx = {"actions": {"a.b.record": {
            "name": "Record Ops", "trust": "sandbox", "status": "valid"}}}
        scored = [{'entry': self._entry(), 'score': 0.0,
                   'match_fields': [], 'reason': ''}]
        self._server_reg(monkeypatch, idx, scored)
        server = mcp_server.MCPServer(stdout=io.BytesIO())
        resp = server._call_tool({"name": "actus_search",
                                  "arguments": {"query": ""}})
        payload = json.loads(resp["content"][0]["text"])
        row = payload["data"]["actions"][0]
        assert row["score"] == 0.0
        assert row["match_fields"] == []
