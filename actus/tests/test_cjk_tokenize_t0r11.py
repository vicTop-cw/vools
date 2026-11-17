"""T0r11: F3 中文/多语言支持测试。

覆盖提升计划 F3「中文/多语言支持」验收标准：
- 统一 tokenizer：英文按词切分（与 str.split() 等价，零回归）、
  CJK 走 jieba（可选依赖），无 jieba 时 2-gram N-gram 降级；
- search('监控 文件夹') 与 search('监控文件夹') 命中同一动作集合；
- 中文 tag/description 分词后排序不劣于整串子串匹配；
- 英文关键词/倒排/fuzzy 检索不回归；
- 无 jieba 环境（模拟导入失败 / monkeypatch / 运行期异常）降级
  路径不崩溃且可检索。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

import pytest

from vools.actus.registry import (
    ActionRegistry,
    RegistryEntry,
    SearchParams,
)
import vools.actus.tokenizer as tokenizer_mod

#: T0r11 专用条目库：中英混合字段。
#: actus.monitor.dir 的 usage/tag 含中文整串（"监控文件夹变化"），
#: 用于验证"监控 文件夹"与"监控文件夹"在统一分词下命中同一集合；
#: web / calculator 用于英文检索不回归断言。
MIXED = [
    dict(id="actus.monitor.dir", name="Folder Monitor",
         desc="watch filesystem folder for changes",
         usage="监控文件夹变化", tags=["monitor", "watch", "监控"]),
    dict(id="actus.web.open", name="Open Browser",
         desc="open browser and navigate web pages",
         usage="浏览网页 打开链接", tags=["web", "browser"]),
    dict(id="actus.basics.calculator", name="Calculator",
         desc="compute numbers with a calculator",
         usage="计算器 算数", tags=["math", "arith"]),
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


class TestTokenizer:
    """统一 tokenizer 行为。"""

    def test_english_identical_to_split(self):
        # 英文/数字输入必须与 str.split() 完全一致（英文零回归锚点）
        for s in ["monitor folder", "open browser and navigate web pages",
                  "calcuator", "web.page x", "monitor", "folder"]:
            assert tokenizer_mod.tokenize(s) == s.strip().lower().split()

    def test_chinese_2gram_fallback_no_jieba(self, monkeypatch):
        # 无 jieba（模拟导入失败）→ 2-gram N-gram 降级：整词 + 全部 2-gram
        monkeypatch.setattr(tokenizer_mod, "_JIEBA", None)
        toks = tokenizer_mod.tokenize("监控文件夹")
        assert toks == ["监控文件夹", "监控", "控文", "文件", "件夹"]
        # 带空格的独立 CJK 词同样展开（3 字及以上词 → 整词 + 2-gram）
        assert tokenizer_mod.tokenize("监控 文件夹") == [
            "监控", "文件夹", "文件", "件夹"]

    def test_jieba_runtime_failure_falls_back(self, monkeypatch):
        # jieba 运行期异常 → 同样 2-gram 降级，绝不抛异常
        class _BadJieba:
            @staticmethod
            def lcut(seg):
                raise RuntimeError("simulated jieba failure")

        monkeypatch.setattr(tokenizer_mod, "_JIEBA", _BadJieba())
        toks = tokenizer_mod.tokenize("监控文件夹")
        assert "监控文件夹" in toks
        assert "监控" in toks and "文件" in toks

    def test_mixed_cjk_english(self, monkeypatch):
        monkeypatch.setattr(tokenizer_mod, "_JIEBA", None)
        toks = tokenizer_mod.tokenize("监控 folder 变化")
        assert "folder" in toks
        assert "监控" in toks and "变化" in toks

    def test_empty_and_whitespace(self):
        assert tokenizer_mod.tokenize("") == []
        assert tokenizer_mod.tokenize("   ") == []

    def test_expand_ngram_false_keeps_whole_segments(self):
        # 检索打分/意图路由侧：expand_ngram=False 仅整段 + 英文词，
        # 与 str.split() 粒度等价（保既有"跨义词零命中"契约）
        assert tokenizer_mod.tokenize("监控文件夹", expand_ngram=False) == [
            "监控文件夹"]
        assert tokenizer_mod.tokenize("监控 文件夹", expand_ngram=False) == [
            "监控", "文件夹"]
        assert tokenizer_mod.tokenize("monitor folder",
                                      expand_ngram=False) == [
            "monitor", "folder"]


class TestChineseSearch:
    """中文检索验收：同集合命中 / 排序不劣 / 降级可检索。"""

    def test_space_and_compact_hit_same_set(self, monkeypatch):
        # ① '监控 文件夹' 与 '监控文件夹' 命中同一动作集合
        monkeypatch.setattr(tokenizer_mod, "_JIEBA", None)
        reg = _mk_registry()
        a = set(_ids(reg.search("监控 文件夹")))
        b = set(_ids(reg.search("监控文件夹")))
        assert a == b
        assert "actus.monitor.dir" in a

    def test_no_jieba_ngram_still_searchable(self, monkeypatch):
        # ② 无 jieba 降级路径下可正常检索（不崩溃）
        monkeypatch.setattr(tokenizer_mod, "_JIEBA", None)
        reg = _mk_registry()
        res = _ids(reg.search("监控文件夹"))
        assert "actus.monitor.dir" in res

    def test_scoring_not_worse_than_whole_string(self, monkeypatch):
        # ③ 中文 tag/描述分词后排序不劣于整串子串匹配
        monkeypatch.setattr(tokenizer_mod, "_JIEBA", None)
        reg = _mk_registry()
        entry = reg._entries["actus.monitor.dir"]
        q = "监控文件夹"
        old_words = set(q.split())
        new_words = set(tokenizer_mod.tokenize(q))
        # 分词 token 集是整串 split 的超集（整词保留 + 2-gram 扩展）
        assert old_words <= new_words
        old_score, _ = ActionRegistry._score_entry_ex(entry, q, old_words)
        new_score, _ = ActionRegistry._score_entry_ex(entry, q, new_words)
        assert new_score > 0
        assert new_score >= old_score


class TestEnglishNotRegressed:
    """④ 英文关键词/倒排/fuzzy 检索不回归。"""

    def test_english_keyword_search(self):
        reg = _mk_registry()
        assert "actus.web.open" in _ids(reg.search("open browser"))

    def test_english_inverted_and_linear_equivalent(self):
        reg = _mk_registry()
        a = set(_ids(reg.search_params(SearchParams(query="monitor folder"))))
        b = set(_ids(reg.search_params(
            SearchParams(query="monitor folder", use_inverted=False))))
        assert a == b
        assert "actus.monitor.dir" in a

    def test_english_fuzzy_not_regressed(self):
        reg = _mk_registry()
        assert "actus.basics.calculator" in _ids(
            reg.search("calcuator", fuzzy=True))
