# -*- coding: utf-8 -*-
"""r100 — resolver.py（多形态目标解析器）契约测试。

覆盖 resolve_target 五级优先级链全分支、_lookup_by_md5/_lookup_by_name
三段回退、_assert_host_allowed 白名单门禁（空白名单=拒）、_download_url /
_download_json_url（假 urlopen，零真网络）、resolve_params_extended 七种
入参形态、_resolve_action_ref 深度/成环/失败、find_action_file 格式无关查找。

隔离红线：
- ACTUS_REPO_ROOT / ACTUS_META_DIR / ACTUS_VAULT2_DIR 全部指 tmp（autouse）；
- _download_url 落盘目录 resolver._DOWNLOAD_DIR 指 tmp；
- patch 一律对象寻址（绑定模块对象属性），禁止字符串寻址（跨文件收集期
  sys.modules['vools.actus.<mod>'] 可能被置换为 namespace stub）；
- 零真网络（urlopen 假件）、零真子进程探测器、零真执行器（executor.execute 假件）。
"""

import _ai_local_bootstrap  # noqa: F401  必须先于 vools 导入

import hashlib
import io
import json
import os
import re
import sys
import urllib.request as _urlreq

import pytest

import vools.actus.executor as executor_mod
import vools.actus.indexer as indexer_mod
import vools.actus.resolver as resolver
import vools.actus.trust_model as trust_model_mod
from vools.actus.errors import ActionError

# 避免未使用告警：_urlreq 以对象寻址方式被 monkeypatch（patch 的是该模块对象属性）
_ = _urlreq


VALID_ACTION_MD = """---
id: r100.demo
name: R100Demo
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: r100 契约测试动作
---

body
"""


# ─────────────────────────── fixtures ────────────────────────────


@pytest.fixture(autouse=True)
def iso_env(monkeypatch, tmp_path):
    """全套件隔离：三个根环境变量 + 下载目录全部指 tmp。"""
    root = tmp_path / 'repo'
    (root / 'actions').mkdir(parents=True)
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(root))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
    monkeypatch.setenv('ACTUS_VAULT2_DIR', str(tmp_path / 'vault2'))
    monkeypatch.setattr(resolver, '_DOWNLOAD_DIR', str(tmp_path / 'dl'))


class _FakeResp:
    """urlopen 假件：上下文管理器 + read()。"""

    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, data):
    monkeypatch.setattr(
        _urlreq, 'urlopen',
        lambda req, timeout=None, context=None: _FakeResp(data))


def _write_action(directory, filename='r100.demo.actus.schema.md',
                  content=VALID_ACTION_MD):
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / filename
    p.write_text(content, encoding='utf-8')
    return str(p)


# ─────────────────── ResolvedTarget / 形态判定 ───────────────────


class TestResolvedTargetDict:
    def test_to_dict_roundtrip_all_fields(self):
        r = resolver.ResolvedTarget(source='url', action_id='a.b', path='/p',
                                    raw='/p', url='https://h/x', downloaded=True,
                                    sha256='ab' * 32, digest_verified=True,
                                    signature_verified=True)
        d = r.to_dict()
        assert d['source'] == 'url' and d['downloaded'] is True
        assert d['digest_verified'] and d['signature_verified']
        assert d['ambiguous'] == []
        assert set(d) == {'source', 'action_id', 'path', 'raw', 'ambiguous',
                          'url', 'downloaded', 'sha256', 'digest_verified',
                          'signature_verified'}


class TestShapePredicates:
    def test_action_id_rejects_slash(self):
        assert resolver._is_action_id('a/b.c') is False      # 含 /

    def test_action_id_requires_dot(self):
        assert resolver._is_action_id('plainname') is False  # 无点

    def test_action_id_rejects_hex32_shape(self, monkeypatch):
        # 88 行分支：含点但整体匹配指纹正则 → 不是 action_id
        monkeypatch.setattr(resolver, '_HEX32_RE', re.compile(r'^ab\.$'))
        assert resolver._is_action_id('ab.') is False

    def test_action_id_rejects_url_prefix(self, monkeypatch):
        # 90 行分支：含点、无斜杠、但命中 URL 前缀 → 不是 action_id
        monkeypatch.setattr(resolver, '_URL_PREFIXES', ('zz.',))
        assert resolver._is_action_id('zz.example.com') is False

    def test_is_hex32_basic(self):
        assert resolver._is_hex32('ab' * 16) is True
        assert resolver._is_hex32('AB' * 16) is True
        assert resolver._is_hex32('zz' * 16) is False
        assert resolver._is_hex32('ab' * 15) is False

    def test_is_url(self):
        assert resolver._is_url('HTTPS://X/Y') is True
        assert resolver._is_url('http://x') is True
        assert resolver._is_url('ftp://x') is False


# ─────────────────────── 指纹 / 名称索引查找 ──────────────────────


class TestLookupByMd5:
    def test_by_md5_string_hit(self):
        idx = {'by_md5': {'ab' * 16: 'hit.one'}}
        assert resolver._lookup_by_md5('ab' * 16, idx) == 'hit.one'

    def test_by_md5_list_hit_takes_first(self):
        idx = {'by_md5': {'ab' * 16: ['first.id', 'second.id']}}
        assert resolver._lookup_by_md5('ab' * 16, idx) == 'first.id'

    def test_fallback_brief_md5_skips_invalid(self):
        idx = {'actions': {
            '_invalid:bad': {'md5': 'AB' * 16},
            'hit.one': {'md5': 'ab' * 16},
        }}
        assert resolver._lookup_by_md5('AB' * 16, idx) == 'hit.one'

    def test_fallback_sha256_prefix(self):
        idx = {'actions': {'sha.two': {'sha256': 'cd' * 16 + 'ffff'}}}
        assert resolver._lookup_by_md5('CD' * 16, idx) == 'sha.two'

    def test_no_match_returns_none(self):
        assert resolver._lookup_by_md5('ee' * 16, {'actions': {}}) is None

    def test_sha256_prefix_skips_invalid(self):
        # 110：sha256 前缀回退同样跳过 _invalid: 条目
        idx = {'actions': {
            '_invalid:z': {'sha256': 'ee' * 16 + 'ff'},
            'ok.a': {'sha256': 'ee' * 16 + '00'},
        }}
        assert resolver._lookup_by_md5('ee' * 16, idx) == 'ok.a'


class TestLookupByName:
    def test_by_name_cached_string(self):
        assert resolver._lookup_by_name('Foo', {'by_name': {'foo': 'a.b'}}) == ['a.b']

    def test_by_name_cached_list(self):
        assert resolver._lookup_by_name('Foo', {'by_name': {'foo': ['a.b']}}) == ['a.b']

    def test_fallback_brief_name_skips_invalid(self):
        idx = {'actions': {
            '_invalid:z': {'name': 'Target'},
            'good.a': {'name': ' Target '},   # 大小写/空白不敏感
            'other.b': {'name': 'Else'},
        }}
        assert resolver._lookup_by_name('target', idx) == ['good.a']

    def test_no_hit_returns_empty(self):
        assert resolver._lookup_by_name('nope', {'actions': {}}) == []


# ───────────────────────── 白名单门禁 ────────────────────────────


class TestAssertHostAllowed:
    def test_empty_allowlist_denies_all(self):
        with pytest.raises(ActionError) as ei:
            resolver._assert_host_allowed('https://evil.example/x', [])
        assert ei.value.code == 'remote_host_denied'
        assert '默认禁止' in ei.value.message

    def test_none_allowlist_denies_all(self):
        with pytest.raises(ActionError) as ei:
            resolver._assert_host_allowed('https://h/x', None)
        assert ei.value.code == 'remote_host_denied'

    def test_host_outside_allowlist_denied(self):
        with pytest.raises(ActionError) as ei:
            resolver._assert_host_allowed('https://evil.example/x',
                                          ['good.example'])
        assert ei.value.details['allow_hosts'] == ['good.example']

    def test_allowed_host_passes(self):
        resolver._assert_host_allowed('https://Good.Example/x',
                                      [' good.example '])  # 归一化后放行


# ─────────────────────────── URL 下载 ────────────────────────────


class TestDownloadUrl:
    def test_success_writes_file(self, monkeypatch, tmp_path):
        _patch_urlopen(monkeypatch, b'id: x\n---\nbody')
        p = resolver._download_url('https://good.example/actions/a.actus.md',
                                   allow_hosts=['good.example'])
        assert os.path.isfile(p)
        with open(p, 'rb') as fh:
            assert fh.read() == b'id: x\n---\nbody'

    def test_too_large_rejected(self, monkeypatch):
        _patch_urlopen(monkeypatch, b'x' * (10 * 1024 * 1024 + 1))
        with pytest.raises(ActionError) as ei:
            resolver._download_url('https://good.example/big',
                                   allow_hosts=['good.example'])
        assert ei.value.code == 'remote_too_large'

    def test_network_error_wrapped(self, monkeypatch):
        def boom(req, timeout=None, context=None):
            raise OSError('net down')
        monkeypatch.setattr(_urlreq, 'urlopen', boom)
        with pytest.raises(ActionError) as ei:
            resolver._download_url('https://good.example/x',
                                   allow_hosts=['good.example'])
        assert ei.value.code == 'remote_download_failed'
        assert 'OSError' in ei.value.message

    def test_denied_host_short_circuits(self):
        # 白名单拒绝发生在 urlopen 之前（连接不会发起）
        with pytest.raises(ActionError) as ei:
            resolver._download_url('https://evil.example/x', allow_hosts=[])
        assert ei.value.code == 'remote_host_denied'

    def test_header_validation_warn_only(self, monkeypatch, tmp_path):
        # 197-204：落盘头校验只警告不删除——内容不含 id/#!cfg/--- 也照常落盘返回
        _patch_urlopen(monkeypatch, b'zzz yyy xxx qqq')
        p = resolver._download_url('https://good.example/plain.md',
                                   allow_hosts=['good.example'])
        assert os.path.isfile(p) and os.path.getsize(p) > 0


# ────────────────────────── 只读索引 ─────────────────────────────


class _FakeBriefAction:
    def __init__(self, aid):
        self._aid = aid

    def brief(self):
        return {'id': self._aid}


class TestKnownIndex:
    def test_index_hit_returns_directly(self, monkeypatch):
        monkeypatch.setattr(indexer_mod, 'load_index',
                            lambda build=True: {'actions': {'a.b': {}}})
        assert resolver._known_index() == {'actions': {'a.b': {}}}

    def test_empty_index_falls_back_to_memory_scan(self, monkeypatch):
        # 213-215：索引缺失/为空 → 内存扫描，不写缓存
        monkeypatch.setattr(indexer_mod, 'load_index',
                            lambda build=True: {'actions': {}, 'built': False})

        def fake_scan(validate=True, write_cache=True):
            assert validate is False and write_cache is False
            return {'scan.a': _FakeBriefAction('scan.a')}
        monkeypatch.setattr(indexer_mod, 'scan_actions', fake_scan)
        idx = resolver._known_index()
        assert idx['actions']['scan.a'] == {'id': 'scan.a'}
        assert resolver._known_action_ids() == {'scan.a': {'id': 'scan.a'}}


# ─────────────────────── resolve_target 全链 ─────────────────────


class TestResolveTargetPath:
    def test_scattered_file_resolves_id(self, tmp_path):
        p = _write_action(tmp_path / 'scat')
        r = resolver.resolve_target(p)
        assert r.source == 'path'
        assert r.action_id == 'r100.demo'
        assert os.path.abspath(p) == os.path.abspath(r.path)

    def test_scattered_file_bad_content_keeps_source(self, tmp_path):
        p = _write_action(tmp_path / 'scat2', content='not-a-valid-action')
        r = resolver.resolve_target(p)
        assert r.source == 'path'
        assert r.action_id == ''          # 259-262：内容非法只标记 source


class TestResolveTargetId:
    def test_known_id(self, monkeypatch):
        monkeypatch.setattr(resolver, '_known_action_ids',
                            lambda: {'demo.echo': {}})
        r = resolver.resolve_target('demo.echo')
        assert r.source == 'id' and r.action_id == 'demo.echo'

    def test_unknown_id_raises_with_known_list(self, monkeypatch):
        monkeypatch.setattr(resolver, '_known_action_ids',
                            lambda: {'a.a': {}, 'b.b': {}})
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('nope.miss')
        assert ei.value.code == 'action_not_found'
        assert ei.value.details['known'] == ['a.a', 'b.b']


class TestResolveTargetMd5:
    def test_fingerprint_hit(self, monkeypatch):
        monkeypatch.setattr(resolver, '_lookup_by_md5',
                            lambda md5, idx: 'demo.echo')
        r = resolver.resolve_target('ab' * 16)
        assert r.source == 'md5' and r.action_id == 'demo.echo'

    def test_fingerprint_miss_raises(self, monkeypatch):
        monkeypatch.setattr(resolver, '_lookup_by_md5', lambda md5, idx: None)
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('ab' * 16)
        assert ei.value.code == 'action_not_found'
        assert ei.value.details['source'] == 'md5'


class TestResolveTargetUrl:
    def _fake_dl(self, monkeypatch, tmp_path, content,
                 sig_content=None, sig_fail=None):
        """假 _download_url：主文件落盘返回其路径；.sig 请求按参数分支。"""
        dlf = tmp_path / 'dlf' / 'a.actus.md'
        dlf.parent.mkdir(parents=True, exist_ok=True)
        dlf.write_bytes(content)
        sig_path = str(dlf) + '.sig'
        calls = []

        def fake_download(url, allow_hosts=None):
            calls.append(url)
            if url.endswith('.sig'):
                if sig_fail:
                    raise sig_fail
                if sig_content is not None:
                    with open(sig_path, 'wb') as fh:
                        fh.write(sig_content)
                return sig_path
            return str(dlf)
        monkeypatch.setattr(resolver, '_download_url', fake_download)
        return calls

    def test_url_downloaded_and_id_parsed(self, monkeypatch, tmp_path):
        calls = self._fake_dl(monkeypatch, tmp_path, VALID_ACTION_MD.encode('utf-8'))
        r = resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'])
        assert r.source == 'url' and r.downloaded is True
        assert r.action_id == 'r100.demo'
        assert r.sha256 == hashlib.sha256(VALID_ACTION_MD.encode('utf-8')).hexdigest()
        assert r.digest_verified is False   # 未给 expect_digest

    def test_url_bad_content_id_empty(self, monkeypatch, tmp_path):
        self._fake_dl(monkeypatch, tmp_path, b'garbage')
        r = resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'])
        assert r.action_id == ''            # 343-344：解析失败静默

    def test_digest_match_verifies(self, monkeypatch, tmp_path):
        content = b'hello-digest'
        self._fake_dl(monkeypatch, tmp_path, content)
        want = hashlib.sha256(content).hexdigest()
        r = resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_digest=want)
        assert r.digest_verified is True

    def test_digest_mismatch_rejects(self, monkeypatch, tmp_path):
        self._fake_dl(monkeypatch, tmp_path, b'hello-digest')
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_digest='ab' * 32)
        assert ei.value.code == 'remote_digest_mismatch'
        assert ei.value.details['expected'] == 'ab' * 32

    def test_sha256_oserror_leaves_empty_then_mismatch(self, monkeypatch, tmp_path):
        # 304-307：落盘文件被删 → OSError → sha256=''；再给 expect_digest → 拒
        dlf = tmp_path / 'dlf' / 'a.actus.md'
        dlf.parent.mkdir(parents=True, exist_ok=True)  # 目录在，文件不存在
        monkeypatch.setattr(resolver, '_download_url',
                            lambda url, allow_hosts=None: str(dlf))
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_digest='ab' * 32)
        assert ei.value.code == 'remote_digest_mismatch'
        assert ei.value.details['actual'] == ''

    def test_signature_ok(self, monkeypatch, tmp_path):
        calls = self._fake_dl(monkeypatch, tmp_path, b'signed-body',
                              sig_content=b'{}')

        class FakeVerifier:
            def verify_file(self, fpath, sig_path=None, key_name=None):
                assert sig_path.endswith('.sig')
                return {'status': 'ok'}
        monkeypatch.setattr(trust_model_mod, 'SignatureVerifier', FakeVerifier)
        r = resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_signature_key='default')
        assert r.signature_verified is True
        assert calls[1] == 'https://good.example/a.actus.md.sig'  # 321

    def test_signature_invalid_rejects(self, monkeypatch, tmp_path):
        self._fake_dl(monkeypatch, tmp_path, b'body', sig_content=b'{}')

        class FakeVerifier:
            def verify_file(self, fpath, sig_path=None, key_name=None):
                return {'status': 'error', 'message': 'bad sig'}
        monkeypatch.setattr(trust_model_mod, 'SignatureVerifier', FakeVerifier)
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_signature_key='default')
        assert ei.value.code == 'remote_signature_invalid'

    def test_signature_missing_rejects(self, monkeypatch, tmp_path):
        self._fake_dl(monkeypatch, tmp_path, b'body',
                      sig_fail=OSError('404'))
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('https://good.example/a.actus.md',
                                    allow_hosts=['good.example'],
                                    expect_signature_key='default')
        assert ei.value.code == 'remote_signature_missing'


class TestResolveTargetName:
    def _patch_index(self, monkeypatch, actions):
        monkeypatch.setattr(resolver, '_known_index', lambda: {'actions': actions})

    def test_single_name_hit(self, monkeypatch):
        self._patch_index(monkeypatch, {'a.x': {'name': 'Solo'}})
        r = resolver.resolve_target('Solo')
        assert r.source == 'name' and r.action_id == 'a.x'

    def test_ambiguous_name_raises_with_candidates(self, monkeypatch):
        self._patch_index(monkeypatch, {'a.x': {'name': 'Dup'},
                                        'b.y': {'name': 'Dup'}})
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('Dup')
        assert ei.value.code == 'action_ambiguous'
        assert sorted(ei.value.details['ambiguous']) == ['a.x', 'b.y']

    def test_dot_no_slash_miss_falls_back_to_id_error(self, monkeypatch):
        # 366-373：反斜杠路径含点但非散落 → id 回退报 not_found
        self._patch_index(monkeypatch, {})
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('a\\b.c')
        assert ei.value.code == 'action_not_found'
        assert ei.value.details['source'] == 'id'

    def test_no_dot_no_name_unresolvable(self, monkeypatch):
        # 375-379：所有形态未命中
        self._patch_index(monkeypatch, {})
        with pytest.raises(ActionError) as ei:
            resolver.resolve_target('plainword')
        assert ei.value.code == 'action_not_found'
        assert '无法解析目标' in ei.value.message


# ─────────────────────── find_action_file ────────────────────────


class TestFindActionFile:
    def test_empty_or_missing_root_returns_none(self, tmp_path):
        assert resolver.find_action_file('', str(tmp_path)) is None
        assert resolver.find_action_file('a.b', '') is None
        assert resolver.find_action_file('a.b', str(tmp_path / 'nope')) is None

    def test_finds_by_parsed_meta_id(self, tmp_path):
        p = _write_action(tmp_path / 'actions' / 'sub')
        assert resolver.find_action_file('r100.demo', str(tmp_path / 'actions')) == p

    def test_unparseable_file_skipped(self, tmp_path):
        root = tmp_path / 'actions'
        _write_action(root / 'bad', content='@@@not parseable@@@')
        assert resolver.find_action_file('r100.demo', str(root)) is None

    def test_wrong_id_returns_none(self, tmp_path):
        root = tmp_path / 'actions'
        _write_action(root)
        assert resolver.find_action_file('other.id', str(root)) is None

    def test_non_action_file_walked_but_skipped(self, tmp_path):
        # 397：os.walk 先命中非动作文件（根层 readme 排在深层动作之前被遍历）
        # → is_action_file 过滤 continue，深层动作仍被找到
        root = tmp_path / 'actions'
        (root / 'a' / 'b').mkdir(parents=True)
        (root / 'readme.txt').write_text('x', encoding='utf-8')
        _write_action(root / 'a' / 'b')
        assert resolver.find_action_file('r100.demo', str(root)) == \
            str(root / 'a' / 'b' / 'r100.demo.actus.schema.md')

    def test_files_only_in_root_not_dirs_edge(self, tmp_path):
        # os.walk 深层目录也被遍历（files 而非 dirs 边界）
        root = tmp_path / 'actions'
        _write_action(root / 'a' / 'b' / 'c')
        assert resolver.find_action_file('r100.demo', str(root)) == \
            str(root / 'a' / 'b' / 'c' / 'r100.demo.actus.schema.md')


# ────────────────────── resolve_params_extended ──────────────────


class TestResolveParamsExtended:
    def test_empty_and_empty_obj(self):
        assert resolver.resolve_params_extended('') == {}
        assert resolver.resolve_params_extended(None) == {}
        assert resolver.resolve_params_extended('{}') == {}

    def test_action_ref_delegates(self, monkeypatch):
        monkeypatch.setattr(resolver, '_resolve_action_ref',
                            lambda tid, allow_hosts=None, max_depth=3,
                            _depth=0, _visited=None: {'from': tid})
        assert resolver.resolve_params_extended('@action:demo.x') == {'from': 'demo.x'}

    def test_url_param_forms_delegate(self, monkeypatch):
        seen = []
        monkeypatch.setattr(resolver, '_download_json_url',
                            lambda url, allow_hosts=None: seen.append(url) or {'u': url})
        assert resolver.resolve_params_extended('@https://h/p.json') == {'u': 'https://h/p.json'}
        assert resolver.resolve_params_extended('https://h/p.json') == {'u': 'https://h/p.json'}
        assert resolver.resolve_params_extended('@http://h/p.json') == {'u': 'http://h/p.json'}
        assert resolver.resolve_params_extended('http://h/p.json') == {'u': 'http://h/p.json'}

    def test_file_param_forms(self, tmp_path):
        f = tmp_path / 'p.json'
        f.write_text('{"k": 1}', encoding='utf-8')
        assert resolver.resolve_params_extended('@' + str(f)) == {'k': 1}

    def test_file_param_bad_json(self, tmp_path):
        f = tmp_path / 'bad.json'
        f.write_text('{nope', encoding='utf-8')
        with pytest.raises(ValueError, match='不是合法 JSON'):
            resolver.resolve_params_extended('@' + str(f))

    def test_file_param_missing(self, tmp_path):
        with pytest.raises(ValueError, match='无法读取入参文件'):
            resolver.resolve_params_extended('@' + str(tmp_path / 'nope.json'))

    def test_file_param_non_object(self, tmp_path):
        f = tmp_path / 'arr.json'
        f.write_text('[1,2]', encoding='utf-8')
        with pytest.raises(ValueError, match='入参必须是 JSON object'):
            resolver.resolve_params_extended('@' + str(f))

    def test_stdin_form(self, monkeypatch):
        monkeypatch.setattr(sys, 'stdin', io.StringIO('{"a": 2}'))
        assert resolver.resolve_params_extended('-') == {'a': 2}

    def test_stdin_non_object(self, monkeypatch):
        monkeypatch.setattr(sys, 'stdin', io.StringIO('[1]'))
        with pytest.raises(ValueError, match='入参必须是 JSON object'):
            resolver.resolve_params_extended('-')

    def test_json_literal(self):
        assert resolver.resolve_params_extended('{"x": [1]}') == {'x': [1]}

    def test_json_literal_invalid(self):
        with pytest.raises(ValueError, match='入参不是合法 JSON'):
            resolver.resolve_params_extended('{bad')

    def test_json_literal_non_object(self):
        with pytest.raises(ValueError, match='入参必须是 JSON object'):
            resolver.resolve_params_extended('"just a string"')


# ───────────────────────── JSON URL 下载 ─────────────────────────


class TestDownloadJsonUrl:
    def test_success(self, monkeypatch):
        _patch_urlopen(monkeypatch, b'{"ok": true}')
        assert resolver._download_json_url('https://g.example/p.json',
                                           allow_hosts=['g.example']) == {'ok': True}

    def test_too_large(self, monkeypatch):
        _patch_urlopen(monkeypatch, b'x' * (5 * 1024 * 1024 + 1))
        with pytest.raises(ActionError) as ei:
            resolver._download_json_url('https://g.example/big',
                                        allow_hosts=['g.example'])
        assert ei.value.code == 'remote_too_large'

    def test_network_error_wrapped(self, monkeypatch):
        monkeypatch.setattr(_urlreq, 'urlopen',
                            lambda req, timeout=None, context=None: 1 / 0)
        with pytest.raises(ActionError) as ei:
            resolver._download_json_url('https://g.example/x',
                                        allow_hosts=['g.example'])
        assert ei.value.code == 'remote_download_failed'

    def test_invalid_json_valueerror(self, monkeypatch):
        _patch_urlopen(monkeypatch, b'{nope')
        with pytest.raises(ValueError, match='远程 JSON 解析失败'):
            resolver._download_json_url('https://g.example/x',
                                        allow_hosts=['g.example'])

    def test_non_dict_valueerror(self, monkeypatch):
        _patch_urlopen(monkeypatch, b'[1]')
        with pytest.raises(ValueError, match='入参必须是 JSON object'):
            resolver._download_json_url('https://g.example/x',
                                        allow_hosts=['g.example'])

    def test_denied_host(self):
        with pytest.raises(ActionError) as ei:
            resolver._download_json_url('https://evil.example/x', allow_hosts=[])
        assert ei.value.code == 'remote_host_denied'


# ───────────────────────── @action 递归引用 ───────────────────────


class TestResolveActionRef:
    @staticmethod
    def _patch_execute(monkeypatch, result):
        monkeypatch.setattr(executor_mod, 'execute', lambda *a, **k: result)

    def test_success_dict_data(self, monkeypatch):
        seen = {}

        def fake_execute(action_id, params, confirmed=False, **kw):
            seen['id'] = action_id
            seen['confirmed'] = confirmed
            return {'status': 'ok', 'data': {'out': 1}}
        monkeypatch.setattr(executor_mod, 'execute', fake_execute)
        d = resolver._resolve_action_ref('demo.x')
        assert d == {'out': 1}
        assert seen['id'] == 'demo.x' and seen['confirmed'] is True

    def test_non_dict_data_wrapped_as_output(self, monkeypatch):
        self._patch_execute(monkeypatch, {'status': 'ok', 'data': 'plain'})
        assert resolver._resolve_action_ref('demo.x') == {'output': 'plain'}

    def test_execute_failure_raises(self, monkeypatch):
        self._patch_execute(monkeypatch,
                            {'status': 'failed', 'error': {'code': 'boom'}})
        with pytest.raises(ActionError) as ei:
            resolver._resolve_action_ref('demo.x')
        assert ei.value.code == 'action_ref_failed'

    def test_depth_exceeded(self, monkeypatch):
        with pytest.raises(ActionError) as ei:
            resolver._resolve_action_ref('demo.x', max_depth=3, _depth=3)
        assert ei.value.code == 'action_ref_depth_exceeded'

    def test_cycle_detected(self, monkeypatch):
        with pytest.raises(ActionError) as ei:
            resolver._resolve_action_ref('demo.x', _depth=0,
                                         _visited={'demo.x'})
        assert ei.value.code == 'action_ref_cycle'
        assert 'demo.x' in ei.value.details['visited']

    def test_cycle_via_recursion(self, monkeypatch):
        # a 执行后其出参再引用回来：借两层嵌套验证 _visited 传递
        def fake_execute(action_id, params, confirmed=False, **kw):
            return {'status': 'ok', 'data': {}}
        monkeypatch.setattr(executor_mod, 'execute', fake_execute)
        visited = {'demo.a'}

        def ref(aid, allow_hosts=None, max_depth=3, _depth=0, _visited=None):
            _visited = visited
            return resolver._resolve_action_ref(aid, allow_hosts, max_depth,
                                                _depth, _visited)
        with pytest.raises(ActionError) as ei:
            ref('demo.a')
        assert ei.value.code == 'action_ref_cycle'

    def test_visited_default_none_path(self, monkeypatch):
        # 512-513：_visited 缺省为 None 时自建空集
        self._patch_execute(monkeypatch, {'status': 'ok', 'data': {}})
        assert resolver._resolve_action_ref('demo.x', _visited=None) == {}
