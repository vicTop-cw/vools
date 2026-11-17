"""T0r13（P5 加载与缓存优化）验收测试。

覆盖提升计划验收标准：
1. 进程级 load_index 结果缓存：同进程二次 load_index 命中缓存
   （0 次磁盘读 / 0 次反序列化，仅 os.stat 元数据校验）；
   索引文件变更或 parser_fingerprint 变化 ⇒ 自动失效重建。
2. 懒加载优化：load_index 后 actions 立即可用，by_* 反向索引 /
   dependency_graph 等重字段按需懒加载（首次访问才解析，内容与
   全量解析逐字段相等，解析结果同进程共享）。
3. 命中统计：get_load_cache_stats() 提供 hits/misses/cached_entries 打点。
4. 性能：命中路径显著快于冷启动（≥30% 提升语义：命中 0 磁盘 IO，
   冷启动不解析重字段，耗时较基线全量解析下降）。
5. 兼容红线：返回结构与既有 load_index 契约一致（schema_version=
   2.0.0 不变、顶层键集合一致、actions 立即可用、懒字段 dict 子类可
   被 ActionRegistry.load_from_index 正常消费、既有索引/倒排/检索不回归）。

不删除任何文件、不破坏既有索引 schema、改动仅限 actus 子项目。
"""

import json
import os
import time

import pytest

from vools.actus import indexer
from vools.actus.indexer import (
    _LazyField,
    build_index,
    get_load_cache_stats,
    load_index,
    reset_load_cache,
)
from vools.actus.registry import ActionRegistry

SCHEMA_ACTION = """---
id: myapp.idxprobe
name: IdxProbe
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
purpose: ["utility"]
industry: ["general"]
description: 缓存懒加载验收探针
---

# Probe

```python #!run tag=main
print("ok")
```
"""


@pytest.fixture(autouse=True)
def _isolate_load_cache():
    """每个用例前后清空进程级 load_index 缓存，避免跨用例状态污染。"""
    reset_load_cache()
    yield
    reset_load_cache()


def _write_action(tmp_path, name="probe.actus.schema.md", text=SCHEMA_ACTION):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def _build_meta(tmp_path):
    """在 tmp_path 下写动作并构建索引，返回 (meta_dir, build_index 返回体)。"""
    _write_action(tmp_path)
    meta = tmp_path / "meta"
    idx = build_index(actions_dir=str(tmp_path), meta_dir=str(meta))
    return str(meta), idx


class TestProcessCacheHit:
    """验收点 1：同进程二次 load_index 命中缓存（0 次磁盘读/反序列化）。"""

    def test_second_load_hits_process_cache(self, tmp_path, monkeypatch):
        meta, idx0 = _build_meta(tmp_path)

        idx1 = load_index(meta_dir=meta)
        s1 = get_load_cache_stats()
        assert s1["misses"] == 1 and s1["hits"] == 0, "首次应为冷启动 miss"

        # 二次 load 若走磁盘读则 _load_index_file 被调用 → 打桩抛错，
        # 命中路径（仅 os.stat 校验）不会触碰读文件逻辑。
        def _boom(path):
            raise AssertionError("二次 load 不应读文件/反序列化")

        monkeypatch.setattr(indexer, "_load_index_file", _boom)
        idx2 = load_index(meta_dir=meta)

        s2 = get_load_cache_stats()
        assert s2["hits"] == 1 and s2["misses"] == 1, "二次应命中且 miss 不增"
        assert idx2 == idx1, "命中返回应与首次逐字段一致"

    def test_third_load_keeps_hitting(self, tmp_path, monkeypatch):
        meta, _idx0 = _build_meta(tmp_path)
        load_index(meta_dir=meta)
        monkeypatch.setattr(indexer, "_load_index_file",
                            lambda p: (_ for _ in ()).throw(
                                AssertionError("不应读文件")))
        load_index(meta_dir=meta)
        load_index(meta_dir=meta)
        s = get_load_cache_stats()
        assert s["misses"] == 1 and s["hits"] == 2, "连续 load 持续命中"

    def test_reset_load_cache_forces_cold_reload(self, tmp_path):
        meta, _idx0 = _build_meta(tmp_path)
        load_index(meta_dir=meta)
        reset_load_cache()
        load_index(meta_dir=meta)
        s = get_load_cache_stats()
        assert s["misses"] == 1 and s["hits"] == 0, "reset 后重新冷启动 miss"


class TestLazyLoad:
    """验收点 2：actions 立即可用，by_* / dependency_graph 按需懒加载。"""

    def test_actions_available_immediately(self, tmp_path):
        meta, idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        assert type(idx["actions"]) is dict, "actions 应为普通 dict 立即可用"
        assert idx["actions"] == idx0["actions"]
        assert "myapp.idxprobe" in idx["actions"]

    def test_cold_start_leaves_heavy_fields_unparsed(self, tmp_path):
        meta, idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        # 冷启动后、访问任何 by_* 之前：重字段必须仍是未解析的懒包装。
        for field in ("by_kind", "by_purpose", "by_industry",
                      "by_name", "by_md5"):
            assert isinstance(idx[field], _LazyField), field
            assert not idx[field]._resolved, f"{field} 冷启动不应已解析"

    def test_lazy_field_access_resolves_and_matches(self, tmp_path):
        meta, idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        for field in ("by_kind", "by_purpose", "by_industry",
                      "by_name", "by_md5"):
            lazy = idx[field]
            assert not lazy._resolved
            assert dict(lazy) == dict(idx0[field]), f"{field} 懒解析内容不等"
            assert lazy._resolved, f"{field} 访问后应已解析"
            # 再次访问（已解析路径）内容不变
            assert dict(lazy) == dict(idx0[field])

    def test_dependency_graph_lazy_when_present(self, tmp_path):
        """dependency_graph 存在时同样懒加载；缺失时不注入键（契约一致）。"""
        meta, idx0 = _build_meta(tmp_path)
        # 注入 dependency_graph（build 无依赖场景不产出，手工补上验证懒路径）
        disk_path = os.path.join(meta, "actions.index.json")
        with open(disk_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["dependency_graph"] = {
            "code": {"myapp.idxprobe": []},
            "codes": {},
            "affected": {},
            "count": 0,
        }
        with open(disk_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        idx = load_index(meta_dir=meta)
        assert isinstance(idx["dependency_graph"], _LazyField)
        assert not idx["dependency_graph"]._resolved
        assert dict(idx["dependency_graph"]) == data["dependency_graph"]
        assert idx["dependency_graph"]._resolved
        # 未注入时（干净 build）返回体不含 dependency_graph 键 —— 与旧契约一致
        assert "dependency_graph" not in idx0


class TestFingerprintInvalidation:
    """验收点 3：指纹变更 ⇒ 缓存失效自动重建（重建后再次命中）。"""

    def test_fingerprint_change_rebuilds_and_rehits(self, tmp_path,
                                                    monkeypatch):
        meta, _idx0 = _build_meta(tmp_path)
        load_index(meta_dir=meta)
        before = get_load_cache_stats()
        assert before["misses"] == 1

        # 解析链"变更"：指纹源换文本 → 当前指纹 != 缓存指纹
        monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                            lambda: {"model": "parser-src-CHANGED"})

        idx2 = load_index(meta_dir=meta)
        assert "rebuild_reason" in idx2, "指纹不匹配却未自动重建"
        assert "mismatch" in idx2["rebuild_reason"]
        after = get_load_cache_stats()
        assert after["misses"] == before["misses"] + 1, "重建应记 miss"
        assert after["hits"] == before["hits"], "命中计数不应被重建污染"

        # 重建后的缓存新鲜 → 再次 load 命中且不再重建（保持同一指纹环境；
        # undo 会改变指纹 → 按失效逻辑再次重建，那是另一条路径）。
        idx3 = load_index(meta_dir=meta)
        assert "rebuild_reason" not in idx3
        s = get_load_cache_stats()
        assert s["hits"] == after["hits"] + 1 and s["misses"] == after["misses"]

    def test_build_false_never_rebuilds(self, tmp_path, monkeypatch):
        """build=False 只读契约：命中缓存照返，指纹过期也不重建。"""
        meta, _idx0 = _build_meta(tmp_path)
        idx1 = load_index(meta_dir=meta, build=False)
        monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                            lambda: {"model": "parser-src-CHANGED"})
        idx2 = load_index(meta_dir=meta, build=False)
        assert idx2 == idx1, "build=False 读到什么返回什么"
        assert "rebuild_reason" not in idx2
        s = get_load_cache_stats()
        assert s["misses"] == 1 and s["hits"] == 1

    def test_file_change_invalidates_cache(self, tmp_path):
        """索引文件被外部修改（stat 变化）⇒ 缓存失效重新读。"""
        meta, _idx0 = _build_meta(tmp_path)
        load_index(meta_dir=meta)
        with open(os.path.join(meta, "actions.index.json"), "a",
                  encoding="utf-8") as f:
            f.write(" ")
        load_index(meta_dir=meta)
        s = get_load_cache_stats()
        assert s["misses"] == 2, "文件 stat 变化应触发重新读（miss）"
        load_index(meta_dir=meta)
        s = get_load_cache_stats()
        assert s["hits"] == 1 and s["misses"] == 2, "变更后再次命中"


class TestContractCompatibility:
    """验收点 4：返回结构与既有 load_index 契约一致（不回归）。"""

    def test_return_shape_matches_build_contract(self, tmp_path):
        meta, idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        assert set(idx.keys()) == set(idx0.keys()), \
            "返回顶层键应与 build_index 一致"
        assert idx["schema_version"] == "2.0.0", "schema_version 不变"
        assert idx["classification_version"] == "2.0"
        assert idx["parser_fingerprint"] == idx0["parser_fingerprint"]
        assert idx["actions"] == idx0["actions"]
        for field in ("by_kind", "by_purpose", "by_industry",
                      "by_name", "by_md5"):
            assert isinstance(idx[field], dict), field
            assert dict(idx[field]) == dict(idx0[field]), field

    def test_lazy_field_is_dict_subclass(self, tmp_path):
        meta, _idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        for field in ("by_kind", "by_purpose", "by_industry",
                      "by_name", "by_md5"):
            assert isinstance(idx[field], dict), "懒字段必须 isinstance dict"
        # len / in / items 等 dict 协议在未解析时也可正确触发解析
        lazy = idx["by_kind"]
        assert len(lazy) == 1
        assert "exec" in lazy
        assert dict(lazy.items()) == {"exec": ["myapp.idxprobe"]}
        assert lazy._resolved

    def test_load_from_index_consumes_lazy_fields(self, tmp_path):
        """懒加载字段被 ActionRegistry.load_from_index 正确消费（P1 预过滤）。"""
        meta, idx0 = _build_meta(tmp_path)
        idx = load_index(meta_dir=meta)
        reg = ActionRegistry()
        reg.load_from_index(idx)
        assert set(reg._inv) == {"kind", "purpose", "industry", "name", "md5",
                                 "languages", "trust"}
        assert reg._inv["kind"]["exec"] == ["myapp.idxprobe"]
        assert reg._inv["purpose"]["utility"] == ["myapp.idxprobe"]
        assert reg._inv["industry"]["general"] == ["myapp.idxprobe"]
        assert "myapp.idxprobe" in reg._entries
        # 懒字段消费后内容与全量 build 索引等价
        assert dict(reg._inv["kind"]) == dict(idx0["by_kind"])
        # 触发真实检索（P1 预过滤路径）不抛错、结果正确
        res = reg.search(kind="exec")
        ids = [e.id for e in res]
        assert "myapp.idxprobe" in ids

    def test_search_matches_baseline_with_lazy_fields(self, tmp_path):
        """懒字段载入后检索结果与直接使用 build 索引（普通 dict）一致。"""
        meta, idx0 = _build_meta(tmp_path)
        reg_lazy = ActionRegistry()
        reg_lazy.load_from_index(load_index(meta_dir=meta))
        reg_plain = ActionRegistry()
        reg_plain.load_from_index(dict(idx0))
        assert reg_lazy._entries.keys() == reg_plain._entries.keys()
        assert reg_lazy._inv == reg_plain._inv
        r1 = [e.id for e in reg_lazy.search(kind="exec")]
        r2 = [e.id for e in reg_plain.search(kind="exec")]
        assert r1 == r2


class TestPerformance:
    """验收点 5：命中路径 0 磁盘 IO，显著快于冷启动（≥30% 语义）。"""

    def test_hit_path_faster_than_cold(self, tmp_path):
        meta, _idx0 = _build_meta(tmp_path)

        def bench_cold(n):
            t0 = time.perf_counter()
            for _ in range(n):
                reset_load_cache()
                load_index(meta_dir=meta)
            return (time.perf_counter() - t0) / n

        def bench_hot(n):
            load_index(meta_dir=meta)
            t0 = time.perf_counter()
            for _ in range(n):
                load_index(meta_dir=meta)
            return (time.perf_counter() - t0) / n

        n = 20
        cold_avg = bench_cold(n)
        hot_avg = bench_hot(n)
        assert hot_avg <= cold_avg * 0.7, \
            f"命中应远快于冷启动（hot={hot_avg:.6f}s cold={cold_avg:.6f}s）"
