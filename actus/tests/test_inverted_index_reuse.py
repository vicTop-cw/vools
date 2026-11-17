# -*- coding: utf-8 -*-
"""P1 反向索引复用与等价性测试（提升计划 P0）。

验证统一检索内核（registry.search_params）真正复用 indexer 构建的
`_meta/actions.index.json` 中 by_kind/by_purpose/by_industry/by_name/by_md5
反向索引做预过滤：
- 维度命中反向索引 → 先按索引求交集得到候选集，再对候选集评分/切片，
  替代对 `actions` 全量的线性扫描；
- **等价性**：索引预过滤路径（load_from_index 载入 by_*）与全量线性扫描
  路径（旧索引无 by_*，即清空 `_inv` 回退）返回结果**完全一致**（有序 id）；
- 向后兼容：旧索引（无 by_* 键）不崩、正常回退全量；
- schema v2.0.0 索引文件结构不被本功能改动（load_from_index 只读）。
"""

import pytest

from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, SearchParams


@pytest.fixture(autouse=True)
def _repo_root_to_tmp(tmp_path, monkeypatch):
    """测试卫生：`scan_actions` 的 mtime 缓存只认 `_repo_root()`，
    不隔离会把缓存写进真实仓库 `_meta/`。指到 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))


ACTIONS = [
    # (aid, name, kind, purpose, industry, author, tags, desc)
    ("test.inv.alpha", "Alpha Compute", "exec", "compute", "general",
     "alice", ["alpha", "math"], "反向索引复用测试：计算类动作"),
    ("test.inv.beta", "Beta File Ops", "exec", "automation", "general",
     "alice", ["beta", "file"], "反向索引复用测试：文件操作动作"),
    ("test.inv.gamma", "Gamma Demo", "demo", "compute", "finance",
     "bob", ["gamma", "demo"], "反向索引复用测试：演示动作"),
    ("test.inv.delta", "Delta Template", "template", "control", "health",
     "bob", ["delta", "template"], "反向索引复用测试：模板动作"),
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
def indexed_pair(tmp_path):
    """构造两个数据同源但索引形态不同的 registry：

    - `reg_with`：load_from_index 正常载入 by_* 反向索引（P1 预过滤路径）；
    - `reg_ref`：同一索引 load 后清空 `_inv`（等价于旧索引无 by_*），
      走全量线性扫描回退路径（等价性基准）。
    二者 `_entries` / `_name_key_of` / `_id_md5` 完全一致。
    """
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid, name, kind, purpose, industry, author, tags, desc in ACTIONS:
        (actions_dir / f"{aid}.actus.schema.md").write_text(
            _action_md(aid, name, kind, purpose, industry, author, tags, desc),
            encoding="utf-8")
    meta_dir = str(tmp_path / "meta")
    idx = build_index(actions_dir=str(actions_dir), meta_dir=meta_dir, write=True)
    # 固定 actions 键序 = 注册序（空查询"最近注册在前"依赖插入序），
    # 与 test_search_unified_entry.py 同一口径。
    ordered = {}
    for aid, *_rest in ACTIONS:
        if aid in idx.get("actions", {}):
            ordered[aid] = idx["actions"][aid]
    for aid in idx.get("actions", {}):
        if aid not in ordered:
            ordered[aid] = idx["actions"][aid]
    idx["actions"] = ordered

    reg_with = ActionRegistry()
    reg_with.load_from_index(idx)
    reg_ref = ActionRegistry()
    reg_ref.load_from_index(idx)
    reg_ref._inv.clear()  # 模拟旧索引无 by_* → 全量回退
    return reg_with, reg_ref, idx


def _ids(entries):
    return [e.id for e in entries]


class TestInvIndexLoaded:
    """反向索引确实被 load_from_index 提取、内容与 entries 一致。"""

    def test_inv_has_all_dimensions(self, indexed_pair):
        reg, _, _ = indexed_pair
        # T0r14：维度集合新增 languages / trust（与 indexer 建键对齐）
        assert set(reg._inv) == {"kind", "purpose", "industry", "name", "md5",
                                 "languages", "trust"}

    def test_inv_members_subset_of_entries(self, indexed_pair):
        reg, _, _ = indexed_pair
        entry_ids = set(reg._entries)
        for dim in ("kind", "purpose", "industry", "name"):
            for ids in reg._inv[dim].values():
                assert set(ids) <= entry_ids
        assert set(reg._inv["md5"].values()) <= entry_ids

    def test_inv_kind_matches_entry_kind(self, indexed_pair):
        reg, _, _ = indexed_pair
        for aid, _, kind, _, _, _, _, _ in ACTIONS:
            assert aid in reg._inv["kind"].get(kind, [])

    def test_inv_md5_is_single_value_map(self, indexed_pair):
        reg, _, idx = indexed_pair
        for md5, aid in reg._inv["md5"].items():
            assert isinstance(md5, str) and len(md5) == 32
            assert isinstance(aid, str)
            assert idx["actions"][aid].get("md5") == md5

    def test_inv_index_not_mutated(self, indexed_pair):
        reg, _, idx = indexed_pair
        schema_before = idx["schema_version"]
        by_keys_before = sorted(k for k in idx if k.startswith("by_"))
        # 触发一次检索（含维度），确认 load/search 不修改索引结构
        reg.search_params(SearchParams(kind="exec", query="alpha"))
        assert idx["schema_version"] == schema_before
        assert sorted(k for k in idx if k.startswith("by_")) == by_keys_before


class TestDimensionEquivalence:
    """索引预过滤 vs 全量扫描：结果完全一致（含大小写归一与未命中值）。"""

    @pytest.mark.parametrize("kind", ["exec", "demo", "template",
                                      "EXEC", "Demo", "nope", ""])
    def test_kind(self, indexed_pair, kind):
        reg, ref, _ = indexed_pair
        assert _ids(reg.search_params(SearchParams(kind=kind))) == \
               _ids(ref.search_params(SearchParams(kind=kind)))

    @pytest.mark.parametrize("purpose", ["compute", "automation", "control",
                                         "COMPUTE", "nope", ""])
    def test_purpose(self, indexed_pair, purpose):
        reg, ref, _ = indexed_pair
        assert _ids(reg.search_params(SearchParams(purpose=purpose))) == \
               _ids(ref.search_params(SearchParams(purpose=purpose)))

    @pytest.mark.parametrize("industry", ["general", "finance", "health",
                                          "GENERAL", "nope", ""])
    def test_industry(self, indexed_pair, industry):
        reg, ref, _ = indexed_pair
        assert _ids(reg.search_params(SearchParams(industry=industry))) == \
               _ids(ref.search_params(SearchParams(industry=industry)))

    @pytest.mark.parametrize("name", ["Alpha Compute", "alpha compute",
                                      "GAMMA DEMO", "nope", ""])
    def test_name(self, indexed_pair, name):
        reg, ref, _ = indexed_pair
        assert _ids(reg.search_params(SearchParams(name=name))) == \
               _ids(ref.search_params(SearchParams(name=name)))

    def test_md5(self, indexed_pair):
        reg, ref, idx = indexed_pair
        assert reg._inv["md5"], "测试夹具应生成 by_md5 反向索引"
        md5 = next(iter(reg._inv["md5"]))
        assert _ids(reg.search_params(SearchParams(md5=md5))) == \
               _ids(ref.search_params(SearchParams(md5=md5)))
        # 未命中 md5 → 两边一致（空结果）
        assert _ids(reg.search_params(SearchParams(md5="0" * 32))) == \
               _ids(ref.search_params(SearchParams(md5="0" * 32)))


class TestQueryAndPagingEquivalence:
    """query 子串评分、空查询、多维度组合、分页：预过滤与全量一致。"""

    def test_query_substring(self, indexed_pair):
        reg, ref, _ = indexed_pair
        for query in ("alpha", "compute", "exec", "calc", ""):
            assert _ids(reg.search_params(SearchParams(query=query))) == \
                   _ids(ref.search_params(SearchParams(query=query)))

    def test_query_with_dimension(self, indexed_pair):
        reg, ref, _ = indexed_pair
        for query in ("alpha", "ops", "demo", ""):
            for kind in ("exec", "demo", None):
                got = _ids(reg.search_params(SearchParams(query=query, kind=kind)))
                expect = _ids(ref.search_params(SearchParams(query=query, kind=kind)))
                assert got == expect, (query, kind)

    def test_empty_query_dimension_recent_first(self, indexed_pair):
        reg, ref, _ = indexed_pair
        # 空查询 + kind 维度：候选集保持注册序逆序（最近注册在前）
        got = _ids(reg.search_params(SearchParams(kind="exec")))
        expect = _ids(ref.search_params(SearchParams(kind="exec")))
        assert got == expect
        assert got == ["test.inv.beta", "test.inv.alpha"]  # 注册序逆序

    def test_multi_dimension_intersection(self, indexed_pair):
        reg, ref, _ = indexed_pair
        combos = [
            dict(kind="exec", purpose="compute"),
            dict(kind="demo", industry="finance"),
            dict(kind="exec", purpose="compute", industry="general"),
            dict(kind="exec", purpose="nope", industry="general"),
        ]
        for combo in combos:
            got = _ids(reg.search_params(SearchParams(**combo)))
            expect = _ids(ref.search_params(SearchParams(**combo)))
            assert got == expect, combo

    def test_offset_limit(self, indexed_pair):
        reg, ref, _ = indexed_pair
        for limit in (1, 2, 10):
            for offset in (0, 1, 3, 10):
                got = _ids(reg.search_params(SearchParams(kind="exec", limit=limit, offset=offset)))
                expect = _ids(ref.search_params(SearchParams(kind="exec", limit=limit, offset=offset)))
                assert got == expect, (limit, offset)

    def test_no_dimension_same_as_before(self, indexed_pair):
        """无维度过滤时预过滤路径不改变 E1 行为（与全量完全一致）。"""
        reg, ref, _ = indexed_pair
        for query in ("alpha", "compute", "demo", ""):
            assert _ids(reg.search_params(SearchParams(query=query))) == \
                   _ids(ref.search_params(SearchParams(query=query)))

    def test_dimension_with_category_author_tags(self, indexed_pair):
        """category/author/tags 无反向索引，由 _filter_entry 在候选集上兜底。"""
        reg, ref, _ = indexed_pair
        got = _ids(reg.search_params(
            SearchParams(kind="exec", author="alice", tags=["alpha"])))
        expect = _ids(ref.search_params(
            SearchParams(kind="exec", author="alice", tags=["alpha"])))
        assert got == expect
        assert got == ["test.inv.alpha"]


class TestBackwardCompat:
    """旧索引（无 by_* 键）不崩、回退全量等价。"""

    def test_load_index_without_by_keys(self, indexed_pair):
        reg, ref, idx = indexed_pair
        old = {k: v for k, v in idx.items() if not k.startswith("by_")}
        assert not any(k.startswith("by_") for k in old)
        old_reg = ActionRegistry()
        old_reg.load_from_index(old)
        assert not old_reg._inv
        assert len(old_reg._entries) == len(reg._entries)
        for query in ("alpha", "compute", ""):
            for kind in ("exec", "demo", None):
                assert _ids(old_reg.search_params(SearchParams(query=query, kind=kind))) == \
                       _ids(reg.search_params(SearchParams(query=query, kind=kind)))

    def test_load_index_without_name_md5_actions(self, indexed_pair):
        """部分维度缺反向索引（如 by_name/by_md5 为空 dict）时回退等价。"""
        reg, ref, idx = indexed_pair
        partial = dict(idx)
        partial["by_name"] = {}
        partial["by_md5"] = {}
        p_reg = ActionRegistry()
        p_reg.load_from_index(partial)
        assert "name" not in p_reg._inv
        for name in ("alpha compute", "nope", ""):
            assert _ids(p_reg.search_params(SearchParams(name=name))) == \
                   _ids(ref.search_params(SearchParams(name=name)))
