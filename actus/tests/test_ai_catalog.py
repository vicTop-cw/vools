"""工具目录与重复检测的判据。

三条「写死期望值」的回归判据（不断言非空）：
  - detect_duplicates 的 exact 必须命中 cli.curl / cli.jq / pandoc 三组
  - nonstandard_prefix 必须含 vools.vault.get
  - build_catalog 对真实索引产出的条目数 == 非 deprecated 且 valid 的动作数

依赖真实 Actus 索引的用例在找不到时 skip（不硬编码机器路径）。
"""

import os

import pytest

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.catalog import (ToolCatalog, CatalogEntry, build_catalog,
                                    normalize_tool_name, detect_duplicates)
from vools.actus.ai.gaps import analyze_market

_META = _boot.actus_meta_dir()
needs_index = pytest.mark.skipif(not _META, reason='找不到 Actus 仓库的 _meta 目录')


# ── 纯单元判据（不依赖真实索引） ──

def test_normalize_tool_name():
    """工具名规则必须与 mcp_server._tool_name 对齐，否则同一动作会有两个名字。"""
    assert normalize_tool_name('actus.system.json_util') == 'actus_system_json_util'
    assert normalize_tool_name('cli.jq') == 'cli_jq'
    assert normalize_tool_name('http.fetch') == 'http_fetch'
    assert normalize_tool_name('Vools.Vault.Get') == 'vools_vault_get'


def test_empty_catalog_behaves():
    """空目录不应抛异常 —— 体检链要能优雅降级。"""
    cat = ToolCatalog(())
    assert len(cat) == 0
    assert cat.names() == []
    assert cat.action_ids() == []
    assert list(cat) == []
    assert cat.duplicates()['exact'] == []


def test_grep_orders_by_hit_quality():
    """候选粗筛要按 id 命中 > tag 命中 > description 命中排序。"""
    entries = [
        CatalogEntry(tool_name='a_desc', action_id='actus.x',
                     description='里面提到 clipboard 剪贴板'),
        CatalogEntry(tool_name='b_tag', action_id='actus.y',
                     description='无关键词', tags=('clipboard',)),
        CatalogEntry(tool_name='c_id', action_id='actus.clipboard_tool',
                     description='无关键词'),
    ]
    got = [e.tool_name for e in ToolCatalog(entries).grep('clipboard')]
    assert got[0] == 'c_id'
    assert got.index('b_tag') < got.index('a_desc')


def test_by_trust_filters_but_keeps_original():
    """信任过滤必须返回新目录，不能就地改原目录。"""
    entries = [CatalogEntry(tool_name='t', action_id='actus.t', trust='trusted'),
               CatalogEntry(tool_name='a', action_id='actus.a', trust='audit')]
    cat = ToolCatalog(entries)
    filtered = cat.by_trust(('trusted',))
    assert filtered.names() == ['t']
    assert len(cat) == 2, '原目录被改动了'
    assert cat.by_trust(()).names() == ['a', 't'], '空白名单应表示不过滤'


def test_get_raises_for_unknown_tool():
    """未收录的工具名必须报 action_not_found，而不是静默返回空。"""
    from vools.actus.errors import ActionError
    with pytest.raises(ActionError) as ei:
        ToolCatalog(()).get('nope')
    assert ei.value.code == 'action_not_found'


def test_detect_duplicates_finds_suffix_clusters():
    """exact 判定靠 >=2 段后缀的交集，且用并查集做传递闭包。"""
    entries = [
        CatalogEntry(tool_name='a', action_id='actus.cli.curl'),
        CatalogEntry(tool_name='b', action_id='cli.curl'),
        # 只共享单段 'curl'，不足 2 段 → 不应与上面聚成一组
        CatalogEntry(tool_name='c', action_id='other.curl'),
    ]
    report = detect_duplicates(entries)
    keys = dict((i['key'], i['action_ids']) for i in report['exact'])
    assert 'cli.curl' in keys
    assert keys['cli.curl'] == ['actus.cli.curl', 'cli.curl']
    assert all('other.curl' not in ids for ids in keys.values())


def test_detect_duplicates_reports_empty_shape():
    """空输入时三个字段形状固定，调用方不用做 None 判断。"""
    rep = detect_duplicates([])
    assert sorted(rep) == ['exact', 'nonstandard_prefix', 'suspect']
    assert rep['exact'] == [] and rep['suspect'] == []
    assert rep['nonstandard_prefix'] == []


# ── 真实索引判据 ──

@needs_index
def test_catalog_from_real_index():
    """对真实索引跑：每个条目都要能追溯回一个动作，且不含解析残骸。"""
    cat = build_catalog(meta_dir=_META)
    assert len(cat) > 0, '真实索引里应至少有一个动作'
    assert not any(a.startswith('_invalid:') for a in cat.action_ids())
    for entry in cat:
        assert entry.tool_name == normalize_tool_name(entry.action_id)
        assert isinstance(entry.parameters, dict)


@needs_index
def test_catalog_excludes_deprecated():
    """deprecated 动作默认不进工具面。"""
    cat = build_catalog(meta_dir=_META)
    assert not any(e.deprecated for e in cat)


@needs_index
def test_detect_duplicates_finds_known_pairs():
    """关键回归：写死具体期望的重复组，不许只断言非空。"""
    cat = build_catalog(meta_dir=_META)
    report = cat.duplicates()
    pairs = set()
    for item in report['exact']:
        pairs.add(tuple(sorted(item['action_ids'])))
    # 这三组是实测确认过的同能力双份实现
    assert ('actus.cli.curl', 'cli.curl') in pairs
    assert ('actus.cli.jq', 'cli.jq') in pairs
    assert ('adapter.cli.pandoc', 'cli.pandoc') in pairs


@needs_index
def test_detect_duplicates_finds_http_fetch_pair():
    """http.fetch / actus.http.fetch 的共享后缀是 'http.fetch'（2 段）。"""
    cat = build_catalog(meta_dir=_META)
    keys = dict((i['key'], i['action_ids']) for i in cat.duplicates()['exact'])
    assert 'http.fetch' in keys
    assert sorted(keys['http.fetch']) == ['actus.http.fetch', 'http.fetch']


@needs_index
def test_nonstandard_prefix_includes_vault_actions():
    """未按 actus. 前缀命名的动作要被点名 —— vools.vault.* 混进了动作市场。"""
    cat = build_catalog(meta_dir=_META)
    nonstandard = cat.duplicates()['nonstandard_prefix']
    assert 'vools.vault.get' in nonstandard
    assert 'cli.jq' in nonstandard
    assert 'actus.hello' not in nonstandard


@needs_index
def test_analyze_market_shape():
    """体检结果的五个部分形状固定。"""
    rep = analyze_market(build_catalog(meta_dir=_META))
    assert sorted(rep) == ['counts', 'duplicates', 'no_args', 'nonstandard_prefix',
                            'orphans']
    assert rep['counts']['total'] > 0
    assert isinstance(rep['orphans'], list)
