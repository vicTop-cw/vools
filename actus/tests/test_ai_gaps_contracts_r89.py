"""gaps.py 边界分支契约测试（r89）。

补齐 test_ai_gaps.py 未触达的私有辅助函数与 health_report 输出分支。
全程离线，不依赖真实索引。
"""

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.catalog import ToolCatalog, CatalogEntry
from vools.actus.ai import gaps as gaps_mod


def _entry(action_id, description='', tags=()):
    return CatalogEntry(tool_name=action_id.replace('.', '_'),
                        action_id=action_id, description=description,
                        tags=tuple(tags))


# ── _jaccard 边界 ──

def test_jaccard_empty_side_returns_zero():
    assert gaps_mod._jaccard(set(), {'a'}) == 0.0
    assert gaps_mod._jaccard({'a'}, set()) == 0.0


def test_jaccard_disjoint_returns_zero():
    assert gaps_mod._jaccard({'a'}, {'b'}) == 0.0


def test_jaccard_intersection_value():
    # 交 1 / 并 3 = 1/3
    assert gaps_mod._jaccard({'a', 'b'}, {'b', 'c'}) == 1 / 3


# ── _segment_score 分级 ──

def test_segment_score_long_segment_is_strong():
    e = _entry('x.json_util', '转换')
    assert gaps_mod._segment_score('json_util 转换', e) == 0.8


def test_segment_score_mid_segment():
    e = _entry('x.abc', '转换')
    assert gaps_mod._segment_score('abc 转换', e) == 0.7


def test_segment_score_short_segment():
    e = _entry('x.ab', '转换')
    assert gaps_mod._segment_score('ab 转换', e) == 0.5


def test_segment_score_tag_hit():
    e = _entry('x.y', '转换', tags=('json',))
    assert gaps_mod._segment_score('json 转换', e) == 0.6


def test_segment_score_no_hit():
    e = _entry('x.y', '转换')
    assert gaps_mod._segment_score('毫无关系', e) == 0.0


# ── _anchor_hit / similarity 边界 ──

def test_anchor_hit_empty_query():
    e = _entry('cli.jq', 'jq JSON')
    assert gaps_mod._anchor_hit('', e) == ('', 0.0)


def test_similarity_tokenless_query_returns_zero():
    # strip 后非空（不走 311 短路），但分词为空 → 324 行 0.0
    e = _entry('cli.jq', 'jq JSON')
    assert gaps_mod.similarity('（）', e) == 0.0


# ── analyze_market 孤儿依赖扫描 ──

def _mk_cat(*ids):
    return ToolCatalog(tuple(_entry(i, 'desc') for i in ids))


def test_analyze_market_orphan_deps_scanned(monkeypatch):
    cat = _mk_cat('a.aa', 'a.bb')
    idx = {'actions': {
        'a.aa': {'deps': ['action:ghost', 'plain', 'cs_skip', 'ns:x',
                          'a.bb']},
        'a.bb': 'junk-not-a-dict',          # 433: brief 非 dict
    }}

    def fake_load_index(_meta=None):
        return idx
    monkeypatch.setattr('vools.actus.indexer.load_index', fake_load_index)
    rep = gaps_mod.analyze_market(cat)
    # ghost（action: 前缀剥离）、plain（裸名）、junk 跳过、cs_/冒号跳过、
    # a.bb 在目录内不算孤儿
    assert rep['orphans'] == ['ghost', 'plain']


def test_analyze_market_index_failure_yields_no_orphans(monkeypatch):
    def boom(_meta=None):
        raise RuntimeError('index unavailable')
    monkeypatch.setattr('vools.actus.indexer.load_index', boom)
    rep = gaps_mod.analyze_market(_mk_cat('a.aa'))
    assert rep['orphans'] == []


# ── health_report 输出分支 ──

def test_health_report_empty_sections_and_truncations(monkeypatch):
    # 35 个非 actus 前缀动作 → 命名不规范截断（518）
    ids = ['tool%d.func' % i for i in range(35)]
    # 共享 >=2 段后缀（x.curl）→ exact 重复（501-502）
    ids += ['a.x.curl', 'b.x.curl', 'a.aa']
    cat = _mk_cat(*ids)

    def fake_load_index(_meta=None):
        return {'actions': {
            'a.aa': {'deps': ['action:ghost%d' % i for i in range(25)]},
        }}
    monkeypatch.setattr('vools.actus.indexer.load_index', fake_load_index)
    text = gaps_mod.health_report(cat)

    assert '同能力多实现：1 组' in text          # 501-502
    assert '（无）' in text                      # 511 suspect 空
    assert '…（其余 5 个略）' in text            # 518: 35-30
    assert '孤儿依赖：25 个' in text             # 521
    assert '…（其余 5 个略）' in text            # 525: 25-20（行内容同为截断文案）


def test_health_report_no_orphans_line(monkeypatch):
    def fake_load_index(_meta=None):
        return {'actions': {}}
    monkeypatch.setattr('vools.actus.indexer.load_index', fake_load_index)
    text = gaps_mod.health_report(_mk_cat('a.aa'))
    assert '孤儿依赖：0 个' in text
