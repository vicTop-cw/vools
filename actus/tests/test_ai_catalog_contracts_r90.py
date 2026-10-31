"""catalog.py 边界分支契约测试（r90）。

补齐 test_ai_catalog.py 未触达的目录查询、构建过滤与缓存分支。
"""

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

import pytest

from vools.actus.ai import catalog as cat_mod
from vools.actus.ai.catalog import (CatalogEntry, ToolCatalog,
                                    normalize_tool_name, _suffixes,
                                    detect_duplicates, _entries_from_index,
                                    build_catalog, load_catalog)
from vools.actus.errors import ActionError


def _entry(action_id, description='', tags=(), **kw):
    return CatalogEntry(tool_name=normalize_tool_name(action_id),
                        action_id=action_id, description=description,
                        tags=tuple(tags), **kw)


# ── CatalogEntry ──

def test_entry_to_tool_spec_roundtrip():
    e = _entry('cli.jq', 'jq JSON', tags=('json',),
               parameters={'type': 'object'}, trust='sandbox')
    spec = e.to_tool_spec()
    assert spec.name == 'cli_jq' and spec.action_id == 'cli.jq'
    assert spec.trust == 'sandbox' and spec.parameters == {'type': 'object'}


# ── ToolCatalog 查询 ──

def test_catalog_contains_and_names():
    cat = ToolCatalog((_entry('b.b'), _entry('a.a')))
    assert 'b_b' in cat and 'zzz' not in cat
    assert cat.names() == ['a_a', 'b_b']


def test_catalog_get_missing_raises():
    cat = ToolCatalog(())
    with pytest.raises(ActionError) as ei:
        cat.get('nope')
    assert ei.value.code == 'action_not_found'
    assert ei.value.details['known_count'] == 0


def test_catalog_find_by_action_miss_returns_none():
    cat = ToolCatalog((_entry('a.a'),))
    assert cat.find_by_action('a.a') is not None
    assert cat.find_by_action('zz.z') is None


def test_catalog_grep_empty_keyword_returns_all():
    e1, e2 = _entry('a.aa', 'json'), _entry('b.bb', 'curl')
    cat = ToolCatalog((e1, e2))
    assert cat.grep('') == [e1, e2]            # 228
    assert cat.grep(' , /') == [e1, e2]        # 231 分词后为空
    assert cat.grep('json') == [e1]            # 正常命中
    assert cat.grep('json', limit=0) == []     # limit 截断


def test_catalog_get_found_returns_entry():
    cat = ToolCatalog((_entry('a.a'),))
    assert cat.get('a_a').action_id == 'a.a'   # 185 命中返回


def test_catalog_to_tool_specs_filter_no_args():
    e_args = _entry('a.withargs', 'x',
                    parameters={'type': 'object',
                                'properties': {'q': {}}})
    e_noargs = _entry('b.noargs', 'y', no_args=True)
    cat = ToolCatalog((e_args, e_noargs))
    assert len(cat.to_tool_specs()) == 2                    # 默认全收
    assert cat.to_tool_specs(include_no_args=False) == \
        [e_args.to_tool_spec()]


# ── _suffixes ──

def test_suffixes_empty_first_segment():
    assert _suffixes('.curl') == set()


def test_suffixes_below_min_segments():
    assert _suffixes('onlyone', min_segments=2) == set()


def test_suffixes_normal():
    assert _suffixes('actus.cli.curl', min_segments=2) == {
        'actus.cli.curl', 'cli.curl'}


# ── detect_duplicates ──

def test_detect_duplicates_skips_empty_action_id():
    e_none = CatalogEntry(tool_name='x', action_id='')
    rep = detect_duplicates([e_none, _entry('a.aa')])
    assert rep['exact'] == [] and rep['nonstandard_prefix'] == ['a.aa']


# ── _entries_from_index 过滤 ──

def _brief(**kw):
    d = {'description': 'd', 'trust': 'sandbox'}
    d.update(kw)
    return d


def test_entries_from_index_filters_all_branches():
    idx = {'actions': {
        '_invalid:bad': {},                       # 447 解析残骸
        'x.junk': 'not-a-dict',                   # 449
        'x.retired': _brief(status='retired'),    # 452 下架
        'x.old': _brief(deprecated=True),         # 455 deprecated
        'x.ok': _brief(args={'properties': {'q': {}}}),
    }}
    entries = _entries_from_index(idx)
    assert [e.action_id for e in entries] == ['x.ok']
    assert entries[0].no_args is False
    # include_deprecated 收录下架动作
    entries2 = _entries_from_index(idx, include_deprecated=True)
    assert 'x.old' in [e.action_id for e in entries2]


def test_entries_from_index_sorted_by_id():
    idx = {'actions': {'b.b': _brief(), 'a.a': _brief()}}
    assert [e.action_id for e in _entries_from_index(idx)] == ['a.a', 'b.b']


# ── build_catalog / load_catalog 缓存 ──

def test_build_catalog_index_failure_returns_empty(monkeypatch):
    def boom(_meta=None):
        raise RuntimeError('unavailable')
    monkeypatch.setattr('vools.actus.indexer.load_index', boom)
    cat = build_catalog('somewhere')
    assert len(cat) == 0 and cat.meta_dir == 'somewhere'


def test_load_catalog_caches_by_stamp(monkeypatch):
    cat_mod._CACHE.clear()
    builds = {'n': 0}
    real_build = cat_mod.build_catalog

    def counting_build(meta_dir=None, include_deprecated=False):
        builds['n'] += 1
        return real_build(meta_dir, include_deprecated)
    monkeypatch.setattr(cat_mod, 'build_catalog', counting_build)

    def fake_load_index(_meta=None):
        return {'generated_at': 'g1', 'actions': {'a.a': _brief()}}
    monkeypatch.setattr('vools.actus.indexer.load_index', fake_load_index)

    c1 = load_catalog('md')
    c2 = load_catalog('md')
    assert c1 is c2 and builds['n'] == 1       # 缓存命中不重建

    def fake_load_index2(_meta=None):
        return {'generated_at': 'g2',          # stamp 变化 → 缓存失效
                'actions': {'a.a': _brief()}}
    monkeypatch.setattr('vools.actus.indexer.load_index', fake_load_index2)
    c3 = load_catalog('md')
    assert c3 is not c1 and builds['n'] == 2
    cat_mod._CACHE.clear()


def test_load_catalog_index_failure_caches_empty(monkeypatch):
    cat_mod._CACHE.clear()
    builds = {'n': 0}
    real_build = cat_mod.build_catalog

    def counting_build(meta_dir=None, include_deprecated=False):
        builds['n'] += 1
        return real_build(meta_dir, include_deprecated)
    monkeypatch.setattr(cat_mod, 'build_catalog', counting_build)

    def boom(_meta=None):
        raise RuntimeError('down')
    monkeypatch.setattr('vools.actus.indexer.load_index', boom)
    c1 = load_catalog('mdown')
    c2 = load_catalog('mdown')
    # 失败 stamp='' 也按键缓存（连续故障不反复撞索引）
    assert len(c1) == 0 and c1 is c2 and builds['n'] == 1
    cat_mod._CACHE.clear()
