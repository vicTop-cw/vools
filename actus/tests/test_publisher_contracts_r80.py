# -*- coding: utf-8 -*-
"""publisher.py 契约测试（第 80 轮）。

覆盖：resolve_token / 三重门（sigma/omega/contract 全分支）/ triple_gate 聚合 /
GitHubClient（opener 注入 + urllib 错误路径 + 各端点）/ validate_action_paths /
_check_copy_target / _copy_into_repo（幂等/冲突/force）/ _refresh_registry
（真实 registry 重建 + 点前缀合并 + 失败兜底 + 清理）/ publish_local_only
（gate/dry_run/force/半截发布防护/id 三来源）/ publish_to_repo（本地仓形态/
owner 形态缺克隆/非 dev 仓/push 三态）/ publish 统一入口（三途径 + PR 全分支）。

隔离：HOME/ACTUS_META_DIR 指 tmp；token 用 monkeypatch 环境；git 用 fake。
"""

import _ai_local_bootstrap  # noqa: F401  必须先于 vools 导入

import io
import json
import os
import time

import pytest

import vools.actus.publisher as pubmod
from vools.actus.publisher import (
    GITHUB_TOKEN_ENV,
    GitHubClient,
    PublishError,
    _check_copy_target,
    _copy_into_repo,
    _gate_contract,
    _gate_omega,
    _gate_sigma,
    publish,
    publish_local_only,
    publish_to_repo,
    resolve_token,
    triple_gate,
    validate_action_paths,
)
from vools.actus.repo import REGISTRY_FILENAMES, ActionRepo, is_dev_repo


# ── 基建 ──────────────────────────────────────────────────────────────

REG = 'actus.registry.json'

_CFG = {
    'id': 'pub.sample', 'name': '样本', 'version': '1.0.0',
    'trust': 'sandbox', 'entry': 'main', 'kind': 'exec',
    'description': '发布契约测试样本', 'author': 'ownr',
    'platform': 'desktop',
}


def _action_file(dirpath, cfg=None, extra='', fid='pub.sample'):
    c = dict(_CFG)
    if cfg:
        c.update(cfg)
    c['id'] = fid
    body = '```json #!cfg\n' + json.dumps(c, ensure_ascii=False) + '\n```\n'
    body += '```python #!run tag=main\nprint("hi")\n```\n' + extra
    p = os.path.join(dirpath, fid.replace('.', '_') + '.actus.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body)
    return p


def _dev_repo(root, name='myrepo.actus'):
    repo = os.path.join(str(root), name)
    os.makedirs(os.path.join(repo, 'actions'), exist_ok=True)
    with open(os.path.join(repo, REG), 'w', encoding='utf-8') as f:
        json.dump({'actions': [], 'owner': 'ownr'}, f)
    return repo


def _patch_gates(monkeypatch, sigma='pass', omega=None, contract='pass'):
    """把三重门钉到指定状态；omega 传 spec 路径字符串（None→blocked）。"""
    sig = __import__('vools.actus.sigma', fromlist=['x'])
    if sigma == 'pass':
        monkeypatch.setattr(sig, 'extract_sigma_block', lambda t: 'sig', raising=False)
        monkeypatch.setattr(sig, 'parse_module_text', lambda t: object(), raising=False)
        monkeypatch.setattr(sig, 'verify_module',
                            lambda m: {'passed': True, 'fingerprint': 'fp',
                                       'violations': [], 'tests': 3}, raising=False)
    elif sigma == 'fail':
        monkeypatch.setattr(sig, 'extract_sigma_block', lambda t: 'sig', raising=False)
        monkeypatch.setattr(sig, 'parse_module_text', lambda t: object(), raising=False)
        monkeypatch.setattr(sig, 'verify_module',
                            lambda m: {'passed': False, 'fingerprint': 'fp',
                                       'violations': ['v1'] * 12, 'tests': 0}, raising=False)
    elif sigma == 'boom':
        monkeypatch.setattr(sig, 'extract_sigma_block', lambda t: 'sig', raising=False)
        monkeypatch.setattr(sig, 'parse_module_text',
                            lambda t: (_ for _ in ()).throw(RuntimeError('sig blew')), raising=False)

    om = __import__('vools.actus.omega', fromlist=['x'])
    if omega is None:
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: None, raising=False)
    else:
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: omega, raising=False)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / 'meta'))
    monkeypatch.delenv(GITHUB_TOKEN_ENV, raising=False)
    return tmp_path


# ── PublishError / resolve_token ─────────────────────────────────────

class TestErrorAndToken:
    def test_payload(self):
        e = PublishError('x_code', 'msg', {'k': 1})
        assert e.to_payload() == {'code': 'x_code', 'message': 'msg', 'details': {'k': 1}}

    def test_payload_defaults(self):
        assert PublishError('c', 'm').to_payload()['details'] == {}

    def test_env_first(self, world, monkeypatch):
        monkeypatch.setenv(GITHUB_TOKEN_ENV, 'env_tok')
        assert resolve_token() == 'env_tok'

    def test_vault_fallback(self, world, monkeypatch):
        import vools.actus.vault as vm
        monkeypatch.setattr(vm, 'get_key', lambda name, meta_dir='': 'vault_tok')
        assert resolve_token(meta_dir='m') == 'vault_tok'

    def test_all_missing_none(self, world, monkeypatch):
        import vools.actus.vault as vm
        monkeypatch.setattr(vm, 'get_key', lambda name, meta_dir='': None)
        assert resolve_token() is None

    def test_vault_exception_none(self, world, monkeypatch):
        import vools.actus.vault as vm
        def boom(*a, **k):
            raise RuntimeError('vault down')
        monkeypatch.setattr(vm, 'get_key', boom)
        assert resolve_token() is None

    def test_custom_env_name(self, world, monkeypatch):
        monkeypatch.setenv('MY_TOK', 'custom')
        assert resolve_token('MY_TOK') == 'custom'


# ── 三重门 ────────────────────────────────────────────────────────────

class TestGateSigma:
    def test_no_block_skipped(self, world):
        p = _action_file(str(world))
        g = _gate_sigma(p)
        assert g['status'] == 'skipped' and '未内嵌' in g['reason']

    def test_unreadable_fail(self, world):
        g = _gate_sigma(str(world / 'nope.actus.md'))
        assert g['status'] == 'fail' and '不可读' in g['reason']

    def test_engine_exception_fail(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, sigma='boom')
        g = _gate_sigma(p)
        assert g['status'] == 'fail' and '内部异常' in g['reason'] and 'RuntimeError' in g['reason']

    def test_pass_carries_fingerprint(self, world, monkeypatch):
        p = _action_file(str(world), extra='```sigma\nlaw: x\n```\n')
        _patch_gates(monkeypatch, sigma='pass')
        g = _gate_sigma(p)
        assert g == {'status': 'pass', 'fingerprint': 'fp', 'violations': [], 'tests': 3}

    def test_fail_truncates_violations(self, world, monkeypatch):
        p = _action_file(str(world), extra='```sigma\nlaw: x\n```\n')
        _patch_gates(monkeypatch, sigma='fail')
        g = _gate_sigma(p)
        assert g['status'] == 'fail' and len(g['violations']) == 10

    def test_sigma_unimportable_blocked(self, world, monkeypatch):
        p = _action_file(str(world), extra='```sigma\nlaw: x\n```\n')
        monkeypatch.setitem(__import__('sys').modules, 'vools.actus.sigma', None)
        g = _gate_sigma(p)
        assert g['status'] == 'blocked' and '不可导入' in g['reason']


class TestGateOmega:
    def test_no_spec_blocked(self, world, monkeypatch):
        _patch_gates(monkeypatch, omega=None)
        g = _gate_omega('x.actus.md', 'a.b', None)
        assert g['status'] == 'blocked' and g['spec'] is None and '补语料' in g['reason']

    def test_finder_exception_blocked(self, world, monkeypatch):
        om = __import__('vools.actus.omega', fromlist=['x'])
        def boom(*a):
            raise RuntimeError('finder broke')
        monkeypatch.setattr(om, '_find_omega_spec', boom)
        g = _gate_omega('x', 'a.b', None)
        assert g['status'] == 'blocked' and '不可用' in g['reason']

    def test_spec_unreadable_fail(self, world, monkeypatch):
        spec = world / 'b.spec.json'
        spec.write_text('{bad json', encoding='utf-8')
        _patch_gates(monkeypatch, omega=str(spec))
        g = _gate_omega('x', 'a.b', None)
        assert g['status'] == 'fail' and '不可读' in g['reason']
        assert g['spec'].endswith('b.spec.json') and '\\' not in g['spec']

    def test_pass_counts_cases(self, world, monkeypatch):
        spec = world / 'b.spec.json'
        spec.write_text(json.dumps({'cases': [1, 2, 3]}), encoding='utf-8')
        _patch_gates(monkeypatch, omega=str(spec))
        assert _gate_omega('x', 'a.b', None) == {
            'status': 'pass', 'spec': str(spec).replace(os.sep, '/'), 'cases': 3}

    def test_pass_counts_tests_key(self, world, monkeypatch):
        spec = world / 'b.spec.json'
        spec.write_text(json.dumps({'tests': [1]}), encoding='utf-8')
        _patch_gates(monkeypatch, omega=str(spec))
        assert _gate_omega('x', 'a.b', None)['cases'] == 1


class TestGateContract:
    def test_pass(self, world):
        p = _action_file(str(world))
        g = _gate_contract(p)
        assert g['status'] == 'pass' and g['action_id'] == 'pub.sample'
        assert g['trust'] == 'sandbox' and g['visibility'] == 'public'

    def test_unimportable_fail(self, world, monkeypatch):
        monkeypatch.setitem(__import__('sys').modules, 'vools.actus.validate', None)
        g = _gate_contract('whatever')
        assert g['status'] == 'fail' and '不可导入' in g['reason']

    def test_invalid_action_fail(self, world):
        p = world / 'bad.actus.md'
        p.write_text('```json #!cfg\n{"id": "x"}\n```\n', encoding='utf-8')
        g = _gate_contract(str(p))
        assert g['status'] == 'fail' and g['reason']


class TestTripleGate:
    def test_missing_file_raises(self, world):
        with pytest.raises(PublishError) as ei:
            triple_gate(str(world / 'ghost.actus.md'))
        assert ei.value.code == 'action_not_found'

    def test_all_green_publishable(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, sigma='pass', omega='absent')
        # sigma 门被钉 pass 但动作文件无 sigma 块→skipped；omega 钉到不存在路径→blocked
        om = __import__('vools.actus.omega', fromlist=['x'])
        spec = world / 'sample.spec.json'
        spec.write_text(json.dumps({'cases': [1]}), encoding='utf-8')
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: str(spec))
        r = triple_gate(p)
        assert r['publishable'] is True and r['failed'] == [] and r['blocked'] == []
        assert r['action_id'] == 'pub.sample' and r['path'].endswith('.actus.md')

    def test_blocked_not_publishable(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = triple_gate(p)
        assert r['publishable'] is False and r['blocked'] == ['omega']

    def test_failed_not_publishable(self, world, monkeypatch):
        p = _action_file(str(world), extra='```sigma\nlaw: x\n```\n')
        _patch_gates(monkeypatch, sigma='fail', omega=None)
        r = triple_gate(p)
        assert r['publishable'] is False and 'sigma' in r['failed']

    def test_action_id_param_wins(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = triple_gate(p, action_id='forced.id')
        assert r['action_id'] == 'forced.id'


# ── GitHubClient ─────────────────────────────────────────────────────

class TestGitHubClient:
    def test_opener_injection(self):
        seen = {}

        def fake(method, url, body, token):
            seen.update(method=method, url=url, body=body, token=token)
            return {'ok': True, 'status': 200, 'json': {}}

        c = GitHubClient(token='t', opener=fake)
        assert c.repo('o', 'n')['ok'] is True
        assert seen['method'] == 'GET' and seen['url'] == GitHubClient.API + '/repos/o/n'
        assert seen['token'] == 't'

    def test_endpoints_paths_and_bodies(self):
        calls = []

        def fake(method, url, body, token):
            calls.append((method, url, body))
            return {'ok': True, 'status': 200, 'json': {}}

        c = GitHubClient(token='t', opener=fake)
        c.create_repo('n', private=True, description='d')
        c.fork('o', 'n')
        c.create_pr('o', 'n', 'title', 'head:b', base='dev', body='b')
        c.open_prs('o', 'n', 'fo', 'fb')
        assert calls[0] == ('POST', GitHubClient.API + '/user/repos',
                            {'name': 'n', 'private': True, 'description': 'd',
                             'auto_init': False})
        assert calls[1][1] == GitHubClient.API + '/repos/o/n/forks'
        assert calls[2][2]['base'] == 'dev'
        assert calls[3][1].endswith('/pulls?state=open&head=fo:fb')

    def test_no_token_auth_required(self):
        c = GitHubClient(token=None)
        with pytest.raises(PublishError) as ei:
            c.repo('o', 'n')
        assert ei.value.code == 'auth_required' and GITHUB_TOKEN_ENV in ei.value.message

    def test_http_error_shape(self, monkeypatch):
        import urllib.error
        c = GitHubClient(token='t')
        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, 'nf', {},
                                         io.BytesIO(b'{"message":"missing"}'))
        import urllib.request
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        r = c.repo('o', 'n')
        assert r['ok'] is False and r['status'] == 404 and 'missing' in r['error']

    def test_generic_exception_status_zero(self, monkeypatch):
        import urllib.request
        c = GitHubClient(token='t')
        def fake_urlopen(req, timeout=None):
            raise OSError('net down')
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        r = c.repo('o', 'n')
        assert r == {'ok': False, 'status': 0, 'error': 'OSError: net down'}

    def test_request_headers_and_empty_body(self, monkeypatch):
        import urllib.request
        seen = {}
        class Resp:
            status = 201
            def read(self):
                return b''
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake_urlopen(req, timeout=None):
            seen['req'] = req
            return Resp()
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        c = GitHubClient(token='tok', timeout=7)
        r = c.create_pr('o', 'n', 't', 'h')
        req = seen['req']
        assert req.get_header('Authorization') == 'Bearer tok'
        assert '2022-11-28' in (req.get_header('X-github-api-version') or '')
        assert r == {'ok': True, 'status': 201, 'json': {}}

    def test_timeout_passthrough(self, monkeypatch):
        import urllib.request
        seen = {}
        class Resp:
            status = 200
            def read(self):
                return b'{}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake_urlopen(req, timeout=None):
            seen['timeout'] = timeout
            return Resp()
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        GitHubClient(token='t', timeout=9).repo('o', 'n')
        assert seen['timeout'] == 9


# ── validate_action_paths ────────────────────────────────────────────

class TestValidatePaths:
    def test_single_file(self, world):
        p = _action_file(str(world))
        assert validate_action_paths([p]) == [os.path.abspath(p)]

    def test_dir_expand_sorted_skip_pycache(self, world):
        d = world / 'acts'
        (d / '__pycache__').mkdir(parents=True)
        _action_file(str(d), fid='b.act')
        _action_file(str(d / '__pycache__'), fid='z.act')
        _action_file(str(d), fid='a.act')
        (d / 'note.txt').write_text('x', encoding='utf-8')
        out = validate_action_paths([str(d)])
        assert len(out) == 2
        assert [os.path.basename(x) for x in out] == [
            'a_act.actus.md', 'b_act.actus.md']

    def test_non_action_file_rejected(self, world):
        f = world / 'x.txt'
        f.write_text('hi', encoding='utf-8')
        with pytest.raises(PublishError) as ei:
            validate_action_paths([str(f)])
        assert ei.value.code == 'action_invalid'

    def test_missing_path(self, world):
        with pytest.raises(PublishError) as ei:
            validate_action_paths([str(world / 'ghost')])
        assert ei.value.code == 'action_not_found'

    def test_empty_result(self, world):
        d = world / 'empty'
        d.mkdir()
        with pytest.raises(PublishError) as ei:
            validate_action_paths([str(d)])
        assert '没有任何动作文件' in ei.value.message

    def test_dedupe(self, world):
        p = _action_file(str(world))
        assert len(validate_action_paths([p, p, p])) == 1


# ── copy 目标预检 / 拷贝 ──────────────────────────────────────────────

class TestCopyTarget:
    def test_absent_target_ok(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        dest = _check_copy_target(p, ar)
        assert dest.endswith(os.path.join('actions', os.path.basename(p)))

    def test_force_ok(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        assert _check_copy_target(p, ar, force=True)

    def test_identical_idempotent(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        assert _check_copy_target(p, ar)  # 内容相同→放行

    def test_conflict_raises_with_details(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        p2 = _action_file(str(world), cfg={'name': '改版'}, fid='pub.sample')
        with pytest.raises(PublishError) as ei:
            _check_copy_target(p2, ar)
        assert ei.value.code == 'action_exists'
        assert ei.value.details['source'].endswith(os.path.basename(p2))

    def test_category_subdir(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        dest = _check_copy_target(p, ar, category='utils')
        assert os.path.join('actions', 'utils') in dest


class TestCopyIntoRepo:
    def test_copy_and_relpath(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        rel = _copy_into_repo(p, ar)
        assert rel.startswith('actions/')
        assert os.path.isfile(os.path.join(repo, rel.replace('/', os.sep)))

    def test_idempotent_no_rewrite(self, world, monkeypatch):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        calls = []
        real_copy = pubmod.shutil.copyfile

        def spy(src, dst):
            calls.append(dst)
            return real_copy(src, dst)
        monkeypatch.setattr(pubmod.shutil, 'copyfile', spy)
        _copy_into_repo(p, ar)
        assert calls == []  # 幂等 no-op：不重写

    def test_force_rewrites(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        p2 = _action_file(str(world), cfg={'name': 'v2'}, fid='pub.sample')
        rel = _copy_into_repo(p2, ar, force=True)
        with open(os.path.join(repo, rel.replace('/', os.sep)), encoding='utf-8') as f:
            assert 'v2' in f.read()


# ── _refresh_registry ────────────────────────────────────────────────

class TestRefreshRegistry:
    def test_real_rebuild_gains_entry(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        data = pubmod._refresh_registry(ar, ['pub.sample'])
        ids = {a['id'] for a in data['actions']}
        assert 'pub.sample' in ids
        assert data['owner'] == 'ownr' and data['trust_baseline'] == 'community'

    def test_stale_canonical_entries_kept(self, world):
        repo = _dev_repo(world)
        stale = os.path.join(repo, REG)
        with open(stale, encoding='utf-8') as f:
            doc = json.load(f)
        doc['actions'].append({'id': 'ghost.removed', 'source': 'manual'})
        with open(stale, 'w', encoding='utf-8') as f:
            json.dump(doc, f)
        ar = ActionRepo(repo, owner='ownr')
        data = pubmod._refresh_registry(ar, [])
        assert 'ghost.removed' in {a['id'] for a in data['actions']}

    def test_publish_fallback_for_unknown_ids(self, world, monkeypatch):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        reg = __import__('vools.actus.registry', fromlist=['x'])
        def boom(self, *a, **k):
            raise RuntimeError('gen broke')
        monkeypatch.setattr(reg.ActionRegistry, 'build_from_directory', boom)
        data = pubmod._refresh_registry(ar, ['fallback.id'])
        entry = [a for a in data['actions'] if a['id'] == 'fallback.id'][0]
        assert entry['source'] == 'publish' and 'published_at' in entry

    def test_cleanup_strays(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        stray = os.path.join(repo, '.actus-cache')
        os.makedirs(stray, exist_ok=True)
        with open(os.path.join(stray, 'j.json'), 'w', encoding='utf-8') as f:
            f.write('{}')
        pubmod._refresh_registry(ar, [])
        assert not os.path.isdir(stray)
        # 权威文件存在且点前缀副本被清
        assert os.path.isfile(os.path.join(repo, REG))
        for fn in REGISTRY_FILENAMES:
            if fn != REG:
                assert not os.path.isfile(os.path.join(repo, fn))


# ── publish_local_only ───────────────────────────────────────────────

class TestPublishLocalOnly:
    def test_gate_fail_rejects_all(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_local_only([p], str(_dev_repo(world)), dry_run=False)
        assert r['status'] == 'failed' and r['published'] == []
        assert r['error']['code'] == 'action_invalid'
        assert 'omega' in r['error']['details']['blocked']

    def test_gate_reports_carry_all(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_local_only([p], str(_dev_repo(world)))
        assert set(r['gates'][0]['gates']) == {'actus_contract', 'sigma', 'omega'}

    def test_not_dev_repo_raises(self, world):
        p = _action_file(str(world))
        plain = world / 'plain'
        plain.mkdir()
        with pytest.raises(PublishError) as ei:
            publish_local_only([p], str(plain), gate=False)
        assert ei.value.code == 'action_not_found' and '开发仓' in ei.value.message

    def test_dry_run_planned_dest(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_local_only([p], repo, gate=False, dry_run=True)
        assert r['status'] == 'ok' and r['dry_run'] is True
        assert r['published'][0]['planned_dest'] == 'actions/pub_sample.actus.md'
        assert 'dest' not in r['published'][0]
        assert not os.path.isfile(os.path.join(repo, 'actions', 'pub_sample.actus.md'))

    def test_real_publish_registry_count(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_local_only([p], repo, gate=False, dry_run=False)
        assert r['status'] == 'ok' and r['dry_run'] is False
        assert r['published'][0]['dest'].startswith('actions/')
        assert r['registry_actions'] >= 1

    def test_id_resolution_from_gate(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        om = __import__('vools.actus.omega', fromlist=['x'])
        spec = world / 'sample.spec.json'
        spec.write_text(json.dumps({'cases': [1]}), encoding='utf-8')
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: str(spec))
        r = publish_local_only([p], repo, dry_run=True)
        assert r['published'][0]['action_id'] == 'pub.sample'
        assert r['published'][0]['id_resolution'] == 'gate'

    def test_id_resolution_parsed_when_no_gate(self, world):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        r = publish_local_only([p], repo, gate=False, dry_run=True)
        assert r['published'][0]['id_resolution'] == 'parsed'

    def test_id_unresolved_for_garbage(self, world):
        repo = _dev_repo(world)
        p = world / 'junk.actus.md'
        p.write_text('not a config', encoding='utf-8')
        r = publish_local_only([str(p)], repo, gate=False, dry_run=True)
        assert r['published'][0]['action_id'] == ''
        assert r['published'][0]['id_resolution'] == 'unresolved'

    def test_conflict_precheck_no_half_publish(self, world):
        repo = _dev_repo(world)
        pa = _action_file(str(world), fid='a.act')
        pb = _action_file(str(world), fid='b.act')
        # b 的目标已存在且内容不同 → 预检阶段整笔拒绝，a 一个字节都不能落
        dest_b = os.path.join(repo, 'actions', os.path.basename(pb))
        with open(dest_b, 'w', encoding='utf-8') as f:
            f.write('different')
        with pytest.raises(PublishError) as ei:
            publish_local_only([pa, pb], repo, gate=False, dry_run=False)
        assert ei.value.code == 'action_exists'
        assert not os.path.isfile(os.path.join(repo, 'actions',
                                               os.path.basename(pa)))

    def test_conflict_raises_before_any_copy_with_gate(self, world, monkeypatch):
        # gate 全绿时同样走预检（冲突在写盘前暴露）
        repo = _dev_repo(world)
        pa = _action_file(str(world), fid='a.act')
        pb = _action_file(str(world), fid='b.act')
        dest_b = os.path.join(repo, 'actions', os.path.basename(pb))
        with open(dest_b, 'w', encoding='utf-8') as f:
            f.write('different')
        om = __import__('vools.actus.omega', fromlist=['x'])
        spec = world / 'dummy.spec.json'
        spec.write_text(json.dumps({'cases': [1]}), encoding='utf-8')
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: str(spec))
        with pytest.raises(PublishError):
            publish_local_only([pa, pb], repo, dry_run=False)

    def test_force_overwrites_existing(self, world):
        repo = _dev_repo(world)
        ar = ActionRepo(repo, owner='ownr')
        p = _action_file(str(world))
        _copy_into_repo(p, ar)
        p2 = _action_file(str(world), cfg={'name': '新版'}, fid='pub.sample')
        r = publish_local_only([p2], repo, gate=False, dry_run=False, force=True)
        assert r['status'] == 'ok'
        with open(os.path.join(repo, 'actions', os.path.basename(p)),
                  encoding='utf-8') as f:
            assert '新版' in f.read()


# ── publish_to_repo ──────────────────────────────────────────────────

class TestPublishToRepo:
    def test_local_dir_form(self, world, monkeypatch):
        repo = _dev_repo(world, 'own.actus')
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_to_repo([p], repo, gate=False)
        assert r['route'] == 'own_repo' and r['status'] == 'ok'
        assert r['local_root'].endswith('own.actus')
        assert r['repo_ref'] == repo

    def test_owner_form_without_clone(self, world):
        p = _action_file(str(world))
        r = publish_to_repo([p], 'someowner/myrepo.actus', gate=False)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'action_not_found'
        assert 'clone' in r['error']['message']

    def test_owner_form_bad_ref(self, world):
        p = _action_file(str(world))
        with pytest.raises(PublishError):
            publish_to_repo([p], '!!!', gate=False)

    def test_local_dir_not_dev(self, world):
        # 无 owner 的裸名引用：parse_ref 成功 → local_root=裸名 → 非 dev 仓 → 后缀提示分支
        p = _action_file(str(world))
        r = publish_to_repo([p], 'plainrepo.actus', gate=False)
        assert r['status'] == 'failed' and r['error']['details']['need_name_suffix']

    def test_push_dry_run_message(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=True)
        assert r['push'] == {'ok': True, 'dry_run': True,
                             'message': 'dry_run=True，未真正 push'}

    def test_push_without_token_auth_required(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=False)
        assert r['status'] == 'failed' and r['error']['code'] == 'auth_required'

    def test_push_flow_with_fake_git(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        monkeypatch.setenv(GITHUB_TOKEN_ENV, 'tok')
        steps = []

        def fake_git(root, argv, timeout=120):
            steps.append(argv)
            return {'ok': True, 'stdout': '', 'stderr': ''}
        monkeypatch.setattr(pubmod, 'run_git', fake_git)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=False,
                            branch='dev')
        assert r['status'] == 'ok' and r['push']['ok'] is True
        assert steps[0] == ['add', '-A']
        assert steps[-1] == ['push', 'origin', 'dev']
        assert any('commit' in a for s in steps for a in s)
        assert 'publish: 1 action(s)' in ' '.join(steps[1])

    def test_git_commit_fail_internal(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        monkeypatch.setenv(GITHUB_TOKEN_ENV, 'tok')

        def fake_git(root, argv, timeout=120):
            return {'ok': False, 'stderr': 'boom', 'argv': argv}
        monkeypatch.setattr(pubmod, 'run_git', fake_git)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=False)
        assert r['status'] == 'failed' and r['error']['code'] == 'internal'
        assert 'git add 失败' in r['error']['message']

    def test_nothing_to_commit_tolerated(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        monkeypatch.setenv(GITHUB_TOKEN_ENV, 'tok')

        def fake_git(root, argv, timeout=120):
            if argv[0] == 'push':
                return {'ok': True, 'stdout': '', 'stderr': ''}
            return {'ok': False, 'stdout': 'nothing to commit, working tree clean',
                    'stderr': ''}
        monkeypatch.setattr(pubmod, 'run_git', fake_git)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=False)
        assert r['status'] == 'ok'

    def test_push_fail_internal(self, world, monkeypatch):
        repo = _dev_repo(world)
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        monkeypatch.setenv(GITHUB_TOKEN_ENV, 'tok')

        def fake_git(root, argv, timeout=120):
            if argv[0] == 'push':
                return {'ok': False, 'stderr': 'rejected', 'argv': argv}
            return {'ok': True, 'stdout': '', 'stderr': ''}
        monkeypatch.setattr(pubmod, 'run_git', fake_git)
        r = publish_to_repo([p], repo, gate=False, push=True, dry_run=False)
        assert r['status'] == 'failed' and 'push 失败' in r['error']['message']


# ── publish 统一入口 ─────────────────────────────────────────────────

class TestPublishEntry:
    def test_no_route_rejected(self, world):
        with pytest.raises(PublishError) as ei:
            publish(['x'])
        assert ei.value.code == 'param_invalid' and 'to_repo' in ei.value.message

    def test_to_repo_delegates(self, world, monkeypatch):
        repo = _dev_repo(world, 'deleg.actus')
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish([p], to_repo=repo, gate=False)
        assert r['route'] == 'own_repo'

    def test_to_fork_route_and_api(self, world, monkeypatch):
        # fork-API 分支要求 parse_ref(<owner>/<name>.actus) 成功 → 用 cache 里的克隆仓
        cache_repo = world / '.actus' / 'cache' / 'ownr_myrepo.actus'
        repo = _dev_repo(cache_repo, '')
        p = _action_file(str(world))
        seen = {}

        class FakeGh:
            def fork(self, owner, name):
                seen['fork'] = (owner, name)
                return {'ok': True}
        r = publish([p], to_fork='ownr/myrepo.actus', gate=False,
                    dry_run=False, to_pr='upstream/official', client=FakeGh())
        assert r['route'] == 'fork' and r['fork_api'] == {'ok': True}
        assert seen['fork'] == ('upstream', 'official.actus')

    def test_to_fork_no_upstream_skips_fork_api(self, world, monkeypatch):
        cache_repo = world / '.actus' / 'cache' / 'ownr_myrepo.actus'
        _dev_repo(cache_repo, '')
        p = _action_file(str(world))
        r = publish([p], to_fork='ownr/myrepo.actus', gate=False, dry_run=False)
        assert r['fork_api'] == {'ok': True, 'skipped': True}

    def test_to_fork_local_path_api_step_leaks_repo_error(self, world, monkeypatch):
        # BUG-PUB1（现状佐证）：publish_to_repo 支持"本地仓目录"形态，但 publish()
        # 的 fork-API 步骤无条件 parse_ref(to_fork) → 本地路径形态在 dry_run=False
        # 且发布成功时抛**裸 RepoError**（非 PublishError），且 fork 流程中断。
        repo = _dev_repo(world, 'forkd.actus')
        p = _action_file(str(world))
        # 按类型名断言：registry 系测试合跑会触发 bootstrap 重建 vools.actus.repo，
        # 与本文件 import 的 RepoError 身份分裂 → pytest.raises(RepoError) 漏接
        raised = None
        try:
            publish([p], to_fork=repo, gate=False, dry_run=False)
        except Exception as e:                               # noqa: BLE001
            raised = e
        assert raised is not None and type(raised).__name__ == 'RepoError'
        assert not isinstance(raised, PublishError)

    def test_to_fork_dry_run_no_api(self, world, monkeypatch):
        repo = _dev_repo(world, 'forkd.actus')
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish([p], to_fork=repo, gate=False, dry_run=True)
        assert 'fork_api' not in r

    def test_to_pr_needs_owner(self, world):
        p = _action_file(str(world))
        with pytest.raises(PublishError) as ei:
            publish([p], to_pr='justname')
        assert ei.value.code == 'param_invalid' and '<owner>/<repo>' in ei.value.message

    def test_to_pr_gate_fail(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish([p], to_pr='own/official')
        assert r['status'] == 'failed' and r['error']['code'] == 'action_invalid'
        assert r['route'] == 'pr'

    def test_to_pr_dry_run_plan(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish([p], to_pr='own/official', branch='feat', base='dev',
                    title='T', fork_owner='me', dry_run=True, gate=False)
        assert r['pr']['dry_run'] is True
        assert r['pr']['planned'] == {'title': 'T', 'head': 'me:feat', 'base': 'dev'}
        assert r['target'] == 'own/official.actus'

    def test_to_pr_dry_run_default_title(self, world, monkeypatch):
        p = _action_file(str(world))
        _patch_gates(monkeypatch, omega=None)
        r = publish([p], to_pr='own/official', dry_run=True, gate=False)
        assert r['pr']['planned']['title'] == 'publish: 1 action(s)'

    def test_to_pr_real_with_fake_client(self, world, monkeypatch):
        p = _action_file(str(world))
        om = __import__('vools.actus.omega', fromlist=['x'])
        spec = world / 'sample.spec.json'
        spec.write_text(json.dumps({'cases': [1]}), encoding='utf-8')
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: str(spec))
        seen = {}

        class FakeGh:
            def create_pr(self, owner, name, title, head, base, body):
                seen.update(owner=owner, name=name, title=title, head=head,
                            base=base, body=body)
                return {'ok': True, 'status': 201}
        r = publish([p], to_pr='own/official', dry_run=False, client=FakeGh())
        assert r['status'] == 'ok' and r['pr']['status'] == 201
        assert seen['owner'] == 'own' and seen['base'] == 'master'
        assert '三重门已过' in seen['body']

    def test_to_pr_api_fail(self, world, monkeypatch):
        p = _action_file(str(world))
        om = __import__('vools.actus.omega', fromlist=['x'])
        spec = world / 'sample.spec.json'
        spec.write_text(json.dumps({'cases': [1]}), encoding='utf-8')
        monkeypatch.setattr(om, '_find_omega_spec', lambda *a, **k: str(spec))

        class FakeGh:
            def create_pr(self, *a, **k):
                return {'ok': False, 'status': 422, 'error': 'validation failed'}
        r = publish([p], to_pr='own/official', dry_run=False, client=FakeGh())
        assert r['status'] == 'failed' and r['error']['code'] == 'internal'
        assert '422' in r['error']['message']
        assert 'validation failed' in r['error']['details']['response']


# ── 模块导出 ─────────────────────────────────────────────────────────

def test_all_exports():
    import vools.actus.publisher as m
    assert set(m.__all__) == {
        'PublishError', 'triple_gate', 'publish', 'publish_to_repo',
        'publish_local_only', 'resolve_token', 'GITHUB_TOKEN_ENV',
        'GitHubClient', 'validate_action_paths'}
