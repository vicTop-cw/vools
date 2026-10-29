# -*- coding: utf-8 -*-
"""workflow.py 编排契约测试（第 39 轮，round 32 任务）。

目标：把 DAG 调度 / 状态机 / 失败策略 / 条件 / 引用解析的**真实分支**钉住。
发现的产品 bug 只报告、不在本文件修（见汇报）。全部隔离在 tmp_path；
动作执行用 monkeypatch 假 execute，不碰真实引擎/副作用。

每条 docstring 写「退步了会怎样」。
"""
import json
import os
import re
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import workflow as wf_mod  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.workflow import (DAGScheduler, Workflow, WorkflowExecutor)  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────

def _action(meta, action_id='wf.test'):
    base = {'id': action_id, 'name': 'wf', 'version': '1.0.0',
            'trust': 'sandbox'}
    base.update(meta)
    return SimpleNamespace(meta=base)


def _workflow(nodes, graph=None, wid='wf.test'):
    meta = {'id': wid, 'workflow': {'nodes': nodes, 'graph': graph or {}}}
    return Workflow(_action(meta, wid))


class _FakeExecute(object):
    """可编排的假 execute：按 action_id 返回/抛错，并记录调用。"""

    def __init__(self, results=None, errors=None):
        self.results = results or {}
        self.errors = errors or {}
        self.calls = []

    def __call__(self, action_id, params=None, confirmed=True, meta_dir=None):
        self.calls.append({'action_id': action_id, 'params': params,
                           'confirmed': confirmed, 'meta_dir': meta_dir})
        entry = self.results.get(action_id)
        if callable(entry):
            return entry(len(self.calls), params)
        if isinstance(entry, Exception):
            raise entry
        if entry is not None:
            return entry
        err = self.errors.get(action_id)
        if err is not None:
            raise err
        return {'status': 'ok', 'data': {'value': action_id}}


@pytest.fixture
def fake_exec(monkeypatch, tmp_path):
    fake = _FakeExecute()
    monkeypatch.setattr(wf_mod._execute, 'execute', fake)
    return fake


def _executor(monkeypatch, tmp_path, nodes, graph=None):
    wf = _workflow(nodes, graph)
    return WorkflowExecutor(wf, str(tmp_path), max_workers=4)


# ═══════════════════════════════════════════════════════════════════════
# DAGScheduler：拓扑 / 缺失依赖 / 环 / 归一
# ═══════════════════════════════════════════════════════════════════════

def test_scheduler_accepts_list_and_dict_and_linear_layers():
    """退步了会怎样：构造器只接受一种形态（此前 validate 用 list、run 用 dict，
    一条路径静默漏节点）→ 这里直接断言两种输入层一致。"""
    nodes = [{'id': 'a'}, {'id': 'b', 'depends': ['a']}, {'id': 'c', 'depends': ['b']}]
    sched_list = DAGScheduler(nodes)
    sched_dict = DAGScheduler({n['id']: n for n in nodes})
    assert sched_list.topological_sort() == [['a'], ['b'], ['c']]
    assert sched_dict.topological_sort() == [['a'], ['b'], ['c']]


def test_scheduler_diamond_layers():
    """退步了会怎样：diamond 依赖层算错（b/c 应在同层、d 在最后一层）→ 并行/时序全乱。"""
    nodes = [{'id': 'a'}, {'id': 'b', 'depends': ['a']},
             {'id': 'c', 'depends': ['a']},
             {'id': 'd', 'depends': ['b', 'c']}]
    layers = DAGScheduler(nodes).topological_sort()
    assert [set(x) for x in layers] == [{'a'}, {'b', 'c'}, {'d'}]


def test_scheduler_missing_dependency_is_fail_loud():
    """退步了会怎样：未知依赖被静默丢弃（旧实现 `if dep in nodes`）→ 本该串行的节点
    被并发执行，顺序约束无声失效。断言 ActionError + code + details。"""
    with pytest.raises(ActionError) as exc:
        DAGScheduler([{'id': 'a'}, {'id': 'b', 'depends': ['ghost']}])
    assert exc.value.code == 'dag_missing_dep', exc.value
    assert exc.value.details.get('unknown') == {'b': ['ghost']}


def test_scheduler_cycle_is_rejected():
    """退步了会怎样：环被当成正常 DAG → 执行器死循环/永远 pending。"""
    with pytest.raises(ActionError) as exc:
        DAGScheduler([{'id': 'a', 'depends': ['b']},
                      {'id': 'b', 'depends': ['a']}]).topological_sort()
    assert exc.value.code == 'dag_cycle'


def test_scheduler_duplicate_dep_is_same_as_single_dep():
    """重复依赖必须等价单条依赖；旧实现 in_degree 按列表元素加 2、adj 是 set
    只有一条边 → 误报 dag_cycle（#2 已修，去掉 xfail 钉死）。"""
    layers = DAGScheduler([{'id': 'a'},
                           {'id': 'b', 'depends': ['a', 'a']}]).topological_sort()
    assert [set(x) for x in layers] == [{'a'}, {'b'}]


def test_scheduler_get_dependents():
    """退步了会怎样：邻接表漏边 → 下游节点永远等不到。"""
    sched = DAGScheduler([{'id': 'a'}, {'id': 'b', 'depends': ['a']}])
    assert sched.get_dependents('a') == {'b'}
    assert sched.get_dependents('b') == set()
    assert sched.get_dependents('nope') == set()


# ═══════════════════════════════════════════════════════════════════════
# Workflow 模型：归一 / 校验
# ═══════════════════════════════════════════════════════════════════════

def test_workflow_normalizes_schema_aliases():
    """退步了会怎样：schema 键（action/args/deps）没归一 → 引擎读 action_id 为空，
    节点执行空 id 直接失败。断言三种别名都映射到引擎键。"""
    wf = _workflow([
        {'id': 'a', 'action': 'x.one', 'args': {'p': 1}},
        {'id': 'b', 'action_id': 'x.two', 'deps': ['a']},
    ])
    assert wf.nodes['a']['action_id'] == 'x.one'
    assert wf.nodes['a']['params'] == {'p': 1}
    assert wf.nodes['b']['depends'] == ['a']
    assert wf.nodes['b']['action_id'] == 'x.two'


def test_workflow_skips_nodes_without_id():
    """退步了会怎样：无 id 节点被塞进 nodes 字典（key ''）→ 调度器里出现幽灵节点。"""
    wf = _workflow([{'action': 'x.one'}, {'id': 'a', 'action': 'x.two'}])
    assert '' not in wf.nodes
    assert set(wf.nodes) == {'a'}


def test_workflow_validate_reports_empty_duplicate_and_unknown():
    """退步了会怎样：校验只查一半——空 nodes/重复 id/幽灵依赖任一漏检，
    错误流到执行器才炸（或更糟：静默跑错）。"""
    assert Workflow(_action({'id': 'w', 'workflow': {'nodes': []}})).validate() \
        == ['workflow.nodes 为空']

    dup = _workflow([{'id': 'a'}, {'id': 'a'}]).validate()
    assert any('重复 id' in e for e in dup), dup

    unknown = _workflow([{'id': 'a'}, {'id': 'b', 'depends': ['ghost']}]).validate()
    assert any('依赖不存在' in e for e in unknown), unknown


def test_workflow_validate_reports_cycle():
    """退步了会怎样：validate 放行环状工作流 → run 时才抛，配置错误晚发现。"""
    errors = _workflow([{'id': 'a', 'depends': ['b']},
                        {'id': 'b', 'depends': ['a']}]).validate()
    assert any('环' in e or 'dag_cycle' in e for e in errors), errors


def test_workflow_execute_delegates_to_executor(fake_exec, tmp_path):
    """退步了会怎样：Workflow.execute 没把 meta_dir/max_workers/confirmed 传下去 →
    留痕/并行/确认语义在便捷入口丢失。"""
    wf = _workflow([{'id': 'a', 'action': 'x.one'}], graph={'parallel': False})
    result = wf.execute(str(tmp_path / 'meta'), max_workers=2, confirmed=False)
    assert result['status'] == 'ok'
    assert fake_exec.calls[0]['confirmed'] is False
    assert fake_exec.calls[0]['meta_dir'] == str(tmp_path / 'meta')


# ═══════════════════════════════════════════════════════════════════════
# 执行器：成功 / 失败 / 策略 / 重试 / fallback / 超时
# ═══════════════════════════════════════════════════════════════════════

def test_executor_success_outputs_and_persistence(fake_exec, tmp_path):
    """退步了会怎样：节点成功但 outputs 没回填 / 留痕没落盘 → 下游引用与复盘全断。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {'v': 1}},
                         'x.two': {'status': 'ok', 'data': {'v': 2}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.one'},
        {'id': 'b', 'action_id': 'x.two', 'depends': ['a']}],
        graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'ok'
    assert result['node_status'] == {'a': 'ok', 'b': 'ok'}
    assert result['outputs']['a'] == {'v': 1}
    persisted = json.load(open(os.path.join(str(tmp_path), 'workflows',
                                            'wf.test.json'), encoding='utf-8'))
    assert persisted['status'] == 'ok' and persisted['node_status']['b'] == 'ok'


def test_executor_failure_abort_stops_downstream(fake_exec, tmp_path):
    """退步了会怎样（级联）：a 失败但 b/c 继续跑 —— 失败的上游被当成成功，
    下游拿不到输出还继续执行，产生一串假结果。"""
    fake_exec.results = {'x.ok': {'status': 'ok', 'data': {}},
                         'x.bad': {'status': 'failed', 'error': {'message': 'boom'}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.bad'},
        {'id': 'b', 'action_id': 'x.ok', 'depends': ['a']}],
        graph={'parallel': False})
    result = ex.run()
    assert result['node_status'] == {'a': 'failed'}
    assert 'b' not in result['node_status']
    assert [c['action_id'] for c in fake_exec.calls] == ['x.bad']
    assert result['status'] == 'failed'


def test_executor_partial_status_and_continue_policy(fake_exec, tmp_path):
    """退步了会怎样：on_failure=continue 时下游被 abort 掉（或状态全报 failed）——
    部分成功的工作流无法被上层区分。"""
    fake_exec.results = {'x.bad': {'status': 'failed', 'error': {'message': 'e'}},
                         'x.ok': {'status': 'ok', 'data': {}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.bad'},
        {'id': 'b', 'action_id': 'x.ok', 'depends': ['a']}],
        graph={'parallel': False, 'on_failure': 'continue'})
    result = ex.run()
    assert result['node_status'] == {'a': 'failed', 'b': 'ok'}
    assert result['status'] == 'partial'
    assert [c['action_id'] for c in fake_exec.calls] == ['x.bad', 'x.ok']


def test_executor_fail_fast_false_derives_continue(fake_exec, tmp_path):
    """退步了会怎样：契约键 fail_fast=false 被忽略（默认 abort）→ 动作声明
    "失败不中断"却静默中断。"""
    fake_exec.results = {'x.bad': {'status': 'failed', 'error': {'message': 'e'}},
                         'x.ok': {'status': 'ok', 'data': {}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.bad'},
        {'id': 'b', 'action_id': 'x.ok', 'depends': ['a']}],
        graph={'parallel': False, 'fail_fast': False})
    result = ex.run()
    assert result['node_status']['b'] == 'ok'
    assert len(fake_exec.calls) == 2


def test_executor_retry_then_success(fake_exec, tmp_path):
    """退步了会怎样：retry.max_attempts 没生效（只跑一次就放弃）→ 瞬时故障导致整单失败。"""
    attempts = {'n': 0}

    def flaky(n, params):
        attempts['n'] += 1
        if attempts['n'] < 3:
            return {'status': 'failed', 'error': {'message': 'flake'}}
        return {'status': 'ok', 'data': {'ok': 1}}

    fake_exec.results = {'x.flaky': flaky}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.flaky',
         'retry': {'max_attempts': 3}}], graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'ok'
    assert attempts['n'] == 3
    assert result['records'][-1].get('attempt') == 3


def test_executor_retry_exhausted_fallback_success(fake_exec, tmp_path):
    """退步了会怎样：fallback 分支没接上 → 有替代动作也白等失败；或 fallback 成功
    但 node_status 仍 failed。"""
    fake_exec.results = {'x.primary': {'status': 'failed', 'error': {'message': 'x'}},
                         'x.backup': {'status': 'ok', 'data': {'from': 'backup'}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.primary', 'fallback': 'x.backup'}],
        graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'ok'
    assert result['node_status']['a'] == 'ok'
    assert result['outputs']['a'] == {'from': 'backup'}
    assert any(r.get('fallback') == 'x.backup' for r in result['records'])


def test_executor_retry_exhausted_fallback_also_fails(fake_exec, tmp_path):
    """退步了会怎样：fallback 也失败却报 ok（假绿灯）。"""
    fake_exec.results = {'x.primary': {'status': 'failed', 'error': {'message': 'p'}},
                         'x.backup': {'status': 'failed', 'error': {'message': 'b'}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.primary', 'fallback': 'x.backup',
         'retry': {'max_attempts': 2}}], graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'failed'
    assert result['node_status']['a'] == 'failed'


def test_executor_backoff_sleeps_between_attempts(fake_exec, monkeypatch, tmp_path):
    """退步了会怎样：backoff_ms/backoff_multiplier 被忽略 → 重试立即打满（打爆下游）。"""
    sleeps = []
    real_sleep = time.sleep
    monkeypatch.setattr(wf_mod.time, 'sleep', lambda s: sleeps.append(s))
    fake_exec.results = {'x.bad': {'status': 'failed', 'error': {'message': 'e'}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.bad',
         'retry': {'max_attempts': 3, 'backoff_ms': 10,
                   'backoff_multiplier': 2}}], graph={'parallel': False})
    ex.run()
    assert sleeps == [0.01, 0.02], sleeps


def test_executor_timeout_records_abandoned_thread(fake_exec, tmp_path):
    """退步了会怎样：节点超时被当成普通失败且不说明线程还在跑（用户以为已停），
    或超时不生效（join 永远等）。断言 timeout 记录 + abandoned 标记 + failed 状态。"""
    done = threading.Event()

    def slow(action_id, params=None, confirmed=True, meta_dir=None):
        done.wait(0.3)
        return {'status': 'ok', 'data': {}}

    fake_exec.results = {'x.slow': slow}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.slow', 'timeout_s': 0.05}],
        graph={'parallel': False})
    result = ex.run()
    done.set()
    assert result['status'] == 'failed'
    recs = [r for r in result['records'] if r.get('status') == 'timeout']
    assert recs and recs[0]['abandoned'] is True
    assert recs[0]['timeout_s'] == 0.05


# ═══════════════════════════════════════════════════════════════════════
# 条件分支
# ═══════════════════════════════════════════════════════════════════════

def test_executor_condition_false_skips_node(fake_exec, tmp_path):
    """退步了会怎样：condition 为 false 仍执行节点（或跳过但状态记 ok）→ 条件分支失效。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.one',
         'condition': '$missing.status == "ok"'}], graph={'parallel': False})
    result = ex.run()
    assert result['node_status'] == {'a': 'skipped'}
    assert fake_exec.calls == []
    assert any(r.get('status') == 'skipped' for r in result['records'])


def test_executor_condition_on_upstream_output(fake_exec, tmp_path):
    """退步了会怎样：条件只能看 status、不能看上游 output → 真实分支（按结果值）
    永远走 false 或误走 true。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {'result': 7}},
                         'x.two': {'status': 'ok', 'data': {}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.one'},
        {'id': 'b', 'action_id': 'x.two', 'depends': ['a'],
         'condition': '$a.output.result == 7'}], graph={'parallel': False})
    result = ex.run()
    assert result['node_status'] == {'a': 'ok', 'b': 'ok'}


@pytest.mark.parametrize('cond,expected', [
    ('$n.value contains "cat"', True),
    ('$n.value >= 3', True),
    ('$n.value < 3', False),
    ('$n.value != "x"', True),
    ('$n.value == "x" and $n.value != "y"', False),
    ('$n.value == "x" or $n.value == "cats and dogs"', True),
])
def test_eval_condition_operators(cond, expected):
    """退步了会怎样：任一算子（contains/数值/布尔/and/or/引号内 and）写错 →
    条件分支方向翻转。用 `$` 可选写法与引号内含 and 的字符串一起钉住。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'value': 'cats and dogs', 'num': 5}
    # 数值用例改用真实数值字段
    if '>= 3' in cond or '< 3' in cond:
        ex._node_outputs['n'] = {'value': 5}
    assert ex._eval_condition(cond) is expected, cond


def test_eval_condition_boolean_normalization():
    """退步了会怎样：动作输出 JSON 的 true/false 与条件里的 'true' 字符串比较写错 →
    布尔分支反向（把 false 当 true 放行）。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'passed': True}
    assert ex._eval_condition('$n.passed == true') is True
    assert ex._eval_condition('$n.passed != false') is True
    ex._node_outputs['n'] = {'passed': 'true'}   # 字符串形态也要归一
    assert ex._eval_condition('$n.passed == true') is True


def test_eval_condition_malformed_is_false_with_warning():
    """退步了会怎样：无法解析的条件按 true 处理（节点被误执行），或抛异常中断工作流。
    断言：False + records 里出现 warning 审计。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    assert ex._eval_condition('this is not a condition') is False
    assert any(r.get('status') == 'warning' for r in ex._records)


# ═══════════════════════════════════════════════════════════════════════
# 跨节点引用
# ═══════════════════════════════════════════════════════════════════════

def test_resolve_params_output_alias_and_real_field():
    """退步了会怎样：$node.output 的两种真实语义（真字段 vs 别名）没区分 →
    动作打印 {"result":...} 时下游引用恒 None。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'result': {'x': 42}}
    assert ex._resolve_params({'v': '$n.output.result.x'})['v'] == 42
    ex._node_outputs['n'] = {'output': {'x': 42}}
    assert ex._resolve_params({'v': '$n.output.x'})['v'] == 42


def test_resolve_params_nested_list_embedded_and_literal_dollar():
    """退步了会怎样：只解析顶层整串引用（旧实现）→ 嵌套/内嵌引用原样漏给动作；
    或把 "$100" 当引用吃掉。断言三类位置都解析 + 字面美元保留。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'id': 'abc', 'v': 3}
    params = {
        'top': '$n.output.id',
        'nested': {'list': ['$n.output.v', 'price $100']},
        'embedded': 'prefix/$n.output.id/suffix',
    }
    got = ex._resolve_params(params)
    assert got['top'] == 'abc'
    assert got['nested']['list'][0] == 3
    assert got['nested']['list'][1] == 'price $100'
    assert got['embedded'] == 'prefix/abc/suffix'


def test_resolve_params_unresolvable_is_recorded_not_silently_dropped():
    """退步了会怎样：解析失败的引用静默保留原样（看起来"正常"，动作拿到字面量）——
    留痕里必须能看到 unparsable_refs。"""
    unparsable = []
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'output': {'a': 1}}
    got = ex._resolve_params({'v': 'id/$n.output.missing'}, unparsable)
    assert got['v'] == 'id/$n.output.missing'
    assert unparsable and unparsable[0]['ref'] == '$n.output.missing'

    # #8 修复后：整串形态解析失败也必须留痕（旧实现直接返回 None 无审计，
    # 与内嵌形态不一致）。
    whole_unparsable = []
    assert ex._resolve_params({'v': '$n.output.missing'}, whole_unparsable)['v'] is None
    assert whole_unparsable and whole_unparsable[0]['ref'] == '$n.output.missing'
    assert '整串引用' in whole_unparsable[0]['reason']


def test_walk_path_scalar_stops_at_none():
    """退步了会怎样：路径下钻对非 dict 抛异常（一个缺字段就炸整个工作流）。"""
    assert WorkflowExecutor._walk_path({'a': 1}, 'a.b.c') is None
    assert WorkflowExecutor._walk_path({'a': {'b': 2}}, 'a.b') == 2


# ═══════════════════════════════════════════════════════════════════════
# 并发上限 / 状态聚合 / 便捷入口
# ═══════════════════════════════════════════════════════════════════════

def test_declared_concurrency_caps_max_workers():
    """退步了会怎样：graph.max_concurrency 声明被忽略 → 动作写 2 却按 4 并发跑，
    破坏下游容量假设。语义取 min（调用方仍可下调）。"""
    ex = WorkflowExecutor(_workflow([{'id': 'a'}], graph={'max_concurrency': 2}),
                          meta_dir='', max_workers=4)
    assert ex.declared_concurrency == 2 and ex.max_workers == 2
    ex2 = WorkflowExecutor(_workflow([{'id': 'a'}], graph={'max_concurrency': 2}),
                           meta_dir='', max_workers=1)
    assert ex2.max_workers == 1


def test_compute_status_three_states():
    """退步了会怎样：mixed 状态被报成 ok/failed 二选一 → 上层无法区分部分成功。"""
    ex = WorkflowExecutor(_workflow([{'id': 'a'}]), meta_dir='')
    ex._node_status = {'a': 'ok', 'b': 'ok'}
    assert ex._compute_status() == 'ok'
    ex._node_status = {'a': 'failed', 'b': 'failed'}
    assert ex._compute_status() == 'failed'
    ex._node_status = {'a': 'ok', 'b': 'failed'}
    assert ex._compute_status() == 'partial'


def test_parallel_and_serial_entry_helpers(fake_exec, tmp_path):
    """退步了会怎样：parallel=false 仍并发执行（顺序/资源约束失效）；或并行层异常
    没被记成 failed（层直接崩）。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {}},
                         'x.two': {'status': 'ok', 'data': {}}}
    ex = _executor(None, tmp_path, [
        {'id': 'a', 'action_id': 'x.one'},
        {'id': 'b', 'action_id': 'x.two'}], graph={'parallel': False})
    sched = DAGScheduler(ex.workflow.nodes)
    ex._execute_serial(['a', 'b'], sched, 'abort')
    assert ex._node_status == {'a': 'ok', 'b': 'ok'}

    # 并行层：_execute_node 抛异常 → future.result 捕获并记 failed
    def boom(node_id):
        raise RuntimeError('boom')
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ex, '_execute_node', boom)
    try:
        ex._node_status.clear()
        ex._execute_parallel(['a'], sched, 'abort')
        assert ex._node_status['a'] == 'failed'
        assert any(r.get('error') == 'boom' for r in ex._records)
    finally:
        monkeypatch.undo()


def test_run_workflow_missing_action_raises(tmp_path):
    """退步了会怎样：run_workflow 对不存在的 id 静默返回空/None → 调用方以为成功。"""
    from vools.actus.workflow import run_workflow
    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'actions.index.json').write_text(
        json.dumps({'actions': {}}), encoding='utf-8')
    with pytest.raises(ActionError) as exc:
        run_workflow('no.such.workflow', str(meta))
    assert exc.value.code == 'workflow_not_found'
