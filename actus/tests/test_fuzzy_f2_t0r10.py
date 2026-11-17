"""T0r10: F2 模糊匹配与拼写纠错测试。

覆盖提升计划 F2「模糊匹配与拼写纠错」验收标准：
- 编辑距离容错：Levenshtein 距离 ≤2，查询词与索引 term（id/name/
  desc/tag/usage 的 token）匹配，常见拼写错误可纠回正确动作；
- 可选开关：fuzzy 默认关闭时行为与关键词基线一致不回归；
  开关开启仅做兜底，不改变精确命中路径的排序；
- 无命中时给出纠错建议（did you mean）：`suggest()` 返回距离最近且
  相似度达阈值的候选词/动作（kind=edit / kind=pinyin）；
- 拼音前缀容错：pypinyin 可选；开启后中文查询按拼音命中；缺失时
  优雅降级为无拼音候选，不崩溃（纯编辑距离路径照常）。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

import pytest

from vools.actus.registry import (
    ActionRegistry,
    RegistryEntry,
    SearchParams,
    _FUZZY_CUTOFF,
    _FUZZY_MAX_DIST,
)
import vools.actus.fuzzy as fuzzy_mod

#: F2 专用条目库：calculator / monitor / web / notes，含中英混合字段。
#: calculator 的 tag 刻意不含 "calc" 前缀词——保证 'calcuator' 这类拼写
#: 错误在关键词基线路径零命中（tag 包含判定 `tag in query` 会误命中
#: 'calc'），只有模糊开关开启才被纠错召回。
MIXED = [
    dict(id="actus.basics.calculator", name="Calculator",
         desc="compute numbers with a calculator",
         usage="计算器 算数", tags=["math", "arith"]),
    dict(id="actus.monitor.dir", name="Folder Monitor",
         desc="watch filesystem folder for changes",
         usage="监控文件夹变化", tags=["monitor", "watch"]),
    dict(id="actus.web.open", name="Open Browser",
         desc="open browser and navigate web pages",
         usage="浏览网页 打开链接", tags=["web", "browser"]),
    dict(id="actus.notes.md", name="Markdown Notes",
         desc="write markdown notes records",
         usage="记录笔记", tags=["notes"]),
]


def _mk_registry(specs=None):
    """构造 ActionRegistry（直接塞 entries，不落盘）。"""
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


class TestFuzzyEditDistance:
    """编辑距离容错（Levenshtein ≤2）。"""

    def test_closed_by_default_matches_baseline(self):
        reg = _mk_registry()
        # 默认 fuzzy=False：拼写错误零命中（与基线一致）
        assert _ids(reg.search("calcuator")) == []

    def test_edit_distance_one_recall(self):
        reg = _mk_registry()
        # 'calcuator' vs 'calculator' 编辑距离 1 → 纠回正确动作
        res = _ids(reg.search("calcuator", fuzzy=True))
        assert "actus.basics.calculator" in res

    def test_edit_distance_two_recall(self):
        reg = _mk_registry()
        # 'calcualtor' vs 'calculator' 编辑距离 2（换位+插入等价 2 步）
        res = _ids(reg.search("calcualtor", fuzzy=True))
        assert "actus.basics.calculator" in res

    def test_fuzzy_zero_dist_disables(self):
        reg = _mk_registry()
        # fuzzy_max_dist=0 等价关闭容错 → 仍零命中
        assert _ids(reg.search("calcuator", fuzzy=True, fuzzy_max_dist=0)) == []

    def test_exact_hits_keep_keyword_path(self):
        reg = _mk_registry()
        # 精确命中存在时不触发模糊兜底，排序与 fuzzy=False 完全一致
        base = _ids(reg.search("calc"))
        fuzzy = _ids(reg.search("calc", fuzzy=True))
        assert base and fuzzy == base

    def test_explain_marks_fuzzy_hit(self):
        reg = _mk_registry()
        rows = reg.search_explain("calcuator", fuzzy=True)
        assert rows and rows[0]["match_fields"]
        assert any("fuzzy=" in f for f in rows[0]["match_fields"])
        assert rows[0]["reason"]
        assert 0 < rows[0]["score"] <= 1


class TestDidYouMean:
    """无命中时返回纠错建议（did you mean）。"""

    def test_suggest_edit_candidate(self):
        reg = _mk_registry()
        out = reg.suggest("calcuator")
        assert out
        top = out[0]
        assert top["kind"] == "edit"
        assert top["distance"] <= _FUZZY_MAX_DIST
        assert top["similarity"] >= _FUZZY_CUTOFF
        assert top["action_id"] == "actus.basics.calculator"

    def test_suggest_empty_query(self):
        reg = _mk_registry()
        assert reg.suggest("") == []
        assert reg.suggest(None) == []

    def test_suggest_distance_ordering(self):
        reg = _mk_registry()
        # 更近的候选排前面（距离升序）
        out = reg.suggest("calcuator")
        distances = [s["distance"] for s in out]
        assert distances == sorted(distances)


class TestPinyin:
    """拼音前缀容错（可选 pypinyin）。"""

    def test_pinyin_recall_when_enabled(self):
        reg = _mk_registry()
        # 'jiankong'（监控）拼音包含于 '监控文件夹变化' 拼音 → 命中监控动作
        assert "actus.monitor.dir" in _ids(reg.search("jiankong", pinyin=True))

    def test_pinyin_closed_by_default(self):
        reg = _mk_registry()
        # pinyin 默认关闭 → 拼音零命中（基线）
        assert _ids(reg.search("jiankong")) == []

    def test_pinyin_suggest(self):
        reg = _mk_registry()
        out = reg.suggest("jiankong", use_pinyin=True)
        kinds = [s["kind"] for s in out]
        assert "pinyin" in kinds
        assert any(s["action_id"] == "actus.monitor.dir"
                   for s in out if s["kind"] == "pinyin")

    def test_pinyin_missing_degrades_gracefully(self, monkeypatch):
        # 模拟 pypinyin 不可用：拼音路径无命中、不崩溃，
        # 编辑距离路径照常工作。
        monkeypatch.setattr(fuzzy_mod, "_HAS_PYPINYIN", False)
        monkeypatch.setattr(fuzzy_mod, "_lazy_pinyin", None)
        reg = _mk_registry()
        # 纯拼音查询 'jiankong'：无拼音支持 → 无命中（编辑距离也不命中）
        assert _ids(reg.search("jiankong", pinyin=True)) == []
        assert reg.suggest("jiankong", use_pinyin=True) == []
        # 纯编辑距离建议不受影响
        out = reg.suggest("calcuator", use_pinyin=True)
        assert out and out[0]["kind"] == "edit"
        # 精确中文子串命中不因拼音开关改变（开关不破坏基线）
        assert _ids(reg.search("监控文件夹", pinyin=True)) == [
            "actus.monitor.dir"]


class TestSearchParams:
    """F2 开关字段透传与过滤语义。"""

    def test_params_fields(self):
        p = SearchParams(fuzzy=True, pinyin=True,
                         fuzzy_max_dist=2, fuzzy_cutoff=0.5)
        assert p.fuzzy is True
        assert p.pinyin is True
        assert p.fuzzy_max_dist == 2
        assert p.fuzzy_cutoff == 0.5

    def test_fuzzy_not_a_filter_field(self):
        # fuzzy/pinyin 是打分开关，不是过滤约束
        p = SearchParams(fuzzy=True, pinyin=True)
        fa = p.filtered_args()
        assert "fuzzy" not in fa
        assert "pinyin" not in fa


class TestFuzzyModule:
    """fuzzy.py 纯函数契约（直接面向验收标准）。"""

    def test_levenshtein_bound(self):
        assert fuzzy_mod.levenshtein_distance("calcuator", "calculator", 2) == 1
        assert fuzzy_mod.levenshtein_distance("calcualtor", "calculator", 2) == 2
        # 距离超上限返回 max_dist+1（不无限计算）
        assert fuzzy_mod.levenshtein_distance("abc", "xyzabc", 2) == 3

    def test_edit_similarity_threshold(self):
        assert fuzzy_mod.edit_similarity("calcuator", "calculator", 2) >= 0.5
        assert fuzzy_mod.edit_similarity("abc", "xyzabc", 2) == 0.0

    def test_fuzzy_match_case_insensitive(self):
        assert fuzzy_mod.fuzzy_match("Calculator", "calculator", 2)
        assert not fuzzy_mod.fuzzy_match("", "calculator", 2)
