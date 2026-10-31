# -*- coding: utf-8 -*-
"""r92 — vault.py v1 边界分支 + 统一 resolver（v2 兼容层）契约测试。

此前 vault.py 仅被零散消费文件触达（68%）。本文件补齐：
- v1 边界：Xor 后端往返/HMAC、迁移 conflict/migrated/failed、原子写失败回滚、
  set 写盘失败内存回滚、get v2 回退/解密失败、inspect 三态、resolve_secrets 双格式
- resolver：_v2_session（真 db 缺失/假件成功失败/错误缓存）、resolve_secret 全矩阵、
  write_secret 全矩阵、rotate 薄包装、resolve_vault_refs、list_secret_names、
  delete_secret、migrate_legacy_secrets、_v2_readonly_session 真路径

v2 交互默认走假件（monkeypatch vault2._get_vault2），readonly 真路径用真注册身份。
零真网络、零真 keyring。
"""

import _ai_local_bootstrap  # noqa: F401  必须先于 vools 导入（见 docstring）

import json
import os
import sys

import pytest

import vools.actus.vault as vm
from vools.actus.vault import (Vault, _secret_fingerprint, delete_secret,
                               list_secret_names, migrate_legacy_secrets,
                               resolve_secret, resolve_vault_refs,
                               resolver_status, rotate_kek_v2,
                               rotate_seed_key_v2, write_secret)


# ──────────────────────────── fixtures ────────────────────────────


@pytest.fixture
def venv(monkeypatch, tmp_path):
    """v1+resolver 隔离环境：主密钥、meta 根、清三个会话缓存。"""
    meta = tmp_path / 'meta'
    meta.mkdir()
    monkeypatch.setenv('ACTUS_VAULT_KEY', 'k' * 32)
    monkeypatch.setenv('ACTUS_META_DIR', str(meta))
    monkeypatch.delenv(vm.RESOLVER_ENV, raising=False)
    monkeypatch.delenv(vm.LAZY_MIGRATE_ENV, raising=False)
    monkeypatch.delenv('ACTUS_VAULT_MIGRATE', raising=False)
    for cache in (vm._V2_SESSION_CACHE, vm._V2_ERROR_CACHE,
                  vm._V2_READONLY_CACHE):
        cache.clear()
    monkeypatch.delenv(vm.V2_IDENTITY_ENV, raising=False)
    monkeypatch.delenv(vm.V2_MACHINE_ENV, raising=False)
    monkeypatch.delenv(vm.V2_PIN_ENV, raising=False)
    monkeypatch.delenv('ACTUS_VAULT2_DIR', raising=False)
    monkeypatch.setattr(vm, '_get_vault', lambda _m=None: Vault(str(meta)))
    yield meta


class _FakeV2:
    """resolver 的 v2 假件：auth/get_secret/set_secret/delete_secret/..."""

    def __init__(self):
        self.auth_result = {'status': 'ok', 'session_token': 'tok-1'}
        self.secrets = {}
        self.calls = []
        self.get_payload = None
        self.fail_set = None
        self.fail_get = None
        self.fail_delete = None
        self.fail_rotate = None
        self.fail_seed = None
        self.fail_migrate = None

    def auth(self, ident, machine, pin):
        self.calls.append(('auth', ident))
        if isinstance(self.auth_result, Exception):
            raise self.auth_result
        return dict(self.auth_result)

    def get_secret(self, token, name, caller=None, read_only=False):
        self.calls.append(('get', name))
        if self.get_payload is not None:
            return dict(self.get_payload)
        if self.fail_get:
            raise RuntimeError(self.fail_get)
        if name in self.secrets:
            return {'status': 'ok', 'value': self.secrets[name]}
        return {'status': 'failed', 'message': '凭证不存在: %s' % name}

    def set_secret(self, token, name, value, caller=None):
        self.calls.append(('set', name))
        if self.fail_set:
            raise RuntimeError(self.fail_set)
        self.secrets[name] = value
        return {'status': 'ok'}

    def delete_secret(self, token, name, caller=None):
        self.calls.append(('delete', name))
        if self.fail_delete:
            raise RuntimeError(self.fail_delete)
        if name in self.secrets:
            del self.secrets[name]
            return {'status': 'ok'}
        return {'status': 'failed', 'message': '凭证不存在: %s' % name}

    def list_secrets(self, token):
        self.calls.append(('list',))
        return {'status': 'ok', 'secrets': [
            {'name': n} for n in sorted(self.secrets)]}

    def rotate_kek(self, token, caller=None, apply=True, mode=None):
        self.calls.append(('rotate_kek', apply, mode))
        if self.fail_rotate:
            raise RuntimeError(self.fail_rotate)
        return {'status': 'ok', 'applied': apply, 'mode': mode}

    def rotate_seed_key(self, token, caller=None):
        self.calls.append(('rotate_seed',))
        if self.fail_seed:
            raise RuntimeError(self.fail_seed)
        return {'status': 'ok'}

    def migrate_legacy_rows(self, token):
        self.calls.append(('migrate',))
        if self.fail_migrate:
            raise RuntimeError(self.fail_migrate)
        return {'status': 'ok', 'checked': 3, 'migrated': 2,
                'failed': [{'name': 'bad-one', 'reason': 'boom'}]}


@pytest.fixture
def fake_v2(venv, monkeypatch):
    """读路径（readonly）+ 写路径（session）都交给假会话。"""
    f = _FakeV2()
    monkeypatch.setattr('vools.actus.vault2._get_vault2', lambda: f)
    monkeypatch.setattr(vm, '_v2_readonly_session', lambda: (f, 'tok-ro', None))
    monkeypatch.setattr(vm, '_v2_session', lambda force=False: (f, 'tok-1', None))
    return f


@pytest.fixture
def v2_module(venv, monkeypatch):
    """真 _v2_session 路径：env 凭据 + 存在的 db 文件 + 假 _get_vault2。"""
    f = _FakeV2()
    monkeypatch.setattr('vools.actus.vault2._get_vault2', lambda: f)
    monkeypatch.setenv(vm.V2_IDENTITY_ENV, 'id1')
    monkeypatch.setenv(vm.V2_MACHINE_ENV, 'm1')
    monkeypatch.setenv(vm.V2_PIN_ENV, '123456')
    v2dir = venv.parent / 'v2m'
    v2dir.mkdir()
    (v2dir / 'vault2.db').write_text('', encoding='utf-8')
    monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
    return f


# ──────────────────── v1：Xor 后端 / 迁移 / 写入回滚 ────────────────────


class TestXorBackend:
    def test_make_backend_falls_back_to_xor(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'cryptography.fernet', None)
        b = vm._make_backend('k' * 32)
        assert isinstance(b, vm._XorHmacBackend)

    def test_xor_roundtrip_multiblock(self):
        b = vm._XorHmacBackend('k' * 32)
        payload = 'x' * 300          # 跨多个 64B 块
        ct = b.encrypt(payload)
        assert ct.startswith('xor:')
        assert b.decrypt(ct) == payload

    def test_xor_tampered_mac_raises(self):
        b = vm._XorHmacBackend('k' * 32)
        raw = bytearray(__import__('base64').b64decode(
            b.encrypt('secret')[len('xor:'):]))
        raw[20] ^= 0xFF               # mac 区（nonce16+mac32，mac 起点 16）
        tampered = 'xor:' + __import__('base64').b64encode(bytes(raw)).decode()
        with pytest.raises(ValueError):
            b.decrypt(tampered)


class TestVaultMigration:
    def _seed_legacy(self, meta, name='other-root'):
        legacy = meta.parent / name / '_meta' / 'vault'
        legacy.mkdir(parents=True)
        (legacy / 'keys.json').write_text('{}', encoding='utf-8')
        return legacy

    def test_conflict_when_both_sides_have_data(self, monkeypatch, tmp_path):
        meta = tmp_path / 'meta'
        vault_dir = meta / 'vault'
        vault_dir.mkdir(parents=True)
        (vault_dir / 'keys.json').write_text('{}', encoding='utf-8')
        legacy = self._seed_legacy(meta, 'legacy-root')
        monkeypatch.setenv('ACTUS_META_DIR', str(meta))
        monkeypatch.setenv('ACTUS_VAULT_MIGRATE', '1')
        monkeypatch.setenv('ACTUS_VAULT_KEY', 'k' * 32)
        monkeypatch.chdir(tmp_path / 'legacy-root')     # 候选一 = cwd/_meta/vault
        monkeypatch.setattr('vools.actus.paths.repo_root',
                            lambda: str(tmp_path / 'legacy-root'))
        v = Vault(str(meta), migrate_legacy=True)
        assert v.migration_conflict.startswith('ambiguous:')
        assert v.migrated_from is None

    def test_migrate_failed_on_oserror(self, monkeypatch, tmp_path):
        meta = tmp_path / 'meta'
        (meta / 'vault').mkdir(parents=True)          # 新位置为空
        legacy = self._seed_legacy(meta, 'legacy-root')
        monkeypatch.setenv('ACTUS_META_DIR', str(meta))
        monkeypatch.setenv('ACTUS_VAULT_KEY', 'k' * 32)
        monkeypatch.setattr(Vault, '_legacy_vault_candidates',
                            staticmethod(lambda: [str(legacy)]))

        def boom(src, dst):
            raise OSError('disk full')
        monkeypatch.setattr(vm.shutil, 'move', boom)
        v = Vault(str(meta), migrate_legacy=True)       # 254-255
        assert v.migration_conflict.startswith('migrate_failed:')

    def test_pending_skipped_in_test_env(self, venv):
        legacy = self._seed_legacy(venv, 'legacy-root')
        monkeypatch_candidates = None  # noqa
        import unittest.mock as _mock
        with _mock.patch.object(Vault, '_legacy_vault_candidates',
                                staticmethod(lambda: [str(legacy)])):
            v = Vault(str(venv), migrate_legacy=None)   # 测试环境 → pending
        assert v.migration_conflict and 'pending:' in v.migration_conflict
        assert legacy.exists()


class TestVaultWriteEdges:
    def test_set_rollback_on_save_failure(self, venv, monkeypatch):
        v = Vault(str(venv))
        assert v.set('a', '1')['status'] == 'ok'

        def boom(_path, _data):
            raise OSError('disk full')
        monkeypatch.setattr(Vault, '_atomic_write', staticmethod(boom))
        r = v.set('b', '2')                              # 355-364
        assert r['status'] == 'failed' and r['code'] == 'vault_write_failed'
        assert 'b' not in v._keys_data.get('global', {})  # 内存已回滚
        assert 'a' in v._keys_data['global']              # 已有键不受影响

    def test_atomic_write_failure_unlinks_tmp(self, venv, monkeypatch):
        v = Vault(str(venv))
        real_replace = os.replace

        def replace_fail(src, dst):
            raise OSError('replace boom')
        monkeypatch.setattr(os, 'replace', replace_fail)
        with pytest.raises(OSError):
            v._atomic_write(str(venv / 'vault' / 'x.json'), {'a': 1})
        monkeypatch.setattr(os, 'replace', real_replace)
        leftovers = [n for n in os.listdir(str(venv / 'vault'))
                     if n.startswith('.vault-')]
        assert leftovers == []                            # 302-305 tmp 已清

    def test_atomic_write_unlink_failure_swallowed(self, venv, monkeypatch):
        v = Vault(str(venv))

        def replace_fail(src, dst):
            raise OSError('replace boom')

        def unlink_fail(_p):
            raise OSError('unlink boom')
        monkeypatch.setattr(os, 'replace', replace_fail)
        monkeypatch.setattr(os, 'unlink', unlink_fail)
        with pytest.raises(OSError):
            v._atomic_write(str(venv / 'vault' / 'x.json'), {'a': 1})  # 304-305

    def test_ephemeral_refusal_sets_last_refusal(self, monkeypatch, tmp_path):
        monkeypatch.delenv('ACTUS_VAULT_KEY', raising=False)
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        v = Vault(str(tmp_path / 'meta'))
        assert v.ephemeral_key is True
        assert v.set('k', 'v')['code'] == 'vault_ephemeral_key'
        assert v.delete('k') is False and v.last_refusal  # 424-428

    def test_get_undecryptable_returns_none(self, venv):
        v = Vault(str(venv))
        v.set('a', '1')
        v._keys_data['global']['a'] = 'garbage-not-encrypted'
        assert v.get('a') is None                          # 395-396

    def test_inspect_three_states(self, venv):
        v = Vault(str(venv))
        assert v.inspect('nope') == 'absent'
        v.set('a', '1')
        assert v.inspect('a') == 'ok'
        v._keys_data['global']['a'] = 'garbage'
        assert v.inspect('a') == 'undecryptable'           # 409-410

    def test_get_v2_fallback_when_v1_missing(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_read_secret',
                            lambda name: ('found', 'from-v2', None))
        v = Vault(str(venv))
        assert v.get('only-in-v2') == 'from-v2'
        assert v.last_read_source == 'v2'                  # 384-388

    def test_get_no_fallback_when_resolver_off(self, venv, monkeypatch):
        monkeypatch.setenv(vm.RESOLVER_ENV, '0')
        called = []
        monkeypatch.setattr(vm, '_v2_read_secret',
                            lambda name: called.append(name) or (
                                'found', 'x', None))
        v = Vault(str(venv))
        assert v.get('x') is None and called == []

    def test_resolve_secrets_schema_format(self, venv):
        v = Vault(str(venv))
        v.set('openai', 'sk-1')
        v.set('scoped', 'sv', scope='project')
        out = v.resolve_secrets([
            {'provider': 'openai', 'env': 'OPENAI_API_KEY',
             'scopes': ['project', 'global']},             # 472-483
            {'provider': 'scoped', 'env': 'SCOPED',
             'scopes': ['global', 'project']},             # scope 轮询命中
            {'key': 'missing', 'scope': 'global',
             'default': 'fallback'},                       # 485-490
        ])
        assert out == {'OPENAI_API_KEY': 'sk-1', 'SCOPED': 'sv',
                       'missing': 'fallback'}


def test_secret_fingerprint_is_short_hash():
    fp = _secret_fingerprint('value')
    assert len(fp) == 12 and fp == _secret_fingerprint('value')


# ──────────────────── 第二批：便利函数 / v1 错误路径 / readonly 深分支 ────────────────────


class TestConvenienceFns:
    def test_set_get_delete_list_via_singleton(self, venv):
        assert vm.set_key('ck', 'cv', description='d')['status'] == 'ok'
        assert vm.get_key('ck') == 'cv'
        assert vm.list_keys()[0]['key'] == 'ck'
        assert vm.delete_key('ck') is True
        assert vm.get_key('ck') is None

    def test_resolve_secrets_convenience(self, venv):
        vm.set_key('p', 'pv')
        out = vm.resolve_secrets([{'provider': 'p', 'env': 'P_KEY'}])
        assert out == {'P_KEY': 'pv'}


class TestV1ReadSecretErrors:
    def test_vault_open_failure(self, venv, monkeypatch):
        def boom(_meta):
            raise RuntimeError('no dir')
        monkeypatch.setattr(vm, 'Vault', boom)
        state, value, reason = vm._v1_read_secret('k', 'global', str(venv))
        assert state == 'error' and 'no dir' in reason        # 692-693

    def test_undecryptable_maps_to_error(self, venv):
        v = Vault(str(venv))
        v.set('k', 'v')
        v._keys_data['global']['k'] = 'garbage'
        v._save()                                   # 读路径重新打开磁盘库
        state, _v, reason = vm._v1_read_secret('k', 'global', str(venv))
        assert state == 'error' and '解不开' in reason         # 698 + 744

    def test_inspect_ok_but_get_none(self, venv, monkeypatch):
        v = Vault(str(venv))
        v.set('k', 'v')
        monkeypatch.setattr(Vault, 'get', lambda self, *a, **k: None)
        state, value, _r = vm._v1_read_secret('k', 'global', str(venv))
        assert state == 'absent' and value is None            # 702


class TestResolveMore:
    def test_get_exception_maps_unavailable(self, fake_v2):
        fake_v2.fail_get = 'socket reset'
        state, value, reason = vm._v2_read_secret('k')
        assert state == 'unavailable' and 'socket reset' in reason  # 663-664

    def test_session_invalid_retries_once(self, fake_v2):
        fake_v2.get_payloads = [
            {'status': 'failed', 'message': '会话无效: tok-ro'},
            {'status': 'ok', 'value': 'fresh'}]
        fake_v2.get_payload = None

        def get_secret(token, name, caller=None, read_only=False):
            return dict(fake_v2.get_payloads.pop(0))
        fake_v2.get_secret = get_secret
        state, value, reason = vm._v2_read_secret('k')
        assert (state, value, reason) == ('found', 'fresh', None)   # 671-684

    def test_session_invalid_twice_maps_error(self, fake_v2):
        fake_v2.get_payload = {'status': 'failed',
                               'message': '会话无效: tok'}
        state, _v, _r = vm._v2_read_secret('k')
        assert state == 'error'                              # 685 兜底

    def test_v1_undecryptable_short_circuits(self, venv):
        v = Vault(str(venv))
        v.set('k', 'v')
        v._keys_data['global']['k'] = 'garbage'
        v._save()
        fake_v2_secrets = {}
        import unittest.mock as _mock
        with _mock.patch.object(vm, '_v2_readonly_session',
                                lambda: (None, None, 'no creds')):
            r = resolve_secret('k')
        assert r['status'] == 'error' and '解不开' in r['message']   # 743-745

    def test_lazy_migrate_failure_warns(self, fake_v2, venv, monkeypatch):
        monkeypatch.setenv(vm.LAZY_MIGRATE_ENV, '1')
        Vault(str(venv)).set('k', 'v1-val')            # v2 空 → v1-only 分支
        import unittest.mock as _mock
        with _mock.patch.object(vm, '_migrate_to_v2',
                                lambda name, value: (False, 'write boom')):
            r = resolve_secret('k')
        assert r['status'] == 'ok' and r['value'] == 'v1-val'
        assert any('懒迁移失败' in w and 'write boom' in w
                   for w in r['warnings'])                   # 778-779

    def test_v2_unavailable_falls_back_with_warning(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_readonly_session',
                            lambda: (None, None, 'no creds'))
        Vault(str(venv)).set('k', 'v1-val')
        r = resolve_secret('k')
        assert r['status'] == 'ok' and r['value'] == 'v1-val'
        assert any('v2 不可用' in w for w in r['warnings'])    # 767-768

    def test_migrate_to_v2_session_reason(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_session',
                            lambda force=False: (None, None, 'no creds'))
        ok, reason = vm._migrate_to_v2('k', 'v')
        assert not ok and reason == 'no creds'                # 794

    def test_migrate_to_v2_fail_status(self, fake_v2):
        fake_v2.set_secret = lambda *a, **k: {
            'status': 'failed', 'message': 'quota'}
        ok, reason = vm._migrate_to_v2('k', 'v')
        assert not ok and 'quota' in reason                   # 800

    def test_write_v2_error_maps_read_failed(self, fake_v2):
        fake_v2.get_payload = {'status': 'failed', 'message': 'db boom'}
        r = write_secret('k', 'v')
        assert r['code'] == 'v2_read_failed'                  # 827

    def test_write_v1_failure_appends_warning(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_read_secret',
                            lambda name: ('unavailable', None, 'no creds'))
        Vault(str(venv))
        monkeypatch.setattr(Vault, 'set',
                            lambda self, *a, **k: {'status': 'failed',
                                                   'message': 'disk full'})
        r = write_secret('k', 'v', allow_v1_write=True)
        assert r['status'] == 'failed'
        assert any('v1' in w for w in r['warnings'])          # 863-864


class TestReadonlyDeep:
    def test_get_vault2_exception(self, venv, monkeypatch):
        for env, val in ((vm.V2_IDENTITY_ENV, 'i'), (vm.V2_MACHINE_ENV, 'm'),
                         (vm.V2_PIN_ENV, '123456')):
            monkeypatch.setenv(env, val)
        v2dir = venv.parent / 'v2x'
        v2dir.mkdir()
        (v2dir / 'vault2.db').write_text('', encoding='utf-8')
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))

        def boom():
            raise RuntimeError('store down')
        monkeypatch.setattr('vools.actus.vault2._get_vault2', boom)
        _m, _t, reason = vm._v2_readonly_session()
        assert 'v2 不可用（RuntimeError' in reason             # 1048-1049

    def test_identity_row_missing(self, venv, monkeypatch):
        import vools.actus.vault2 as v2
        v2dir = venv.parent / 'v2y'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_VAULT_KEY', 'k' * 32)
        vault = v2.Vault2(vault_dir=str(v2dir))
        vault._ensure_ready()                          # 建库（读路径不造库的前置）
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, 'ghost-id')
        monkeypatch.setenv(vm.V2_MACHINE_ENV, 'm')
        monkeypatch.setenv(vm.V2_PIN_ENV, '123456')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        _m, _t, reason = vm._v2_readonly_session()
        assert 'v2 身份不存在' in reason                       # 1058

    def test_machine_not_registered(self, monkeypatch, tmp_path):
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2z'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u3', '222222', 'host3', security_level='L1')
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, 'wrong-machine')
        monkeypatch.setenv(vm.V2_PIN_ENV, '222222')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        _m, _t, reason = vm._v2_readonly_session()
        assert 'v2 机器未注册' in reason                       # 1072

    def test_l2_dynamic_code_branch(self, monkeypatch, tmp_path):
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2l2'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u4', '333333', 'host4', security_level='L2')
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        monkeypatch.setenv(vm.V2_PIN_ENV, '333333')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        _m, token, reason = vm._v2_readonly_session()
        assert reason is None and token.startswith('readonly-')  # 1079

    def test_old_token_evicted_on_rebuild(self, monkeypatch, tmp_path):
        """换缓存键后旧只读 token 从 vault._sessions 里清掉（1098-1101）。"""
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2e'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u5', '444444', 'host5', security_level='L1')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        vm._V2_READONLY_CACHE.clear()
        monkeypatch.setenv(vm.V2_PIN_ENV, '444444')
        _m1, t1, r1 = vm._v2_readonly_session()
        assert r1 is None
        monkeypatch.setenv(vm.V2_PIN_ENV, '444444')
        vm._V2_READONLY_CACHE.pop('key', None)   # 强制缓存 miss（换键）
        vm._V2_READONLY_CACHE.update({'key': ('old',), 'token': t1})
        # 同凭据 → 缓存 key 不匹配 → 重建 → 旧 token 被清
        _m2, t2, r2 = vm._v2_readonly_session()
        assert r2 is None and t2 != t1
        assert t1 not in vault._sessions          # 1098-1101

    def test_fingerprint_mismatch(self, monkeypatch, tmp_path):
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2f'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u6', '555555', 'host6', security_level='L1')
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        monkeypatch.setenv(vm.V2_PIN_ENV, '555555')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        monkeypatch.setattr(vault, '_machine_fingerprint', lambda: 'zzz')
        _m, _t, reason = vm._v2_readonly_session()
        assert '指纹不匹配' in reason                          # 1074

    def test_legacy_identity_pin_derivation(self, monkeypatch, tmp_path):
        """key_salt 为空的旧身份走 pin 派生分支（1084-1086）。"""
        import sqlite3
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2old'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u7', '666666', 'host7', security_level='L1')
        db = os.path.join(str(v2dir), 'vault2.db')
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE identities SET key_salt=NULL WHERE id=?',
                         (reg['identity_id'],))
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        monkeypatch.setenv(vm.V2_PIN_ENV, '666666')
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        _m, token, reason = vm._v2_readonly_session()
        assert reason is None and token.startswith('readonly-')  # 1085

    def test_readonly_names_error_paths(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_readonly_session',
                            lambda: (None, None, 'no creds'))
        names, avail, reason = vm._v2_readonly_names()
        assert names == [] and avail is False and reason == 'no creds'

        class _F:
            def list_secrets(self, token):
                raise RuntimeError('list boom')
        monkeypatch.setattr(vm, '_v2_readonly_session',
                            lambda: (_F(), 't', None))
        names, avail, reason = vm._v2_readonly_names()
        assert avail is False and 'list boom' in reason        # 1114-1115

        class _G:
            def list_secrets(self, token):
                return {'status': 'failed', 'message': 'locked'}
        monkeypatch.setattr(vm, '_v2_readonly_session',
                            lambda: (_G(), 't', None))
        names, avail, reason = vm._v2_readonly_names()
        assert avail is False and reason == 'locked'           # 1117


class TestListDeleteMore:
    def test_v1_list_exception_sets_v1_error(self, fake_v2, venv,
                                             monkeypatch):
        def boom(_meta):
            raise RuntimeError('keys corrupt')
        monkeypatch.setattr(vm, 'Vault', boom)
        r = list_secret_names(meta_dir=str(venv))
        assert 'keys corrupt' in r['v1_error']                 # 1151-1152

    def test_delete_vault_prefix_stripped(self, fake_v2):
        fake_v2.secrets['k'] = 'v'
        r = delete_secret('vault://k')
        assert r['status'] == 'ok' and r['key'] == 'k'         # 1189

    def test_delete_v2_fail_status(self, fake_v2):
        fake_v2.delete_secret = lambda token, name, caller=None: {
            'status': 'failed', 'message': 'locked'}
        r = delete_secret('k')
        assert r['status'] == 'failed' and 'locked' in r['errors'][0]  # 1204

    def test_delete_v1_exception(self, fake_v2, venv, monkeypatch):
        def boom(self, key, scope='global'):
            raise OSError('fs ro')
        monkeypatch.setattr(Vault, 'delete', boom)
        r = delete_secret('k', meta_dir=str(venv), include_v1=True)
        assert any('v1 删除异常' in e for e in r['errors'])     # 1217-1218

    def test_legacy_secret_names_no_identity(self, fake_v2, venv):
        v = Vault(str(venv))
        assert vm._legacy_secret_names(v, 'no-token') == []    # 1238

    def test_migrate_fail_status_maps_error(self, fake_v2):
        fake_v2.migrate_legacy_rows = lambda token: {
            'status': 'failed', 'message': 'schema old'}
        r = migrate_legacy_secrets()
        assert r['status'] == 'error' and 'schema old' in r['message']  # 1287


# ──────────────────── resolver：_v2_session ────────────────────


class TestV2Session:
    def test_missing_credentials(self, venv):
        mod, token, reason = vm._v2_session()
        assert mod is None and '未配置 v2 凭据' in reason

    def test_db_missing(self, venv, monkeypatch):
        for env, val in ((vm.V2_IDENTITY_ENV, 'id'), (vm.V2_MACHINE_ENV, 'm'),
                         (vm.V2_PIN_ENV, '123456')):
            monkeypatch.setenv(env, val)
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(venv.parent / 'nope'))
        mod, token, reason = vm._v2_session()
        assert mod is None and 'v2 密钥库不存在' in reason

    def test_success_then_cache_hit(self, v2_module):
        m1, t1, r1 = vm._v2_session()
        assert r1 is None and t1 == 'tok-1'
        v2_module.auth_result = {'status': 'ok', 'session_token': 'tok-2'}
        m2, t2, r2 = vm._v2_session()                    # 缓存命中，不再 auth
        assert (t2, r2, m2 is m1) == ('tok-1', None, True)
        assert v2_module.calls.count(('auth', 'id1')) == 1

    def test_error_cached_within_ttl(self, v2_module):
        v2_module.auth_result = {'status': 'failed', 'message': 'PIN 错误'}
        m1, _t, r1 = vm._v2_session()
        assert 'v2 auth 失败' in r1
        v2_module.auth_result = {'status': 'ok', 'session_token': 'x'}
        _m2, _t2, r2 = vm._v2_session()                  # 错误缓存内不重试
        assert r2 == r1

    def test_exception_reason_cached(self, v2_module):
        v2_module.auth_result = RuntimeError('keyring down')
        _m, _t, r1 = vm._v2_session()
        assert 'v2 不可用（RuntimeError' in r1           # 629-632


# ──────────────────── resolver：resolve_secret 全矩阵 ────────────────────


class TestResolveSecret:
    def test_empty_name_param_invalid(self, fake_v2):
        r = resolve_secret('   ')
        assert r['status'] == 'error' and r['code'] == 'param_invalid'

    def test_vault_prefix_stripped(self, fake_v2):
        fake_v2.secrets['k'] = 'v'
        r = resolve_secret('vault://k')
        assert r['status'] == 'ok' and r['value'] == 'v'

    def test_v2_error_no_fallback(self, fake_v2):
        fake_v2.get_payload = {'status': 'failed', 'message': 'db exploded'}
        r = resolve_secret('k')
        assert r['status'] == 'error' and r['code'] == 'v2_read_failed'

    def test_both_found_same_value(self, fake_v2, venv):
        fake_v2.secrets['k'] = 'same'
        Vault(str(venv)).set('k', 'same')
        r = resolve_secret('k')
        assert r['status'] == 'ok' and r['source'] == 'v2+v1'

    def test_both_found_diff_value_conflict(self, fake_v2, venv):
        fake_v2.secrets['k'] = 'v2-val'
        Vault(str(venv)).set('k', 'v1-val')
        r = resolve_secret('k')
        assert r['status'] == 'conflict'
        assert 'v1 指纹' in r['message'] and 'v2 指纹' in r['message']

    def test_v2_only_ok(self, fake_v2):
        fake_v2.secrets['k'] = 'only2'
        r = resolve_secret('k')
        assert r['status'] == 'ok' and r['source'] == 'v2'

    def test_v1_only_with_warning(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'only1')
        fake_v2.secrets.pop('k', None)
        r = resolve_secret('k')
        assert r['status'] == 'ok' and r['value'] == 'only1'
        assert any('only-v1' in w or 'v1' in w for w in r['warnings'])

    def test_v1_only_lazy_migrate(self, fake_v2, venv, monkeypatch):
        monkeypatch.setenv(vm.LAZY_MIGRATE_ENV, '1')
        Vault(str(venv)).set('k', 'migrate-me')
        r = resolve_secret('k')
        assert r['status'] == 'ok'
        assert fake_v2.secrets.get('k') == 'migrate-me'   # 772-779

    def test_neither_found(self, fake_v2):
        r = resolve_secret('ghost')
        assert r['status'] == 'not_found'


def test_migrate_to_v2_branches(fake_v2, venv):
    ok, reason = vm._migrate_to_v2('k', 'v')
    assert ok and reason is None and fake_v2.secrets['k'] == 'v'
    fake_v2.fail_set = 'write boom'
    ok2, reason2 = vm._migrate_to_v2('k2', 'v')
    assert not ok2 and 'write boom' in reason2


# ──────────────────── resolver：write_secret 全矩阵 ────────────────────


class TestWriteSecret:
    def test_param_invalid(self, fake_v2):
        assert write_secret('', '')['code'] == 'param_invalid'
        assert write_secret('k', None)['code'] == 'param_invalid'

    def test_v2_write_new_key(self, fake_v2):
        r = write_secret('k', 'v')
        assert r == {'status': 'ok', 'name': 'k', 'source': 'v2',
                     'warnings': []}

    def test_v2_overwrites_same_v1_value(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'old')
        fake_v2.secrets['k'] = 'stale-v2'
        # 冲突判定比较 v1 值与**本次要写的值**；相同 → 覆盖 v2 + warning
        r = write_secret('k', 'old')
        assert r['status'] == 'ok'
        assert fake_v2.secrets['k'] == 'old'
        assert any('v1 未改动' in w for w in r['warnings'])

    def test_conflict_when_v1_differs(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'v1-val')
        fake_v2.secrets['k'] = 'v2-old'
        r = write_secret('k', 'v2-new')
        assert r['status'] == 'conflict'

    def test_session_refused(self, fake_v2, monkeypatch):
        monkeypatch.setattr(vm, '_v2_session',
                            lambda force=False: (None, None, 'no keyring'))
        assert write_secret('k', 'v')['status'] == 'refused'

    def test_set_secret_exception(self, fake_v2):
        fake_v2.fail_set = 'disk full'
        r = write_secret('k', 'v')
        assert r['code'] == 'v2_write_failed' and 'disk full' in r['message']

    def test_set_secret_fail_status(self, fake_v2):
        def fail_set(token, name, value, caller=None):
            return {'status': 'failed', 'message': 'quota'}
        fake_v2.set_secret = fail_set
        assert write_secret('k', 'v')['code'] == 'v2_write_failed'

    def test_overwrite_path_exception_and_fail(self, fake_v2, venv):
        """v2 found + v1 同值 → 走 836-851 的覆盖路径（异常/fail 两分支）。"""
        Vault(str(venv)).set('k', 'same')
        fake_v2.secrets['k'] = 'stale'
        fake_v2.fail_set = 'write boom'
        r = write_secret('k', 'same')
        assert r['code'] == 'v2_write_failed' and 'write boom' in r['message']

        def fail_set(token, name, value, caller=None):
            return {'status': 'failed', 'message': 'quota'}
        fake_v2.fail_set = None
        fake_v2.set_secret = fail_set
        r2 = write_secret('k', 'same')
        assert r2['code'] == 'v2_write_failed'               # 845-847

    def test_session_refused_with_v2_found(self, fake_v2, monkeypatch):
        fake_v2.secrets['k'] = 'exists'
        monkeypatch.setattr(vm, '_v2_session',
                            lambda force=False: (None, None, 'no keyring'))
        r = write_secret('k', 'v')
        assert r['status'] == 'refused'                      # 836-839

    def test_session_invalid_rebuild_paths(self, fake_v2, monkeypatch):
        """重建会话后的四条出路：reason / 异常 / absent / ok（674-684）。"""
        class _Raiser:
            def get_secret(self, token, name, caller=None, read_only=False):
                raise RuntimeError('会话无效: tok1')

        class _Raiser2:
            def get_secret(self, token, name, caller=None, read_only=False):
                raise OSError('socket down')

        class _Absent:
            def get_secret(self, token, name, caller=None, read_only=False):
                return {'status': 'failed', 'message': '凭证不存在'}

        class _OK:
            def get_secret(self, token, name, caller=None, read_only=False):
                return {'status': 'ok', 'value': 'after-rebuild'}

        def _session_raiser():
            return (_Raiser(), 'tok-ro', None)
        monkeypatch.setattr(vm, '_v2_readonly_session', _session_raiser)
        st, _v, _r = vm._v2_read_secret('k')          # 首会话 → 会话无效

        outcomes = [((_Raiser(), 't2', None), 'unavailable', None),   # 674
                    ((_Raiser2(), 't2', None), 'unavailable', 'OSError'),  # 678
                    ((_Absent(), 't2', None), 'absent', None),        # 684
                    ((_OK(), 't2', None), 'found', 'after-rebuild')]
        for session_out, want_state, want_val in outcomes:
            import unittest.mock as _mock
            with _mock.patch.object(vm, '_v2_readonly_session',
                                    lambda s=session_out: s):
                st, val, reason = vm._v2_read_secret('k')
            assert st == want_state
            if want_val is not None and want_state == 'found':
                assert val == want_val
            if want_state == 'unavailable' and want_val == 'OSError':
                assert 'OSError' in reason

    def test_write_strips_vault_prefix(self, fake_v2):
        r = write_secret('vault://k', 'v')            # 817 前缀剥离
        assert r['status'] == 'ok' and fake_v2.secrets['k'] == 'v'

    def test_v2_unavailable_refused_by_default(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_read_secret',
                            lambda name: ('unavailable', None, 'no creds'))
        r = write_secret('k', 'v')
        assert r['status'] == 'refused' and r['code'] == 'vault2_unavailable'

    def test_v2_unavailable_allow_v1_write(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_read_secret',
                            lambda name: ('unavailable', None, 'no creds'))
        r = write_secret('k', 'v', allow_v1_write=True)
        assert r['status'] == 'ok' and r['source'] == 'v1'
        assert Vault(str(venv)).get('k') == 'v'


# ──────────────────── rotate 薄包装 ────────────────────


class TestRotateWrappers:
    def test_kek_refused_without_v2(self, venv):
        r = rotate_kek_v2()
        assert r['status'] == 'refused' and r['code'] == 'vault2_unavailable'

    def test_kek_passthrough_and_exception(self, fake_v2):
        r = rotate_kek_v2(dry_run=True, mode='keyring')
        assert r == {'status': 'ok', 'applied': False, 'mode': 'keyring'}
        fake_v2.fail_rotate = 'boom'
        r2 = rotate_kek_v2()
        assert r2['code'] == 'kek_rotate_failed'

    def test_seed_refused_without_v2(self, venv):
        assert rotate_seed_key_v2()['status'] == 'refused'

    def test_seed_ok_clears_cache(self, fake_v2):
        vm._V2_SESSION_CACHE['stale'] = {'creds': ('x',), 'token': 't',
                                         'ts': 0.0, 'module': None}
        r = rotate_seed_key_v2()
        assert r['status'] == 'ok'
        assert vm._V2_SESSION_CACHE == {}                 # 931-933

    def test_seed_exception(self, fake_v2):
        fake_v2.fail_seed = 'boom'
        assert rotate_seed_key_v2()['code'] == 'rotate_failed'


# ──────────────────── resolve_vault_refs / resolver_status ────────────────────


class TestResolveVaultRefs:
    def test_non_dict_skipped_and_default_used(self, fake_v2):
        r = resolve_vault_refs(['junk', {'env': 'E', 'key': 'plain',
                                         'default': 'dflt'}])
        assert r['status'] == 'ok' and r['resolved'] == {'E': 'dflt'}

    def test_ok_missing_and_conflict(self, fake_v2, venv):
        fake_v2.secrets['good'] = 'g'
        Vault(str(venv)).set('bad', 'a')
        fake_v2.secrets['bad'] = 'b'                      # 双库异值
        r = resolve_vault_refs([
            {'env': 'E1', 'key': 'vault://good'},
            {'env': 'E3', 'key': 'vault://ghost'},
        ])
        assert r['status'] == 'ok'
        assert r['resolved'] == {'E1': 'g'}
        assert r['missing'] == ['vault://ghost']
        r2 = resolve_vault_refs([{'env': 'E2', 'key': 'vault://bad'}])
        assert r2['status'] == 'conflict' and len(r2['conflicts']) == 1

    def test_error_wins_over_missing(self, fake_v2, monkeypatch):
        monkeypatch.setattr(vm, 'resolve_secret',
                            lambda key, meta_dir=None: {
                                'status': 'error', 'message': 'down'})
        r = resolve_vault_refs([{'env': 'E', 'key': 'vault://k'}])
        assert r['status'] == 'error' and r['code'] == 'vault_read_failed'

    def test_conflict_wins(self, fake_v2, monkeypatch):
        monkeypatch.setattr(vm, 'resolve_secret',
                            lambda key, meta_dir=None: {
                                'status': 'conflict', 'message': 'diff'})
        r = resolve_vault_refs([{'env': 'E', 'key': 'vault://k'}])
        assert r['status'] == 'conflict'

    def test_not_found_with_default(self, fake_v2, monkeypatch):
        monkeypatch.setattr(vm, 'resolve_secret',
                            lambda key, meta_dir=None: {'status': 'not_found'})
        r = resolve_vault_refs([{'env': 'E', 'key': 'vault://k',
                                 'default': 'fb'}])
        assert r['resolved'] == {'E': 'fb'} and r['missing'] == []


def test_resolver_status_fields(venv, monkeypatch):
    monkeypatch.setattr(vm, '_v2_readonly_session',
                        lambda: (None, None, 'no creds'))
    r = resolver_status()
    assert r == {'enabled': True, 'v2_available': False,
                 'v2_reason': 'no creds',
                 'v1_path': os.path.join(str(venv), 'vault'),
                 'lazy_migrate': False}


# ──────────────────── 合并清单 / 删除 / 迁移 ────────────────────


class TestListSecretNames:
    def test_v1_only(self, fake_v2, venv):
        Vault(str(venv)).set('a', '1')
        r = list_secret_names(meta_dir=str(venv))
        assert r['v2_available'] is True
        assert [k['key'] for k in r['keys']] == ['a']
        assert r['keys'][0]['source'] == 'v1'

    def test_conflict_row_flagged(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'v1')
        fake_v2.secrets['k'] = 'v2'
        r = list_secret_names(meta_dir=str(venv))
        (row,) = r['keys']
        assert row['conflict'] is True and row['source'] == 'v1+v2'

    def test_same_value_source_v2_first(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'same')
        fake_v2.secrets['k'] = 'same'
        (row,) = list_secret_names(meta_dir=str(venv))['keys']
        assert row['source'] == 'v2+v1' and row['conflict'] is False


class TestDeleteSecret:
    def test_v2_delete_ok(self, fake_v2):
        fake_v2.secrets['k'] = 'v'
        r = delete_secret('k')
        assert r['status'] == 'ok' and r['deleted_v2'] is True
        assert 'hint' in r

    def test_v2_absent_not_found(self, fake_v2):
        assert delete_secret('ghost')['status'] == 'not_found'

    def test_v2_error_failed(self, fake_v2):
        fake_v2.fail_delete = 'boom'
        r = delete_secret('k')
        assert r['status'] == 'failed' and r['errors']

    def test_include_v1_deletes_both(self, fake_v2, venv):
        Vault(str(venv)).set('k', 'v')
        fake_v2.secrets['k'] = 'v'
        r = delete_secret('k', meta_dir=str(venv), include_v1=True)
        assert r['deleted'] == ['v2', 'v1']
        assert Vault(str(venv)).get('k') is None

    def test_v1_refusal_reported(self, fake_v2, venv, monkeypatch):
        v = Vault(str(venv))
        v.set('k', 'v')

        def refuse(self, key, scope='global'):
            self.last_refusal = {'message': 'ephemeral'}
            return False
        monkeypatch.setattr(Vault, 'delete', refuse)
        r = delete_secret('k', meta_dir=str(venv), include_v1=True)
        assert any('v1 删除被拒绝' in e for e in r['errors'])


class TestMigrateLegacy:
    def test_bad_scope(self, fake_v2):
        assert migrate_legacy_secrets(scope='weird')['status'] == 'param_invalid'

    def test_dry_run_refused_without_creds(self, venv):
        r = migrate_legacy_secrets(dry_run=True)
        assert r['status'] == 'refused' and r['code'] == 'vault2_unavailable'

    def test_dry_run_counts(self, fake_v2, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_readonly_session',
                            lambda: (None, None, 'no creds'))
        r = migrate_legacy_secrets(dry_run=True)
        assert r['status'] == 'refused'                   # 1265-1271

    def test_real_refused(self, venv, monkeypatch):
        monkeypatch.setattr(vm, '_v2_session',
                            lambda force=False: (None, None, 'no creds'))
        assert migrate_legacy_secrets()['status'] == 'refused'

    def test_real_ok_and_partial(self, fake_v2):
        r = migrate_legacy_secrets()
        assert r['status'] == 'partial'                   # failed=1
        assert r['checked'] == 3 and r['migrated'] == 2
        assert r['failed_names'] == ['bad-one']

    def test_real_exception(self, fake_v2):
        fake_v2.fail_migrate = 'db locked'
        r = migrate_legacy_secrets()
        assert r['status'] == 'error' and 'db locked' in r['message']


# ──────────────────── readonly session 真路径 ────────────────────


class TestReadonlySessionReal:
    def test_full_real_path(self, monkeypatch, tmp_path):
        """注册真实 L1 身份 → 只读会话拿到 readonly-* token。"""
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        monkeypatch.delenv('ACTUS_VAULT_KEY', raising=False)
        monkeypatch.delenv('ACTUS_VAULT_MIGRATE', raising=False)
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u1', '654321', 'host1', security_level='L1')
        assert reg.get('status') == 'ok'
        # register 返回的是 uuid 主键，读路径 SELECT WHERE id=? 必须用它
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        monkeypatch.setenv(vm.V2_PIN_ENV, '654321')
        monkeypatch.setattr(v2, '_vault2_singleton', vault)
        vault2_get = monkeypatch  # noqa
        tok_cache = {}

        def get_vault2():
            return vault
        monkeypatch.setattr(v2, '_get_vault2', get_vault2)
        m1, t1, r1 = vm._v2_readonly_session()
        assert r1 is None and t1.startswith('readonly-')   # 1089
        m2, t2, r2 = vm._v2_readonly_session()
        assert t2 == t1 and r2 is None                     # 缓存命中
        names, avail, reason = vm._v2_readonly_names()
        assert (avail, reason) == (True, None) and names == []

    def test_wrong_pin(self, monkeypatch, tmp_path):
        import vools.actus.vault2 as v2
        v2dir = tmp_path / 'v2b'
        monkeypatch.setenv('ACTUS_VAULT2_DIR', str(v2dir))
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
        monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
        (tmp_path / 'meta').mkdir()
        vault = v2.Vault2(vault_dir=str(v2dir))
        reg = vault.register('u2', '111111', 'host2', security_level='L1')
        assert reg.get('status') == 'ok'
        monkeypatch.setenv(vm.V2_IDENTITY_ENV, reg['identity_id'])
        monkeypatch.setenv(vm.V2_MACHINE_ENV, reg['machine_id'])
        monkeypatch.setenv(vm.V2_PIN_ENV, '999999')        # 错 PIN
        monkeypatch.setattr(v2, '_get_vault2', lambda: vault)
        _m, _t, reason = vm._v2_readonly_session()
        assert reason == 'PIN 错误'                        # 1067
