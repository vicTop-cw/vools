"""tests/actus/test_curator.py —— 社区策展模块测试。

覆盖：
  - default_repos 增删列（幂等）
  - collections 创建/读取/列出/分享
  - featured 精选（popular ∩ trending）
"""

import os
import pytest

from vools.actus import curator


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """把策展模块的配置目录重定向到 tmp_path（不碰用户真实 ~/.actus）。"""
    config_dir = tmp_path / '.actus' / 'config'
    collections_dir = config_dir / 'collections'
    monkeypatch.setattr(curator, '_CONFIG_DIR', str(config_dir))
    monkeypatch.setattr(curator, '_DEFAULT_REPOS_FILE', str(config_dir / 'default_repos.json'))
    monkeypatch.setattr(curator, '_COLLECTIONS_DIR', str(collections_dir))
    return tmp_path


class TestDefaultRepos:
    """默认仓测试"""

    def test_add_and_list(self, isolated_config):
        assert curator.add_default_repo('https://github.com/x/y') is True
        repos = curator.list_default_repos()
        assert len(repos) == 1
        assert repos[0]['url'] == 'https://github.com/x/y'

    def test_add_idempotent(self, isolated_config):
        assert curator.add_default_repo('https://github.com/x/y') is True
        assert curator.add_default_repo('https://github.com/x/y') is False
        assert len(curator.list_default_repos()) == 1

    def test_remove(self, isolated_config):
        curator.add_default_repo('https://github.com/x/y')
        assert curator.remove_default_repo('https://github.com/x/y') is True
        assert curator.list_default_repos() == []

    def test_remove_nonexistent(self, isolated_config):
        assert curator.remove_default_repo('https://github.com/nope') is False

    def test_list_empty(self, isolated_config):
        assert curator.list_default_repos() == []


class TestCollections:
    """集合测试"""

    def test_create_and_load(self, isolated_config):
        assert curator.create_collection('my-set', ['a.b', 'c.d'], 'desc') is True
        data = curator.load_collection('my-set')
        assert data is not None
        assert data['action_ids'] == ['a.b', 'c.d']
        assert data['name'] == 'my-set'
        assert data['description'] == 'desc'

    def test_load_nonexistent(self, isolated_config):
        assert curator.load_collection('nope') is None

    def test_list_collections(self, isolated_config):
        curator.create_collection('set1', ['a.b'])
        curator.create_collection('set2', ['c.d', 'e.f'])
        sets = curator.list_collections()
        assert len(sets) == 2
        assert sets[0]['name'] == 'set1'
        assert sets[0]['action_count'] == 1

    def test_create_filters_empty_ids(self, isolated_config):
        curator.create_collection('s', ['a.b', '', None])
        data = curator.load_collection('s')
        assert data['action_ids'] == ['a.b']

    def test_share_collection(self, isolated_config):
        curator.create_collection('s', ['a.b'])
        target = isolated_config / 'share_out'
        target.mkdir()
        out = curator.share_collection('s', str(target))
        assert out is not None
        assert os.path.isfile(out)

    def test_share_nonexistent(self, isolated_config):
        assert curator.share_collection('nope', str(isolated_config)) is None

    def test_name_sanitization(self, isolated_config):
        """集合名中的路径穿越字符被清洗"""
        curator.create_collection('../../evil', ['a.b'])
        data = curator.load_collection('../../evil')
        assert data is not None
        assert data['action_ids'] == ['a.b']


class TestFeatured:
    """精选动作测试"""

    def test_featured_from_metrics(self, isolated_config):
        from vools.actus import calllog
        meta_dir = str(isolated_config / '_meta')
        for _ in range(5):
            calllog.write_action_metric('a.hot', ok=True, runtime_ms=10,
                                        caller='t', meta_dir=meta_dir)
        featured = curator.get_featured(limit=5, meta_dir=meta_dir)
        assert featured
        assert featured[0]['action_id'] == 'a.hot'

    def test_featured_empty(self, isolated_config):
        assert curator.get_featured(meta_dir=str(isolated_config / '_meta')) == []
