"""查重与市场体检的判据。

本组最重要的性质：**全程离线**。相似度不许依赖 LLM 或 API key，
否则「体检」这个最有价值的用法（造动作之前先查一遍）在没有密钥的
机器上就废了。
"""

import pytest

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.catalog import ToolCatalog, CatalogEntry, build_catalog
from vools.actus.ai.gaps import (find_similar, analyze_market, health_report,
                                 similarity, CAPABILITY_ANCHORS,
                                 VERDICT_REUSE, VERDICT_COMPOSE, VERDICT_GAP)

_META = _boot.actus_meta_dir()
needs_index = pytest.mark.skipif(not _META, reason='找不到 Actus 仓库的 _meta 目录')


def _entry(action_id, description='', tags=()):
    return CatalogEntry(tool_name=action_id.replace('.', '_'),
                        action_id=action_id, description=description,
                        tags=tuple(tags))


# ── 离线性质 ──

def test_find_similar_works_offline(monkeypatch):
    """**关键性质**：无任何环境变量、无网络时仍要能给出结论。"""
    for name in ('OPENAI_API_KEY', 'GROQ_API_KEY', 'DEEPSEEK_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    cat = ToolCatalog([_entry('cli.jq', 'jq JSON 处理', tags=('json',))])
    rep = find_similar('用 jq 处理 JSON', catalog=cat)
    assert rep.verdict in (VERDICT_REUSE, VERDICT_COMPOSE, VERDICT_GAP)


def test_similarity_does_not_touch_network():
    """similarity 是纯函数，签名里就没有 client —— 结构性保证。"""
    e = _entry('cli.jq', 'jq JSON 处理', tags=('json',))
    assert similarity('用 jq 处理 JSON', e) > 0
    assert similarity('', e) == 0.0


# ── 判定分支 ──

def test_find_similar_says_reuse_for_unique_match():
    """唯一命中且分数够高 → reuse（直接用现成的）。"""
    cat = ToolCatalog([
        _entry('cli.jq', 'jq JSON 处理', tags=('json',)),
        _entry('dialog.alert', '信息确认弹窗'),
    ])
    rep = find_similar('用 jq 处理 JSON', catalog=cat)
    assert rep.verdict == VERDICT_REUSE
    assert rep.similar[0]['action_id'] == 'cli.jq'
    assert 'cli.jq' in rep.advice


def test_find_similar_says_compose_for_multiple_matches():
    """多个候选 → compose（建议用 workflow 组合而不是新造）。"""
    cat = ToolCatalog([
        _entry('cli.jq', 'jq JSON 处理', tags=('json',)),
        _entry('system.json_util', 'JSON 工具', tags=('json',)),
        _entry('dialog.alert', '信息确认弹窗'),
    ])
    rep = find_similar('用 jq 处理 JSON', catalog=cat, threshold=0.35)
    assert rep.verdict == VERDICT_COMPOSE
    assert len(rep.similar) >= 2


def test_find_similar_says_gap_for_unknown_need():
    """没有候选超过阈值 → gap（确实缺能力，可以造）。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq JSON 处理', tags=('json',))])
    rep = find_similar('量子隧穿配平计算', catalog=cat)
    assert rep.verdict == VERDICT_GAP
    assert rep.similar == ()
    assert rep.top_score < 0.35


def test_find_similar_on_empty_catalog():
    """空目录返回 gap，不抛异常。"""
    rep = find_similar('任何东西', catalog=ToolCatalog(()))
    assert rep.verdict == VERDICT_GAP


def test_find_similar_is_deterministic():
    """同分时按 action_id 排序，保证结果可复现。"""
    entries = [_entry('b.two', 'jq 处理'), _entry('a.one', 'jq 处理'),
               _entry('c.three', 'jq 处理')]
    cat = ToolCatalog(entries)
    first = [s['action_id'] for s in find_similar('jq', catalog=cat).similar]
    cat2 = ToolCatalog(list(reversed(entries)))
    second = [s['action_id'] for s in find_similar('jq', catalog=cat2).similar]
    assert first == second


# ── 相似度信号 ──

def test_similarity_prefers_exact_proper_noun():
    """专名（Markdown/docx）应把 pandoc 排在 jq 前面 —— 这是长词覆盖路径。"""
    pandoc = _entry('cli.pandoc',
                    'Pandoc 文档转换。支持 Markdown/HTML/LaTeX/Docx 等格式互转。')
    jq = _entry('cli.jq', 'jq JSON 处理。使用 jq 查询和转换 JSON 数据。')
    query = '把 Markdown 转成 docx'
    assert similarity(query, pandoc) > similarity(query, jq)


def test_similarity_anchor_handles_chinese_synonym():
    """中文同义（「截个图」vs「截取屏幕」）靠能力锚点，不靠字符相似度。"""
    screen = _entry('system.tool_screen', '截取屏幕内容为图片文件')
    query = '截个图看看屏幕'
    assert similarity(query, screen) > 0.35, '锚点表未覆盖该同义表达'


def test_similarity_anchor_prefers_id_match_over_description_only():
    """id/tags 命中应比仅 description 命中分高，否则排序会错。"""
    direct = _entry('system.tool_clipboard', '剪贴板工具', tags=('clipboard',))
    incidental = _entry('other.thing', '顺带会用到剪贴板')
    query = '读取剪贴板内容'
    assert similarity(query, direct) > similarity(query, incidental)


def test_similarity_zero_for_unrelated():
    """完全无关的查询应给低分。"""
    e = _entry('cli.jq', 'jq JSON 处理', tags=('json',))
    assert similarity('今天天气怎么样', e) < 0.35


def test_anchor_table_is_not_empty():
    """锚点表是人工维护的资产，空表等于功能失效。"""
    assert len(CAPABILITY_ANCHORS) >= 10
    for cap, words in CAPABILITY_ANCHORS.items():
        assert words, '锚点 %s 没有配置词' % cap


# ── 市场体检 ──

def test_analyze_market_on_empty_catalog():
    """空目录时各字段为空，不抛异常。"""
    rep = analyze_market(ToolCatalog(()))
    assert rep['counts']['total'] == 0
    assert rep['duplicates']['exact'] == []
    assert rep['orphans'] == []


@needs_index
def test_analyze_market_reports_nonstandard_prefix():
    """真实索引里 vools.vault.* 混进了动作市场，必须被点名。"""
    rep = analyze_market(build_catalog(meta_dir=_META))
    assert 'vools.vault.get' in rep['nonstandard_prefix']
    assert 'cli.jq' in rep['nonstandard_prefix']


@needs_index
def test_health_report_is_readable_text():
    """health_report 面向人，要是有结构的文本。"""
    text = health_report(build_catalog(meta_dir=_META))
    assert isinstance(text, str)
    assert '动作市场体检' in text
    assert '同能力多实现' in text
    assert '命名不规范' in text


def test_health_report_on_empty_catalog():
    """空目录时也要有一句可读的话。"""
    assert '无动作' in health_report(ToolCatalog(()))


@needs_index
def test_real_index_finds_known_duplicates():
    """真实索引必须检出这三组已知重复。"""
    rep = analyze_market(build_catalog(meta_dir=_META))
    pairs = set(tuple(sorted(i['action_ids'])) for i in rep['duplicates']['exact'])
    assert ('actus.cli.curl', 'cli.curl') in pairs
    assert ('actus.cli.jq', 'cli.jq') in pairs
    assert ('actus.http.fetch', 'http.fetch') in pairs
