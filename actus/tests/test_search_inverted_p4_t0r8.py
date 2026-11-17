"""T0r8: P4 检索复杂度优化（倒排/前缀索引）测试。

覆盖提升计划 P4「检索复杂度优化」验收标准：
- 倒排命中与线性扫描结果一致（等价性断言，`use_inverted` 开关对照）；
- 前缀索引（id/name 小写排序数组 + bisect）命中正确；
- P95 ≤ 50ms 基准（模拟 2000 动作库，倒排均值快于线性基线）；
- 候选超过 `_INVERTED_MAX_SCAN` 上界时回退线性且结果一致；
- 词零命中（如中段子串）/ 无空格中文查询回退线性且结果一致；
- entries 变更（load_from_index）后倒排失效、惰性重建。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

import time

import pytest

from vools.actus.registry import (
    ActionRegistry,
    RegistryEntry,
    SearchParams,
    _INVERTED_MAX_SCAN,
)

#: 混合条目库：id/name/description/tags/usage 覆盖 token、token 前缀、
#: id/name 前缀、tag 整串（含空格）等倒排 term 形态。
MIXED = [
    dict(id="bench.action.alpha", name="Alpha Monitor",
         desc="monitor filesystem events compute metrics",
         usage="监控与计算", tags=["alpha", "web tool"]),
    dict(id="bench.action.beta", name="Beta Calculator",
         desc="calculator transform web tooling",
         usage="计算", tags=["beta", "calc"]),
    dict(id="bench.action.gamma", name="Gamma Recorder",
         desc="record operations history",
         usage="记录", tags=["gamma"]),
    dict(id="web.open.browser", name="Open Browser",
         desc="open web browser pages",
         usage="浏览网页", tags=["web", "browser"]),
    dict(id="calc.finance.tax", name="Tax Calculator",
         desc="finance tax calculator",
         usage="税务计算", tags=["finance", "tax"]),
    dict(id="test.e2.alpha", name="Test Alpha",
         desc="e2 alpha record",
         usage="测试记录", tags=["legacy"]),
]


def _mk_registry(specs=None):
    """构造 ActionRegistry（直接塞 entries，不落盘；倒排惰性构建）。"""
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
    return [e.id for e in entries]


def _idset(entries):
    return set(_ids(entries))


def _linear(reg, q, **kw):
    """线性全量打分路径（等价基准）。"""
    return reg.search_params(SearchParams(query=q, use_inverted=False, **kw))


def _inv(reg, q, **kw):
    """倒排/前缀索引加速路径。"""
    return reg.search_params(SearchParams(query=q, use_inverted=True, **kw))


#: 标准查询集：token 精确 / token 前缀 / id 前缀 / tag 整串（跨词）。
STANDARD_QUERIES = [
    "alpha", "monitor", "cal", "calculator", "web", "web tool",
    "bench", "bench.action", "open", "tax", "record",
]


class TestInvertedLinearEquivalence:
    """倒排命中与线性打分结果一致（验收：测试断言等价）。"""

    @pytest.mark.parametrize("q", STANDARD_QUERIES)
    def test_search_results_equivalent(self, q):
        reg = _mk_registry()
        assert _ids(_inv(reg, q)) == _ids(_linear(reg, q))

    def test_standard_queries_use_fast_path(self):
        """标准查询必须走倒排快路径（候选非 None 且非回退）。"""
        reg = _mk_registry()
        reg._ensure_inverted()
        for q in STANDARD_QUERIES:
            cand = reg._inverted_candidates(q.lower(), set(q.lower().split()))
            assert cand is not None, f"{q!r} 意外回退线性"
            assert len(cand) > 0, f"{q!r} 候选为空"

    @pytest.mark.parametrize("q", STANDARD_QUERIES)
    def test_candidates_cover_linear_hits(self, q):
        """倒排候选集合 ⊇ 线性正命中集合（等价性核心）。"""
        reg = _mk_registry()
        reg._ensure_inverted()
        cand = reg._inverted_candidates(q.lower(), set(q.lower().split()))
        if cand is None:
            return  # 回退线性时天然等价（由 search 结果断言覆盖）
        lin_hits = _idset(_linear(reg, q))
        assert lin_hits <= cand

    def test_mid_substring_word_falls_back_linear(self):
        """词仅靠字段中段子串命中（如 'finance.tax' ∈ id）→ 回退线性且等价。"""
        reg = _mk_registry()
        # 'finance.tax' 不是任何 token/前缀，倒排零命中 → 回退线性
        assert _ids(_inv(reg, "finance.tax")) == _ids(_linear(reg, "finance.tax"))
        # 'monitor' 走快路径仍等价
        assert _ids(_inv(reg, "monitor")) == _ids(_linear(reg, "monitor"))

    def test_no_such_query_empty_both_paths(self):
        reg = _mk_registry()
        assert _ids(_inv(reg, "no_such_word_xyz")) == []
        assert _ids(_linear(reg, "no_such_word_xyz")) == []

    def test_cjk_query_falls_back_and_equivalent(self):
        """无空格中文查询（整串 token）倒排/线性一致（回退安全）。"""
        reg = _mk_registry()
        assert _ids(_inv(reg, "监控")) == _ids(_linear(reg, "监控"))
        assert _ids(_inv(reg, "记录")) == _ids(_linear(reg, "记录"))
        assert _ids(_inv(reg, "计算")) == _ids(_linear(reg, "计算"))


class TestPrefixIndex:
    """前缀索引（排序数组 + bisect）命中正确。"""

    def test_id_prefix_hits(self):
        reg = _mk_registry()
        reg._ensure_inverted()
        inv = reg._inverted
        hits = ActionRegistry._prefix_ids(inv, "bench.action")
        assert hits == {"bench.action.alpha", "bench.action.beta",
                        "bench.action.gamma"}
        assert "web.open.browser" not in hits

    def test_name_prefix_hits(self):
        reg = _mk_registry()
        reg._ensure_inverted()
        inv = reg._inverted
        hits = ActionRegistry._prefix_ids(inv, "tax")
        assert hits == {"calc.finance.tax"}  # name "Tax Calculator" 前缀

    def test_prefix_query_returns_correct_ids(self):
        reg = _mk_registry()
        assert _ids(_inv(reg, "bench.action")) == _ids(_linear(reg, "bench.action"))
        by_inv = _ids(_inv(reg, "bench"))
        assert "bench.action.alpha" in by_inv and "bench.action.beta" in by_inv

    def test_exact_prefix_not_substring(self):
        """前缀查询不做中段子串（'ux' 不命中 'tax'）。"""
        reg = _mk_registry()
        reg._ensure_inverted()
        hits = ActionRegistry._prefix_ids(reg._inverted, "ux")
        assert "calc.finance.tax" not in hits


class TestMaxScanFallback:
    """候选超过扫描上界 → 回退线性（限制扫描上界），结果一致。"""

    def test_fallback_when_candidates_exceed_scan_limit(self, monkeypatch):
        reg = _mk_registry()
        # 人为调小上界：'web' 命中 {beta, web.open.browser, ...} > 1 → 回退
        monkeypatch.setattr("vools.actus.registry._INVERTED_MAX_SCAN", 1)
        assert _ids(_inv(reg, "web")) == _ids(_linear(reg, "web"))
        assert _ids(_inv(reg, "monitor")) == _ids(_linear(reg, "monitor"))

    def test_default_scan_limit_respected(self):
        reg = _mk_registry()
        cand = reg._inverted_candidates("web".lower(), {"web"})
        if cand is not None:
            assert len(cand) <= _INVERTED_MAX_SCAN


class TestInvertedIndexLifecycle:
    """构建 / 失效 / 惰性重建。"""

    def test_build_inverted_index_structure(self):
        reg = _mk_registry()
        inv = reg.build_inverted_index()
        assert inv["entry_count"] == len(MIXED)
        assert inv["terms"]["monitor"]  # desc token
        assert inv["terms"]["cal"]  # token 前缀链
        assert inv["terms"]["web tool"]  # tag 整串
        assert inv["id_keys"] == sorted(inv["id_keys"])

    def test_load_from_index_invalidates_inverted(self):
        reg = _mk_registry()
        reg.build_inverted_index()
        assert reg._inverted is not None
        # 模拟 load_from_index 替换条目（复用现条目的 index 结构）
        idx = {"actions": {s["id"]: _brief_of(s) for s in MIXED}}
        reg.load_from_index(idx)
        assert reg._inverted is None  # 失效
        assert _ids(reg.search("monitor")) == ["bench.action.alpha"]

    def test_lazy_build_on_first_search(self):
        reg = _mk_registry()
        assert reg._inverted is None
        _ids(reg.search("monitor"))
        assert reg._inverted is not None
        assert reg._inverted["entry_count"] == len(MIXED)


class TestEmptyAndFilterUnaffected:
    """空查询 / 维度过滤不受倒排启用影响。"""

    def test_empty_query_semantics_unchanged(self):
        reg = _mk_registry()
        # 空查询：最近注册在前
        assert _ids(reg.search(""))[0] == "test.e2.alpha"

    def test_filter_plus_inverted_equivalent(self):
        reg = _mk_registry()
        kw = dict(query="monitor", tags=["alpha"], kind=None, limit=5)
        assert _ids(reg.search_params(SearchParams(**kw))) == _ids(
            reg.search_params(SearchParams(**kw, use_inverted=False)))


# ──────────────────────────── P95 基准 ────────────────────────────

def _bench_registry(n=2000):
    """模拟 2000 动作库：desc 差异化 token，id 同前缀。"""
    reg = ActionRegistry()
    pool = ["monitor", "filesystem", "metrics", "calculator", "transform",
            "web", "aggregate", "scheduler", "pipeline", "alert"]
    for i in range(n):
        t = pool[i % len(pool)]
        reg._entries[f"bench.action.{i:04d}"] = RegistryEntry(
            id=f"bench.action.{i:04d}", name=f"Bench Action {i}",
            version="1.0.0",
            description=(f"action for {t} processing and automation tasks "
                         f"with extra token x{i % 7}"),
            category="bench", path=f"bench/action{i:04d}.actus.md",
            author="bench", tags=["bench", t, "automation"],
            checksum=f"b{i}")
    return reg


BENCH_QUERIES = [
    "monitor", "calculator", "web", "bench", "action",
    "bench.action", "metrics", "transform", "aggregate", "scheduler",
    "pipeline", "alert", "filesystem", "automation", "bench monitor",
]


def _p95(samples_ms):
    s = sorted(samples_ms)
    idx = min(len(s) - 1, int(len(s) * 0.95))
    return s[idx]


class TestP95Benchmark:
    """P4 验收：模拟 2000 动作库查询 P95 ≤ 50ms，倒排均值快于线性基线。"""

    def test_p95_within_50ms_and_faster_than_linear(self):
        reg = _bench_registry()
        reg.build_inverted_index()  # 构建不计入查询延迟

        inv_samples, lin_samples = [], []
        for _ in range(5):
            for q in BENCH_QUERIES:
                t0 = time.perf_counter()
                _ids(_inv(reg, q, limit=10))
                inv_samples.append((time.perf_counter() - t0) * 1000)
        for q in BENCH_QUERIES:
            t0 = time.perf_counter()
            _ids(_linear(reg, q, limit=10))
            lin_samples.append((time.perf_counter() - t0) * 1000)

        inv_p95 = _p95(inv_samples)
        lin_p95 = _p95(lin_samples)
        inv_mean = sum(inv_samples) / len(inv_samples)
        lin_mean = sum(lin_samples) / len(lin_samples)

        # 验收硬指标：P95 ≤ 50ms
        assert inv_p95 <= 50.0, f"倒排 P95={inv_p95:.2f}ms 超限"
        # 验收：倒排快于线性基线（均值对比，防单次抖动）
        assert inv_mean < lin_mean, (
            f"倒排均值 {inv_mean:.2f}ms 未快于线性 {lin_mean:.2f}ms")
        assert lin_p95 <= 500.0  # 线性基线本身也应可测（防环境异常）

    def test_inverted_build_scales_to_2000(self):
        """2000 条构建倒排应可在可接受时间内完成（基准烟测）。"""
        t0 = time.perf_counter()
        reg = _bench_registry()
        inv = reg.build_inverted_index()
        elapsed = time.perf_counter() - t0
        assert inv["entry_count"] == 2000
        assert elapsed < 10.0, f"2000 条构建耗时 {elapsed:.2f}s"


def _brief_of(s):
    """RegistryEntry spec → index brief（load_from_index 用）。"""
    return {
        "name": s["name"], "version": "1.0.0", "trust": "sandbox",
        "kind": "exec", "purpose": ["utility"], "industry": ["general"],
        "description": s["desc"], "author": "tester",
        "tags": s["tags"], "checksum": "x",
    }
