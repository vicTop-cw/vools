# -*- coding: utf-8 -*-
"""workflow.py 契约测试补充（第 39 轮，round 99 任务 T0r5）。

目标：把 r32 未覆盖的真实分支钉住 —— 并行入口、serial 异常中止、超时成功、
fallback 异常吞、引用解析边界（裸根/整串未知根/异常通道）、status 快捷算子、
run_workflow 全链路（相对/绝对/旧绝对/重建/缺失/校验失败）。
全部隔离 tmp_path；动作执行用 monkeypatch 假 execute；产品代码零修改。

每条 docstring 写「退步了会怎样」。
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import workflow as wf_mod  # noqa: E402
from vools.actus import model as actus_model  # noqa: E402
from vools.actus import indexer as actus_indexer  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.workflow import (DAGScheduler, Workflow,  # noqa: E402
                                  WorkflowExecutor, run_workflow)


# ── helpers（对齐 r32 风格）────────────────────────────────────────────

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
def fake_exec(monkeypatch):
    fake = _FakeExecute()
    monkeypatch.setattr(wf_mod._execute, 'execute', fake)
    return fake


def _executor(tmp_path, nodes, graph=None):
    return WorkflowExecutor(_workflow(nodes, graph), str(tmp_path), max_workers=4)


# ═══════════════════════════════════════════════════════════════════════
# 并行入口 / serial 异常 / 超时成功 / fallback 异常
# ═══════════════════════════════════════════════════════════════════════

def test_run_default_graph_uses_parallel_path(fake_exec, tmp_path):
    """退步了会怎样：graph 缺省（parallel 默认 True）时并行分支没实现/绕开 →
    默认配置的工作流要么不执行要么只走串行（并发语义静默降级）。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {'v': 1}}}
    ex = _executor(tmp_path, [{'id': 'a', 'action_id': 'x.one'}])
    result = ex.run()
    assert result['status'] == 'ok'
    assert result['node_status'] == {'a': 'ok'}


def test_execute_serial_exception_breaks_layer_under_abort(fake_exec,
                                                          monkeypatch,
                                                          tmp_path):
    """退步了会怎样：serial 层节点执行抛异常被静默吞/继续跑后续节点 →
    一次内部崩溃产生一串脏状态。断言：记 failed + abort 语义下停止后续节点。"""
    fake_exec.results = {'x.one': {'status': 'ok', 'data': {}}}
    ex = _executor(tmp_path, [{'id': 'a', 'action_id': 'x.one'},
                              {'id': 'b', 'action_id': 'x.two',
                               'depends': ['a']}],
                   graph={'parallel': False})
    executed = {'n': 0}

    def boom(node_id):
        executed['n'] += 1
        raise RuntimeError('node exploded')

    monkeypatch.setattr(ex, '_execute_node', boom)
    sched = DAGScheduler(ex.workflow.nodes)
    ex._execute_serial(['a', 'b'], sched, 'abort')
    assert executed['n'] == 1          # abort：第二个节点不再执行
    assert ex._node_status.get('a') == 'failed'
    assert 'b' not in ex._node_status
    assert any(r.get('error') == 'node exploded' for r in ex._records)


def test_execute_node_records_unparsable_refs_in_records(fake_exec, tmp_path):
    """退步了会怎样：节点执行路径的引用解析失败不留痕（只有直接调
    _resolve_params 才看得到）→ 生产上"参数悄悄变字面量"无审计。"""
    ex = _executor(tmp_path, [{'id': 'a', 'action_id': 'x.one',
                               'params': {'v': '$ghost.output.x'}}],
                   graph={'parallel': False})
    ex.run()
    rec = [r for r in ex._records if r.get('unparsable_refs')]
    assert rec and rec[0]['node_id'] == 'a'
    assert rec[0]['unparsable_refs'][0]['ref'] == '$ghost.output.x'


def test_timeout_success_returns_result_and_cleans_thread(fake_exec, tmp_path):
    """退步了会怎样：timeout_s 的成功路径没接 result_holder → 秒回动作被误判
    超时（或结果丢失）。断言：正常拿结果、无 timeout 记录。"""
    fake_exec.results = {'x.fast': {'status': 'ok', 'data': {'v': 42}}}
    ex = _executor(tmp_path, [{'id': 'a', 'action_id': 'x.fast',
                               'timeout_s': 5}],
                   graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'ok'
    assert result['outputs']['a'] == {'v': 42}
    assert not [r for r in result['records'] if r.get('status') == 'timeout']


def test_fallback_execute_exception_is_swallowed_and_node_fails(fake_exec,
                                                                tmp_path):
    """退步了会怎样：fallback 动作本身抛异常穿透执行器 → 整个工作流崩掉
    （而不是节点记 failed 走失败策略）。断言：异常被吞、节点 failed。"""
    fake_exec.results = {
        'x.primary': {'status': 'failed', 'error': {'message': 'p'}},
    }

    def backup_boom(n, params):
        raise RuntimeError('fallback blew up')

    fake_exec.results['x.backup'] = backup_boom
    ex = _executor(tmp_path, [{'id': 'a', 'action_id': 'x.primary',
                               'fallback': 'x.backup'}],
                   graph={'parallel': False})
    result = ex.run()
    assert result['status'] == 'failed'
    assert result['node_status']['a'] == 'failed'
    # fallback 确实被尝试过，但异常被吞成普通 failed，不记 fallback-ok 假账
    assert [c['action_id'] for c in fake_exec.calls] == ['x.primary', 'x.backup']
    assert not any(r.get('fallback') for r in result['records'])


# ═══════════════════════════════════════════════════════════════════════
# 引用解析边界
# ═══════════════════════════════════════════════════════════════════════

def test_resolve_value_passthrough_non_container():
    """退步了会怎样：int/None 等非容器参数被当成引用处理/被吃掉 → 数字参数丢失。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    assert ex._resolve_value(5, 'x', []) == 5
    assert ex._resolve_value(None, 'x', []) is None
    assert ex._resolve_value(True, 'x', []) is True


def test_is_known_ref_without_workflow_attr_returns_true():
    """退步了会怎样：反序列化/旁路构造的执行器缺 workflow 属性时 _is_known_ref
    抛 AttributeError → 节点执行直接崩。断言：空壳实例按"已知"放行。"""
    ex = WorkflowExecutor.__new__(WorkflowExecutor)   # 不跑 __init__ 的空壳
    assert ex._is_known_ref('$anything.output.x') is True


def test_resolve_string_keeps_dollar_digit_literal():
    """退步了会怎样："$100" 被当引用解析 → 价格文本被吃掉变 None。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    unparsable = []
    assert ex._resolve_string('$100', 'x', unparsable) == '$100'
    assert unparsable == []


def test_resolve_string_unknown_root_whole_string_noted_and_kept():
    """退步了会怎样：整串引用的根不是本工作流节点时静默返回 None（旧实现）
    → 动作拿到 None 还不知道为什么。断言：原样返回 + 留痕 reason 点名未知根。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    unparsable = []
    got = ex._resolve_string('$ghost.output.x', 'x', unparsable)
    assert got == '$ghost.output.x'
    assert unparsable and unparsable[0]['ref'] == '$ghost.output.x'
    assert '未知' in unparsable[0]['reason'] or '节点' in unparsable[0]['reason']


def test_resolve_string_plain_text_without_dollar_is_untouched():
    """退步了会怎样：普通文本被引用解析改写（re 误匹配）→ 动作收到脏参数。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    assert ex._resolve_string('plain text no refs', 'x', []) == 'plain text no refs'


def test_resolve_string_embedded_unknown_ref_token_kept():
    """退步了会怎样：内嵌引用的 token 解析失败被替换成空串 → 文本被静默截断。
    断言：未知 token 原样保留在结果里。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    unparsable = []
    got = ex._resolve_string('x $ghost.a y', 'x', unparsable)
    assert got == 'x $ghost.a y'
    assert unparsable == []          # 未知根的内嵌 token 保留但**不留痕**是可辩护
    # 与整串形态区分：这里只断言不抛、不丢 token


def test_dereference_records_reason_when_resolve_ref_raises():
    """退步了会怎样：_resolve_ref 内部异常穿透 _dereference → 节点执行崩掉。
    断言：异常被记入 unparsable 留痕并返回原串。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'a': 1}

    def raise_value_error(ref):
        raise ValueError('bad walk')

    object.__setattr__(ex, '_resolve_ref', raise_value_error)
    unparsable = []
    got = ex._dereference('$n.a', 'w.n', unparsable)
    assert got == '$n.a'
    assert unparsable and unparsable[0]['ref'] == '$n.a'
    assert 'ValueError' in unparsable[0]['reason']


def test_resolve_ref_unmatched_shape_returns_ref_verbatim():
    """退步了会怎样：无 '.' 的引用形态被路径下钻炸掉（KeyError）→ 非标准引用
    直接崩工作流。断言：原样返回。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    assert ex._resolve_ref('$n') == '$n'


def test_resolve_ref_bare_output_returns_whole_data():
    """退步了会怎样：$node.output 的"整包"形态没实现 → 只能引用具体字段，
    动作想把上游完整输出传下去做不到。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    data = {'output': {'a': 1, 'b': 2}}
    ex._node_outputs['n'] = data
    assert ex._resolve_ref('$n.output') is data


def test_note_condition_unparsable_swallows_record_append_failure():
    """退步了会怎样：留痕通道自身异常（records 不可写）穿透 _eval_condition
    → 条件评估反而崩工作流。断言：异常被吞、条件评估继续返回 False。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')

    class BadRecords(list):
        def append(self, x):
            raise RuntimeError('disk full')

    ex._records = BadRecords()
    assert ex._eval_condition('not a condition at all') is False


# ═══════════════════════════════════════════════════════════════════════
# 条件：status 快捷算子 / 非数值比较
# ═══════════════════════════════════════════════════════════════════════

def test_eval_condition_status_shortcut_ok_and_failed():
    """退步了会怎样：status 字段快捷比较看的是 output 而不是节点状态表 →
    `$n.status == "ok"` 恒 False（skipped 分支全乱）。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_status['n'] = 'ok'
    assert ex._eval_condition('$n.status == "ok"') is True
    ex._node_status['n'] = 'failed'
    assert ex._eval_condition('$n.status == "ok"') is False
    assert ex._eval_condition('$n.status == "failed"') is True


def test_eval_condition_numeric_compare_non_numeric_is_false():
    """退步了会怎样：非数值参与数值比较抛 ValueError 穿透 → 工作流崩。
    断言：返回 False（安全缺省）。"""
    ex = WorkflowExecutor(_workflow([{'id': 'n'}]), meta_dir='')
    ex._node_outputs['n'] = {'value': 'abc'}
    assert ex._eval_condition('$n.value >= 3') is False
    ex._node_outputs['n'] = {'value': None}
    assert ex._eval_condition('$n.value > 0') is False


# ═══════════════════════════════════════════════════════════════════════
# run_workflow 全链路
# ═══════════════════════════════════════════════════════════════════════

WORLD = {'wf.x': {'path': 'actions/wf.x.actus.md'}}


def _fake_parse_ok(path):
    return SimpleNamespace(meta={'id': 'wf.x',
                                 'workflow': {'nodes': [
                                     {'id': 'a', 'action': 'x.one'}]}})


def _fake_parse_ghost_dep(path):
    return SimpleNamespace(meta={'id': 'wf.x',
                                 'workflow': {'nodes': [
                                     {'id': 'a', 'depends': ['ghost']}]}})


@pytest.fixture
def wf_world(tmp_path, monkeypatch):
    """搭建 run_workflow 的三个外部依赖：load_index / parse / repo_root。"""
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
    monkeypatch.setattr(actus_indexer, 'load_index',
                        lambda meta_dir: {'actions': dict(WORLD)})
    monkeypatch.setattr(actus_model, 'parse_cfg_from_file', _fake_parse_ok)
    actions_dir = tmp_path / 'actions'
    actions_dir.mkdir(exist_ok=True)
    src = actions_dir / 'wf.x.actus.md'
    src.write_text('# workflow fixture\n', encoding='utf-8')
    return src


def test_run_workflow_relative_path_hit(wf_world, fake_exec, tmp_path):
    """退步了会怎样：相对路径没按 repo_root 重锚 → 换目录/换根后工作流全部
    workflow_source_missing。断言：相对条目命中并执行。"""
    result = run_workflow('wf.x', str(tmp_path / 'meta'))
    assert result['status'] == 'ok'
    assert fake_exec.calls[0]['action_id'] == 'x.one'


def test_run_workflow_absolute_path_hit(wf_world, fake_exec, tmp_path,
                                        monkeypatch):
    """退步了会怎样：索引条目为绝对路径时被当相对拼进 repo_root → 必然
    miss。断言：绝对路径直接命中。"""
    monkeypatch.setattr(actus_indexer, 'load_index',
                        lambda meta_dir: {'actions': {
                            'wf.x': {'path': str(wf_world)}}})
    result = run_workflow('wf.x', str(tmp_path / 'meta'))
    assert result['status'] == 'ok'


def test_run_workflow_stale_absolute_refixes_via_actions_tail(wf_world,
                                                              fake_exec,
                                                              tmp_path,
                                                              monkeypatch):
    """退步了会怎样：克隆/搬家后索引里的旧绝对路径（含 /actions/ 尾巴）没被
    重锚 → 全部 workflow_source_missing。断言：旧路径按当前根重锚后命中。"""
    monkeypatch.setattr(actus_indexer, 'load_index',
                        lambda meta_dir: {'actions': {
                            'wf.x': {'path': 'E:/old/repo/actions/wf.x.actus.md'}}})
    result = run_workflow('wf.x', str(tmp_path / 'meta'))
    assert result['status'] == 'ok'


def test_run_workflow_rebuilds_via_scan_actions_when_index_stale(wf_world,
                                                                 fake_exec,
                                                                 tmp_path,
                                                                 monkeypatch):
    """退步了会怎样：索引路径失效且不现扫重建 → 必须手动重建索引才能跑工作流。
    断言：scan_actions 返回的真实路径被采用。"""

    class _Fresh(object):
        path = str(wf_world)

    monkeypatch.setattr(actus_indexer, 'load_index',
                        lambda meta_dir: {'actions': {
                            'wf.x': {'path': 'gone/nowhere.md'}}})
    monkeypatch.setattr(actus_indexer, 'scan_actions',
                        lambda root, validate=False, use_cache=False:
                            {'wf.x': _Fresh()})
    result = run_workflow('wf.x', str(tmp_path / 'meta'))
    assert result['status'] == 'ok'


def test_run_workflow_scan_actions_failure_is_source_missing(tmp_path,
                                                             monkeypatch):
    """退步了会怎样：scan_actions 异常穿透 run_workflow → 调用方拿到裸
    超市错误而不是可读的 workflow_source_missing。"""
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
    monkeypatch.setattr(actus_indexer, 'load_index',
                        lambda meta_dir: {'actions': {
                            'wf.x': {'path': 'gone/nowhere.md'}}})

    def boom(*a, **k):
        raise RuntimeError('scan exploded')

    monkeypatch.setattr(actus_indexer, 'scan_actions', boom)
    with pytest.raises(ActionError) as exc:
        run_workflow('wf.x', str(tmp_path / 'meta'))
    assert exc.value.code == 'workflow_source_missing'


def test_run_workflow_invalid_definition_rejected(wf_world, tmp_path,
                                                  monkeypatch):
    """退步了会怎样：校验失败的工作流被放行执行 → 一半节点跑了才崩。
    断言：workflow_invalid 在执行前抛出。"""
    monkeypatch.setattr(actus_model, 'parse_cfg_from_file', _fake_parse_ghost_dep)
    with pytest.raises(ActionError) as exc:
        run_workflow('wf.x', str(tmp_path / 'meta'))
    assert exc.value.code == 'workflow_invalid'
    assert 'ghost' in str(exc.value)


def test_run_workflow_passes_meta_dir_and_confirmed(wf_world, tmp_path,
                                                    monkeypatch):
    """退步了会怎样：run_workflow 丢了 confirmed/meta_dir → 工作流以
    confirmed=True 偷跑危险动作。断言：参数完整透传。"""
    captured = {}
    fake = _FakeExecute()
    orig_call = fake.__call__

    def spy(action_id, params=None, confirmed=True, meta_dir=None):
        captured['confirmed'] = confirmed
        captured['meta_dir'] = meta_dir
        return orig_call(action_id, params, confirmed, meta_dir)

    monkeypatch.setattr(wf_mod._execute, 'execute', spy)
    meta = str(tmp_path / 'meta')
    result = run_workflow('wf.x', meta, confirmed=False)
    assert result['status'] == 'ok'
    assert captured['confirmed'] is False
    assert captured['meta_dir'] == meta
