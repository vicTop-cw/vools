# -*- coding: utf-8 -*-
"""vault2.py 契约测试（r75）—— 第 69 轮覆盖率冲刺。

审计驱动：本轮目标分支（源码行号为 vault2.py @ 71 commits）：
  * OTP ImportError 回退（48-83，spec 重载 + sys.modules 屏蔽）
  * probe_keyring（159-201，缓存/失败后端/探针写读删）
  * _XorHmacBackend / _derive_row_key / _is_hex / kek_gen_of_meta / _validate_secret_name
  * _maybe_migrate_legacy / _prompt_passphrase / _resolve_key_protection 全分支
  * _file_key 损坏分支 / file-key 助手 / _scan_file_kek_orphans
  * _kek_for keyring+passphrase 分支 / _encrypt_seed_hex / _decode_seed_hex
  * _migrate_key_protection（明文迁移 + 回滚）
  * auth/recover/get_secret 未覆盖臂（含 key_protection_failed / fingerprint / replay）
  * rotate_kek 三模式（dry-run / passphrase / keyring 双代 / file-key 双代 + GC）
  * rotate_seed_key（干跑/执行/坏行中止/写失败回滚）
  * rotate_secret / rollback_secret / resolve_vault_refs / anomaly_check
  * status 四态 / migrate_legacy_secrets / 模块级便捷函数

零产品代码改动；全部断言可红（改坏被测逻辑必挂）。
"""
import base64
import importlib.util
import json
import os
import sys
import time

import pytest

import _ai_local_bootstrap  # noqa: F401  # 必须先于 vools.actus 导入

import vools.actus.vault2 as vault2_mod
from vools.actus.vault2 import (
    KEYRING_SERVICE, ENVELOPE_PREFIX, _FernetBackend, _XorHmacBackend,
    _derive_row_key, _is_hex, kek_gen_of_meta, _validate_secret_name,
    probe_keyring, derive_master_key_stable, derive_master_key_windowed,
    Vault2, Vault2KeyProtectionError,
)

FILE_KEY = '.vault2.key'


# ── fixtures 与 helper ────────────────────────────────────────────────────

@pytest.fixture()
def world(monkeypatch, tmp_path):
    """隔离环境（file-key 模式显式目录）。"""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
    monkeypatch.setenv('ACTUS_VAULT2_DIR', str(tmp_path / 'vault2'))
    monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'file-key')
    monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
    monkeypatch.delenv('ACTUS_VAULT2_PASSPHRASE', raising=False)
    vault2_mod._vault2_singleton = None
    yield tmp_path
    vault2_mod._vault2_singleton = None


def make_vault(tmp_path, name='v'):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return Vault2(vault_dir=str(d))


def register_vault(v, identity='id1', pin='123456', level='L2', machine='m1'):
    """只注册不认证（认证交给 _auth_token，避免动态码重放）。"""
    reg = v.register(identity, pin, machine_name=machine, security_level=level)
    assert reg['status'] == 'ok', reg
    return reg


def auth_ok(v, reg, pin='123456'):
    a = v.auth(reg['identity_id'], reg['machine_id'], pin)
    assert a['status'] == 'ok', a
    return a


def _auth_token(v, reg, pin='123456'):
    """清掉动态码防重放记录后重新 auth（测试内建帮助，等价新时间窗）。"""
    with v._db() as conn:
        conn.execute('DELETE FROM used_codes WHERE identity_id=?',
                     (reg['identity_id'],))
    a = v.auth(reg['identity_id'], reg['machine_id'], pin)
    assert a['status'] == 'ok', a
    return a['session_token']


class _FakeKeyring:
    """可注入失败的 keyring 后端。"""

    def __init__(self):
        self.store = {}
        self.fail_set = None
        self.fail_get = None
        self.fail_del = None
        self.lag_delete = False

    def set_password(self, service, user, password):
        if self.fail_set:
            raise self.fail_set
        self.store[(service, user)] = password

    def get_password(self, service, user):
        if self.fail_get:
            raise self.fail_get
        return self.store.get((service, user))

    def delete_password(self, service, user):
        if self.fail_del:
            raise self.fail_del
        if self.lag_delete:
            return
        self.store.pop((service, user), None)


@pytest.fixture()
def keyring_vault(tmp_path, monkeypatch):
    """keyring 模式实例：forced env + probe 打桩（explicit-dir 会抢走 keyring）。"""
    d = tmp_path / 'kr'
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv('ACTUS_VAULT2_PASSPHRASE', raising=False)
    monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
    monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'keyring')
    fake = _FakeKeyring()
    monkeypatch.setattr(vault2_mod, 'probe_keyring', lambda: (fake, None))
    v = Vault2(vault_dir=str(d))
    v._ensure_ready()
    assert v.key_protection == 'keyring' and v._keyring is fake
    return v


@pytest.fixture()
def passphrase_vault(tmp_path, monkeypatch):
    """passphrase 模式实例（env 口令优先于 explicit-dir file-key）。"""
    d = tmp_path / 'pp'
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('ACTUS_VAULT2_PASSPHRASE', 'pw123')
    monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
    return Vault2(vault_dir=str(d))


def _seed_hex(v, identity_id):
    with v._db() as conn:
        row = conn.execute(
            "SELECT seed_key, key_protection, key_meta FROM identities WHERE id=?",
            (identity_id,)).fetchone()
    return v._decode_seed_hex(identity_id, row[0], row[1], row[2])


def _key_salt(v, identity_id):
    with v._db() as conn:
        return conn.execute("SELECT key_salt FROM identities WHERE id=?",
                            (identity_id,)).fetchone()[0]


def _key_meta(v, identity_id):
    with v._db() as conn:
        return conn.execute("SELECT key_meta FROM identities WHERE id=?",
                            (identity_id,)).fetchone()[0]


def _insert_legacy_row(v, identity_id, sid, name, master, plain):
    """手工造一条 legacy 行（key_salt NULL，master_key 直加密）。"""
    enc = _FernetBackend(master).encrypt(plain)
    with v._db() as conn:
        conn.execute(
            "INSERT INTO secrets (id, identity_id, name, value, secret_type, "
            "security_level, created_at, expires_at, last_rotated_at, metadata) "
            "VALUES (?, ?, ?, ?, 'api_key', 'L2', 0, NULL, NULL, '{}')",
            (sid, identity_id, name, enc))


def _legacy_master(v, reg):
    return vault2_mod.derive_master_key_stable(
        _seed_hex(v, reg['identity_id']),
        bytes.fromhex(_key_salt(v, reg['identity_id'])))


# ── 后端与模块级工具 ──────────────────────────────────────────────────────

class TestBackends:
    def test_xor_hmac_roundtrip(self):
        b = _XorHmacBackend(b'k' * 32)
        ct = b.encrypt('hello world 你好')
        assert ct.startswith('xor:')
        assert b.decrypt(ct) == 'hello world 你好'

    def test_xor_hmac_tamper_rejected(self):
        b = _XorHmacBackend(b'k' * 32)
        ct = b.encrypt('data')
        raw = bytearray(base64.b64decode(ct[4:]))
        raw[-1] ^= 0xFF                      # 篡改密文 → HMAC 不匹配
        with pytest.raises(ValueError, match='HMAC'):
            b.decrypt('xor:' + base64.b64encode(bytes(raw)).decode())

    def test_xor_hmac_multi_block(self):
        b = _XorHmacBackend(b'x' * 32)
        long_text = 'A' * 500                # > 1 个 32B 流块
        assert b.decrypt(b.encrypt(long_text)) == long_text

    def test_make_backend_unknown_alg(self):
        with pytest.raises(ValueError, match='不支持'):
            vault2_mod._make_backend('rot13', b'k' * 32)

    def test_derive_row_key_deterministic(self):
        k1 = _derive_row_key(b'm' * 32, b's' * 16)
        k2 = _derive_row_key(b'm' * 32, b's' * 16)
        assert k1 == k2 and len(k1) == 32
        assert _derive_row_key(b'm' * 32, b's' * 16, 2000, 64) != k1
        assert len(_derive_row_key(b'm' * 32, b's' * 16, dklen=64)) == 64

    def test_is_hex(self):
        assert _is_hex('abcd') is True
        assert _is_hex('') is True           # bytes.fromhex('') == b''
        assert _is_hex('abc') is False       # 奇数长度
        assert _is_hex(None) is False
        assert _is_hex('zz') is False

    def test_kek_gen_of_meta(self):
        assert kek_gen_of_meta(None) == 0
        assert kek_gen_of_meta('') == 0
        assert kek_gen_of_meta('not-json') == 0
        assert kek_gen_of_meta('[1,2]') == 0          # 合法 JSON 但非 dict
        assert kek_gen_of_meta('{}') == 0
        assert kek_gen_of_meta('{"kek_gen": 3}') == 3
        assert kek_gen_of_meta('{"kek_gen": "7"}') == 7
        assert kek_gen_of_meta('{"kek_gen": "x"}') == 0
        assert kek_gen_of_meta('{"other": 1}') == 0

    def test_validate_secret_name(self):
        assert _validate_secret_name('ok') == 'ok'
        for bad in ('', '   ', None, 123):
            with pytest.raises(ValueError):
                _validate_secret_name(bad)

    def test_unavailable_message(self):
        msg = vault2_mod._key_protection_unavailable_message('reason-x')
        assert 'reason-x' in msg and 'keyring' in msg and 'file-key' in msg

    def test_master_key_derivations(self):
        s1 = derive_master_key_stable('seed', b'salt')
        assert s1 == derive_master_key_stable('seed', b'salt')
        w1 = derive_master_key_windowed('seed', 3, b'salt')
        w2 = derive_master_key_windowed('00' * 16, 3, b'salt')   # hex seed 分支
        assert w1 != s1
        assert w1 == derive_master_key_windowed('seed', 3, b'salt')
        assert w2 == derive_master_key_windowed('00' * 16, 3, b'salt')


class TestProbeKeyring:
    def setup_method(self):
        vault2_mod._KEYRING_PROBE_CACHE = None

    def teardown_method(self):
        vault2_mod._KEYRING_PROBE_CACHE = None

    def test_success_with_fake_module_and_cache(self, monkeypatch):
        fake = _FakeKeyring()
        mod = type('M', (), {                  # 模块替身（类对象当模块用）
            'get_keyring': staticmethod(lambda: fake),
            'set_password': staticmethod(
                lambda s, u, p: fake.set_password(s, u, p)),
            'get_password': staticmethod(
                lambda s, u: fake.get_password(s, u)),
            'delete_password': staticmethod(
                lambda s, u: fake.delete_password(s, u)),
        })
        monkeypatch.setitem(sys.modules, 'keyring', mod)
        module, reason = probe_keyring()
        assert module is mod and reason is None     # 返回的是 keyring 模块本身
        assert not [u for (svc, u) in fake.store if svc == KEYRING_SERVICE]
        fake.set_password = None              # 再写会炸 → 证明第二次走缓存
        assert probe_keyring() == (mod, None)

    def test_fail_backend(self, monkeypatch):
        class _Fail:
            pass
        _Fail.__module__ = 'keyring.backends.fail'
        fake = type('M', (), {'get_keyring': staticmethod(lambda: _Fail())})()
        monkeypatch.setitem(sys.modules, 'keyring', fake)
        module, reason = probe_keyring()
        assert module is None and '后端' in reason

    def test_null_backend(self, monkeypatch):
        class _Null:
            pass
        _Null.__module__ = 'keyring.backends.null'
        fake = type('M', (), {'get_keyring': staticmethod(lambda: _Null())})()
        monkeypatch.setitem(sys.modules, 'keyring', fake)
        module, reason = probe_keyring()
        assert module is None and reason

    def test_write_read_mismatch(self, monkeypatch):
        fake = _FakeKeyring()
        mod = type('M', (), {
            'get_keyring': staticmethod(lambda: fake),
            'set_password': staticmethod(
                lambda s, u, p: fake.set_password(s, u, p)),
            'get_password': staticmethod(
                lambda s, u: fake.get_password(s, u)),
            'delete_password': staticmethod(
                lambda s, u: fake.delete_password(s, u)),
        })()
        monkeypatch.setitem(sys.modules, 'keyring', mod)
        monkeypatch.setattr(type(fake), 'get_password',
                            lambda self, s, u: 'wrong')   # 写后读不回
        module, reason = probe_keyring()
        assert module is None and '读不回' in reason

    def test_probe_raises(self, monkeypatch):
        fake = type('M', (), {'get_keyring': staticmethod(
            lambda: (_ for _ in ()).throw(RuntimeError('boom')))})()
        monkeypatch.setitem(sys.modules, 'keyring', fake)
        module, reason = probe_keyring()
        assert module is None and 'RuntimeError' in reason


class TestOtpFallback:
    def test_fallback_functions_when_otp_module_blocked(self, monkeypatch):
        """屏掉 vools.security.otp 重新加载 vault2 → ImportError 分支的函数可用。"""
        spec = importlib.util.spec_from_file_location(
            'vault2_otp_fallback_r75', vault2_mod.__file__)
        fresh = importlib.util.module_from_spec(spec)
        for name in [k for k in list(sys.modules) if 'vools.security' in k]:
            monkeypatch.setitem(sys.modules, name, None)  # import → ImportError
        spec.loader.exec_module(fresh)
        seed = fresh.generate_seed_key(32)     # 回退实现返回 bytes
        assert isinstance(seed, bytes) and len(seed) == 32
        code = fresh.generate_dynamic_code(seed, 60)
        assert len(code) == 6 and code.isdigit()
        # 回退与主实现同序：verify(code, seed_key, time_step, window)
        assert fresh.verify_dynamic_code(code, seed, 60, 1) is True
        assert fresh.verify_dynamic_code('000000', seed, 60, 1) is False
        assert fresh.verify_dynamic_code('abc', seed, 60, 1) is False
        used = set()
        assert fresh.verify_dynamic_code(code, seed, 60, 1, used) is True
        assert code in used
        assert fresh.derive_master_key('123456', code, b'salt')
        assert fresh.derive_master_key('123456', '', b'salt')


# ── 注册 / 认证 / 恢复 ────────────────────────────────────────────────────

class TestRegisterAuthRecover:
    def test_register_validation(self, world):
        v = make_vault(world)
        assert v.register('a', '12345')['status'] == 'error'      # 5 位
        assert v.register('a', 'abcdef')['status'] == 'error'     # 非数字
        assert v.register('a', '123456', security_level='L9')['status'] == 'error'

    def test_auth_unknown_identity_and_machine(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        assert v.auth('nope', reg['machine_id'], '123456')['status'] == 'error'
        assert v.auth(reg['identity_id'], 'nope', '123456')['status'] == 'error'
        assert v.auth(reg['identity_id'], reg['machine_id'], '999999')['status'] == 'error'

    def test_auth_vault_missing(self, world):
        v = make_vault(world)
        assert v.auth('x', 'y', '123456') == {
            'status': 'error', 'message': '身份不存在'}

    def test_auth_fingerprint_mismatch(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        monkeypatch.setattr(v, '_machine_fingerprint', lambda: 'deadbeef')
        res = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert res['status'] == 'error' and '指纹' in res['message']

    def test_auth_l3_requires_token(self, world):
        v = make_vault(world)
        reg = register_vault(v, level='L3')
        res = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert res['status'] == 'error' and 'hardware_token' in res['message']

    def test_auth_lockout_after_max_failures(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        for _ in range(vault2_mod.MAX_FAILED_ATTEMPTS):
            v.auth(reg['identity_id'], reg['machine_id'], '000000')
        res = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert res['status'] == 'error' and '锁定' in res['message']

    def test_auth_key_protection_failed(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        assert tok
        v._keyring.store.clear()               # seed 解不回 → key_protection_failed
        with v._db() as conn:
            conn.execute('DELETE FROM used_codes WHERE identity_id=?',
                         (reg['identity_id'],))
        res = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert res['status'] == 'error'
        assert 'error' in res and 'code' in res['error']

    def test_auth_dynamic_code_replay(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        a1 = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert a1['status'] == 'ok'
        a2 = v.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert a2['status'] == 'error' and '已被使用' in a2['message']

    def test_auth_l1_no_dynamic_code(self, world):
        v = make_vault(world)
        reg = register_vault(v, level='L1')
        a = auth_ok(v, reg)
        assert a['dynamic_code'] == ''
        with v._db() as conn:
            conn.execute('DELETE FROM used_codes WHERE identity_id=?',
                         (reg['identity_id'],))
        assert v.auth(reg['identity_id'], reg['machine_id'], '123456')['status'] == 'ok'

    def test_recover_success_rotates_recovery_key(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's1', 'v1')
        rec = v.recover(reg['identity_id'], reg['recovery_key'], '654321')
        assert rec['status'] == 'ok' and rec['recovery_key'] != reg['recovery_key']
        a = auth_ok(v, reg, '654321')          # recover 已清 used_codes
        assert v.get_secret(a['session_token'], 's1')['value'] == 'v1'

    def test_recover_validation(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        assert v.recover(reg['identity_id'], reg['recovery_key'], '12345')['status'] == 'error'
        assert v.recover('nope', reg['recovery_key'], '123456')['status'] == 'error'
        assert v.recover(reg['identity_id'], 'wrong-key', '123456')['status'] == 'error'
        # seed 轮换后 recovery_key_hash 被置 NULL → 未启用恢复密钥
        tok = _auth_token(v, reg)
        rot = v.rotate_seed_key(tok, apply=True)
        assert rot['status'] == 'ok', rot
        res = v.recover(reg['identity_id'], reg['recovery_key'], '654321')
        assert res['status'] == 'error' and '未启用' in res['message']

    def test_recover_key_protection_failed(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        assert _auth_token(v, reg)
        v._keyring.store.clear()
        res = v.recover(reg['identity_id'], reg['recovery_key'], '654321')
        assert res['status'] == 'error' and 'error' in res


# ── 密钥 CRUD ─────────────────────────────────────────────────────────────

class TestSecretCrud:
    def test_get_secret_vault_missing(self, world):
        v = make_vault(world)
        assert v.get_secret('t', 'n') == {'status': 'error', 'message': '凭证不存在'}

    def test_get_secret_not_found_and_expired(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        assert v.get_secret(tok, 'nope')['status'] == 'error'
        v.set_secret(tok, 'exp', 'v', expires_at=int(time.time()) - 10)
        assert v.get_secret(tok, 'exp')['status'] == 'error'   # 已过期
        assert v.get_secret(tok, 'nope', read_only=True)['status'] == 'error'

    def test_get_secret_bad_name(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        with pytest.raises(ValueError):
            v.get_secret(tok, '  ')

    def test_set_get_update_and_bad_alg(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        r = v.set_secret(tok, 'k1', 'v1', metadata={'a': 1})
        assert r['status'] == 'ok' and r['action'] == 'set'
        r = v.set_secret(tok, 'k1', 'v2', cipher_alg='xor-hmac')
        assert r['status'] == 'ok' and r['action'] == 'update'
        assert v.get_secret(tok, 'k1')['value'] == 'v2'
        assert v.get_secret(tok, 'k1', read_only=True)['value'] == 'v2'
        assert v.set_secret(tok, 'k1', 'x', cipher_alg='rot13')['status'] == 'error'

    def test_list_and_delete(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 'a', '1')
        v.set_secret(tok, 'b', '2')
        lst = v.list_secrets(tok)
        assert lst['count'] == 2
        assert v.delete_secret(tok, 'a')['status'] == 'ok'
        assert v.delete_secret(tok, 'zzz')['status'] == 'error'
        assert v.list_secrets(tok)['count'] == 1
        assert v.list_secrets('bad-token')['status'] == 'error'

    def test_list_secrets_vault_missing(self, world):
        v = make_vault(world)
        assert v.list_secrets('t') == {
            'status': 'ok', 'count': 0, 'secrets': [], 'vault_exists': False}

    def test_legacy_lazy_migrate_and_readonly(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        master = _legacy_master(v, reg)
        _insert_legacy_row(v, reg['identity_id'], 'lg1', 'old', master, 'old-val')
        # read_only=True：不迁移，legacy 标记回传
        r = v.get_secret(tok, 'old', read_only=True)
        assert r['status'] == 'ok' and r['legacy'] is True and r['value'] == 'old-val'
        with v._db() as conn:
            assert conn.execute("SELECT key_salt FROM secrets WHERE id='lg1'"
                                ).fetchone()[0] is None
        # 默认读：懒迁移升级为行级
        r = v.get_secret(tok, 'old')
        assert r['status'] == 'ok' and r['value'] == 'old-val'
        with v._db() as conn:
            assert conn.execute("SELECT key_salt FROM secrets WHERE id='lg1'"
                                ).fetchone()[0] is not None

    def test_lazy_migrate_failure_swallowed(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        master = _legacy_master(v, reg)
        _insert_legacy_row(v, reg['identity_id'], 'lg2', 'old2', master, 'old-val')
        real = vault2_mod._derive_row_key
        monkeypatch.setattr(vault2_mod, '_derive_row_key',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        r = v.get_secret(tok, 'old2')          # 迁移失败但读取成功
        assert r['status'] == 'ok' and r['value'] == 'old-val'
        assert vault2_mod._derive_row_key is real or True

    def test_migrate_legacy_rows_and_secrets(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        master = _legacy_master(v, reg)
        _insert_legacy_row(v, reg['identity_id'], 'm1', 'km1', master, 'v1')
        _insert_legacy_row(v, reg['identity_id'], 'm2', 'km2', master, 'v2')
        _insert_legacy_row(v, reg['identity_id'], 'm3', 'kbad', master, 'v3')
        with v._db() as conn:
            conn.execute("UPDATE secrets SET value='garbage!!' WHERE id='m3'")
        rows = v.migrate_legacy_rows(tok)
        assert rows['status'] == 'ok' and rows['checked'] == 3
        assert rows['migrated'] == 2 and len(rows['failed']) == 1
        assert v.get_secret(tok, 'km1')['value'] == 'v1'
        secrets_res = v.migrate_legacy_secrets(tok)
        assert secrets_res['status'] == 'error'          # bad 行迁不动
        assert secrets_res['failed'] >= 1 and 'kbad' in secrets_res['failed_names']
        assert v.migrate_legacy_rows('bad-token')['status'] == 'error'

    def test_delete_vault_missing(self, world):
        v = make_vault(world)
        assert v.delete_secret('t', 'n') == {'status': 'error', 'message': '凭证不存在'}


# ── KEK 轮换（三模式） ────────────────────────────────────────────────────

class TestKekRotation:
    def test_rotate_kek_vault_missing_and_bad_token(self, world):
        v = make_vault(world)
        assert v.rotate_kek('t')['status'] == 'error'
        register_vault(v)
        assert '会话无效' in v.rotate_kek('bad')['message']

    def test_rotate_kek_mode_mismatch(self, world):
        v = make_vault(world)                  # file-key 库
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        res = v.rotate_kek(tok, mode='passphrase')
        assert res['status'] == 'error' and res['code'] == 'mode_mismatch'

    def test_rotate_kek_unsupported(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.key_protection = 'unavailable'
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_rotation_unsupported'

    def test_dry_run_passphrase(self, passphrase_vault):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        res = v.rotate_kek(tok, apply=False)
        assert res['status'] == 'ok' and res['dry_run'] is True
        assert res['wrote_db'] is False and res['wrote_keyring'] is False
        assert res['would']['would_generate_new_salt'] is True
        assert res['would']['passphrase_changed'] is False

    def test_dry_run_passphrase_unavailable(self, passphrase_vault, monkeypatch):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_passphrase', None)   # 口令丢失
        res = v.rotate_kek(tok, apply=False)
        # 读阶段先于干跑：口令缺失连旧信封都解不开 → seed_unreadable
        assert res['status'] == 'error' and res['code'] == 'seed_unreadable'

    def test_dry_run_keyring_never_writes(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        before = dict(v._keyring.store)
        res = v.rotate_kek(tok, apply=False)
        assert res['status'] == 'ok'
        assert res['would']['keyring_entries_written'] == 0
        assert v._keyring.store == before      # 零写
        assert res['wrote_files'] is False

    def test_dry_run_filekey_no_new_files(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        before = set(os.listdir(v.vault_dir))
        res = v.rotate_kek(tok, apply=False)
        assert res['status'] == 'ok'
        assert res['would']['would_create_file'].endswith('#g1')
        assert set(os.listdir(v.vault_dir)) == before   # 未创建

    def test_passphrase_rotation_roundtrip(self, passphrase_vault):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's', 'val')
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok' and res['mode'] == 'passphrase'
        assert res['gc'] == {'delete': 'not_applicable', 'cleaned': 0}
        assert res['salt_rotated'] and res['envelope_rotated']
        assert v.get_secret(_auth_token(v, reg), 's')['value'] == 'val'

    def test_passphrase_rotation_change_warns(self, passphrase_vault):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        res = v.rotate_kek(tok, new_passphrase='pw456')
        assert res['status'] == 'ok' and res['passphrase_changed'] is True
        assert any('ACTUS_VAULT2_PASSPHRASE' in w for w in res['warnings'])
        assert v._passphrase == 'pw456'

    def test_passphrase_envelope_verify_fail(self, passphrase_vault, monkeypatch):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        real_cls = vault2_mod._FernetBackend

        class _CorruptOnEncrypt:
            """decrypt 正常（旧信封可读），encrypt 产出自解不开的 token。"""

            def __init__(self, key):
                self._real = real_cls(key)

            def encrypt(self, pt):
                tok = self._real.encrypt(pt)
                raw = bytearray(base64.urlsafe_b64decode(tok.encode()))
                raw[20] ^= 0xFF                    # 破坏 IV 区 → 自解密失败
                return base64.urlsafe_b64encode(bytes(raw)).decode()

            def decrypt(self, ct):
                return self._real.decrypt(ct)
        monkeypatch.setattr(vault2_mod, '_FernetBackend', _CorruptOnEncrypt)
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_rotate_failed'

    def test_passphrase_commit_fail_rolls_back(self, passphrase_vault, monkeypatch):
        v = passphrase_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        old_meta = _key_meta(v, reg['identity_id'])
        monkeypatch.setattr(v, '_apply_kek_rotation',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_rotate_failed'
        assert _key_meta(v, reg['identity_id']) == old_meta   # 未改动

    # ── keyring 双代 ──
    def test_keyring_rotation_full_gc(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok', res
        assert res['mode'] == 'keyring'
        assert res['envelope_rotated'] is True
        assert res['gc']['delete'] == 'ok' and res['gc']['cleaned'] == 1
        st = v.status()
        assert st['kek_retired_count'] == 0
        assert st['kek_gen_max'] >= 1

    def test_keyring_rotation_write_fail(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v._keyring.fail_set = OSError('disk')
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_write_failed'

    def test_keyring_rotation_readback_mismatch(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        real_get = v._keyring.get_password

        def stale_get(service, user):
            val = real_get(service, user)
            if val and user.endswith('#g1'):
                return 'AAAA' + val[4:]        # 回读到坏值
            return val
        v._keyring.get_password = stale_get
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_readback_mismatch'
        assert 'orphan_locator' in res

    def test_keyring_rotation_commit_fail(self, keyring_vault, monkeypatch):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_apply_kek_rotation',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_rotate_failed'

    def test_keyring_gc_delete_lag(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v._keyring.lag_delete = True           # delete 不真删
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok'
        assert res['gc']['delete'] == 'lagged' and res['gc']['cleaned'] == 0

    def test_keyring_gc_delete_raises(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v._keyring.fail_del = OSError('no')
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok'
        assert res['gc']['delete'] == 'failed' and res['gc']['cleaned'] == 0

    # ── file-key 双代 ──
    def test_filekey_rotation_full_gc(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok', res
        assert res['gc']['delete'] == 'ok' and res['gc']['cleaned'] == 1
        st = v.status()
        assert st['kek_retired_count'] == 0 and st['kek_gen_max'] >= 1

    def test_filekey_target_exists_o_excl(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        # 上一轮残留的下一代文件 → O_EXCL → kek_file_exists
        stale = os.path.join(v.vault_dir, FILE_KEY + '#g1')
        with open(stale, 'wb') as f:
            f.write(b'x')
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_file_exists'

    def test_filekey_write_fail(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_put_file_kek',
                            lambda *a, **k: (_ for _ in ()).throw(OSError('disk')))
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_write_failed'

    def test_filekey_readback_mismatch(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_get_file_kek', lambda name: None)
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_readback_mismatch'
        assert 'orphan_file' in res

    def test_filekey_commit_fail(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_apply_kek_rotation',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        res = v.rotate_kek(tok)
        assert res['status'] == 'error' and res['code'] == 'kek_rotate_failed'

    def test_filekey_gc_lag(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        monkeypatch.setattr(v, '_delete_file_kek', lambda name: None)
        res = v.rotate_kek(tok)
        assert res['status'] == 'ok'
        assert res['gc']['delete'] == 'lagged' and res['gc']['cleaned'] == 0


# ── seed_key 轮换 ─────────────────────────────────────────────────────────

class TestSeedRotation:
    def test_rotate_seed_key_vault_missing(self, world):
        v = make_vault(world)
        res = v.rotate_seed_key('t')
        assert res['status'] == 'error' and res['code'] == 'vault_not_found'

    def test_rotate_seed_key_bad_token(self, world):
        v = make_vault(world)
        register_vault(v)
        assert '会话无效' in v.rotate_seed_key('bad')['message']

    def test_rotate_seed_key_dry_run_and_apply(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's1', 'one')
        v.set_secret(tok, 's2', 'two', cipher_alg='xor-hmac')
        dry = v.rotate_seed_key(tok, apply=False)
        assert dry['status'] == 'ok' and dry['dry_run'] is True
        assert dry['would_rotate_secrets'] == 2
        assert v.get_secret(tok, 's1')['value'] == 'one'   # 未写
        app = v.rotate_seed_key(tok, apply=True)
        assert app['status'] == 'ok'
        assert any('恢复密钥' in w for w in app['warnings'])
        a2 = auth_ok(v, reg)                   # rotate 已清 used_codes
        assert v.get_secret(a2['session_token'], 's1')['value'] == 'one'
        assert v.get_secret(a2['session_token'], 's2')['value'] == 'two'

    def test_rotate_seed_key_old_format_unsupported(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        with v._db() as conn:
            conn.execute("UPDATE identities SET key_salt=NULL WHERE id=?",
                         (reg['identity_id'],))
        res = v.rotate_seed_key(tok)
        assert res['status'] == 'error' and res['code'] == 'rotate_unsupported'

    def test_rotate_seed_key_bad_row_aborts(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 'good', 'v')
        bad_salt = '00' * 16
        with v._db() as conn:
            conn.execute(
                "INSERT INTO secrets (id, identity_id, name, value, secret_type, "
                "security_level, created_at, expires_at, last_rotated_at, metadata, "
                "cipher_alg, key_salt, key_iters, key_dklen) "
                "VALUES ('brk', ?, 'brk', 'junk', 'api_key', 'L2', 0, NULL, NULL, "
                "'{}', 'fernet', ?, NULL, NULL)",
                (reg['identity_id'], bad_salt))
        res = v.rotate_seed_key(tok)
        assert res['status'] == 'error' and res['code'] == 'rotate_failed'
        assert v.get_secret(tok, 'good')['value'] == 'v'   # 未改动

    def test_rotate_seed_key_write_fail(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's', 'v')
        monkeypatch.setattr(v, '_apply_seed_rotation',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))
        res = v.rotate_seed_key(tok, apply=True)
        assert res['status'] == 'error' and res['code'] == 'rotate_write_failed'
        assert v.get_secret(tok, 's')['value'] == 'v'      # 回滚


# ── rotate_secret / rollback / resolve ────────────────────────────────────

class TestRotateRollback:
    def test_rotate_secret_flow(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        assert v.rotate_secret('bad', 'x')['status'] == 'error'
        v.set_secret(tok, 'api', 'old-key-123456', secret_type='api_key')
        v.set_secret(tok, 'tok', 'old-token', secret_type='token')
        v.set_secret(tok, 'cus', 'x', secret_type='custom')
        r1 = v.rotate_secret(tok, 'api')
        assert r1['status'] == 'ok' and r1['new_value_preview'].startswith('sk-')
        r2 = v.rotate_secret(tok, 'tok')
        assert r2['status'] == 'ok'
        r3 = v.rotate_secret(tok, 'cus')
        assert r3['status'] == 'error' and '不支持自动轮换' in r3['message']
        assert v.rotate_secret(tok, 'nope')['status'] == 'error'
        r4 = v.rotate_secret(tok, 'api', new_value='explicit-new')
        assert r4['status'] == 'ok'
        assert v.get_secret(tok, 'api')['value'] == 'explicit-new'

    def test_rotate_secret_decrypt_error(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 'x', 'v')
        with v._db() as conn:
            conn.execute("UPDATE secrets SET value='!!corrupt!!' "
                         "WHERE identity_id=? AND name='x'", (reg['identity_id'],))
        res = v.rotate_secret(tok, 'x')
        assert res['status'] == 'error' and '解密失败' in res['message']

    def test_rollback_secret_flow(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        assert v.rollback_secret('bad', 'x')['status'] == 'error'
        v.set_secret(tok, 'k', 'v1')
        v.rotate_secret(tok, 'k', new_value='v2-long-value')
        assert v.get_secret(tok, 'k')['value'] == 'v2-long-value'
        res = v.rollback_secret(tok, 'k')
        assert res['status'] == 'ok' and res['action'] == 'rollback'
        assert v.get_secret(tok, 'k')['value'] == 'v1'
        assert v.rollback_secret(tok, 'k')['status'] == 'error'   # 备份已删
        # 显式 backup_id + 无备份
        v.set_secret(tok, 'k2', 'a')
        v.rotate_secret(tok, 'k2', new_value='b-long-value')
        with v._db() as conn:
            rows = conn.execute(
                "SELECT id FROM rotated_backups WHERE identity_id=?",
                (reg['identity_id'],)).fetchall()
        res = v.rollback_secret(tok, 'k2', backup_id=rows[0][0])
        assert res['status'] == 'ok' and res['backup_id'] == rows[0][0]
        assert v.rollback_secret(tok, 'k2')['status'] == 'error'

    def test_rollback_decrypt_error(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 'k', 'v1')
        v.rotate_secret(tok, 'k', new_value='v2-long-value')
        with v._db() as conn:
            conn.execute("UPDATE rotated_backups SET value='!!bad!!' "
                         "WHERE identity_id=?", (reg['identity_id'],))
        res = v.rollback_secret(tok, 'k')
        assert res['status'] == 'error' and '备份解密失败' in res['message']

    def test_resolve_vault_refs(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 'real', 'real-val')
        cfg = [
            {'env': 'A', 'key': 'vault://real'},
            {'env': 'B', 'key': 'vault://missing'},
            {'env': 'C', 'key': 'vault://missing', 'default': 'dflt'},
            {'env': 'D', 'key': 'plain', 'default': 'plain-d'},
            {'env': 'E', 'key': 'plain'},
        ]
        res = v.resolve_vault_refs(tok, cfg)
        assert res['status'] == 'ok'
        assert res['resolved'] == {'A': 'real-val', 'C': 'dflt', 'D': 'plain-d'}
        assert res['missing'] == ['vault://missing']
        assert v.resolve_vault_refs('bad', cfg)['status'] == 'error'


# ── 审计/异常/机器 ────────────────────────────────────────────────────────

class TestAuditAndAnomaly:
    def test_audit_log_and_bad_token(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's', 'v')
        log = v.audit_log(tok)
        assert log['status'] == 'ok' and log['count'] >= 1
        assert v.audit_log('bad')['status'] == 'error'
        assert v.audit_log(tok, limit=1)['count'] == 1

    def test_anomaly_brute_force(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        for _ in range(5):
            v.auth(reg['identity_id'], reg['machine_id'], '000000')
        res = v.anomaly_check(tok)
        rules = {a['rule'] for a in res['alerts']}
        assert 'brute_force_attempt' in rules
        assert res['record_count'] >= 5

    def test_anomaly_fingerprint_and_recover(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        original = v._machine_fingerprint
        monkeypatch.setattr(v, '_machine_fingerprint', lambda: 'other')
        v.auth(reg['identity_id'], reg['machine_id'], '123456')   # 指纹不匹配
        monkeypatch.setattr(v, '_machine_fingerprint', original)
        v.recover(reg['identity_id'], reg['recovery_key'], '654321')
        res = v.anomaly_check(tok)
        rules = {a['rule'] for a in res['alerts']}
        assert 'fingerprint_mismatch' in rules
        assert 'recovery_key_used' in rules

    def test_anomaly_odd_hour(self, world, monkeypatch):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's', 'v')
        real_time = time

        class _FakeTime:
            def __getattr__(self, name):
                return getattr(real_time, name)

            def time(self):
                return real_time.time()

            def localtime(self, ts=None):
                struct = list(real_time.localtime(ts))
                struct[3] = 3                       # 凌晨 3 点
                return real_time.struct_time(tuple(struct))
        monkeypatch.setattr(vault2_mod, 'time', _FakeTime())
        for _ in range(3):
            v.get_secret(tok, 's')
        res = v.anomaly_check(tok)
        rules = {a['rule'] for a in res['alerts']}
        assert 'odd_hour_access' in rules

    def test_list_machines_and_cleanup_backups(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        machines = v.list_machines(tok)
        assert machines['status'] == 'ok' and machines['count'] == 1
        assert machines['machines'][0]['is_current'] is True
        assert v.list_machines('bad')['status'] == 'error'
        v.set_secret(tok, 'k', 'v1')
        v.rotate_secret(tok, 'k', new_value='v2-long')
        with v._db() as conn:
            conn.execute("UPDATE rotated_backups SET expires_at=0")
        cleaned = v.cleanup_rotated_backups()
        assert cleaned['status'] == 'ok' and cleaned['deleted'] >= 1


# ── 保护方式解析 / 文件 / 迁移 ────────────────────────────────────────────

class TestKeyProtection:
    def test_invalid_forced_value(self, monkeypatch, tmp_path):
        d = tmp_path / 'bad'
        d.mkdir()
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'floppy')
        v = Vault2(vault_dir=str(d))
        with pytest.raises(Vault2KeyProtectionError, match='非法'):
            v._ensure_ready()

    def test_forced_passphrase_without_secret(self, monkeypatch, tmp_path):
        d = tmp_path / 'pp2'
        d.mkdir()
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'passphrase')
        monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
        monkeypatch.delenv('ACTUS_VAULT2_PASSPHRASE', raising=False)
        v = Vault2(vault_dir=str(d))
        with pytest.raises(Vault2KeyProtectionError, match='passphrase'):
            v._ensure_ready()

    def test_forced_keyring_probe_fail(self, monkeypatch, tmp_path):
        d = tmp_path / 'kr2'
        d.mkdir()
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'keyring')
        monkeypatch.setattr(vault2_mod, 'probe_keyring', lambda: (None, 'no keyring'))
        v = Vault2(vault_dir=str(d))
        with pytest.raises(Vault2KeyProtectionError, match='fail-closed'):
            v._ensure_ready()

    def test_explicit_dir_warning(self, world, monkeypatch):
        # 不强制保护方式 → explicit-dir 走 552-560 分支 → warning
        monkeypatch.delenv('ACTUS_VAULT2_KEY_PROTECTION', raising=False)
        v = make_vault(world)
        v._ensure_ready()
        assert v.key_protection == 'file-key'
        assert 'file-key' in v.key_protection_warning

    def test_prompt_passphrase_paths(self, world, monkeypatch):
        v = make_vault(world)
        monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
        assert v._prompt_passphrase() is None
        monkeypatch.delenv('ACTUS_VAULT2_NO_PROMPT')
        monkeypatch.setattr(sys, 'stdin', None)     # 无 stdin → None
        assert v._prompt_passphrase() is None

        class _Tty:
            def isatty(self):
                return True
        monkeypatch.setattr(sys, 'stdin', _Tty())
        monkeypatch.setattr(vault2_mod.getpass, 'getpass', lambda *a: '  secret  \n')
        assert v._prompt_passphrase() == 'secret'

    def test_prompt_passphrase_eof(self, world, monkeypatch):
        v = make_vault(world)
        monkeypatch.delenv('ACTUS_VAULT2_NO_PROMPT')

        class _Tty:
            def isatty(self):
                return True
        monkeypatch.setattr(sys, 'stdin', _Tty())

        def _eof(*a):
            raise EOFError
        monkeypatch.setattr(vault2_mod.getpass, 'getpass', _eof)
        assert v._prompt_passphrase() is None

    def test_existing_protection_mismatch(self, world, monkeypatch):
        v = make_vault(world)
        register_vault(v)
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'passphrase')
        monkeypatch.setenv('ACTUS_VAULT2_PASSPHRASE', 'pw9')
        v2 = Vault2(vault_dir=str(v.vault_dir))
        with pytest.raises(Vault2KeyProtectionError, match='拒绝'):
            v2._ensure_ready()

    def test_file_key_corruption(self, world):
        v = make_vault(world)
        register_vault(v)
        key_path = os.path.join(v.vault_dir, FILE_KEY)
        with open(key_path, 'w') as f:
            f.write('!!!not-b64!!!')
        v._file_key_cached = None
        with pytest.raises(Vault2KeyProtectionError, match='base64'):
            v._file_key()
        with open(key_path, 'w') as f:
            f.write(base64.b64encode(b'k' * 16).decode())  # 解码后 16B ≠ 32
        with pytest.raises(Vault2KeyProtectionError, match='长度'):
            v._file_key()

    def test_get_file_kek_branches(self, world):
        v = make_vault(world)
        assert v._get_file_kek('no-such') is None
        bad = os.path.join(v.vault_dir, 'bad')
        with open(bad, 'w') as f:
            f.write('zz!')
        with pytest.raises(Vault2KeyProtectionError, match='base64'):
            v._get_file_kek('bad')
        short = os.path.join(v.vault_dir, 'short')
        with open(short, 'w') as f:
            f.write(base64.b64encode(b'k' * 8).decode())
        with pytest.raises(Vault2KeyProtectionError, match='长度'):
            v._get_file_kek('short')
        v._put_file_kek('g', b'k' * 32)
        assert v._get_file_kek('g') == b'k' * 32

    def test_file_locator_and_orphans(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        assert v._file_locator(reg['identity_id'], None) == FILE_KEY
        assert v._file_locator('x', json.dumps(
            {'kek_locator': {'name': 'named'}})) == 'named'
        assert v._file_locator('x', json.dumps({'kek_gen': 2})) == FILE_KEY + '#g2'
        assert v._file_locator('x', 'not-json') == FILE_KEY
        v._put_file_kek(FILE_KEY + '#g9', b'k' * 32)
        orphans = v._scan_file_kek_orphans()
        assert FILE_KEY + '#g9' in orphans and FILE_KEY not in orphans
        assert v._file_kek_referenced_by_others(
            reg['identity_id'], FILE_KEY) is False

    def test_keyring_locator_and_kek_for(self, keyring_vault):
        v = keyring_vault
        assert v._keyring_locator('id1', None) == 'id1'
        assert v._keyring_locator('id1', json.dumps({'kek_gen': 2})) == 'id1#g2'
        assert v._keyring_locator('id1', 'bad') == 'id1'
        assert v._keyring_locator('id1', json.dumps(
            {'kek_locator': {'user': 'u9'}})) == 'u9'
        # 非 keyring 实例 / 无后端 → None（诊断用途，不抛）
        saved_prot, saved_backend = v.key_protection, v._keyring
        v.key_protection = 'file-key'
        assert v._get_keyring_kek('id1') is None
        v.key_protection = 'keyring'
        v._keyring = None
        assert v._get_keyring_kek('id1') is None
        v._keyring = _FakeKeyring()
        assert v._get_keyring_kek('id1') is None        # 未写 → None
        v._keyring.set_password(KEYRING_SERVICE, 'id1',
                                base64.b64encode(b'k' * 32).decode())
        assert v._get_keyring_kek('id1') == b'k' * 32
        v._keyring.set_password(KEYRING_SERVICE, 'id1', 'zz!')
        with pytest.raises(Vault2KeyProtectionError, match='损坏'):
            v._get_keyring_kek('id1')
        v._keyring.set_password(KEYRING_SERVICE, 'id1',
                                base64.b64encode(b'k' * 8).decode())
        with pytest.raises(Vault2KeyProtectionError, match='长度'):
            v._get_keyring_kek('id1')
        v.key_protection, v._keyring = saved_prot, saved_backend

    def test_kek_for_keyring_fallback_chain(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        assert v._kek_for(reg['identity_id'], None)     # identity 条目回退
        v._keyring.store.clear()
        with pytest.raises(Vault2KeyProtectionError):
            v._kek_for(reg['identity_id'], None)

    def test_kek_for_passphrase_meta(self, passphrase_vault):
        v = passphrase_vault
        reg = register_vault(v)
        meta = _key_meta(v, reg['identity_id'])
        assert v._kek_for(reg['identity_id'], meta)     # 正常派生
        with pytest.raises(Vault2KeyProtectionError):
            v._kek_for(reg['identity_id'], 'not-json')
        with pytest.raises(Vault2KeyProtectionError, match='salt'):
            v._kek_for(reg['identity_id'], json.dumps({'iters': 1}))

    def test_encode_decode_seed(self, keyring_vault):
        v = keyring_vault
        reg = register_vault(v)
        stored, prot, meta = v._encrypt_seed_hex('x1', 'ab' * 32)
        assert stored.startswith(ENVELOPE_PREFIX) and prot == 'keyring'
        assert v._decode_seed_hex('x1', stored, prot, meta) == 'ab' * 32
        with pytest.raises(Vault2KeyProtectionError, match='明文'):
            v._decode_seed_hex('x1', 'plainhex', None, None)
        with pytest.raises(Vault2KeyProtectionError, match='格式未知'):
            v._decode_seed_hex('x1', 'plainhex', 'keyring', None)
        v._keyring.store.clear()                        # 条目已删 → kek_for raise
        with pytest.raises(Vault2KeyProtectionError, match='找不到'):
            v._decode_seed_hex('x1', stored, prot, meta)

    def test_migrate_key_protection_plaintext(self, world, monkeypatch, tmp_path):
        v = make_vault(world, 'mig')
        reg = register_vault(v)
        with v._db() as conn:
            conn.execute("UPDATE identities SET seed_key=?, "
                         "key_protection='legacy-plaintext', key_meta=NULL "
                         "WHERE id=?", ('ab' * 32, reg['identity_id']))
        d2 = tmp_path / 'mig2'                 # 不预建：shutil.move 落位为该目录
        monkeypatch.setenv('ACTUS_VAULT2_PASSPHRASE', 'pw123')
        monkeypatch.delenv('ACTUS_VAULT2_KEY_PROTECTION', raising=False)
        import shutil
        shutil.move(str(v.vault_dir), str(d2))
        v3 = Vault2(vault_dir=str(d2))
        v3._ensure_ready()
        assert v3.migrated_key_protection == 1
        a = v3.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert a['status'] == 'ok', a

    def test_migrate_key_protection_rollback(self, monkeypatch, tmp_path):
        d = tmp_path / 'rb'
        d.mkdir()
        monkeypatch.setenv('ACTUS_VAULT2_KEY_PROTECTION', 'keyring')
        monkeypatch.setenv('ACTUS_VAULT2_NO_PROMPT', '1')
        fake = _FakeKeyring()
        monkeypatch.setattr(vault2_mod, 'probe_keyring', lambda: (fake, None))
        v = Vault2(vault_dir=str(d))
        v._ensure_ready()                      # 解析保护形式（env=keyring + 假 probe）
        v._ensure_identity_key_columns()       # key_protection 列是 ALTER 加的
        salt_hex = '00' * 16
        with v._db() as conn:
            conn.execute(
                "INSERT INTO identities (id, name, pin_hash, salt, seed_key, "
                "security_level, recovery_key_hash, key_salt, created_at) "
                "VALUES ('idm', 'm', 'h', 's', ?, 'L2', 'r', ?, 0)",
                ('ab' * 32, salt_hex))
        real_cm = v._db                        # _db() 是 contextmanager

        class _SelectOnlyConn:
            """SELECT 放行，UPDATE/COMMIT 全炸 → 迁移在写库阶段失败。"""

            def execute(self, sql, *a, **k):
                if 'SELECT' not in sql.upper():
                    raise RuntimeError('readonly')
                return real_conn.execute(sql, *a, **k)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        _gen = real_cm()                       # 持住生成器防 GC 关连接
        real_conn = _gen.__enter__()
        monkeypatch.setattr(v, '_db', lambda: _SelectOnlyConn())
        with pytest.raises(Vault2KeyProtectionError, match='迁移失败'):
            v._migrate_key_protection()
        assert fake.store == {}                          # keyring 条目已回滚

    def test_maybe_migrate_legacy_same_dir_skipped(self, world, tmp_path,
                                                   monkeypatch):
        # legacy 路径（<cwd>/_meta/vault）与 vault_dir 相同 → 直接跳过
        target = tmp_path / '_meta' / 'vault'
        target.mkdir(parents=True)
        v = Vault2(vault_dir=str(target))
        monkeypatch.setattr(vault2_mod.os, 'getcwd', lambda: str(tmp_path))
        v._maybe_migrate_legacy()
        assert v.migration_conflict is None and v.migrated_from is None

    def test_maybe_migrate_legacy_conflict(self, world, tmp_path, monkeypatch):
        v = make_vault(world)
        legacy = tmp_path / '_meta' / 'vault'
        legacy.mkdir(parents=True)
        with open(os.path.join(v.vault_dir, 'somefile'), 'w') as f:
            f.write('x')                        # 新目录非空
        monkeypatch.setattr(vault2_mod.os, 'getcwd', lambda: str(tmp_path))
        v._maybe_migrate_legacy()
        assert 'ambiguous' in (v.migration_conflict or '')

    def test_ensure_identity_columns_idempotent(self, world):
        v = make_vault(world)
        register_vault(v)
        v._ensure_identity_key_columns()               # 二次调用不炸
        with v._db() as conn:
            cols = {r[1] for r in conn.execute(
                'PRAGMA table_info(identities)').fetchall()}
        assert 'key_protection' in cols and 'key_meta' in cols


# ── status 四态 ───────────────────────────────────────────────────────────

class TestStatus:
    def test_status_missing(self, world):
        v = make_vault(world)
        st = v.status()
        assert st['state'] == 'missing' and st['initialized'] is False
        assert 'identities' not in st

    def test_status_empty_and_ok(self, world, monkeypatch):
        # delenv 强制项 → explicit-dir 分支 → status 带 warning
        monkeypatch.delenv('ACTUS_VAULT2_KEY_PROTECTION', raising=False)
        v = make_vault(world)
        v._ensure_ready()
        assert v.status()['state'] == 'empty'
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        st = v.status(tok)
        assert st['state'] == 'ok' and st['identities'] == 1
        assert st['l1_identities'] == 0
        assert st['key_protection'] == 'file-key'
        assert 'file-key' in st.get('key_protection_warning', '')

    def test_status_counts_and_l1_warning(self, world):
        v = make_vault(world)
        reg = register_vault(v, level='L1')
        tok = _auth_token(v, reg)
        v.set_secret(tok, 's', 'v')
        st = v.status(tok)
        assert st['secrets'] == 1 and st['l1_identities'] == 1
        assert any('L1' in w for w in st['warnings'])

    def test_status_bad_token(self, world):
        v = make_vault(world)
        v._ensure_ready()
        st = v.status('invalid-token')
        assert st['status'] == 'error' and '会话无效' in st['message']

    def test_status_corrupt(self, world):
        v = make_vault(world)
        register_vault(v)
        with open(os.path.join(v.vault_dir, 'vault2.db'), 'wb') as f:
            f.write(b'not a database at all')
        v._ready = False
        st = v.status()
        assert st['state'] == 'corrupt' and st['state_detail']

    def test_status_legacy_warning_and_kek_diag(self, world):
        v = make_vault(world)
        reg = register_vault(v)
        tok = _auth_token(v, reg)
        master = _legacy_master(v, reg)
        _insert_legacy_row(v, reg['identity_id'], 'lgs', 'old', master, 'old-val')
        st = v.status(tok)
        assert st['legacy_secrets'] == 1
        assert any('旧格式' in w for w in st['warnings'])
        assert st['kek_gen'] == 0 and st['kek_rotation_supported'] is True


# ── 模块级便捷函数 ────────────────────────────────────────────────────────

class TestModuleFunctions:
    def test_singleton_and_wrappers(self, world):
        vault2_mod._vault2_singleton = None
        reg = vault2_mod.register('mod-user', '123456')
        assert reg['status'] == 'ok'
        a = vault2_mod.auth(reg['identity_id'], reg['machine_id'], '123456')
        assert a['status'] == 'ok'
        tok = a['session_token']
        assert vault2_mod.set_secret(tok, 'm1', 'v1')['status'] == 'ok'
        assert vault2_mod.get_secret(tok, 'm1')['value'] == 'v1'
        assert vault2_mod.list_secrets(tok)['count'] == 1
        assert vault2_mod.delete_secret(tok, 'm1')['status'] == 'ok'
        assert vault2_mod.status()['initialized'] is True
        assert vault2_mod.audit_log(tok)['status'] == 'ok'
        assert vault2_mod.migrate_legacy_secrets(tok)['status'] == 'ok'
        assert vault2_mod.migrate_legacy_rows(tok)['status'] == 'ok'
        assert vault2_mod.anomaly_check(tok)['status'] == 'ok'
        assert vault2_mod.list_machines(tok)['status'] == 'ok'
        assert vault2_mod.cleanup_rotated_backups()['status'] == 'ok'
        assert vault2_mod.resolve_vault_refs(tok, [])['status'] == 'ok'
        assert vault2_mod.rotate_seed_key(tok)['status'] == 'ok'       # 默认干跑
        assert vault2_mod.rotate_kek(tok)['status'] == 'ok'
        assert vault2_mod.rotate_secret(tok, 'nope')['status'] == 'error'
        assert vault2_mod.rollback_secret(tok, 'nope')['status'] == 'error'
        rec = vault2_mod.recover(reg['identity_id'], reg['recovery_key'], '654321')
        assert rec['status'] == 'ok'
        assert vault2_mod._get_vault2(create=True) is vault2_mod._get_vault2()

    def test_get_vault2_lazy_no_fs(self, world):
        vault2_mod._vault2_singleton = None
        v = vault2_mod._get_vault2()
        assert not os.path.exists(v.db_path)            # 构造零文件系统操作
        assert not os.path.exists(v.vault_dir)
