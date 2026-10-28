"""tests/actus/test_exec_iface.py —— 统一执行接口测试。

覆盖：
  - ExecResult.to_dict / ok 属性
  - ERROR_KINDS 闭集
  - result_from_adapter 适配
  - result_from_exception 错误归一
  - _classify_error / _classify_exception 分类
  - executor_for 三路接线
"""

import pytest

from vools.actus.exec_iface import (
    ExecutionContext, ExecResult, ERROR_KINDS,
    result_from_adapter, result_from_exception,
    executor_for, _classify_error,
)
from vools.actus.errors import ActionError


class _FakeAction:
    """最小 Action 替身（exec_iface 只读 id/path/meta）。"""

    def __init__(self, aid='a.b', path='', meta=None):
        self.id = aid
        self.path = path
        self.meta = meta or {}


class TestExecResult:
    """ExecResult 结构测试"""

    def test_default_ok(self):
        r = ExecResult()
        assert r.status == 'ok'
        assert r.ok is True

    def test_error_not_ok(self):
        r = ExecResult(status='error', error='boom')
        assert r.ok is False

    def test_to_dict(self):
        r = ExecResult(status='ok', data={'a': 1}, duration_ms=100,
                       artifacts=[{'name': 'x', 'path': '/tmp/x'}])
        d = r.to_dict()
        assert d['status'] == 'ok'
        assert d['data'] == {'a': 1}
        assert d['duration_ms'] == 100
        assert d['artifacts'] == [{'name': 'x', 'path': '/tmp/x'}]

    def test_artifacts_accept_dict_and_str(self):
        """artifacts 兼容双来源：executor dict 列表 + adapter 字符串路径"""
        r = ExecResult(artifacts=[{'path': '/a'}, '/b'])
        assert r.artifacts == [{'path': '/a'}, '/b']

    def test_error_kinds_closed_set(self):
        """error_kind 必须落在闭集内"""
        for kind in ERROR_KINDS:
            r = ExecResult(status='error', error_kind=kind)
            assert kind in ERROR_KINDS


class TestExecutionContext:
    """ExecutionContext 结构测试"""

    def test_defaults(self):
        ctx = ExecutionContext()
        assert ctx.params == {}
        assert ctx.dry_run is False
        assert ctx.timeout_ms == 0

    def test_capabilities(self):
        ctx = ExecutionContext(params={'x': 1}, caller='test',
                               capabilities={'stream': True})
        assert ctx.params == {'x': 1}
        assert ctx.capabilities['stream'] is True


class TestResultFromAdapter:
    """AdapterResult → ExecResult 适配测试"""

    def test_success(self):
        class _AR:
            success = True
            stdout = '{"a": 1}'
            stderr = ''
            returncode = 0
            data = {'a': 1}
            duration = 0.5
            artifact_path = ''
        r = result_from_adapter(_AR())
        assert r.status == 'ok'
        assert r.data == {'a': 1}
        assert r.duration_ms == 500

    def test_failure_classified(self):
        class _AR:
            success = False
            stdout = ''
            stderr = 'auth failed'
            returncode = 401
            data = None
            duration = 0.1
            artifact_path = ''
        r = result_from_adapter(_AR())
        assert r.status == 'error'
        assert r.error_kind == 'auth'

    def test_artifact_path(self):
        class _AR:
            success = True
            stdout = ''
            stderr = ''
            returncode = 0
            data = None
            duration = 0
            artifact_path = '/tmp/out.txt'
        r = result_from_adapter(_AR())
        assert r.artifacts == ['/tmp/out.txt']


class TestResultFromException:
    """异常 → ExecResult 归一测试"""

    def test_action_error_invalid(self):
        exc = ActionError('action_invalid', 'bad')
        r = result_from_exception(exc)
        assert r.status == 'error'
        assert r.error_kind == 'invalid'

    def test_action_error_auth(self):
        exc = ActionError('auth_required', 'no key')
        r = result_from_exception(exc)
        assert r.error_kind == 'auth'

    def test_generic_exception_runtime(self):
        r = result_from_exception(ValueError('x'))
        assert r.error_kind == 'runtime'


class TestClassifyError:
    """stderr → error_kind 分类测试"""

    def test_auth(self):
        assert _classify_error('unauthorized access', 403) == 'auth'
        assert _classify_error('', 401) == 'auth'

    def test_quota(self):
        assert _classify_error('rate limit exceeded', 429) == 'quota'

    def test_timeout(self):
        assert _classify_error('operation timed out', 0) == 'timeout'

    def test_unreachable(self):
        assert _classify_error('connection refused', 0) == 'unreachable'

    def test_runtime_fallback(self):
        assert _classify_error('something weird', 1) == 'runtime'


class TestExecutorFor:
    """三路接线测试"""

    def test_executor(self):
        ex = executor_for('executor')
        assert hasattr(ex, 'execute')

    def test_adapter(self):
        ex = executor_for('adapter')
        assert hasattr(ex, 'execute')

    def test_scattered(self):
        ex = executor_for('scattered')
        assert hasattr(ex, 'execute')

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError):
            executor_for('bogus')

    def test_execute_returns_exec_result(self):
        """三路 execute 对坏输入返回统一 ExecResult（不抛），且失败语义要具体。

        审计加固：原来只断言 `isinstance(r, ExecResult)` —— 返回一个默认的
        `ExecResult()`（status=ok、无 error）也会绿，等于坏输入被当成功。
        现在断言具体失败契约：ok=False、status=error、error_kind=invalid、错误消息点名动作。
        """
        ex = executor_for('executor')
        r = ex.execute(_FakeAction(aid='nonexistent.action'), ExecutionContext())
        assert isinstance(r, ExecResult)
        assert r.ok is False, '坏输入不得返回成功 ExecResult: %r' % (r.to_dict(),)
        assert r.status == 'error'
        assert r.error_kind == 'invalid', r.to_dict()
        assert 'nonexistent.action' in (r.error or ''), r.error


class TestExecutorResultNormalization:
    """executor 真实返回结构（docs/03 §7.2）→ ExecResult 归一化测试。

    复核发现：executor.execute 的真实契约是
      {'status': 'ok'|'failed', 'data': ..., 'error': None | {'code','message','details'},
       'artifacts': [{name,path,hash,block}]}
    不是早期假设的平铺 error 字符串 + status ∈ {ok,success,completed}。
    """

    def test_ok_result(self):
        """status=ok → ExecResult.ok，data/artifacts 透传"""
        from vools.actus.exec_iface import _ExecutorIface

        class _ExecMod:
            @staticmethod
            def execute(action_id, params):
                return {'status': 'ok', 'data': {'r': 1}, 'error': None,
                        'artifacts': [{'name': 'o', 'path': '/a', 'hash': None, 'block': 0}]}

        import sys
        from vools.actus import executor as real_exec
        orig = real_exec.execute
        real_exec.execute = _ExecMod.execute
        try:
            r = _ExecutorIface().execute(_FakeAction(), ExecutionContext())
        finally:
            real_exec.execute = orig
        assert r.status == 'ok'
        assert r.ok is True
        assert r.data == {'r': 1}
        assert r.artifacts == [{'name': 'o', 'path': '/a', 'hash': None, 'block': 0}]
        assert r.error == ''

    def test_failed_result_with_nested_error(self):
        """status=failed + error 嵌套 dict → error 字符串 + error_kind 映射"""
        from vools.actus.exec_iface import _ExecutorIface

        class _ExecMod:
            @staticmethod
            def execute(action_id, params):
                return {'status': 'failed', 'data': None,
                        'error': {'code': 'auth_required',
                                  'message': '需要人类确认',
                                  'details': {}}}

        from vools.actus import executor as real_exec
        orig = real_exec.execute
        real_exec.execute = _ExecMod.execute
        try:
            r = _ExecutorIface().execute(_FakeAction(), ExecutionContext())
        finally:
            real_exec.execute = orig
        assert r.status == 'error'
        assert r.ok is False
        assert r.error == '需要人类确认'
        assert r.error_kind == 'auth'  # auth_required → auth 闭集映射

    def test_unknown_error_code_falls_back_runtime(self):
        """未知 error.code → runtime 兜底（闭集内）"""
        from vools.actus.exec_iface import _ExecutorIface, _map_error_code

        assert _map_error_code('totally_bogus_code') == ''
        # iface 侧兜底 runtime
        class _ExecMod:
            @staticmethod
            def execute(action_id, params):
                return {'status': 'failed', 'data': None,
                        'error': {'code': 'bogus_code', 'message': 'x', 'details': {}}}

        from vools.actus import executor as real_exec
        orig = real_exec.execute
        real_exec.execute = _ExecMod.execute
        try:
            r = _ExecutorIface().execute(_FakeAction(), ExecutionContext())
        finally:
            real_exec.execute = orig
        assert r.error_kind == 'runtime'

    def test_error_code_mapping_table(self):
        """error.code 映射表覆盖常见码"""
        from vools.actus.exec_iface import _map_error_code

        assert _map_error_code('param_invalid') == 'invalid'
        assert _map_error_code('timeout') == 'timeout'
        assert _map_error_code('quota_exceeded') == 'quota'
        assert _map_error_code('permission_denied') == 'resource'
        assert _map_error_code('action_not_found') == 'invalid'
        assert _map_error_code('dep_missing') == 'unreachable'
        assert _map_error_code('trust_denied') == 'auth'
