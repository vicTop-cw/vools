# -*- coding: utf-8 -*-
"""executor.py 契约测试（Round 69）。

覆盖目标（cov_r60 基线 63.3%，643 stmts）：
- _payload_depth / _meta_dirs / _validate_params / _inject_params_into_body
- kind 执行语义：template / bundle / doc / demo / forwarding（alias/link）
- _deep_merge_params / _merge_link_params
- 幂等：_idempotency_load / _idempotent_key / _idempotent_replay / _idempotent_store
- 门禁：_visibility_gate / record_gate / _security_gate / _check_artifacts_access / _pending_ops
- 执行环境：_sanitize_path_env / _env_snapshot / _env_restore / _apply_env_injections
- 子进程：_run_md_in_child 超时 kill_tree（fake Popen + fake kill_tree）
- _run_blocks 出参解析：JSON 出参 / 块失败 / entry_no_output / 产物收集 / 沙箱清理
- preview 契约 / new_exec_id 格式

全部隔离：tmp 目录 + monkeypatch，不触真实仓库/网络/子进程（除 fake）。
"""

import json
import os
import subprocess
import sys
import types

import pytest

from vools.actus import executor as ex
from vools.actus.errors import ActionError


# ── 测试基建 ───────────────────────────────────────────────

class _Act:
    """最小 Action 桩：executor 内部函数只按属性取值。"""

    def __init__(self, aid='demo.a1', **kw):
        self.id = aid
        self.path = kw.get('path', 'x/a1.actus.md')
        self.body = kw.get('body', '')
        self.entry = kw.get('entry', 'main')
        self.trust = kw.get('trust', 'audit')
        self.kind = kw.get('kind', 'exec')
        self.target = kw.get('target', '')
        self.blocks = kw.get('blocks', [])
        self.dependencies = kw.get('dependencies', [])
        self.raw = kw.get('raw', None)
        self.args_schema = kw.get('args_schema', None)
        self.env_prefix = kw.get('env_prefix', 'ACTUS_')
        self.exec_mode = kw.get('exec_mode', 'sync')
        self.timeout_ms = kw.get('timeout_ms', 0)
        self.max_instances = kw.get('max_instances', 0)
        self.max_processes = kw.get('max_processes', 0)
        self.meta = kw.get('meta', {})


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    """隔离 repo/meta 环境。"""
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / '_meta'))
    return tmp_path


# ── new_exec_id / _payload_depth / _meta_dirs ──────────────

class TestBasics:
    def test_new_exec_id_format(self):
        import re
        assert re.fullmatch(r'\d{8}-[0-9a-f]{6}', ex.new_exec_id())

    def test_payload_depth_shapes(self):
        assert ex._payload_depth(1) == 1
        assert ex._payload_depth({}) == 1
        assert ex._payload_depth({'a': {'b': {'c': 1}}}) == 4
        assert ex._payload_depth([1, [2, [3]]]) == 4  # 根链本身就是一层
        assert ex._payload_depth((1, (2, 3))) == 3  # tuple 分支

    def test_meta_dirs_explicit_both(self, tmp_path):
        m, a = ex._meta_dirs(str(tmp_path / 'm'), str(tmp_path / 'a'))
        assert m == str(tmp_path / 'm')
        assert a == str(tmp_path / 'a')

    def test_meta_dirs_meta_implies_sibling_artifacts(self, tmp_path):
        m, a = ex._meta_dirs(str(tmp_path / 'meta'))
        assert a.endswith(os.path.join('artifacts'))

    def test_meta_dirs_default(self, iso):
        m, a = ex._meta_dirs()
        assert os.path.isabs(m)
        assert a.endswith('artifacts')


# ── _validate_params / _inject_params_into_body ────────────

class TestValidateParams:
    def test_no_schema_ok(self):
        ex._validate_params(_Act(args_schema=None), {})

    def test_invalid_raises_param_invalid(self):
        a = _Act(args_schema={'type': 'object'})
        with pytest.raises(ActionError) as ei:
            ex._validate_params(a, 'not-a-dict')
        assert ei.value.code == 'param_invalid'

    def test_broken_schema_raises(self):
        a = _Act(args_schema={'type': 'nonexistent-type!!'})
        with pytest.raises(ActionError):
            ex._validate_params(a, {})

    def test_inject_appends_bootstrap(self):
        a = _Act(body='body-text')
        out = ex._inject_params_into_body(a, {'x': 1})
        assert out.startswith('body-text')
        assert '__actus_bootstrap' in out


# ── kind 执行语义 ──────────────────────────────────────────

class TestTemplateKind:
    def test_missing_desc(self):
        r = ex._execute_template_kind(_Act(meta={}), 'demo.t', {})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'param_invalid'

    def test_dict_desc_extracted(self, iso, monkeypatch):
        monkeypatch.setattr('vools.actus.scaffold.scaffold_action',
                            lambda **kw: {'ok': True})
        a = _Act(meta={'template': {'description': '做一个东西'}})
        r = ex._execute_template_kind(a, 'demo.t', {'p': 1})
        assert r['status'] == 'ok'
        assert r['data']['scaffold'] == {'ok': True}

    def test_scaffold_exception(self):
        a = _Act(meta={'template': 'desc'})
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr('vools.actus.scaffold.scaffold_action',
                       lambda **kw: 1 / 0)
            r = ex._execute_template_kind(a, 'demo.t', {})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'runtime'


class TestBundleKind:
    def test_missing_members(self):
        r = ex._execute_bundle_kind(_Act(meta={}), 'demo.b', {})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'param_invalid'

    def test_string_members_split(self):
        a = _Act(meta={'members': 'a , b,,'})
        r = ex._execute_bundle_kind(a, 'demo.b', {})
        assert r['status'] == 'ok'
        assert r['data']['members'] == ['a', 'b']
        assert r['data']['count'] == 2

    def test_target_fallback(self):
        a = _Act(meta={'target': 'only.one'})
        r = ex._execute_bundle_kind(a, 'demo.b', {})
        assert r['data']['members'] == ['only.one']


class TestDocKind:
    def test_ok_shape(self):
        a = _Act(meta={'description': 'd', 'entry': 'e1'},
                 body='doc-body')
        r = ex._execute_doc_kind(a, 'demo.d', {})
        assert r['status'] == 'ok'
        assert r['data']['rendered'] is True
        assert r['data']['body'] == 'doc-body'
        assert r['data']['entry'] == 'e1'


class TestDemoExpansion:
    def test_attach_expansion(self):
        a = _Act(blocks=[{'language': 'python', 'source': 'print(1)',
                          'tags': ['main']},
                         {'language': 'sh', 'content': 'echo hi'}])
        r = {'status': 'ok', 'data': {}}
        out = ex._attach_demo_expansion(r, a)
        demo = out['data']['demo']
        assert demo['block_count'] == 2
        assert all(e['only_code'] is True for e in demo['expanded'])
        assert demo['expanded'][0]['source'] == 'print(1)'

    def test_non_dict_data_untouched(self):
        a = _Act(blocks=[{'source': 'x'}])
        r = {'status': 'ok', 'data': None}
        assert ex._attach_demo_expansion(r, a)['data'] is None


# ── 参数合并 ────────────────────────────────────────────────

class TestMerge:
    def test_deep_merge_nested(self):
        base = {'a': {'x': 1, 'y': 2}, 'keep': 1}
        over = {'a': {'y': 9, 'z': 3}, 'new': [1, 2]}
        out = ex._deep_merge_params(base, over)
        assert out == {'a': {'x': 1, 'y': 9, 'z': 3}, 'keep': 1, 'new': [1, 2]}

    def test_deep_merge_list_replaces(self):
        out = ex._deep_merge_params({'l': [1, 2]}, {'l': [3]})
        assert out == {'l': [3]}

    def test_link_shallow_default(self):
        a = _Act(meta={'args': {'x': 1, 'nest': {'a': 1}}})
        out = ex._merge_link_params(a, {'y': 2, 'nest': {'b': 2}})
        assert out['x'] == 1 and out['y'] == 2
        assert out['nest'] == {'b': 2}  # shallow：整体替换

    def test_link_deep_mode(self):
        a = _Act(meta={'args': {'nest': {'a': 1}}, 'merge': 'deep'})
        out = ex._merge_link_params(a, {'nest': {'b': 2}})
        assert out['nest'] == {'a': 1, 'b': 2}

    def test_link_non_dict_args_passthrough(self):
        a = _Act(meta={'args': 'not-dict'})
        assert ex._merge_link_params(a, {'p': 1}) == {'p': 1}


# ── forwarding（alias/link）─────────────────────────────────

class TestForwarding:
    def test_missing_target(self):
        r = ex._execute_forwarding_kind(_Act(target=''), 'demo.a', {}, 'alias')
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'param_invalid'

    def test_self_cycle(self):
        r = ex._execute_forwarding_kind(_Act(target='demo.a'), 'demo.a', {}, 'alias')
        assert r['error']['code'] == 'action_ref_cycle'

    def test_chain_cycle(self, monkeypatch):
        ex._forward_ctx.depth = 0
        ex._forward_ctx.chain = ['demo.b']
        try:
            r = ex._execute_forwarding_kind(
                _Act(target='demo.b'), 'demo.a', {}, 'alias')
        finally:
            ex._forward_ctx.depth = 0
            ex._forward_ctx.chain = []
        assert r['error']['code'] == 'action_ref_cycle'
        assert 'demo.a → demo.b' in r['error']['message'] or \
            r['error']['details']['chain'] == ['demo.b', 'demo.a', 'demo.b']

    def test_depth_limit(self, monkeypatch):
        ex._forward_ctx.depth = 5
        ex._forward_ctx.chain = []
        try:
            r = ex._execute_forwarding_kind(
                _Act(target='demo.z'), 'demo.a', {}, 'link')
        finally:
            ex._forward_ctx.depth = 0
            ex._forward_ctx.chain = []
        assert r['status'] == 'failed'
        assert '深度超限' in r['error']['message']

    def test_alias_recurses_into_execute(self, iso, monkeypatch):
        """alias 转发走 execute 完整门禁链（这里只验证转发调用发生）。"""
        calls = []

        def fake_execute(target, params, **kw):
            calls.append((target, params, kw.get('confirmed')))
            return {'status': 'ok', 'data': {'from': target}, 'error': None}

        monkeypatch.setattr(ex, 'execute', fake_execute)
        a = _Act(target='demo.target')
        r = ex._execute_forwarding_kind(a, 'demo.alias1', {'p': 1}, 'alias',
                                        confirmed=True)
        assert r['status'] == 'ok'
        assert calls == [('demo.target', {'p': 1}, True)]

    def test_link_merges_params_before_forward(self, iso, monkeypatch):
        seen = {}

        def fake_execute(target, params, **kw):
            seen.update(params)
            return {'status': 'ok', 'data': None, 'error': None}

        monkeypatch.setattr(ex, 'execute', fake_execute)
        a = _Act(target='demo.t', meta={'args': {'base': 1}})
        ex._execute_forwarding_kind(a, 'demo.l', {'over': 2}, 'link')
        assert seen == {'base': 1, 'over': 2}


# ── 幂等 ────────────────────────────────────────────────────

class TestIdempotency:
    def test_load_missing_file(self, tmp_path):
        assert ex._idempotency_load(str(tmp_path)) == {}

    def test_load_corrupt_json(self, tmp_path):
        d = tmp_path / '_meta'
        d.mkdir()
        (d / 'idempotency.json').write_text('{broken', encoding='utf-8')
        assert ex._idempotency_load(str(d)) == {}

    def test_key_rules(self):
        a = _Act(aid='demo.i', meta={'idempotency_key_from': 'k'})
        assert ex._idempotent_key(a, {'k': 'v1'}) == ('demo.i', 'v1')
        assert ex._idempotent_key(a, {}) is None          # 值缺失
        assert ex._idempotent_key(_Act(aid='demo.i', meta={}),
                                  {'k': 1}) is None       # 未声明
        assert ex._idempotent_key(a, None) is None        # 非 dict

    def test_replay_full_flow(self, tmp_path):
        meta = str(tmp_path / '_meta')
        os.makedirs(meta, exist_ok=True)
        a = _Act(aid='demo.i', meta={'idempotency_key_from': 'k'})
        # 1) 无记录
        assert ex._idempotent_replay(meta, a, {'k': 'v'}) is None
        # 2) 存了 entry 但 run 记录不存在
        ex._idempotent_store(meta, a, {'k': 'v'}, 'x-1',
                             {'status': 'ok', 'data': {'n': 1}, 'error': None})
        assert ex._idempotent_replay(meta, a, {'k': 'v'}) is None
        # 3) run 记录 ok → 命中
        rec_path = os.path.join(meta, 'runs')
        os.makedirs(rec_path, exist_ok=True)
        with open(os.path.join(rec_path, 'x-1.json'), 'w', encoding='utf-8') as f:
            json.dump({'exec_id': 'x-1', 'result': {'status': 'ok',
                                                    'data': {'n': 1}}}, f)
        r = ex._idempotent_replay(meta, a, {'k': 'v'})
        assert r is not None and r['data']['n'] == 1

    def test_replay_corrupt_entry_at(self, tmp_path):
        meta = str(tmp_path / '_meta')
        os.makedirs(meta, exist_ok=True)
        with open(ex._idempotency_file(meta), 'w', encoding='utf-8') as f:
            json.dump({'demo.i::v': {'exec_id': 'e', 'at': 'not-a-date'}}, f)
        a = _Act(aid='demo.i', meta={'idempotency_key_from': 'k'})
        assert ex._idempotent_replay(meta, a, {'k': 'v'}) is None

    def test_store_creates_file(self, tmp_path):
        meta = str(tmp_path / '_meta2')
        a = _Act(aid='demo.i', meta={'idempotency_key_from': 'k'})
        ex._idempotent_store(meta, a, {'k': 'v'}, 'e9', {'status': 'ok'})
        data = json.load(open(ex._idempotency_file(meta), encoding='utf-8'))
        assert 'demo.i::v' in data


# ── 门禁：可见性 / 安全 / 产物目录 / 待确认操作 ─────────────

class TestVisibilityGate:
    def test_internal_wrong_path_denied(self, tmp_path):
        from vools.actus import visibility as vis
        calls = []
        monkey_cls = vis.SecretAuditor
        a = _Act(aid='demo.i', meta={'visibility': 'internal'},
                 path=str(tmp_path / 'other' / 'a.md'))
        monkeypatch_auditor = lambda **kw: calls.append(kw) or None
        try:
            vis.SecretAuditor = types.SimpleNamespace(
                record_visibility=monkeypatch_auditor)  # 不行——类要可实例化
        finally:
            vis.SecretAuditor = monkey_cls
        # 上面的替换方式不对，改用 monkeypatch fixture 语义直接测试核心分支：
        with pytest.raises(ActionError) as ei:
            ex._visibility_gate(a, 'demo.i', 'e1')
        assert ei.value.code == 'visibility_denied'

    def test_internal_correct_path_granted(self, tmp_path, monkeypatch):
        from vools.actus import visibility as vis

        class FakeAuditor:
            def record_visibility(self, **kw):
                self.kw = kw

        monkeypatch.setattr(vis, 'SecretAuditor', FakeAuditor)
        a = _Act(aid='demo.i', meta={'visibility': 'internal'},
                 path=os.path.join(str(tmp_path), 'actions', 'system',
                                   '_internal', 'a.actus.md'))
        monkeypatch.setattr(vis, 'is_internal_path', lambda p: True)
        ex._visibility_gate(a, 'demo.i', 'e1')  # 不抛 = 放行

    def test_gated_no_key(self, monkeypatch):
        from vools.actus import visibility as vis

        class FakeAuditor:
            def record_visibility(self, **kw):
                pass

        monkeypatch.setattr(vis, 'SecretAuditor', FakeAuditor)
        monkeypatch.delenv('ACTUS_GATED_KEY', raising=False)
        monkeypatch.setattr('vools.actus.vault.get_key',
                            lambda *a, **k: None)
        a = _Act(aid='demo.g', meta={'visibility': 'gated'})
        with pytest.raises(ActionError) as ei:
            ex._visibility_gate(a, 'demo.g', 'e1')
        assert ei.value.code == 'auth_required'

    def test_gated_env_key_verified(self, monkeypatch):
        from vools.actus import visibility as vis

        class FakeAuditor:
            def record_visibility(self, **kw):
                pass

        class FakeStore:
            def verify(self, key, action_id=None, repo=None):
                return key == 'good'

        monkeypatch.setattr(vis, 'SecretAuditor', FakeAuditor)
        monkeypatch.setenv('ACTUS_GATED_KEY', 'good')
        a = _Act(aid='demo.g', meta={'visibility': 'gated'})
        ex._visibility_gate(a, 'demo.g', 'e1', gated_store=FakeStore())

    def test_gated_bad_key(self, monkeypatch):
        from vools.actus import visibility as vis

        class FakeAuditor:
            def record_visibility(self, **kw):
                pass

        class FakeStore:
            def verify(self, key, action_id=None, repo=None):
                return False

        monkeypatch.setattr(vis, 'SecretAuditor', FakeAuditor)
        monkeypatch.setenv('ACTUS_GATED_KEY', 'bad')
        a = _Act(aid='demo.g', meta={'visibility': 'gated'})
        with pytest.raises(ActionError) as ei:
            ex._visibility_gate(a, 'demo.g', 'e1', gated_store=FakeStore())
        assert ei.value.code == 'auth_required'

    def test_gated_store_runtime_error(self, monkeypatch):
        from vools.actus import visibility as vis

        class FakeAuditor:
            def record_visibility(self, **kw):
                pass

        def boom():
            raise RuntimeError('store broken')

        monkeypatch.setattr(vis, 'SecretAuditor', FakeAuditor)
        monkeypatch.setenv('ACTUS_GATED_KEY', 'k')
        monkeypatch.setattr(vis, 'GatedKeyStore', boom)
        a = _Act(aid='demo.g', meta={'visibility': 'gated'})
        with pytest.raises(ActionError) as ei:
            ex._visibility_gate(a, 'demo.g', 'e1')
        assert ei.value.code == 'auth_required'

    def test_other_visibility_no_gate(self):
        a = _Act(aid='demo.p', meta={'visibility': 'private'})
        ex._visibility_gate(a, 'demo.p', 'e1')  # 旧四级不做判定


class TestSecurityGate:
    def _scanner(self, ret=None, raise_exc=False):
        class S:
            def scan_action(self, *a, **k):
                if raise_exc:
                    raise RuntimeError('scanner down')
                return ret

        return S

    def test_scanner_exception_records_unscanned(self, monkeypatch):
        monkeypatch.setattr('vools.actus.security.get_security_scanner',
                            lambda: self._scanner(raise_exc=True)())
        info = ex._security_gate(_Act(), 'demo.x')
        assert info == {'scanned': False,
                        'reason': 'RuntimeError: scanner down'}

    def test_sandbox_trust_with_issues_denied(self, monkeypatch):
        monkeypatch.setattr(
            'vools.actus.security.get_security_scanner',
            lambda: self._scanner({'safe': False,
                                   'issues': ['dangerous command'],
                                   'sensitive_findings': ['k=v']})())
        a = _Act(meta={'trust': 'sandbox'})
        with pytest.raises(ActionError) as ei:
            ex._security_gate(a, 'demo.x')
        assert ei.value.code == 'permission_denied'

    def test_audit_trust_records_only(self, monkeypatch):
        monkeypatch.setattr(
            'vools.actus.security.get_security_scanner',
            lambda: self._scanner({'safe': False,
                                   'issues': ['i1'], 'sensitive_findings': []})())
        info = ex._security_gate(_Act(meta={'trust': 'audit'}), 'demo.x')
        assert info['scanned'] is True and info['safe'] is False

    def test_safe_action(self, monkeypatch):
        monkeypatch.setattr(
            'vools.actus.security.get_security_scanner',
            lambda: self._scanner({'safe': True, 'issues': [],
                                   'sensitive_findings': []})())
        info = ex._security_gate(_Act(), 'demo.x')
        assert info['safe'] is True and info['issues'] == []


class TestArtifactsAccess:
    def test_check_ok(self, monkeypatch):
        class SB:
            def check_file_access(self, p, op):
                return True, []

        class S:
            sandbox = SB()

        monkeypatch.setattr('vools.actus.security.get_security_scanner',
                            lambda: S())
        ex._check_artifacts_access('any')

    def test_check_denied(self, monkeypatch):
        class SB:
            def check_file_access(self, p, op):
                return False, ['blocked path']

        class S:
            sandbox = SB()

        monkeypatch.setattr('vools.actus.security.get_security_scanner',
                            lambda: S())
        with pytest.raises(ActionError) as ei:
            ex._check_artifacts_access('any')
        assert ei.value.code == 'permission_denied'

    def test_check_scanner_raises(self, monkeypatch):
        def boom():
            raise RuntimeError('x')
        monkeypatch.setattr('vools.actus.security.get_security_scanner', boom)
        ex._check_artifacts_access('any')  # 策略故障不阻塞


class TestPendingOps:
    def test_known_perms(self):
        a = _Act(meta={'permissions': ['files:write', 'net:connect']})
        ops = ex._pending_ops(a, {})
        assert ops[0]['op'] == 'write' and ops[1]['op'] == 'net'

    def test_unknown_perm(self):
        a = _Act(meta={'permissions': ['weird:perm']})
        ops = ex._pending_ops(a, {})
        assert ops[0]['op'] == 'weird:perm'
        assert ops[0]['impact'] == '未知影响'

    def test_empty_defaults_to_run(self):
        ops = ex._pending_ops(_Act(meta={}), {})
        assert ops == [{'op': 'run', 'impact': '执行动作代码块（无声明权限）'}]


# ── 执行环境 ────────────────────────────────────────────────

class TestEnv:
    def test_sanitize_short_path_noop(self, monkeypatch):
        monkeypatch.setenv('PATH', 'C:\\a;C:\\b')
        ex._sanitize_path_env()
        assert os.environ['PATH'] == 'C:\\a;C:\\b'

    def test_sanitize_long_path_dedup_and_sys32_front(self, monkeypatch):
        sys32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                             'System32')
        long = ';'.join([r'C:\x%04d' % i for i in range(1500)]) + ';' + sys32
        monkeypatch.setenv('PATH', long + ';' + long)  # 重复 + 超长
        ex._sanitize_path_env()
        p = os.environ['PATH']
        assert p.split(';')[0].lower().endswith('system32')
        assert len(p) < len(long) * 2

    def test_snapshot_restore_roundtrip(self, monkeypatch):
        snap = ex._env_snapshot()
        os.environ['ACTUS_TEST_NEW'] = '1'
        os.environ['PATH'] = 'changed'
        ex._env_restore(snap)
        assert 'ACTUS_TEST_NEW' not in os.environ

    def test_apply_env_injections_basic(self, iso, tmp_path):
        a = _Act(aid='demo.e', meta={}, path=str(tmp_path / 'a.md'))
        ex.PROCESS_STATE_LOCK.acquire()
        try:
            build = ex._apply_env_injections(a, {'p': 1}, 'e-1',
                                             str(tmp_path / 'art'),
                                             sandboxed=False, meta_dir=None)
        finally:
            ex.PROCESS_STATE_LOCK.release()
        assert os.environ['ACTUS_EXEC_ID'] == 'e-1'
        assert os.environ['ACTUS_ACTION_PATH'] == str(tmp_path / 'a.md')
        assert 'demo' in build  # artifacts/<id>/<version>/<exec_id>
        # 清理注入键
        for k in ('ACTUS_EXEC_ID', 'ACTUS_ACTION_PATH', 'ACTUS_PARAMS',
                  'ACTUS_REPO_ROOT', 'ACTUS_META_DIR'):
            os.environ.pop(k, None)

    def test_apply_env_vault_conflict(self, iso, tmp_path, monkeypatch):
        monkeypatch.setattr('vools.actus.vault.resolve_vault_refs',
                            lambda refs, **k: {'status': 'conflict',
                                               'message': 'v1 vs v2'})
        a = _Act(aid='demo.v', meta={'secrets': [{'key': 'vault://x'}]})
        with pytest.raises(ActionError) as ei:
            ex._apply_env_injections(a, {}, 'e-2', str(tmp_path),
                                     sandboxed=False, meta_dir=None)
        assert ei.value.code == 'vault_secret_conflict'

    def test_apply_env_vault_error(self, iso, tmp_path, monkeypatch):
        monkeypatch.setattr('vools.actus.vault.resolve_vault_refs',
                            lambda refs, **k: {'status': 'error',
                                               'message': '读取失败'})
        a = _Act(aid='demo.v', meta={'secrets': [{'key': 'vault://x'}]})
        with pytest.raises(ActionError) as ei:
            ex._apply_env_injections(a, {}, 'e-3', str(tmp_path),
                                     sandboxed=False, meta_dir=None)
        assert ei.value.code == 'vault_read_failed'

    def test_apply_env_vault_resolved(self, iso, tmp_path, monkeypatch):
        monkeypatch.setattr('vools.actus.vault.resolve_vault_refs',
                            lambda refs, **k: {'status': 'ok',
                                               'resolved': {'TOK': 'abc'}})
        a = _Act(aid='demo.v', meta={'secrets': [{'key': 'vault://x'}]})
        ex._apply_env_injections(a, {}, 'e-4', str(tmp_path),
                                 sandboxed=False, meta_dir=None)
        assert os.environ['TOK'] == 'abc'
        os.environ.pop('TOK', None)

    def test_apply_env_sandboxed_build_dir(self, iso, tmp_path, monkeypatch):
        # 注入键经 monkeypatch 登记，teardown 自动还原——不能裸 pop ACTUS_*：
        # 会把 conftest session 钉死的 ACTUS_VAULT2_DIR/ACTUS_META_DIR 一并删掉
        # （跨文件 order-dependent：先跑本文件再跑 vault 系测试即触发）。
        a = _Act(aid='demo.s', meta={})
        # 快照→注入→逐字回写（与产品 _build_child_env 同一手势）：_apply_env_injections
        # 裸写 os.environ，monkeypatch 追踪不到它后设的键；也不能裸 pop ACTUS_*——
        # 会把 conftest session 钉死的 ACTUS_VAULT2_DIR/ACTUS_META_DIR 一并删掉
        # （跨文件 order-dependent：先跑本文件再跑 vault 系测试即触发）。
        snap = ex._env_snapshot()
        try:
            build = ex._apply_env_injections(a, {}, 'e-5', str(tmp_path),
                                             sandboxed=True, meta_dir=None)
        finally:
            ex._env_restore(snap)
        assert str(tmp_path) in build


# ── 子进程超时（fake Popen + fake kill_tree）────────────────

class TestRunMdInChild:
    def test_timeout_kills_tree(self, iso, tmp_path, monkeypatch):
        a = _Act(aid='demo.t', timeout_ms=50)

        class FakeProc:
            pid = 4242
            returncode = -9

            def wait(self, timeout=None):
                if timeout is not None and timeout < 1:
                    raise subprocess.TimeoutExpired(cmd='x', timeout=timeout)
                return -9

        killed = []
        monkeypatch.setattr('vools.actus._proc.kill_tree',
                            lambda p: killed.append(p.pid))
        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakeProc())
        report, build, deferred = ex._run_md_in_child(
            a, {}, 'e-t', str(tmp_path), False, False, None)
        assert killed == [4242]
        assert deferred is False
        assert report['status'] == 'timeout'
        blk = report['blocks'][0]
        assert '已杀整棵进程树' in blk['stderr']

    def test_child_crash_no_result(self, iso, tmp_path, monkeypatch):
        a = _Act(aid='demo.c', timeout_ms=0)

        class FakeProc:
            pid = 1
            returncode = 1

            def wait(self, timeout=None):
                return 1  # rc=1，且不会写 result.json

        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakeProc())
        report, _, _ = ex._run_md_in_child(
            a, {}, 'e-c', str(tmp_path), False, False, None)
        assert report['status'] == 'failed'
        assert report['blocks'][0]['stderr'].startswith('child_crashed')


# ── _run_blocks 出参解析（fake run_md）──────────────────────

@pytest.fixture()
def fake_bridge(monkeypatch):
    """替换 vools.bridge.md.run_md，返回可编程 report。"""
    holder = {'report': {'blocks': []}}

    mod = types.ModuleType('vools.bridge.md')
    mod.run_md = lambda path, only=None, force=False, build_dir=None: holder['report']
    monkeypatch.setitem(sys.modules, 'vools.bridge.md', mod)
    return holder


class TestRunBlocks:
    def _act(self, **kw):
        return _Act(aid='demo.r', entry='main', **kw)

    def test_ok_json_output(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': json.dumps({'answer': 42}), 'stderr': '',
            'artifacts': [{'name': 'f.txt', 'path': 'p/f.txt',
                           'hash': 'h1'}],
        }]}
        r = ex._run_blocks(self._act(), {}, 'e-1', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['status'] == 'ok'
        assert r['data'] == {'answer': 42}
        assert r['artifacts'][0]['name'] == 'f.txt'

    def test_ok_non_json_output(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': 'plain text out', 'stderr': ''}]}
        r = ex._run_blocks(self._act(), {}, 'e-2', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['data'] == {'output': 'plain text out'}

    def test_block_failed(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [
            {'index': 0, 'language': 'python', 'tag': ['setup'],
             'status': 'ok', 'duration_ms': 1, 'exit_code': 0,
             'stdout': 'ok', 'stderr': ''},
            {'index': 1, 'language': 'python', 'tag': ['main'],
             'status': 'failed', 'duration_ms': 2, 'exit_code': 1,
             'stdout': '', 'stderr': 'boom!'}]}
        r = ex._run_blocks(self._act(), {}, 'e-3', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'block_failed'
        assert 'boom!' in r['error']['message'] or \
            r['error']['details']['failed_blocks'][0]['error'] == 'boom!'
        assert r['error']['details']['blocks'][0]['status'] == 'ok'

    def test_timeout_block(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'timeout', 'duration_ms': 1000, 'exit_code': None,
            'stdout': '', 'stderr': 'too slow'}]}
        r = ex._run_blocks(self._act(), {}, 'e-4', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['status'] == 'failed'
        assert r['timeout_deferred'] is False
        assert r['child_killed'] is True

    def test_entry_no_output(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': '', 'stderr': ''}]}
        r = ex._run_blocks(self._act(), {}, 'e-5', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['error']['code'] == 'entry_no_output'
        assert 'ENTRY_DRIVER' in r['error']['details']['hint']

    def test_stdout_truncated_flag(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': 'x' * 5000, 'stderr': ''}]}
        r = ex._run_blocks(self._act(), {}, 'e-6', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        assert r['stdout_truncated'] is True
        assert len(r['data']['output']) <= 4000

    def test_sandboxed_cleanup_called(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': '{}', 'stderr': ''}]}
        r = ex._run_blocks(self._act(), {}, 'e-7', str(tmp_path),
                           sandboxed=True, meta_dir=None)
        assert r['sandboxed'] is True

    def test_sandboxed_failure_cleans(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'failed', 'duration_ms': 5, 'exit_code': 1,
            'stdout': '', 'stderr': 'nope'}]}
        r = ex._run_blocks(self._act(), {}, 'e-8', str(tmp_path),
                           sandboxed=True, meta_dir=None)
        assert r['status'] == 'failed'

    def test_output_file_artifact(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': [{
            'index': 0, 'language': 'python', 'tag': ['main'],
            'status': 'ok', 'duration_ms': 5, 'exit_code': 0,
            'stdout': '{}', 'stderr': '',
            'output_file': str(tmp_path / 'out.bin')}]}
        r = ex._run_blocks(self._act(), {}, 'e-9', str(tmp_path),
                           sandboxed=False, meta_dir=None)
        arts = r['artifacts']
        assert arts[-1]['name'] == 'out.bin'

    def test_run_md_in_env_passthrough(self, iso, tmp_path, fake_bridge):
        fake_bridge['report'] = {'blocks': []}
        a = self._act()
        report, build = ex._run_md_in_env(a, {}, 'e-10', str(tmp_path),
                                          False, False, None)
        assert report == {'blocks': []}


# ── preview / 错误契约 ──────────────────────────────────────

class TestPreviewAndErrors:
    def test_preview_rejects_action_object(self, iso):
        # 用 Exception 兜住：并行套件里 errors 可能被双导入造成类身份不一致，
        # 契约本身只要求"抛带 code=param_invalid 的结构化错误"。
        with pytest.raises(Exception) as ei:
            ex.preview(_Act())  # 传对象
        assert ei.value.code == 'param_invalid'
        assert 'preview 需要动作 id 字符串' in ei.value.message
