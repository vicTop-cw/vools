"""tests/actus/test_vault.py — 密钥保险库测试"""
import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.vault import Vault, set_key, get_key, delete_key, list_keys, resolve_secrets, reset_vault_singleton


class TestVault:
    """Vault 密钥管理测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault = Vault(self.tmpdir, master_key='test_key_12345')
        yield
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        reset_vault_singleton()

    def test_set_and_get(self):
        self.vault.set('api_key', 'secret123')
        result = self.vault.get('api_key')
        assert result == 'secret123'

    def test_get_nonexistent(self):
        assert self.vault.get('nonexistent') is None

    def test_delete(self):
        self.vault.set('to_delete', 'value')
        assert self.vault.delete('to_delete') is True
        assert self.vault.get('to_delete') is None

    def test_delete_nonexistent(self):
        assert self.vault.delete('nonexistent') is False

    def test_list_keys(self):
        self.vault.set('key1', 'val1', description='First key')
        self.vault.set('key2', 'val2', description='Second key')
        keys = self.vault.list()
        assert len(keys) >= 2
        key_names = [k['key'] for k in keys]
        assert 'key1' in key_names
        assert 'key2' in key_names

    def test_list_with_scope(self):
        self.vault.set('k1', 'v1', scope='scope_a')
        self.vault.set('k2', 'v2', scope='scope_b')
        keys = self.vault.list(scope='scope_a')
        assert all(k['scope'] == 'scope_a' for k in keys)

    def test_update_existing_key(self):
        self.vault.set('api_key', 'old_value')
        self.vault.set('api_key', 'new_value')
        assert self.vault.get('api_key') == 'new_value'

    def test_scoped_keys(self):
        self.vault.set('token', 'val_a', scope='provider_a')
        self.vault.set('token', 'val_b', scope='provider_b')
        assert self.vault.get('token', scope='provider_a') == 'val_a'
        assert self.vault.get('token', scope='provider_b') == 'val_b'

    def test_persistence(self):
        self.vault.set('persist_key', 'persist_val')
        # 重新创建 vault 实例，验证持久化
        vault2 = Vault(self.tmpdir, master_key='test_key_12345')
        assert vault2.get('persist_key') == 'persist_val'

    def test_resolve_secrets_schema_format(self):
        self.vault.set('openai_key', 'sk-test123')
        secrets_config = [
            {'provider': 'openai_key', 'env': 'OPENAI_API_KEY', 'scopes': []}
        ]
        resolved = self.vault.resolve_secrets(secrets_config)
        assert resolved.get('OPENAI_API_KEY') == 'sk-test123'

    def test_resolve_secrets_compat_format(self):
        self.vault.set('my_token', 'token_val')
        secrets_config = [
            {'key': 'my_token', 'scope': 'global', 'default': ''}
        ]
        resolved = self.vault.resolve_secrets(secrets_config)
        assert resolved.get('my_token') == 'token_val'

    def test_resolve_secrets_missing_with_default(self):
        secrets_config = [
            {'key': 'missing_key', 'scope': 'global', 'default': 'fallback'}
        ]
        resolved = self.vault.resolve_secrets(secrets_config)
        assert resolved.get('missing_key') == 'fallback'


class TestVaultModuleFunctions:
    """模块级便捷函数测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['ACTUS_VAULT_KEY'] = 'module_test_key'
        yield
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        reset_vault_singleton()

    def test_module_set_get(self):
        set_key('mod_key', 'mod_val', meta_dir=self.tmpdir)
        assert get_key('mod_key', meta_dir=self.tmpdir) == 'mod_val'

    def test_module_delete(self):
        set_key('del_key', 'del_val', meta_dir=self.tmpdir)
        delete_key('del_key', meta_dir=self.tmpdir)
        assert get_key('del_key', meta_dir=self.tmpdir) is None

    def test_module_list(self):
        set_key('lk1', 'v1', meta_dir=self.tmpdir)
        set_key('lk2', 'v2', meta_dir=self.tmpdir)
        keys = list_keys(meta_dir=self.tmpdir)
        names = [k['key'] for k in keys]
        assert 'lk1' in names
