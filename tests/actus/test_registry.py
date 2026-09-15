"""tests/actus/test_registry.py — 动作注册表测试"""
import pytest
import sys
import os
import tempfile
import json
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.registry import (
    ActionRegistry, RegistryEntry, build_registry, search_registry,
)


class TestRegistryEntry:
    """RegistryEntry 数据类测试"""

    def test_creation(self):
        entry = RegistryEntry(
            id='test.hello',
            name='Hello',
            version='1.0.0',
            description='Test action',
            category='test',
            path='actions/test.hello.actus.md',
            author='test',
            tags=['demo'],
            checksum='sha256:abc',
            signature=None,
            permissions=[],
            dependencies=[],
            trust_level='community',
        )
        assert entry.id == 'test.hello'
        assert entry.name == 'Hello'

    def test_to_dict(self):
        entry = RegistryEntry(
            id='test.d', name='D', version='1.0.0',
            description='', category='test', path='actions/t.md',
            author='t', tags=[], checksum='sha256:x',
            signature=None, permissions=[], dependencies=[],
            trust_level='community',
        )
        d = entry.to_dict()
        assert d['id'] == 'test.d'
        assert 'name' in d


class TestActionRegistry:
    """ActionRegistry 核心功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.mkdtemp()
        self.registry = ActionRegistry(cache_dir=self.tmpdir)
        yield
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_action_file(self, dir_path, filename, cfg):
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, filename)
        cfg_json = json.dumps(cfg, indent=2)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'# {cfg.get("name", "Action")}\n\n')
            f.write(f'```json #!cfg\n{cfg_json}\n```\n\n')
            f.write('## Description\nTest action.\n')
        return filepath

    def test_build_from_empty_directory(self):
        actions_dir = os.path.join(self.tmpdir, 'empty_repo', 'actions')
        os.makedirs(actions_dir)
        result = self.registry.build_from_directory(os.path.join(self.tmpdir, 'empty_repo'))
        assert result['actions'] == []

    def test_build_from_directory_with_actions(self):
        repo_dir = os.path.join(self.tmpdir, 'test_repo')
        actions_dir = os.path.join(repo_dir, 'actions')
        self._create_action_file(actions_dir, 'test.hello.actus.md', {
            'id': 'test.hello', 'name': 'Hello', 'trust': 'trusted',
        })
        result = self.registry.build_from_directory(repo_dir)
        assert len(result['actions']) == 1
        assert result['actions'][0]['id'] == 'test.hello'

    def test_build_writes_registry_file(self):
        repo_dir = os.path.join(self.tmpdir, 'test_repo')
        actions_dir = os.path.join(repo_dir, 'actions')
        self._create_action_file(actions_dir, 'my.action.actus.md', {
            'id': 'my.action', 'name': 'MyAction',
        })
        self.registry.build_from_directory(repo_dir)
        registry_path = os.path.join(repo_dir, '.actus.registry.json')
        assert os.path.exists(registry_path)

    def test_load_from_file(self):
        repo_dir = os.path.join(self.tmpdir, 'test_repo')
        actions_dir = os.path.join(repo_dir, 'actions')
        self._create_action_file(actions_dir, 't.actus.md', {
            'id': 't.load', 'name': 'Load',
        })
        self.registry.build_from_directory(repo_dir)
        # 新实例从文件加载
        new_registry = ActionRegistry(cache_dir=self.tmpdir)
        index = new_registry.load_from_file(os.path.join(repo_dir, '.actus.registry.json'))
        assert len(index['actions']) >= 1

    def test_load_from_repo(self):
        repo_dir = os.path.join(self.tmpdir, 'test_repo')
        actions_dir = os.path.join(repo_dir, 'actions')
        self._create_action_file(actions_dir, 'r.actus.md', {
            'id': 'r.test', 'name': 'Repo',
        })
        index = self.registry.load_from_repo(repo_dir)
        assert len(index['actions']) >= 1

    def test_search_empty(self):
        results = self.registry.search(query='nonexistent')
        assert results == []

    def test_list_all_empty(self):
        assert self.registry.list_all() == []

    def test_get_nonexistent(self):
        assert self.registry.get('nonexistent') is None

    def test_compute_checksum(self):
        import hashlib
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b'test content')
            f.flush()
            checksum = ActionRegistry._compute_checksum(f.name)
            assert checksum == hashlib.sha256(b'test content').hexdigest()
        os.unlink(f.name)

    def test_url_to_cache_key(self):
        key = ActionRegistry._url_to_cache_key('https://github.com/repo.git')
        assert 'https' not in key or '_' in key
        assert len(key) <= 64


class TestModuleFunctions:
    """模块级便捷函数测试"""

    def test_build_registry(self):
        result = build_registry
        assert callable(result)

    def test_search_registry(self):
        result = search_registry
        assert callable(result)
