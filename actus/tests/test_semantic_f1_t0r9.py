"""T0r9: F1 语义检索（轻量 TF-IDF 余弦 + 可配置权重融合）测试。

覆盖提升计划 F1「语义检索」验收标准：
- 语义开启时融合排序正确：跨义词查询（关键词基线零命中）由语义分召回；
- 权重生效：`semantic_weight=0` 时与关键词基线完全一致；权重/阈值
  影响收录与融合分；越界权重钳制不崩溃；
- 禁用/无模型优雅回退：`semantic=False` 与关键词基线一致；embedder
  缺失/编码失败/构建异常均回退关键词路径，行为不回归；
- `search_explain` 纯语义命中 reason='语义相近'，排序与 `search` 一致；
- `recommend` 语义融合与回退等价；
- 空查询与倒排开关交互不回归。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

import pytest

from vools.actus.registry import (
    ActionRegistry,
    RegistryEntry,
    SearchParams,
    _SEM_CUTOFF,
    _SEMANTIC_WEIGHT,
)
from vools.actus.semantic import SemanticScorer, try_load_embedder

#: 混合条目库：web/calc/monitor/notes 四类，中英字段混合。
#: `打开网页` 为跨义词查询——关键词基线零命中（usage 只含"浏览网页 打开链接"，
#: 无整串"打开网页"；desc/tags/id 均英文），语义路径经中文 2-gram 命中。
MIXED = [
    dict(id="actus.web.open", name="Open Browser",
         desc="open browser and navigate web pages",
         usage="浏览网页 打开链接", tags=["web", "browser"]),
    dict(id="actus.calc.tax", name="Tax Calculator",
         desc="compute tax and finance numbers",
         usage="税务计算", tags=["finance", "tax"]),
    dict(id="actus.monitor.dir", name="Folder Monitor",
         desc="watch filesystem folder for changes",
         usage="监控文件夹变化", tags=["monitor", "watch"]),
    dict(id="actus.notes.md", name="Markdown Notes",
         desc="write markdown notes records",
         usage="记录笔记", tags=["notes"]),
]


def _mk_registry(specs=None):
    """构造 ActionRegistry（直接塞 entries，不落盘；语义分惰性构建）。"""
    reg = ActionRegistry()
    for i, s in enumerate(specs or MIXED):
        reg._entries[s["id"]] = RegistryEntry(
            id=s["id"], name=s["name"], version="1.0.0",
            description=s["desc"], category="bench",
            path=f"bench/{s['id']}.actus.md", author="tester",
            tags=s["tags"], checksum=f"abc{i}",
            usage=s.get("usage", ""))
    return reg


def _ids(entries):
    out = []
    for e in entries:
        if isinstance(e, dict):
            if "entry" in e:
                e = e["entry"]
            out.append(e["id"])
        else:
            out.append(e.id)
    return out


def _kw(reg, q, **kw):
    """关键词基线路径（semantic=False，默认）。"""
    return reg.search(q, **kw)


def _sem(reg, q, **kw):
    """语义融合路径。"""
    return reg.search(q, semantic=True, **kw)


class TestSemanticRecall:
    """语义开启时跨义词召回与融合排序正确。"""

    def test_cross_term_recall_only_when_semantic(self):
        reg = _mk_registry()
        # 关键词基线：跨义词零命中
        assert _ids(_kw(reg, "打开网页")) == []
        # 语义开启：中文 2-gram 共享"打开/网页" → 召回 web.open
        assert "actus.web.open" in _ids(_sem(reg, "打开网页"))

    def test_semantic_scores_normalized(self):
        reg = _mk_registry()
        sem = reg._semantic_scores("打开网页")
        assert sem
        for v in sem.values():
            assert 0.0 <= v <= 1.0

    def test_fused_order_matches_fused_score(self):
        """融合分 = (1-w)*kw + w*sem 决定排序，最高分条目必然在首。"""
        reg = _mk_registry()
        w = _SEMANTIC_WEIGHT
        for q in ("web", "tax", "监控", "notes"):
            hits = _sem(reg, q, limit=10)
            assert hits
            sem_scores = reg._semantic_scores(q.lower())
            kws = {e.id: reg._score_entry(e, q.lower(), set(q.lower().split()))
                   for e in hits}
            fused = {e.id: ActionRegistry._fuse_scores(
                kws[e.id], sem_scores.get(e.id, 0.0), w) for e in hits}
            top = max(fused.values())
            assert fused[hits[0].id] == top, f"{q!r} 首条非融合最高分"


class TestWeightEffects:
    """权重生效：w=0 完全回退关键词；w/cutoff 控制收录。"""

    def test_weight_zero_equals_keyword_baseline(self):
        reg = _mk_registry()
        for q in ("web", "tax", "监控", "notes", "打开网页", "no_such"):
            assert _ids(_sem(reg, q, semantic_weight=0.0)) == _ids(_kw(reg, q)), q

    def test_weight_zero_drops_pure_semantic_hits(self):
        """纯语义命中（kw=0）在 w=0 时不收录（保持关键词基线）。"""
        reg = _mk_registry()
        assert "actus.web.open" in _ids(_sem(reg, "打开网页"))
        assert "actus.web.open" not in _ids(_sem(reg, "打开网页", semantic_weight=0.0))

    def test_weight_one_keeps_pure_semantic_hits(self):
        reg = _mk_registry()
        assert "actus.web.open" in _ids(_sem(reg, "打开网页", semantic_weight=1.0))

    def test_cutoff_gates_pure_semantic_hits(self):
        """semantic_cutoff 高于语义分时纯语义命中不收录。"""
        reg = _mk_registry()
        assert "actus.web.open" in _ids(_sem(reg, "打开网页", semantic_cutoff=_SEM_CUTOFF))
        assert "actus.web.open" not in _ids(_sem(reg, "打开网页", semantic_cutoff=1.5))

    def test_out_of_range_weights_clamped(self):
        reg = _mk_registry()
        assert _ids(_sem(reg, "web", semantic_weight=-1.0)) == _ids(_sem(reg, "web", semantic_weight=0.0))
        assert _ids(_sem(reg, "web", semantic_weight=2.0)) == _ids(_sem(reg, "web", semantic_weight=1.0))

    def test_fuse_scores_formula(self):
        f = ActionRegistry._fuse_scores
        assert f(0.5, 0.8, 0.4) == pytest.approx(0.5 * 0.6 + 0.8 * 0.4)
        assert f(0.5, 0.8, 0.0) == pytest.approx(0.5)
        assert f(0.5, 0.8, 1.0) == pytest.approx(0.8)
        assert f(0.5, 0.8, 5.0) == pytest.approx(0.8)  # 钳制到 1.0
        assert f(0.5, 0.8, -1.0) == pytest.approx(0.5)  # 钳制到 0.0


class TestGracefulFallback:
    """无模型/禁用时完全回退关键词，行为不回归。"""

    def test_disabled_matches_keyword_baseline(self):
        reg = _mk_registry()
        for q in ("web", "tax", "监控", "打开网页", "browser"):
            assert _ids(_kw(reg, q)) == _ids(reg.search_params(
                SearchParams(query=q, semantic=False)))

    def test_no_embedder_still_fuses_tfidf(self):
        """无 embedder（None）时语义路径走内置 TF-IDF，不崩溃且能召回。"""
        reg = _mk_registry()
        assert reg.semantic_embedder is None
        assert "actus.web.open" in _ids(_sem(reg, "打开网页"))

    def test_broken_embedder_falls_back_tfidf(self):
        """embedder 编码抛异常 → 自动忽略仅走 TF-IDF，结果与无 embedder 相同。"""

        class _BadEmbedder:
            def encode(self, texts):
                raise RuntimeError("model broken")

        reg = _mk_registry()
        reg.semantic_embedder = _BadEmbedder()
        assert _ids(_sem(reg, "打开网页")) == _ids(_sem(_mk_registry(), "打开网页"))

    def test_scorer_build_exception_falls_back_keyword(self, monkeypatch):
        """SemanticScorer 构建失败 → _ensure_semantic 返回 None → 关键词路径。"""
        reg = _mk_registry()

        def _boom(self):
            raise RuntimeError("build failed")

        monkeypatch.setattr(SemanticScorer, "build", _boom)
        for q in ("web", "tax", "打开网页", "no_such"):
            assert _ids(_sem(reg, q)) == _ids(_kw(reg, q)), q

    def test_try_load_embedder_missing_returns_none(self):
        assert try_load_embedder("definitely-not-a-real-model-xyz") is None


class TestExplainSemantic:
    """search_explain 语义解释与排序一致性。"""

    def test_pure_semantic_hit_reason(self):
        reg = _mk_registry()
        out = reg.search_explain("打开网页", semantic=True)
        by_id = {d["entry"].id: d for d in out}
        assert "actus.web.open" in by_id
        d = by_id["actus.web.open"]
        assert d["score"] == 0.0  # 关键词分仍报告 0（既有 E2 契约）
        assert d["reason"] == "语义相近"

    def test_keyword_hit_reason_unchanged(self):
        reg = _mk_registry()
        out = reg.search_explain("web", semantic=True)
        by_id = {d["entry"].id: d for d in out}
        d = by_id["actus.web.open"]
        assert d["score"] > 0.0
        assert "命中" in d["reason"]

    def test_explain_order_matches_search(self):
        reg = _mk_registry()
        for q in ("web", "tax", "打开网页"):
            assert [d["entry"].id for d in reg.search_explain(q, semantic=True)] == \
                   _ids(_sem(reg, q))

    def test_explain_empty_query_same_regardless_semantic(self):
        reg = _mk_registry()
        off = reg.search_explain("")
        on = reg.search_explain("", semantic=True)
        assert len(off) == len(on)
        assert all(d["score"] == 0.0 and d["reason"] == "" for d in on)


class TestRecommendSemantic:
    """recommend 语义融合与回退等价。"""

    def test_recommend_cross_term_recall(self):
        reg = _mk_registry()
        assert _ids(reg.recommend("打开网页", semantic=False)) == []
        assert "actus.web.open" in _ids(reg.recommend("打开网页", semantic=True))

    def test_recommend_weight_zero_matches_baseline(self):
        reg = _mk_registry()
        for q in ("web", "tax", "监控", "打开网页"):
            assert _ids(reg.recommend(q, semantic=True, semantic_weight=0.0)) == \
                   _ids(reg.recommend(q, semantic=False)), q

    def test_recommend_irrelevant_no_crash(self):
        reg = _mk_registry()
        assert reg.recommend("完全无关的xyz描述内容", semantic=True) == []


class TestInteractionRegression:
    """空查询与倒排开关交互不回归。"""

    def test_empty_query_semantic_same_as_disabled(self):
        reg = _mk_registry()
        assert _ids(_sem(reg, "")) == _ids(_kw(reg, ""))

    def test_semantic_ignores_inverted_switch(self):
        """语义分支为独立全量融合循环，use_inverted 开关不改变结果。"""
        reg = _mk_registry()
        on_fast = _ids(reg.search_params(
            SearchParams(query="web", semantic=True, use_inverted=True)))
        on_slow = _ids(reg.search_params(
            SearchParams(query="web", semantic=True, use_inverted=False)))
        assert on_fast == on_slow

    def test_scorer_rebuild_after_entries_change(self):
        reg = _mk_registry()
        assert reg._semantic_scorer is None
        _sem(reg, "打开网页")
        assert reg._semantic_scorer is not None
        # entries 变更入口重置 scorer（惰性重建）
        reg2 = _mk_registry()
        reg2._entries["actus.extra.new"] = RegistryEntry(
            id="actus.extra.new", name="Extra", version="1.0.0",
            description="extra action", category="bench", path="x",
            author="tester", tags=["extra"], checksum="x",
            usage="额外动作")
        assert reg2._semantic_scorer is None
        assert "actus.extra.new" in _ids(_sem(reg2, "额外动作", limit=10))
