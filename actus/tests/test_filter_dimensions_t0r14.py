"""T0r14（F4 过滤组合与新增维度）验收测试。

覆盖提升计划验收标准：
1. 维度补齐：registry.search / SearchParams 新增 languages（多值任一）、
   trust（单值）过滤；load_from_index 提取 by_languages / by_trust 到
   _inv（缺失/空 dict 回退全量扫描，与 P1 行为一致）。
2. 反向索引新增：build_index 写入 by_languages / by_trust（schema
   version 2.0.0 不变、既有 by_kind/by_purpose/by_industry/by_name/
   by_md5 不受影响）。
3. 多 tag 语义：tags_mode="and" 全部命中；None/"or" 任一命中（既有行为）；
   排除语义：exclude_tags 或 tags 内 "-tag" 前缀拆分。
4. 组合过滤：kind/purpose/industry/languages/trust 任意组合与反向索引
   交集逻辑一致（候选集 ∩ 过滤，等价性锚点）。
5. 向后兼容：旧索引缺 by_languages/by_trust 加载不报错、缺字段回退
   全量扫描结果一致。

红线：不删除任何文件、不破坏既有索引 schema 兼容性（schema_version
不变）、可 git 回溯、改动仅限 actus 子项目。
"""

import os

import pytest

from vools.actus.indexer import build_index
from vools.actus.registry import ActionRegistry, RegistryEntry

SCHEMA_PY = """---
id: probe.pyaction
name: PyAction
version: 1.0.0
trust: trusted
kind: exec
entry: main
platform: desktop
purpose: ["utility"]
industry: ["general"]
description: python 语言探针
---

# Py Probe

```python #!run tag=main
print("ok")
```
"""

SCHEMA_SH = """---
id: probe.shaction
name: ShAction
version: 1.0.0
trust: community
kind: exec
entry: main
platform: desktop
purpose: ["automation"]
industry: ["general"]
description: shell 语言探针
---

# Sh Probe

```bash #!run tag=main
echo ok
```
"""

SCHEMA_JS = """---
id: probe.jsaction
name: JsAction
version: 1.0.0
trust: trusted
kind: demo
entry: main
platform: desktop
purpose: ["utility"]
industry: ["devops"]
description: javascript 语言探针
---

# Js Probe

```javascript #!run tag=main
console.log("ok")
```
"""


def _mk_registry(entries):
    """直接塞 RegistryEntry（不落盘），验证全量过滤路径语义。"""
    reg = ActionRegistry()
    for e in entries:
        reg._entries[e.id] = e
    return reg


def _entry(aid, *, tags=None, kind="exec", purpose=None, industry=None,
           languages=None, trust_level="community", name=None):
    purpose = purpose or ["utility"]
    industry = industry or ["general"]
    return RegistryEntry(
        id=aid,
        name=name or aid,
        version="1.0.0",
        description="",
        category=kind,
        path=aid + ".md",
        author="tester",
        tags=tags or [],
        checksum="0" * 32,
        trust_level=trust_level,
        kind=kind,
        purpose=purpose,
        industry=industry,
        languages=languages or [],
    )


def _ids(entries):
    return sorted(e.id for e in entries)


def _build_registry(tmp_path):
    """在 tmp_path 写动作并 build_index，返回 (已 load_from_index 的 registry, idx)。"""
    meta = tmp_path / "meta"
    for name, text in (("probe.pyaction.actus.schema.md", SCHEMA_PY),
                       ("probe.shaction.actus.schema.md", SCHEMA_SH),
                       ("probe.jsaction.actus.schema.md", SCHEMA_JS)):
        (tmp_path / name).write_text(text, encoding="utf-8", newline="")
    idx = build_index(actions_dir=str(tmp_path), meta_dir=str(meta))
    reg = ActionRegistry()
    reg.load_from_index(idx)
    return reg, idx


class TestLanguagesTrustSubset:
    """验收点 1：search(languages=..., trust=...) 返回正确子集。"""

    def test_languages_filter_subset(self):
        reg = _mk_registry([
            _entry("py", languages=["python"]),
            _entry("sh", languages=["bash"]),
            _entry("none"),
        ])
        assert _ids(reg.search(languages=["python"])) == ["py"]
        assert _ids(reg.search(languages=["bash"])) == ["sh"]
        assert _ids(reg.search(languages=["python", "bash"])) == ["py", "sh"]
        assert _ids(reg.search(languages=["go"])) == []

    def test_languages_filter_case_insensitive(self):
        reg = _mk_registry([_entry("py", languages=["python"])])
        assert _ids(reg.search(languages=["Python"])) == ["py"]

    def test_trust_filter_subset(self):
        reg = _mk_registry([
            _entry("a", trust_level="trusted"),
            _entry("b", trust_level="community"),
            _entry("c", trust_level="unverified"),
        ])
        assert _ids(reg.search(trust="trusted")) == ["a"]
        assert _ids(reg.search(trust="community")) == ["b"]
        assert _ids(reg.search(trust="unverified")) == ["c"]
        assert _ids(reg.search(trust="Trusted")) == ["a"]

    def test_languages_trust_combination(self):
        reg = _mk_registry([
            _entry("py_t", languages=["python"], trust_level="trusted"),
            _entry("py_c", languages=["python"], trust_level="community"),
            _entry("js_t", languages=["javascript"], trust_level="trusted"),
        ])
        assert _ids(reg.search(languages=["python"], trust="trusted")) == ["py_t"]
        assert _ids(reg.search(languages=["python"])) == ["py_c", "py_t"]
        assert _ids(reg.search(trust="trusted")) == ["js_t", "py_t"]


class TestTagAndOr:
    """验收点 2：多 tag AND/OR 语义。"""

    def test_tags_default_or_keeps_legacy(self):
        reg = _mk_registry([
            _entry("both", tags=["a", "b"]),
            _entry("only_a", tags=["a"]),
            _entry("other", tags=["c"]),
        ])
        # 既有行为：任一命中（OR），不传 tags_mode 不回归
        assert _ids(reg.search(tags=["a", "b"])) == ["both", "only_a"]

    def test_tags_mode_or_explicit(self):
        reg = _mk_registry([
            _entry("both", tags=["a", "b"]),
            _entry("only_a", tags=["a"]),
            _entry("other", tags=["c"]),
        ])
        assert _ids(reg.search(tags=["a", "b"], tags_mode="or")) == ["both", "only_a"]

    def test_tags_mode_and(self):
        reg = _mk_registry([
            _entry("both", tags=["a", "b"]),
            _entry("only_a", tags=["a"]),
            _entry("other", tags=["c"]),
        ])
        assert _ids(reg.search(tags=["a", "b"], tags_mode="and")) == ["both"]
        assert _ids(reg.search(tags=["a", "c"], tags_mode="and")) == []
        assert _ids(reg.search(tags=["a"], tags_mode="and")) == ["both", "only_a"]

    def test_tags_mode_and_params_object(self):
        reg = _mk_registry([
            _entry("both", tags=["a", "b"]),
            _entry("only_a", tags=["a"]),
        ])
        from vools.actus.registry import SearchParams
        params = SearchParams(tags=["a", "b"], tags_mode="and")
        assert _ids(reg.search_params(params)) == ["both"]


class TestExcludeSemantics:
    """验收点 3：排除语义（exclude_tags / "-tag" 前缀）。"""

    def test_exclude_tags(self):
        reg = _mk_registry([
            _entry("ok", tags=["a"]),
            _entry("secret", tags=["a", "secret"]),
            _entry("plain", tags=["secret"]),
        ])
        assert _ids(reg.search(tags=["a"], exclude_tags=["secret"])) == ["ok"]
        assert _ids(reg.search(exclude_tags=["secret"])) == ["ok"]

    def test_dash_prefix_in_tags(self):
        reg = _mk_registry([
            _entry("ok", tags=["a"]),
            _entry("secret", tags=["a", "secret"]),
        ])
        assert _ids(reg.search(tags=["a", "-secret"])) == ["ok"]

    def test_positive_and_negative_mix(self):
        reg = _mk_registry([
            _entry("both", tags=["a", "b"]),
            _entry("a_only", tags=["a"]),
            _entry("none", tags=["c"]),
        ])
        assert _ids(reg.search(tags=["a", "b", "-b"], tags_mode="or")) == ["a_only"]
        assert _ids(reg.search(tags=["a", "b"], tags_mode="and",
                               exclude_tags=["b"])) == []


class TestIndexBackwardCompat:
    """验收点 4：新增索引字段向后兼容（缺字段回退全量扫描）。"""

    def test_new_index_has_by_languages_and_by_trust(self, tmp_path):
        _, idx = _build_registry(tmp_path)
        assert idx["schema_version"] == "2.0.0"
        assert "by_languages" in idx and isinstance(idx["by_languages"], dict)
        assert "by_trust" in idx and isinstance(idx["by_trust"], dict)
        assert set(idx["by_languages"]).issuperset({"python", "bash", "javascript"})
        assert set(idx["by_trust"]) == {"trusted", "community"}

    def test_legacy_dimensions_preserved(self, tmp_path):
        _, idx = _build_registry(tmp_path)
        for dim in ("kind", "purpose", "industry", "name", "md5"):
            assert "by_" + dim in idx

    def test_load_new_index_dims_into_inv(self, tmp_path):
        reg, _ = _build_registry(tmp_path)
        assert "languages" in reg._inv and "trust" in reg._inv
        assert "python" in reg._inv["languages"]
        assert "trusted" in reg._inv["trust"]

    def test_load_index_filter_uses_inverted_index(self, tmp_path):
        reg, _ = _build_registry(tmp_path)
        assert _ids(reg.search(languages=["python"])) == ["probe.pyaction"]
        assert _ids(reg.search(trust="trusted")) == ["probe.jsaction", "probe.pyaction"]
        assert _ids(reg.search(languages=["python"], trust="trusted")) == ["probe.pyaction"]

    def test_missing_dims_fallback_to_full_scan(self, tmp_path):
        reg, idx = _build_registry(tmp_path)
        legacy = dict(idx)
        legacy.pop("by_languages", None)
        legacy.pop("by_trust", None)
        reg2 = ActionRegistry()
        reg2.load_from_index(legacy)  # 旧索引无新键：不报错
        assert "languages" not in reg2._inv and "trust" not in reg2._inv
        # 回退全量扫描：结果与带索引完全一致（等价性锚点）
        assert _ids(reg2.search(languages=["python"])) == _ids(reg.search(languages=["python"]))
        assert _ids(reg2.search(trust="trusted")) == _ids(reg.search(trust="trusted"))
        assert _ids(reg2.search(languages=["python"], trust="trusted")) == \
            _ids(reg.search(languages=["python"], trust="trusted"))

    def test_empty_dims_fallback_to_full_scan(self, tmp_path):
        reg, idx = _build_registry(tmp_path)
        legacy = dict(idx)
        legacy["by_languages"] = {}
        legacy["by_trust"] = {}
        reg2 = ActionRegistry()
        reg2.load_from_index(legacy)
        assert "languages" not in reg2._inv and "trust" not in reg2._inv
        assert _ids(reg2.search(languages=["python"])) == ["probe.pyaction"]
        assert _ids(reg2.search(trust="trusted")) == ["probe.jsaction", "probe.pyaction"]


class TestCombinedFilters:
    """验收点 5：kind/purpose/industry/languages/trust 任意组合过滤正确。"""

    def test_five_dimensions_combination(self):
        reg = _mk_registry([
            _entry("target", kind="exec", purpose=["utility"],
                   industry=["general"], languages=["python"],
                   trust_level="trusted"),
            _entry("wrong_lang", kind="exec", purpose=["utility"],
                   industry=["general"], languages=["bash"],
                   trust_level="trusted"),
            _entry("wrong_trust", kind="exec", purpose=["utility"],
                   industry=["general"], languages=["python"],
                   trust_level="community"),
            _entry("wrong_kind", kind="demo", purpose=["utility"],
                   industry=["general"], languages=["python"],
                   trust_level="trusted"),
            _entry("wrong_purpose", kind="exec", purpose=["automation"],
                   industry=["general"], languages=["python"],
                   trust_level="trusted"),
            _entry("wrong_industry", kind="exec", purpose=["utility"],
                   industry=["devops"], languages=["python"],
                   trust_level="trusted"),
        ])
        got = reg.search(kind="exec", purpose=["utility"],
                         industry=["general"], languages=["python"],
                         trust="trusted")
        assert _ids(got) == ["target"]

    def test_partial_combinations(self):
        reg = _mk_registry([
            _entry("a", kind="exec", industry=["devops"],
                   languages=["python"], trust_level="trusted"),
            _entry("b", kind="exec", industry=["general"],
                   languages=["python"], trust_level="trusted"),
        ])
        assert _ids(reg.search(kind="exec", industry=["devops"])) == ["a"]
        assert _ids(reg.search(languages=["python"], trust="trusted")) == ["a", "b"]
        assert _ids(reg.search(purpose=["utility"], languages=["python"])) == ["a", "b"]

    def test_indexed_path_equals_linear_path(self, tmp_path):
        """反向索引预过滤结果与全量扫描等价（交集逻辑一致）。"""
        reg, idx = _build_registry(tmp_path)
        indexed = reg.search(languages=["python"], trust="trusted")
        # 模拟无索引全量：清空 _inv 后结果必须一致
        saved = dict(reg._inv)
        reg._inv.clear()
        linear = reg.search(languages=["python"], trust="trusted")
        reg._inv.update(saved)
        assert _ids(indexed) == _ids(linear)
