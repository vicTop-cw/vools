"""exec_iface.py 统一执行接口契约测试（第 81 轮）。

覆盖：ExecResult/ExecutionContext 协议、_run_with_deadline 墙钟闸门、
result_from_adapter/_classify_error 出参归一、_classify_exception/
_map_error_code 错误归一、executor_for 三通道接线、_ExecutorIface
（dry_run 预览/awaiting_confirmation/deferred/非结构化）、_AdapterIface
（dry_run/内联 spec 顶层键拆分/适配器不存在提示/deferred）、_ScatteredIface
（dry_run→check_scattered/confirmed 映射）。

隔离：全部 tmp 目录 + sys.modules 注入（monkeypatch 还原）；
不触真执行器、真适配器、真网络。
"""
import os
import sys
import time
import types

import pytest

import _ai_local_bootstrap  # noqa: F401  # 必须先于 vools.actus 导入

import vools.actus as _pkg
import vools.actus.exec_iface as ei
from vools.actus.exec_iface import (
    ActionExecutor, ERROR_KINDS, ExecutionContext, ExecResult,
    _classify_error, _classify_exception, _deferred_result, _map_error_code,
    _run_with_deadline, executor_for, result_from_adapter,
    result_from_exception,
)

# ═══════════════════════════════════════════════════════════════════
# 夹具与助手
# ═══════════════════════════════════════════════════════════════════


def _fake_submodule(monkeypatch, parent_pkg, name, fake):
    """替包子模块：sys.modules + 父包属性双注入（`from . import x` 走 getattr）。"""
    monkeypatch.setitem(sys.modules, parent_pkg + '.' + name, fake)
    monkeypatch.setattr(_pkg, name, fake, raising=False)


def _action(meta=None, path='/tmp/x.actus.md'):
    import types
    meta = dict(meta or {})
    return types.SimpleNamespace(
        id=meta.get('id', 'demo.x'), path=path, meta=meta)


class _AdapterResult:
    """adapter.AdapterResult 形状替身（result_from_adapter 只 getattr）。"""

    def __init__(self, success=True, stdout='', stderr='', returncode=0,
                 data=None, duration=0.01, artifact_path=''):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.data = data
        self.duration = duration
        self.artifact_path = artifact_path


@pytest.fixture
def iso_meta(tmp_path, monkeypatch):
    meta = tmp_path / 'meta'
    meta.mkdir()
    monkeypatch.setenv('ACTUS_META_DIR', str(meta))
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path / 'repo'))
    yield tmp_path


# ═══════════════════════════════════════════════════════════════════
# 协议与数据类
# ═══════════════════════════════════════════════════════════════════

class TestProtocol:
    def test_error_kinds_closed_set(self):
        assert ERROR_KINDS == ('auth', 'quota', 'unreachable', 'invalid',
                               'timeout', 'resource', 'runtime')

    def test_module_exports(self):
        for name in ('ExecutionContext', 'ExecResult', 'ActionExecutor',
                     'executor_for', 'ERROR_KINDS', 'result_from_adapter',
                     'result_from_exception'):
            assert name in ei.__all__

    def test_exec_result_defaults_and_dict(self):
        r = ExecResult()
        assert r.status == 'ok' and r.data is None and r.error == ''
        assert r.error_kind == '' and r.duration_ms == 0
        assert r.artifacts == [] and r.timeout_deferred is False
        d = r.to_dict()
        assert d['status'] == 'ok' and d['timeout_deferred'] is False
        assert d['artifacts'] == []
        assert r.ok is True

    def test_exec_result_not_ok(self):
        r = ExecResult(status='error', error='boom')
        assert r.ok is False
        r2 = ExecResult(status='skipped')
        assert r2.ok is False

    def test_exec_context_defaults(self):
        c = ExecutionContext()
        assert c.params == {} and c.caller == ''
        assert c.capabilities == {} and c.env == {}
        assert c.timeout_ms == 0 and c.dry_run is False

    def test_protocol_runtime_checkable(self):
        class Ok:
            def execute(self, action, ctx):
                return ExecResult()
        assert isinstance(Ok(), ActionExecutor)
        assert not isinstance(object(), ActionExecutor)


# ═══════════════════════════════════════════════════════════════════
# 墙钟闸门与超时回执
# ═══════════════════════════════════════════════════════════════════

class TestDeadline:
    def test_no_timeout_runs_sync(self):
        val, deferred = _run_with_deadline(lambda: 42, 0)
        assert (val, deferred) == (42, False)
        val2, _ = _run_with_deadline(lambda: 'x', -5)
        assert val2 == 'x'

    def test_fast_fn_meets_deadline(self):
        val, deferred = _run_with_deadline(lambda: 'done', 5000)
        assert val == 'done' and deferred is False

    def test_slow_fn_deferred(self):
        t0 = time.monotonic()
        val, deferred = _run_with_deadline(
            lambda: time.sleep(0.5) or 'late', 80)
        assert val is None and deferred is True
        assert time.monotonic() - t0 < 0.45   # 到点先返回，不等 worker

    def test_deferred_result_shape(self):
        r = _deferred_result(300)
        assert r.status == 'error'
        assert r.error_kind == 'timeout'
        assert r.timeout_deferred is True
        assert '300ms' in r.error and '可能仍在' in r.error


# ═══════════════════════════════════════════════════════════════════
# 出参归一：result_from_adapter
# ═══════════════════════════════════════════════════════════════════

class TestResultFromAdapter:
    def test_ok_with_data(self):
        r = result_from_adapter(_AdapterResult(data={'a': 1}, duration=0.5))
        assert r.status == 'ok' and r.data == {'a': 1}
        assert r.duration_ms == 500 and r.error == '' and r.error_kind == ''
        assert r.ok is True

    def test_ok_text_fallback_captures_stdout(self):
        r = result_from_adapter(_AdapterResult(stdout='hello\n'))
        assert r.status == 'ok'
        assert r.data == {'stdout': 'hello\n'}   # text 适配器兜底（docs/03 §5）

    def test_ok_data_none_no_stdout(self):
        r = result_from_adapter(_AdapterResult())
        assert r.status == 'ok' and r.data is None

    def test_fail_uses_stderr(self):
        r = result_from_adapter(_AdapterResult(
            success=False, stderr='rate limit exceeded', returncode=1))
        assert r.status == 'error' and r.data is None
        assert r.error == 'rate limit exceeded'
        assert r.error_kind == 'quota'

    def test_fail_stderr_empty_falls_back_stdout(self):
        r = result_from_adapter(_AdapterResult(success=False, stdout='out'))
        assert r.error == 'out'

    def test_fail_both_empty_generic_message(self):
        r = result_from_adapter(_AdapterResult(success=False))
        assert r.error == 'adapter 执行失败'

    def test_artifact_path(self):
        r = result_from_adapter(_AdapterResult(artifact_path='C:/x/a.bin'))
        assert r.artifacts == ['C:/x/a.bin']
        r2 = result_from_adapter(_AdapterResult())
        assert r2.artifacts == []


# ═══════════════════════════════════════════════════════════════════
# 错误归一：_classify_error / _classify_exception / _map_error_code
# ═══════════════════════════════════════════════════════════════════

class TestClassifyError:
    @pytest.mark.parametrize('stderr,rc,kind', [
        ('', 401, 'auth'), ('', 403, 'auth'),
        ('HTTP status: 401', 1, 'auth'),
        ('http/1.1 status = 429', 1, 'quota'),
        ('status code 401', 1, 'auth'),
        ('unauthorized access', 1, 'auth'),
        ('authentication failed', 1, 'auth'),
        ('rate limit hit', 1, 'quota'),
        ('quota exceeded', 1, 'quota'),
        ('', 429, 'quota'),
        ('command timed out', 1, 'timeout'),
        ('connection timeout after 3s', 1, 'timeout'),
        ('connection refused', 1, 'unreachable'),
        ('host unreachable', 1, 'unreachable'),
        ('no route to host', 1, 'unreachable'),
        ('name or service not known', 1, 'unreachable'),
        ('temporary failure in name resolution', 1, 'unreachable'),
        ('permission denied', 1, 'resource'),
        ('Access is denied.', 1, 'resource'),
        ('something else', 1, 'runtime'),
        ('', 0, 'runtime'),
    ])
    def test_matrix(self, stderr, rc, kind):
        assert _classify_error(stderr, rc) == kind

    def test_regression_bare_401_not_auth(self):
        # 审计实测：'processed 401 records, then failed' 只是业务数据
        assert _classify_error('processed 401 records, then failed', 1) == 'runtime'

    def test_regression_sqlite_closed_not_unreachable(self):
        assert _classify_error('connection to sqlite db closed', 1) == 'runtime'


class TestMapErrorCode:
    @pytest.mark.parametrize('code,kind', [
        ('auth_required', 'auth'), ('trust_rejected', 'auth'),
        ('visibility_denied', 'auth'), ('approval_required', 'auth'),
        ('concurrency_limit', 'quota'), ('rate_limited', 'quota'),
        ('param_invalid', 'invalid'), ('action_not_found', 'invalid'),
        ('entry_no_output', 'invalid'), ('omega_spec_invalid', 'invalid'),
        ('dependency_cycle', 'invalid'),
        ('timeout', 'timeout'), ('exec_timeout', 'timeout'),
        ('confirmation_timeout', 'timeout'),
        ('path_not_found', 'unreachable'), ('dependency_missing', 'unreachable'),
        ('language_unavailable', 'unreachable'),
        ('permission_denied', 'resource'), ('sandbox_violation', 'resource'),
        ('internal', ''), ('omega_gate_failed', ''),   # 显式豁免 → runtime
        ('whatever_unknown', ''), ('', ''),
    ])
    def test_matrix(self, code, kind):
        assert _map_error_code(code) == kind
    def test_none_like(self):
        assert _map_error_code(None) == ''


class TestClassifyException:
    def _ae(self, code, msg=''):
        from vools.actus.errors import ActionError
        return ActionError(code, msg or code)

    def test_action_error_mapped(self):
        assert _classify_exception(self._ae('trust_rejected')) == 'auth'
        assert _classify_exception(self._ae('action_not_found')) == 'invalid'
        assert _classify_exception(self._ae('timeout')) == 'timeout'
        assert _classify_exception(self._ae('path_not_found')) == 'unreachable'
        assert _classify_exception(self._ae('permission_denied')) == 'resource'

    def test_action_error_unmapped_runtime(self):
        assert _classify_exception(self._ae('internal')) == 'runtime'

    def test_adapter_unavailable(self):
        class AdapterUnavailableError(Exception):
            pass
        assert _classify_exception(AdapterUnavailableError('x')) == 'unreachable'

    def test_adapter_unavailable_by_message(self):
        assert _classify_exception(ValueError('适配器不可用: cli')) == 'unreachable'

    def test_timeout_name_and_message(self):
        class MyTimeout(Exception):
            pass
        assert _classify_exception(MyTimeout()) == 'timeout'
        assert _classify_exception(ValueError('operation timeout')) == 'timeout'

    def test_connection_name_and_unreachable_message(self):
        class MyConnectionError(Exception):
            pass
        assert _classify_exception(MyConnectionError()) == 'unreachable'
        assert _classify_exception(ValueError('host unreachable')) == 'unreachable'

    def test_permission_name_and_denied_message(self):
        assert _classify_exception(PermissionError()) == 'resource'
        assert _classify_exception(ValueError('access denied by policy')) == 'resource'

    def test_generic_runtime(self):
        assert _classify_exception(ValueError('whatever')) == 'runtime'

    def test_uses_message_attr(self):
        class E(Exception):
            message = '定制消息'
        r = result_from_exception(E('x'))
        assert r.error == '定制消息'
        assert r.status == 'error'

    def test_result_from_exception_kind(self):
        r = result_from_exception(self._ae('omega_spec_invalid'))
        assert r.error_kind == 'invalid'


# ═══════════════════════════════════════════════════════════════════
# 接线：executor_for
# ═══════════════════════════════════════════════════════════════════

class TestExecutorFor:
    @pytest.mark.parametrize('src,cls', [
        ('executor', ei._ExecutorIface), ('adapter', ei._AdapterIface),
        ('scattered', ei._ScatteredIface)])
    def test_sources(self, src, cls):
        assert isinstance(executor_for(src), cls)

    def test_unknown_source(self):
        with pytest.raises(ValueError) as ei_v:
            executor_for('nope')
        assert 'nope' in str(ei_v.value)


# ═══════════════════════════════════════════════════════════════════
# _ExecutorIface
# ═══════════════════════════════════════════════════════════════════

class TestExecutorIface:
    def test_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'vools.actus.executor', None)
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and 'executor 不可导入' in r.error
        assert r.error_kind == 'runtime'

    def _fake_exec_mod(self, monkeypatch, preview=None, execute=None):
        m = types.ModuleType('vools.actus.executor')
        if preview is not None:
            m.preview = preview
        if execute is not None:
            m.execute = execute
        _fake_submodule(monkeypatch, 'vools.actus', 'executor', m)
        return m

    def test_dry_run_preview_ok(self, monkeypatch):
        seen = {}
        def preview(aid, params):
            seen['aid'] = aid
            return {'status': 'ok', 'blocks': 2}
        self._fake_exec_mod(monkeypatch, preview=preview)
        r = ei._ExecutorIface().execute(
            _action({'id': 'a.b'}), ExecutionContext(dry_run=True, params={'x': 1}))
        assert seen['aid'] == 'a.b'
        assert r.status == 'skipped' and r.data == {'status': 'ok', 'blocks': 2}
        assert r.ok is False    # skipped ≠ ok（本次没有执行）

    def test_dry_run_preview_fail(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, preview=lambda a, p: {
            'status': 'error', 'error': {'code': 'action_not_found', 'message': '缺'}})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext(dry_run=True))
        assert r.status == 'error' and r.error == '缺'
        assert r.error_kind == 'invalid' and r.data is not None

    def test_dry_run_preview_raises(self, monkeypatch):
        def boom(a, p):
            raise RuntimeError('preview crashed')
        self._fake_exec_mod(monkeypatch, preview=boom)
        r = ei._ExecutorIface().execute(_action(), ExecutionContext(dry_run=True))
        assert r.status == 'error' and 'preview crashed' in r.error

    def test_dry_run_preview_non_dict(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, preview=lambda a, p: 'weird')
        r = ei._ExecutorIface().execute(_action(), ExecutionContext(dry_run=True))
        assert r.status == 'skipped' and r.data == 'weird'

    def test_execute_ok(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: {
            'status': 'ok', 'data': {'v': 1},
            'error': None, 'artifacts': [{'name': 'a'}]})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'ok' and r.data == {'v': 1}
        assert r.error == '' and r.error_kind == ''
        assert r.artifacts == [{'name': 'a'}] and r.ok is True

    def test_execute_failed_dict_error(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: {
            'status': 'failed', 'data': None,
            'error': {'code': 'action_not_found', 'message': '缺动作'},
            'artifacts': []})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and r.error == '缺动作'
        assert r.error_kind == 'invalid'

    def test_execute_failed_string_error(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: {
            'status': 'failed', 'error': '裸字符串错误'})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and r.error == '裸字符串错误'
        assert r.error_kind == 'runtime'   # 无 code 可映射

    def test_execute_awaiting_confirmation_is_skipped(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: {
            'status': 'awaiting_confirmation', 'data': {'exec_id': 'e1'},
            'error': None, 'artifacts': [{'name': 'z'}]})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        # V-03：待确认是正常业务态 → skipped（本次未执行）
        assert r.status == 'skipped' and r.data == {'exec_id': 'e1'}
        assert r.error == '' and r.error_kind == ''
        assert r.artifacts == [{'name': 'z'}]

    def test_execute_deferred(self, monkeypatch):
        self._fake_exec_mod(
            monkeypatch, execute=lambda a, p: time.sleep(0.5) or {})
        r = ei._ExecutorIface().execute(
            _action(), ExecutionContext(timeout_ms=80))
        assert r.status == 'error' and r.timeout_deferred is True
        assert r.error_kind == 'timeout' and '80ms' in r.error

    def test_execute_raises(self, monkeypatch):
        def boom(a, p):
            raise ValueError('engine kapow')
        self._fake_exec_mod(monkeypatch, execute=boom)
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and 'engine kapow' in r.error
        assert r.error_kind == 'runtime'

    def test_execute_non_dict(self, monkeypatch):
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: 'raw text')
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and '非结构化结果（str）' in r.error
        assert r.error_kind == 'invalid'

    def test_execute_error_message_fallback(self, monkeypatch):
        # 非 ok 且引擎没给 message/code → 兜底文案含 status
        self._fake_exec_mod(monkeypatch, execute=lambda a, p: {
            'status': 'failed', 'error': {}})
        r = ei._ExecutorIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and "status='failed'" in r.error


# ═══════════════════════════════════════════════════════════════════
# _AdapterIface
# ═══════════════════════════════════════════════════════════════════

class TestAdapterIface:
    def test_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'vools.actus.adapter', None)
        r = ei._AdapterIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and 'adapter 不可导入' in r.error

    def _fake_adapter_mod(self, monkeypatch, run_adapter=None,
                          registry_cls=None):
        from vools.actus import adapter as real_adapter
        m = types.ModuleType('vools.actus.adapter')
        m.AdapterSpec = real_adapter.AdapterSpec
        m.AdapterRegistry = registry_cls or real_adapter.AdapterRegistry
        m.run_adapter = run_adapter or (lambda aid, p: _AdapterResult())
        monkeypatch.setitem(sys.modules, 'vools.actus.adapter', m)
        return m

    def test_dry_run_ref_str(self, monkeypatch):
        self._fake_adapter_mod(monkeypatch)
        a = _action({'id': 'a.b', 'adapter': 'myad'})
        r = ei._AdapterIface().execute(a, ExecutionContext(dry_run=True))
        assert r.status == 'skipped'
        assert r.data == {'dry_run': True, 'action_id': 'a.b',
                          'adapter_ref': 'myad'}

    def test_dry_run_ref_dict_inline_spec(self, monkeypatch):
        self._fake_adapter_mod(monkeypatch)
        a = _action({'id': 'a.b', 'adapter': {'type': 'cli', 'command': 'x'}})
        r = ei._AdapterIface().execute(a, ExecutionContext(dry_run=True))
        assert r.data['adapter_ref'] == 'inline-spec'

    def test_missing_ref(self, monkeypatch):
        self._fake_adapter_mod(monkeypatch)
        a = _action({'id': 'a.b'})
        r = ei._AdapterIface().execute(a, ExecutionContext())
        assert r.status == 'error' and '未声明 adapter 引用' in r.error
        assert r.error_kind == 'invalid'

    def test_inline_spec_runs(self, monkeypatch):
        captured = {}
        class FakeAdapter:
            def run(self, params):
                captured['params'] = params
                return _AdapterResult(data={'r': 9})
        class FakeRegistry:
            def create_adapter(self, spec):
                captured['spec'] = spec
                return FakeAdapter()
            def ensure_available(self, sid, spec, adapter):
                captured['ensured'] = sid
        self._fake_adapter_mod(monkeypatch, registry_cls=FakeRegistry)
        a = _action({'id': 'a.b', 'adapter': {
            'type': 'cli', 'command': 'echo hi', 'output': {'type': 'file'}}})
        r = ei._AdapterIface().execute(a, ExecutionContext(params={'q': 1}))
        assert r.status == 'ok' and r.data == {'r': 9}
        assert captured['ensured'] == 'a.b'
        # 顶层键拆分：output 留顶层 → from_dict 解析出 output_type
        assert captured['spec'].output_type == 'file'

    def test_inline_spec_top_keys_split(self, monkeypatch):
        captured = {}
        class FakeAdapter:
            def run(self, params):
                return _AdapterResult(data={'ok': 1})
        class FakeRegistry:
            def create_adapter(self, spec):
                captured['spec'] = spec
                return FakeAdapter()
            def ensure_available(self, sid, spec, adapter):
                pass
        self._fake_adapter_mod(monkeypatch, registry_cls=FakeRegistry)
        a = _action({'id': 'a.b', 'adapter': {
            'type': 'http', 'url': 'http://x', 'name': 'n', 'trust': 'trusted',
            'params': {'schema': {}}, 'extra_key': 'goes-into-adapter-block'}})
        ei._AdapterIface().execute(a, ExecutionContext())
        s = captured['spec']
        assert s.name == 'n' and s.trust == 'trusted'
        assert getattr(s.type, 'value', s.type) == 'http'
        # 顶层键拆分不炸：extra_key 随 adapter 子对象进 from_dict（未知键被忽略）

    def test_inline_spec_run_raises(self, monkeypatch):
        class FakeAdapter:
            def run(self, params):
                raise RuntimeError('adapter run boom')
        class FakeRegistry:
            def create_adapter(self, spec):
                return FakeAdapter()
            def ensure_available(self, sid, spec, adapter):
                pass
        self._fake_adapter_mod(monkeypatch, registry_cls=FakeRegistry)
        a = _action({'adapter': {'type': 'cli', 'command': 'x'}})
        r = ei._AdapterIface().execute(a, ExecutionContext())
        assert r.status == 'error' and 'adapter run boom' in r.error

    def test_inline_spec_deferred(self, monkeypatch):
        class FakeAdapter:
            def run(self, params):
                time.sleep(0.5)
                return _AdapterResult()
        class FakeRegistry:
            def create_adapter(self, spec):
                return FakeAdapter()
            def ensure_available(self, sid, spec, adapter):
                pass
        self._fake_adapter_mod(monkeypatch, registry_cls=FakeRegistry)
        a = _action({'adapter': {'type': 'cli', 'command': 'x'}})
        r = ei._AdapterIface().execute(
            a, ExecutionContext(timeout_ms=80))
        assert r.status == 'error' and r.timeout_deferred is True

    def test_ref_str_runs(self, monkeypatch):
        seen = {}
        def run_adapter(aid, params):
            seen['aid'] = aid
            return _AdapterResult(data={'v': 2})
        self._fake_adapter_mod(monkeypatch, run_adapter=run_adapter)
        a = _action({'adapter': 'reg-ad'})
        r = ei._AdapterIface().execute(a, ExecutionContext(params={'p': 1}))
        assert seen['aid'] == 'reg-ad'
        assert r.status == 'ok' and r.data == {'v': 2}

    def test_ref_str_deferred(self, monkeypatch):
        def slow(aid, p):
            time.sleep(0.5)
            return _AdapterResult()
        self._fake_adapter_mod(monkeypatch, run_adapter=slow)
        a = _action({'adapter': 'reg-ad'})
        r = ei._AdapterIface().execute(a, ExecutionContext(timeout_ms=80))
        assert r.timeout_deferred is True and '80ms' in r.error

    def test_ref_str_raises(self, monkeypatch):
        def boom(aid, p):
            raise ValueError('run_adapter boom')
        self._fake_adapter_mod(monkeypatch, run_adapter=boom)
        r = ei._AdapterIface().execute(
            _action({'adapter': 'reg-ad'}), ExecutionContext())
        assert r.status == 'error' and 'run_adapter boom' in r.error

    def test_adapter_not_found_hint(self, monkeypatch):
        def miss(aid, p):
            return _AdapterResult(success=False, stderr='适配器不存在: nope')
        class FakeSpec:
            def __init__(self, i):
                self.id = i
        class FakeRegistry:
            def discover(self):
                return [FakeSpec('zeta'), FakeSpec('alpha')]
        self._fake_adapter_mod(monkeypatch, run_adapter=miss,
                               registry_cls=FakeRegistry)
        r = ei._AdapterIface().execute(
            _action({'adapter': 'nope'}), ExecutionContext())
        assert r.status == 'error' and r.error_kind == 'invalid'
        assert '适配器不存在: nope' in r.error
        assert "['alpha', 'zeta']" in r.error      # 排序列出已注册
        assert 'actions/adapters/*.actus.md' in r.error

    def test_fail_normal_error(self, monkeypatch):
        def fail(aid, p):
            return _AdapterResult(success=False, stderr='permission denied')
        self._fake_adapter_mod(monkeypatch, run_adapter=fail)
        r = ei._AdapterIface().execute(
            _action({'adapter': 'reg-ad'}), ExecutionContext())
        assert r.status == 'error' and r.error_kind == 'resource'


# ═══════════════════════════════════════════════════════════════════
# _ScatteredIface
# ═══════════════════════════════════════════════════════════════════

class TestScatteredIface:
    def test_import_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'vools.actus.scattered', None)
        r = ei._ScatteredIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and 'scattered 不可导入' in r.error

    def _fake_scattered_mod(self, monkeypatch, check=None, run=None):
        m = types.ModuleType('vools.actus.scattered')
        if check is not None:
            m.check_scattered = check
        if run is not None:
            m.run_scattered = run
        _fake_submodule(monkeypatch, 'vools.actus', 'scattered', m)
        return m

    def test_dry_run_check(self, monkeypatch):
        seen = {}
        def check(path):
            seen['path'] = path
            return {'status': 'ok', 'issues': []}
        self._fake_scattered_mod(monkeypatch, check=check)
        a = _action({'id': 'a.b'}, path='C:/x/demo.actus.md')
        r = ei._ScatteredIface().execute(a, ExecutionContext(dry_run=True))
        assert seen['path'] == 'C:/x/demo.actus.md'
        assert r.status == 'skipped'
        assert r.data['dry_run'] is True and r.data['path'].endswith('demo.actus.md')
        assert r.data['check'] == {'status': 'ok', 'issues': []}

    def test_dry_run_check_raises(self, monkeypatch):
        def boom(path):
            raise RuntimeError('check boom')
        self._fake_scattered_mod(monkeypatch, check=boom)
        r = ei._ScatteredIface().execute(
            _action(), ExecutionContext(dry_run=True))
        assert r.status == 'error' and 'check boom' in r.error

    def test_run_ok(self, monkeypatch):
        seen = {}
        def run(path, params, confirmed):
            seen['confirmed'] = confirmed
            return {'status': 'ok', 'data': {'v': 3}, 'error': None,
                    'artifacts': []}
        self._fake_scattered_mod(monkeypatch, run=run)
        r = ei._ScatteredIface().execute(
            _action(), ExecutionContext(params={'x': 1}))
        assert seen['confirmed'] is True     # dry_run=False → confirmed=True
        assert r.status == 'ok' and r.data == {'v': 3}

    def test_run_failed(self, monkeypatch):
        self._fake_scattered_mod(monkeypatch, run=lambda p, c, confirmed: {
            'status': 'failed', 'data': None,
            'error': {'code': 'dependency_missing', 'message': '缺依赖'}})
        r = ei._ScatteredIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and r.error == '缺依赖'
        assert r.error_kind == 'unreachable'

    def test_run_deferred(self, monkeypatch):
        def slow(path, params, confirmed):
            time.sleep(0.5)
            return {}
        self._fake_scattered_mod(monkeypatch, run=slow)
        r = ei._ScatteredIface().execute(
            _action(), ExecutionContext(timeout_ms=80))
        assert r.timeout_deferred is True and r.error_kind == 'timeout'

    def test_run_raises(self, monkeypatch):
        def boom(path, params, confirmed):
            raise RuntimeError('scattered boom')
        self._fake_scattered_mod(monkeypatch, run=boom)
        r = ei._ScatteredIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and 'scattered boom' in r.error

    def test_run_non_dict(self, monkeypatch):
        self._fake_scattered_mod(
            monkeypatch, run=lambda p, c, confirmed: 12345)
        r = ei._ScatteredIface().execute(_action(), ExecutionContext())
        assert r.status == 'error' and '非结构化结果（int）' in r.error
        assert r.error_kind == 'invalid'
