# -*- coding: utf-8 -*-
"""`selfdrive_worker.py` 契约测试（第 33 轮：节点→动作映射器 + worker，18% → ≥50%）。

覆盖重点：
  1. 计划解析 `plan_from_json`（JSON 串/数组/非法项，错误文案带下标）；
  2. 三种分配策略：`leaf_assign`（叶子序/耗尽复用/空动作）、`static_assign`
     （goal 子串 + default）、`order_assign`（按序消费、耗尽复用）；
  3. `ActionWorker.worker`：无映射→结构化 `no_action_assigned`；执行器异常→
     `executor_error`；成功结果透传 + `action` 溯源；注入参数（confirmed/
     actions_dir/meta_dir/artifacts_dir/force）逐项传给执行器；
  4. `spec_resolver`：显式 spec_path / auto_spec 探测命中与未命中 / 关闭 auto_spec。

隔离：执行器全部用替身（**不真跑动作**）；不碰真实仓库/用户目录。
每条 docstring 写「退步了会怎样」。
"""
import json

import pytest

from vools.actus import selfdrive_worker as W


# ═══════════════════════════════════════════════════════════════════
# ① 计划解析
# ═══════════════════════════════════════════════════════════════════


def test_plan_from_json_parses_two_item_forms():
    """退步了会怎样：外部计划两种项形态（纯 id 字符串 / {action,params,spec_path}）
    之一失效 → CLI/MCP 的 `--plan` 入口静默少执行/参数丢失。
    """
    plan = json.dumps(["a.one", {"action": "b.two", "params": {"x": 1},
                                 "spec_path": "/s.json"}])
    actions = W.plan_from_json(plan)
    assert [a.action_id for a in actions] == ['a.one', 'b.two']
    assert actions[0].params == {} and actions[0].spec_path is None
    assert actions[1].params == {'x': 1} and actions[1].spec_path == '/s.json'
    # 直接传 list/tuple 也要支持
    assert [a.action_id for a in W.plan_from_json(('c.three',))] == ['c.three']


@pytest.mark.parametrize("bad,needle", [
    ('{not json', '不是合法 JSON'),
    ('{"a": 1}', '必须是数组'),
    ('["  "]', '动作 id 不能为空'),
    ('[{"params": {}}]', '缺少 action/action_id'),
    ('["a.ok", {"action": 123}]', '缺少 action/action_id'),
])
def test_plan_from_json_rejects_bad_input_with_index(bad, needle):
    """退步了会怎样：坏计划被"尽力解析"成部分结果 → 调度器少跑/错跑节点却报成功；
    契约是抛 ValueError 且错误文案带上出错下标（调用方转 param_invalid）。
    """
    with pytest.raises(ValueError) as exc:
        W.plan_from_json(bad)
    assert needle in str(exc.value), str(exc.value)


# ═══════════════════════════════════════════════════════════════════
# ② 分配策略
# ═══════════════════════════════════════════════════════════════════


def test_leaf_assign_maps_leaves_in_order_and_reuses_last():
    """退步了会怎样：叶子映射错位/耗尽后返回 None → 后半程节点全变
    `no_action_assigned`（工作器空转、任务假失败）。
    """
    nodes = [{'id': 'l1'}, {'id': 'l2'}, {'id': 'p', 'children': [{'id': 'c'}]}]
    assign = W.leaf_assign(nodes, [W.NodeAction('a.1'), W.NodeAction('a.2')])
    assert assign({'id': 'l1'}).action_id == 'a.1'
    assert assign({'id': 'l2'}).action_id == 'a.2'
    assert assign({'id': 'p'}) is None            # 非叶子
    assert assign({'id': 'nope'}) is None         # 未知节点

    one = W.leaf_assign(nodes, [W.NodeAction('only')])
    assert one({'id': 'l2'}).action_id == 'only'  # 耗尽后复用最后一个
    assert W.leaf_assign(nodes, [])({'id': 'l1'}) is None


def test_static_assign_matches_goal_substring_then_default():
    """退步了会怎样：goal 子串匹配失效（或 default 不生效）→ 节点被分到错误动作，
    或未命中节点直接失败。
    """
    assign = W.static_assign({'价格': W.NodeAction('a.price')},
                             default=W.NodeAction('a.default'))
    assert assign({'goal': '计算价格'}).action_id == 'a.price'
    assert assign({'goal': '无关目标'}).action_id == 'a.default'
    assert W.static_assign({})({'goal': 'x'}) is None


def test_order_assign_consumes_in_order_then_reuses_last():
    """退步了会怎样：按序消费错位（跳过/重复第一个）→ 计划的执行顺序与声明不一致
    （selfdrive 的"计划即顺序"契约被破坏）。
    """
    assign = W.order_assign([W.NodeAction('a.1'), W.NodeAction('a.2')])
    assert assign({}).action_id == 'a.1'
    assert assign({}).action_id == 'a.2'
    assert assign({}).action_id == 'a.2'          # 耗尽复用最后一个


# ═══════════════════════════════════════════════════════════════════
# ③ ActionWorker
# ═══════════════════════════════════════════════════════════════════


def test_worker_without_assignment_returns_structured_error():
    """退步了会怎样：没映射到动作时静默返回 ok/抛异常 → 调度器把"没干活"当完成。
    """
    worker = W.ActionWorker(assign=lambda node: None)
    result = worker.worker({'id': 'n1'})
    assert result['status'] == 'failed'
    assert result['error']['code'] == 'no_action_assigned'
    assert 'n1' in result['error']['message']


def test_worker_missing_action_key_is_no_action_assigned_not_executor_error():
    """退步了会怎样（S1）：assign 返回 `{'params': {...}}`（缺 action）时构造出
    `NodeAction(action_id=None)`，执行器抛 `AttributeError: 'NoneType' object has no
    attribute 'rsplit'`，被包成 **executor_error** —— 配置错报成引擎错，排查方向被带偏。
    """
    called = []

    def never_execute(*a, **k):
        called.append(1)
        raise AssertionError('缺 action 的映射不得进入执行器')

    worker = W.ActionWorker(assign=lambda node: {'params': {'x': 1}},
                            execute_fn=never_execute)
    result = worker.worker({'id': 'n-bad'})
    assert result['status'] == 'failed'
    assert result['error']['code'] == 'no_action_assigned', result
    assert called == []


def test_worker_non_dict_executor_result_is_failure_not_success():
    """退步了会怎样（S2）：执行器返回 None（什么都没做）时改前被包成
    `{'status': 'ok', 'value': None}` → **假成功**，调度器以为节点完成了。
    与 `exec_iface` 的同类修复保持一致：非结构化结果判失败。
    """
    for bad_result in (None, 'raw-string', 42, ['x']):
        worker = W.ActionWorker(assign=lambda n: 'a.b',
                                execute_fn=lambda *a, **k: bad_result)
        result = worker.worker({'id': 'n'})
        assert result['status'] != 'ok', (bad_result, result)
        assert result['error']['code'] == 'invalid_result'
        assert type(bad_result).__name__ in result['error']['message']


def test_worker_executor_exception_becomes_executor_error():
    """退步了会怎样：执行器异常穿透 worker → 整个 selfdrive 循环被打断，
    而不是记一个节点失败继续后面的节点。
    """
    def boom(*a, **k):
        raise RuntimeError('引擎炸了')

    worker = W.ActionWorker(assign=lambda node: 'a.b', execute_fn=boom)
    result = worker.worker({'id': 'n2'})
    assert result['status'] == 'failed'
    assert result['error']['code'] == 'executor_error'
    assert '引擎炸了' in result['error']['message']


def test_worker_passes_all_execution_knobs_to_executor():
    """退步了会怎样：confirmed/actions_dir/meta_dir/artifacts_dir/force 中有一项
    没透传 → 隔离目录失效（写进真实仓库）、或 audit 动作被绕过人类确认。
    """
    seen = {}

    def fake_execute(action_id, params, **kw):
        seen.update({'action_id': action_id, 'params': params, 'kw': kw})
        return {'status': 'ok', 'data': {'x': 1}}

    worker = W.ActionWorker(
        assign=lambda node: W.NodeAction('a.b', {'p': 1}),
        actions_dir='/adir', meta_dir='/mdir', artifacts_dir='/art',
        force=True, confirmed=True, execute_fn=fake_execute)
    result = worker.worker({'id': 'n3'})

    assert seen['action_id'] == 'a.b'
    assert seen['params'] == {'p': 1}
    assert seen['kw']['confirmed'] is True and seen['kw']['force'] is True
    assert seen['kw']['actions_dir'] == '/adir'
    assert seen['kw']['meta_dir'] == '/mdir'
    assert seen['kw']['artifacts_dir'] == '/art'
    assert result == {'status': 'ok', 'data': {'x': 1}, 'action': 'a.b'}


def test_worker_accepts_str_and_dict_assignments():
    """退步了会怎样：assign 返回 str（常见简化写法）/ dict 时不再被接受 →
    外部计划接不进来，或 dict 里的 params/spec_path 被丢掉。
    """
    by_str = W.ActionWorker(assign=lambda n: 'a.str',
                            execute_fn=lambda *a, **k: {'status': 'ok'})
    assert by_str.worker({'id': 'n'})['action'] == 'a.str'

    captured = {}
    by_dict = W.ActionWorker(
        assign=lambda n: {'action_id': 'a.dict', 'params': {'k': 2}, 'spec_path': '/s'},
        execute_fn=lambda aid, params, **kw: captured.update(
            {'aid': aid, 'params': params}) or {'status': 'ok'})
    by_dict.worker({'id': 'n'})
    assert captured == {'aid': 'a.dict', 'params': {'k': 2}}
    assert by_dict.spec_resolver({'id': 'n'}) == '/s'


def test_from_plan_binds_plan_in_order():
    """退步了会怎样：`from_plan` 不再按计划顺序绑定 → CLI/MCP 的 plan 入口执行顺序
    与用户给定顺序不一致。
    """
    worker = W.ActionWorker.from_plan(
        '["a.1", "a.2"]', execute_fn=lambda *a, **k: {'status': 'ok'})
    assert worker.worker({'id': 'x'})['action'] == 'a.1'
    assert worker.worker({'id': 'y'})['action'] == 'a.2'


def test_execute_fn_uses_injected_then_real_executor():
    """退步了会怎样：注入的替身被忽略（测试/隔离失效）或惰性导入路径坏掉
    （生产路径取不到 actuscore.execute）。
    """
    injected = lambda *a, **k: {'status': 'ok'}
    assert W.ActionWorker(assign=lambda n: 'a', execute_fn=injected)._execute_fn() is injected

    real = W.ActionWorker(assign=lambda n: 'a')._execute_fn()
    assert callable(real)


# ═══════════════════════════════════════════════════════════════════
# ④ spec_resolver
# ═══════════════════════════════════════════════════════════════════


def test_spec_resolver_explicit_and_auto(monkeypatch):
    """退步了会怎样：显式 spec_path 被自动探测覆盖 / auto_spec 命中不生效 →
    Omega 门禁用错语料（或该有语料却找不到→动作永远 blocked）。
    """
    explicit = W.ActionWorker(assign=lambda n: W.NodeAction('a.b', spec_path='/s.json'))
    assert explicit.spec_resolver({'id': 'n'}) == '/s.json'

    monkeypatch.setattr(W._omega, '_find_omega_spec',
                        lambda aid, adir: '/found/%s.spec.json' % aid)
    auto = W.ActionWorker(assign=lambda n: 'a.b', auto_spec=True)
    assert auto.spec_resolver({'id': 'n'}) == '/found/a.b.spec.json'

    off = W.ActionWorker(assign=lambda n: 'a.b', auto_spec=False)
    assert off.spec_resolver({'id': 'n'}) is None

    none_assigned = W.ActionWorker(assign=lambda n: None)
    assert none_assigned.spec_resolver({'id': 'n'}) is None


def test_spec_resolver_swallows_lookup_errors_as_none_but_logs(monkeypatch, caplog):
    """退步了会怎样（S3）：语料查找器抛异常时把异常放出去 → 单个节点让整个
    selfdrive 循环崩掉；但**完全静默**（改前）又让"为什么没找到 spec"无从排查。
    契约：返回 None（门禁判 blocked）+ 至少一条 warning。
    """
    def boom(aid, adir):
        raise RuntimeError('查找器坏了')

    monkeypatch.setattr(W._omega, '_find_omega_spec', boom)
    worker = W.ActionWorker(assign=lambda n: 'a.b', auto_spec=True)
    with caplog.at_level('WARNING', logger='vools.actus.selfdrive_worker'):
        assert worker.spec_resolver({'id': 'n'}) is None
    assert any('spec 解析失败' in r.getMessage() for r in caplog.records),         [r.getMessage() for r in caplog.records]
