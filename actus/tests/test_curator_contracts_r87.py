# -*- coding: utf-8 -*-
"""curator.py 契约测试（第 86 轮）——社区策展（default_repos/collections/featured）。

覆盖：_read_json/_write_json 降级、default_repos 增删列（脏账本过滤 V-11）、
_collection_path sanitize（V-10 空格+md5 后缀防碰撞）、collections
创建/读取/列表/分享、get_featured（trending 池∩popular、死动作剔除、
交集空回退 hot 池、score 排序——V-12）。

隔离：monkeypatch _DEFAULT_REPOS_FILE/_COLLECTIONS_DIR 到 tmp。
"""
import _ai_local_bootstrap  # noqa: F401

import json
import os

import pytest

import vools.actus.curator as cm
from vools.actus.curator import (add_default_repo, create_collection,
                                 get_featured, list_collections,
                                 list_default_repos, load_collection,
                                 remove_default_repo, share_collection)


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setattr(cm, '_DEFAULT_REPOS_FILE',
                        str(tmp_path / 'default_repos.json'))
    monkeypatch.setattr(cm, '_COLLECTIONS_DIR',
                        str(tmp_path / 'collections'))
    meta = tmp_path / '_meta'
    meta.mkdir()
    monkeypatch.setenv('ACTUS_META_DIR', str(meta))
    return tmp_path


# ═══════════════════════════════════════════════════════════════════
# 基础读写降级
# ═══════════════════════════════════════════════════════════════════

class TestIo:
    def test_read_json_missing_default(self, tmp_path):
        assert cm._read_json(str(tmp_path / 'nope.json'), []) == []

    def test_read_json_bad_default(self, tmp_path):
        p = tmp_path / 'bad.json'
        p.write_text('{broken', encoding='utf-8')
        assert cm._read_json(str(p), None) is None

    def test_write_json_creates_dirs(self, tmp_path):
        p = tmp_path / 'a' / 'b' / 'c.json'
        assert cm._write_json(str(p), {'x': 1}) is True
        assert json.loads(p.read_text(encoding='utf-8')) == {'x': 1}

    def test_write_json_oserror_false(self, tmp_path):
        # 目录路径当文件写 → OSError → False
        d = tmp_path / 'adir'
        d.mkdir()
        assert cm._write_json(str(d), {'x': 1}) is False


# ═══════════════════════════════════════════════════════════════════
# default_repos
# ═══════════════════════════════════════════════════════════════════

class TestDefaultRepos:
    def test_add_and_list(self, world):
        assert add_default_repo('https://x.dev/a/one') is True
        assert add_default_repo('https://x.dev/a/two', name='Two') is True
        repos = list_default_repos()
        assert repos[0]['name'] == 'one'       # 无 name → URL 尾段
        assert repos[1]['name'] == 'Two'

    def test_add_duplicate_false(self, world):
        add_default_repo('https://x.dev/a/one')
        assert add_default_repo('https://x.dev/a/one') is False

    def test_add_with_dirty_ledger(self, world):
        # V-11：字符串等非 dict 元素被过滤，不抛 AttributeError
        p = cm._DEFAULT_REPOS_FILE
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(['legacy-str', {'url': 'https://x.dev/a/old'}], f)
        assert add_default_repo('https://x.dev/a/new') is True
        repos = list_default_repos()
        assert all(isinstance(r, dict) for r in repos)
        assert {r['url'] for r in repos} == {'https://x.dev/a/old',
                                             'https://x.dev/a/new'}

    def test_add_when_file_not_list(self, world):
        p = cm._DEFAULT_REPOS_FILE
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'oops': 1}, f)
        assert add_default_repo('https://x.dev/a/one') is True

    def test_remove(self, world):
        add_default_repo('https://x.dev/a/one')
        assert remove_default_repo('https://x.dev/a/one') is True
        assert remove_default_repo('https://x.dev/a/one') is False
        assert list_default_repos() == []

    def test_remove_when_not_list(self, world):
        p = cm._DEFAULT_REPOS_FILE
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'oops': 1}, f)
        assert remove_default_repo('u') is False

    def test_list_when_missing(self, world):
        assert list_default_repos() == []


# ═══════════════════════════════════════════════════════════════════
# collections
# ═══════════════════════════════════════════════════════════════════

class TestCollections:
    def test_create_load_roundtrip(self, world):
        assert create_collection('工作流', ['a.b', 'c.d'], description='常用') is True
        data = load_collection('工作流')
        assert data['name'] == '工作流'
        assert data['action_ids'] == ['a.b', 'c.d']
        assert data['description'] == '常用'
        assert 'created_at' in data and '+08:00' in data['created_at']

    def test_create_filters_empty_ids(self, world):
        create_collection('t', ['a.b', '', None])
        assert load_collection('t')['action_ids'] == ['a.b']

    def test_load_missing_none(self, world):
        assert load_collection('no-such') is None

    def test_space_names_distinct_files(self, world):
        # V-10：'My List' 与 'MyList' 不同文件（md5 后缀），互不覆盖
        create_collection('My List', ['a.b'])
        create_collection('MyList', ['c.d'])
        names = [c['name'] for c in list_collections()]
        assert set(names) == {'My List', 'MyList'}

    def test_list_collections_shape(self, world):
        create_collection('col', ['a.b', 'c.d', 'e.f'], description='desc')
        rows = list_collections()
        assert len(rows) == 1
        r = rows[0]
        assert r['name'] == 'col' and r['action_count'] == 3
        assert r['description'] == 'desc'

    def test_list_collections_missing_dir(self, world, monkeypatch):
        monkeypatch.setattr(cm, '_COLLECTIONS_DIR',
                            str(world / 'not-there'))
        assert list_collections() == []

    def test_list_skips_corrupt_files(self, world):
        create_collection('good', ['a.b'])
        d = cm._COLLECTIONS_DIR
        (d and open(os.path.join(d, 'bad.json'), 'w', encoding='utf-8')
         ).write('{broken', ) if d else None
        with open(os.path.join(d, 'bad.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        (open(os.path.join(d, 'notjson.txt'), 'w', encoding='utf-8')
         ).write('x') if d else None
        rows = list_collections()
        assert [r['name'] for r in rows] == ['good']

    def test_share_collection(self, world, tmp_path):
        create_collection('share-me', ['a.b'])
        out_dir = tmp_path / 'git-repo'
        out_dir.mkdir()
        target = share_collection('share-me', str(out_dir))
        assert target is not None and os.path.isfile(target)
        data = json.loads(open(target, encoding='utf-8').read())
        assert data['name'] == 'share-me'

    def test_share_missing_none(self, world, tmp_path):
        out_dir = tmp_path / 'g2'
        out_dir.mkdir()
        assert share_collection('ghost', str(out_dir)) is None

    def test_share_write_failure_none(self, world, tmp_path):
        create_collection('collide', ['a.b'])
        out_dir = tmp_path / 'g3'
        out_dir.mkdir()
        # 目标名已被同名目录占用 → open OSError → None（165-166）
        (out_dir / os.path.basename(cm._collection_path('collide'))).mkdir()
        assert share_collection('collide', str(out_dir)) is None


# ═══════════════════════════════════════════════════════════════════
# get_featured（V-12 交集语义）
# ═══════════════════════════════════════════════════════════════════

def _fake_trending(rows):
    def f(limit=40, meta_dir=None):
        return rows[:limit]
    return f


def _fake_popular(rows):
    def f(limit=40, meta_dir=None):
        return rows[:limit]
    return f


class TestFeatured:
    def test_empty_pool_returns_empty(self, world, monkeypatch):
        monkeypatch.setattr('vools.actus.calllog.trending_actions', _fake_trending([]))
        assert get_featured(meta_dir='x') == []

    def test_dead_actions_only_returns_empty(self, world, monkeypatch):
        # growth=0 的死动作不进池 → 不伪造精选
        dead = [{'action_id': 'dead.a', 'count_7d': 0, 'growth': 0.0}]
        monkeypatch.setattr('vools.actus.calllog.trending_actions', _fake_trending(dead))
        assert get_featured(meta_dir='x') == []

    def test_intersection_scored_and_sorted(self, world, monkeypatch):
        trend = [
            {'action_id': 'hot.a', 'count_7d': 10, 'growth': 2.0},
            {'action_id': 'hot.b', 'count_7d': 5, 'growth': 1.0},
        ]
        pop = [
            {'action_id': 'hot.a', 'count': 100, 'success_rate': 0.99},
            {'action_id': 'hot.b', 'count': 50, 'success_rate': 0.95},
        ]
        monkeypatch.setattr('vools.actus.calllog.trending_actions', _fake_trending(trend))
        monkeypatch.setattr('vools.actus.calllog.popular_actions', _fake_popular(pop))
        rows = get_featured(limit=2, meta_dir='x')
        assert [r['action_id'] for r in rows] == ['hot.a', 'hot.b']
        top = rows[0]
        assert top['count'] == 100 and top['count_7d'] == 10
        expected = 2.0 * 0.7 + __import__('math').log1p(100) * 0.3
        assert top['score'] == round(expected, 4)

    def test_popular_hit_but_dead_pool_excluded(self, world, monkeypatch):
        # popular 命中但不在 hot 池（growth=0）→ 剔除（V-12 主场景）
        trend = [{'action_id': 'hot.a', 'count_7d': 3, 'growth': 1.5},
                 {'action_id': 'dead.b', 'count_7d': 0, 'growth': 0.0}]
        pop = [{'action_id': 'dead.b', 'count': 200, 'success_rate': 0.9},
               {'action_id': 'hot.a', 'count': 10, 'success_rate': 1.0}]
        monkeypatch.setattr('vools.actus.calllog.trending_actions', _fake_trending(trend))
        monkeypatch.setattr('vools.actus.calllog.popular_actions', _fake_popular(pop))
        rows = get_featured(meta_dir='x')
        assert [r['action_id'] for r in rows] == ['hot.a']

    def test_empty_intersection_falls_back_to_hot_pool(self, world, monkeypatch):
        # 交集空 → 回退 hot 池（近期活跃仍优于死动作）
        trend = [{'action_id': 'only.hot', 'count_7d': 2, 'growth': 0.8}]
        pop = [{'action_id': 'other.pop', 'count': 5, 'success_rate': 0.8}]
        monkeypatch.setattr('vools.actus.calllog.trending_actions', _fake_trending(trend))
        monkeypatch.setattr('vools.actus.calllog.popular_actions', _fake_popular(pop))
        rows = get_featured(meta_dir='x')
        assert [r['action_id'] for r in rows] == ['only.hot']
        assert rows[0]['count'] == 0 and rows[0]['success_rate'] == 0.0


def test_all_exports():
    assert set(cm.__all__) == {
        'add_default_repo', 'remove_default_repo', 'list_default_repos',
        'create_collection', 'load_collection', 'list_collections',
        'share_collection', 'get_featured'}
