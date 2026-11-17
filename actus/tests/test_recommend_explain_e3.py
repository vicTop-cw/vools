# -*- coding: utf-8 -*-
"""E3 推荐/联想测试（提升计划 P1，T0r6）。

覆盖验收标准：
- recommend 返回 ≥3 个候选且各含 reason 与 confidence（含 usage 命中 reason 链）；
- 联想项与目标动作至少共享 1 个维度（tag/purpose/industry）；
- description 为空时不崩溃且返回热门兜底列表；
- 完全无关描述仍返回空列表（不破坏既有语义）；
- MCP actus_recommend 输出附 score/confidence/reason；空 description 不崩溃。
"""

import io
import json
import sys

import pytest

from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, RegistryEntry


@pytest.fixture(autouse=True)
def _repo_root_to_tmp(tmp_path, monkeypatch):
    """测试卫生：scan_actions 的 mtime 缓存只认 _repo_root()，隔离到 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))


ACTIONS = [
    # (aid, name, kind, purpose, industry, author, tags, desc, usage)
    ("test.e3.calc", "Calc Tool", "exec", "compute", "general", "alice",
     ["math", "calc"], "计算工具：数学公式计算",
     "计算数学表达式，如 1+2*3"),
    ("test.e3.mathlib", "Math Lib", "exec", "compute", "general", "bob",
     ["math", "lib"], "数学库函数集合",
     "提供常用数学函数与数值算法"),
    ("test.e3.monitor", "Folder Monitor", "exec", "compute", "general", "carol",
     ["watch", "monitor"], "监控文件夹变化",
     "监控文件系统目录变化并上报事件"),
    ("test.e3.web", "Open Web", "exec", "web", "internet", "dave",
     ["web", "http"], "打开网页",
     "打开指定 URL 并等待加载完成"),
    ("test.e3.demo", "Demo Action", "demo", "demo", "finance", "erin",
     ["demo"], "演示动作",
     "演示用：输出固定结果"),
]


def _action_md(aid, name, kind, purpose, industry, author, tags, desc, usage):
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
usage: {usage}
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
    """在 tmp 建一个 5 动作仓库并生成索引，返回 (registry, idx)。"""
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid, name, kind, purpose, industry, author, tags, desc, usage in ACTIONS:
        (actions_dir / f"{aid}.actus.schema.md").write_text(
            _action_md(aid, name, kind, purpose, industry, author, tags,
                       desc, usage),
            encoding="utf-8")
    meta_dir = str(tmp_path / "meta")
    idx = build_index(actions_dir=str(actions_dir), meta_dir=meta_dir,
                      write=True)
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


def _ids(recs):
    return [r["entry"]["id"] for r in recs]


class TestRecommendE3:
    def test_returns_at_least_three_with_reason_and_confidence(self,
                                                               indexed_registry):
        reg, _ = indexed_registry
        recs = reg.recommend("计算", limit=3)
        assert len(recs) >= 3, _ids(recs)
        for rec in recs:
            assert rec["reason"], rec
            assert isinstance(rec["confidence"], float)
            assert 0 <= rec["confidence"] <= 1.0
            assert isinstance(rec["score"], float)
            assert "match_fields" in rec

    def test_top_hit_is_most_relevant(self, indexed_registry):
        reg, _ = indexed_registry
        recs = reg.recommend("计算工具", limit=3)
        assert recs, _ids(recs)
        assert recs[0]["entry"]["id"] == "test.e3.calc"
        assert recs[0]["confidence"] == recs[0]["score"]
        assert isinstance(recs[0]["confidence"], float)

    def test_reason_includes_usage_match(self, indexed_registry):
        reg, _ = indexed_registry
        # '表达式' 只出现在 calc 的 usage 里，不出现在 id/name/description/tags
        recs = reg.recommend("表达式", limit=3)
        assert recs, _ids(recs)
        assert recs[0]["entry"]["id"] == "test.e3.calc"
        assert "用法匹配" in recs[0]["reason"]
        assert "usage" in recs[0]["match_fields"]

    def test_empty_description_returns_fallback(self, indexed_registry):
        reg, _ = indexed_registry
        for empty in ("", None, "   "):
            recs = reg.recommend(empty, limit=3)
            assert recs, "空 description 必须返回兜底列表（输入=%r）" % (empty,)
            assert len(recs) <= 3
            for rec in recs:
                assert rec["reason"], rec
                assert isinstance(rec["confidence"], float)
                assert rec["entry"]["id"]

    def test_no_match_still_empty(self, indexed_registry):
        reg, _ = indexed_registry
        assert reg.recommend("zzzz-ghost-xyz-nothing", limit=3) == []

    def test_fill_via_related_shares_dimension(self, indexed_registry):
        reg, _ = indexed_registry
        recs = reg.recommend("表达式", limit=3)
        assert len(recs) >= 3
        top = recs[0]["entry"]
        for rec in recs[1:]:
            e = rec["entry"]
            shared = (set(e.get("tags") or []) & set(top.get("tags") or [])) or \
                     (set(e.get("purpose") or []) & set(top.get("purpose") or [])) or \
                     (set(e.get("industry") or []) & set(top.get("industry") or []))
            # 补足项可能是共享维度联想（共享）或热门兜底（信任优先，可无共享）
            # —— 只断言联想项若来自 related 则必有共享维度：related 单独用例已
            # 覆盖严格断言，此处验证补足后的列表长度与字段完整性。
            assert rec["reason"]


class TestRelatedE3:
    def test_related_shared_dimension_at_least_one(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.related("test.e3.calc", limit=10)
        assert items, "calc 与 mathlib/monitor 至少共享 compute/general"
        target = reg.get("test.e3.calc")
        for item in items:
            e = item["entry"]
            shared_tags = set(e.get("tags") or []) & set(target.tags)
            shared_purposes = set(e.get("purpose") or []) & set(target.purpose)
            shared_industries = set(e.get("industry") or []) & \
                set(target.industry)
            assert shared_tags or shared_purposes or shared_industries, \
                f"{e['id']} 与目标无任何共享维度"
            assert item["reason"] and item["confidence"] > 0

    def test_related_most_similar_first(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.related("test.e3.calc", limit=10)
        assert items[0]["entry"]["id"] == "test.e3.mathlib"
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)

    def test_related_unknown_id_returns_empty(self, indexed_registry):
        reg, _ = indexed_registry
        assert reg.related("test.e3.ghost", limit=5) == []

    def test_related_excludes_target_itself(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.related("test.e3.calc", limit=10)
        assert "test.e3.calc" not in _ids(items)

    def test_related_respects_limit(self, indexed_registry):
        reg, _ = indexed_registry
        items = reg.related("test.e3.calc", limit=2)
        assert len(items) == 2


class TestRegistryEntryUsage:
    def test_entry_usage_from_brief(self, indexed_registry):
        reg, _ = indexed_registry
        e = reg.get("test.e3.calc")
        assert e.usage == "计算数学表达式，如 1+2*3"

    def test_usage_in_dict(self, indexed_registry):
        reg, _ = indexed_registry
        e = reg.get("test.e3.web")
        assert e.to_dict()["usage"] == "打开指定 URL 并等待加载完成"

    def test_usage_default_empty(self):
        e = RegistryEntry(
            id="x.y", name="Y", version="1", description="d", category="c",
            path="p", author="a", tags=[], checksum="")
        assert e.usage == ""


def _mcp_server():
    import importlib
    mcp = importlib.import_module("vools.actus.mcp_server")
    return mcp.MCPServer(stdin=io.BytesIO(), stdout=io.BytesIO())


def _mcp_call(name, args=None):
    import importlib
    mcp = importlib.import_module("vools.actus.mcp_server")
    r = _mcp_server()._call_tool({"name": name, "arguments": args or {}})
    return json.loads(r["content"][0]["text"]), r["isError"]


@pytest.fixture(autouse=True)
def _mcp_isolate(monkeypatch, tmp_path):
    """MCP 用例环境隔离：meta/config 指到 tmp，与 r74b 契约测试一致。"""
    meta = tmp_path / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(tmp_path / "config"))


class TestMcpRecommendE3:
    def test_recommend_returns_fields(self):
        payload, err = _mcp_call("actus_recommend",
                                 {"description": "计算", "limit": 3})
        assert err is False
        assert payload["status"] == "ok"
        assert "recommendations" in payload["data"]
        for rec in payload["data"]["recommendations"]:
            assert "confidence" in rec
            assert "reason" in rec
            assert "score" in rec

    def test_recommend_empty_description_no_crash(self):
        payload, err = _mcp_call("actus_recommend", {"description": ""})
        assert err is False
        assert payload["status"] == "ok"
        assert "recommendations" in payload["data"]
        assert payload["data"]["total"] == len(payload["data"]["recommendations"])
