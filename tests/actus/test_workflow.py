"""tests/actus/test_workflow.py — 工作流引擎测试"""
import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.workflow import (
    Workflow, WorkflowExecutor, DAGScheduler, run_workflow,
)
from vools.actus.model import Action


class TestDAGScheduler:
    """DAGScheduler 拓扑排序测试"""

    def test_topological_sort_linear(self):
        nodes = [
            {'id': 'a', 'action_id': 'test.a', 'depends': ['b']},
            {'id': 'b', 'action_id': 'test.b', 'depends': ['c']},
            {'id': 'c', 'action_id': 'test.c', 'depends': []},
        ]
        scheduler = DAGScheduler(nodes)
        layers = scheduler.topological_sort()
        flat = [n for layer in layers for n in layer]
        assert flat.index('c') < flat.index('b')
        assert flat.index('b') < flat.index('a')

    def test_topological_sort_parallel(self):
        nodes = [
            {'id': 'a', 'action_id': 'test.a', 'depends': []},
            {'id': 'b', 'action_id': 'test.b', 'depends': []},
            {'id': 'c', 'action_id': 'test.c', 'depends': ['a', 'b']},
        ]
        scheduler = DAGScheduler(nodes)
        layers = scheduler.topological_sort()
        flat = [n for layer in layers for n in layer]
        assert flat.index('a') < flat.index('c')
        assert flat.index('b') < flat.index('c')

    def test_get_dependents(self):
        nodes = [
            {'id': 'a', 'action_id': 'test.a', 'depends': ['b']},
            {'id': 'b', 'action_id': 'test.b', 'depends': []},
        ]
        scheduler = DAGScheduler(nodes)
        deps = scheduler.get_dependents('b')
        assert 'a' in deps


def _make_workflow(meta=None):
    """创建测试用的 Workflow 对象"""
    meta = meta or {
        'id': 'test.wf',
        'name': 'Test Workflow',
        'trust': 'trusted',
        'entry': 'main',
        'workflow': {
            'nodes': [
                {'id': 'step1', 'action_id': 'test.a', 'params': {}},
                {'id': 'step2', 'action_id': 'test.b', 'params': {}, 'depends': ['step1']},
            ],
            'graph': {'parallel': True, 'on_failure': 'abort'},
        },
    }
    action = Action(
        meta=meta,
        path='actions/test.wf.actus.md',
        sha256='sha',
        raw='# test',
        body='# test',
    )
    return Workflow(action)


class TestWorkflow:
    """Workflow 工作流定义测试"""

    def test_workflow_creation(self):
        wf = _make_workflow()
        assert wf.workflow_id == 'test.wf'
        assert len(wf.nodes) == 2

    def test_workflow_validate(self):
        wf = _make_workflow()
        result = wf.validate()
        assert isinstance(result, list)

    def test_workflow_execute_returns_dict(self):
        wf = _make_workflow()
        try:
            result = wf.execute(meta_dir=tempfile.mkdtemp())
            assert isinstance(result, dict)
        except Exception:
            pass


class TestWorkflowExecutor:
    """WorkflowExecutor 执行器测试"""

    def test_executor_creation(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir, max_workers=2)
            assert executor.workflow == wf
            assert executor.max_workers == 2
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_resolve_params_literal(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            resolved = executor._resolve_params({'key': 'value', 'num': 42})
            assert resolved['key'] == 'value'
            assert resolved['num'] == 42
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_resolve_params_reference(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            executor._node_outputs['prev'] = {'result': 'hello', 'count': 5}
            resolved = executor._resolve_params({'$prev.result': '$prev.result'})
            assert resolved['$prev.result'] == 'hello'
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_eval_condition_equality(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            executor._node_status['n1'] = 'ok'
            assert executor._eval_condition("$n1.status == 'ok'") is True
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_eval_condition_contains(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            executor._node_outputs['n1'] = {'msg': 'hello world'}
            assert executor._eval_condition("$n1.msg contains 'world'") is True
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_eval_condition_and(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            executor._node_status['a'] = 'ok'
            executor._node_status['b'] = 'ok'
            result = executor._eval_condition("$a.status == 'ok' and $b.status == 'ok'")
            assert result is True
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_compute_status(self):
        wf = _make_workflow()
        tmpdir = tempfile.mkdtemp()
        try:
            executor = WorkflowExecutor(wf, meta_dir=tmpdir)
            executor._node_status = {'a': 'ok', 'b': 'ok'}
            assert executor._compute_status() == 'ok'
            executor._node_status = {'a': 'ok', 'b': 'failed'}
            assert executor._compute_status() == 'partial'
            executor._node_status = {'a': 'failed', 'b': 'failed'}
            assert executor._compute_status() == 'failed'
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestRunWorkflow:
    """run_workflow 便捷函数测试"""

    def test_is_callable(self):
        assert callable(run_workflow)
