# -*- coding: utf-8 -*-
"""ai/planner.py（任务拆解）契约测试 r95：单模块覆盖 ≥90%。

被测对象：``vools/actus/ai/planner.py`` —— LlmPlanner（LLM 拆解）、
PlanStep/Plan 数据类、Planner 协议、plan_from_intent 便捷入口。

退步会怎样（每条契约破坏时对应红灯）：
  * LlmPlanner.decompose 对空 goal 不返回 error='goal_empty' 的 Plan 而
    抛异常/返回空串 → selfdrive.Decomposer 插槽拿到炸调用；
  * client 不可用不编码进 Plan.error 而抛 → provider 抖动炸整条决策链
    （base.py 设计约定 1：失败编码进返回值，不抛异常）；
  * resp.failed / resp=None 分支漂移 → 调用方拿不到失败原因就照空计划执行；
  * 模型输出带 ```json 代码围栏 / 前后噪声时解析不出 → 换一个 provider
    （回复带围栏）拆解全挂；
  * 未知 target_action 被整步丢弃而非清空保留 → 模型编造一个动作 id
    就丢掉有效步骤（planner._parse_steps 的"清空不丢弃"契约）；
  * title 缺失的 step 未被过滤 / 无 id 未补 stepN → 下游 Ω 门拿到无标题步骤；
  * arguments 非 dict 未归一为 {} → PlanStep 构造炸（dataclass frozen）；
  * limit 截断漂移 → 步数上限被无视，模型给 20 步就执行 20 步；
  * plan_from_intent 空 goal 不先校验（被 'provider 不可用' 掩盖）→
    调用方错以为是自己密钥坏了。

隔离：client 全部 Fake（本地内存，零网络）；catalog 用 ToolCatalog 直构
（build_catalog 不依赖真 _meta 索引）。零产品代码改动。
"""

import json

import _ai_local_bootstrap  # noqa: F401  (必须在 import vools.actus 之前)

import pytest

from vools.actus.ai.base import LLMClient, LLMResponse, Message
from vools.actus.ai.catalog import CatalogEntry, ToolCatalog
from vools.actus.ai import planner as P
import sys as _sys
print('COLLECT-ID same:', P is _sys.modules.get('vools.actus.ai.planner'), 'idP=', id(P))


@pytest.fixture(autouse=True)
def _zap(request):
    m = _sys.modules.get('vools.actus.ai.planner')
    print('ZAP', request.node.name, 'same:', P is m,
          'Pfile=', getattr(P, '__file__', None),
          'mfile=', getattr(m, '__file__', None),
          'morigin=', getattr(getattr(m, '__spec__', None), 'origin', None))
    yield



# ---------------------------------------------------------------- fakes

class _FakeClient(LLMClient):
    """可编程假 provider：返回预置 LLMResponse，记录收到的消息。"""

    name = 'fake'

    def __init__(self, resp=None, avail=True):
        self._resp = resp
        self._avail = avail
        self.calls = []

    def available(self):
        return self._avail

    def complete(self, messages, tools=None, temperature=0.0,
                 max_tokens=None, stream=False):
        self.calls.append(list(messages))
        return self._resp


def _resp(content, stop_reason='stop'):
    return LLMResponse(content=content, stop_reason=stop_reason)


def _catalog(*action_ids):
    return ToolCatalog([CatalogEntry(
        tool_name='t_%d' % i, action_id=aid, description='')
        for i, aid in enumerate(action_ids)])


STEPS_JSON = json.dumps({'steps': [
    {'id': 's1', 'title': '第一步', 'target_action': 'cli.echo',
     'arguments': {'q': 'hi'}, 'verify': '输出有 hi'},
    {'id': 's2', 'title': '第二步', 'target_action': 'ghost.action',
     'verify': '跑完'},
]})


# ---------------------------------------------------------------- 数据类/协议

def test_plan_and_planstep_defaults():
    # 默认值契约：goal/steps/source='llm'/error 空串
    plan = P.Plan()
    assert plan.goal == '' and plan.steps == () and plan.error == ''
    assert plan.source == 'llm'
    step = P.PlanStep(id='a')
    assert step.title == '' and step.target_action == ''
    assert step.arguments == {} and step.verify == ''
    # frozen：破坏不可变性会立刻红
    with pytest.raises(Exception):
        plan.source = 'template'


def test_planner_protocol_raises():
    # 协议方法必须 NotImplementedError（漂移 = 静默返回 None）
    with pytest.raises(NotImplementedError):
        P.Planner().decompose('goal')


def test_module_surface():
    assert set(P.__all__) == {'Planner', 'LlmPlanner', 'Plan', 'PlanStep',
                              'plan_from_intent'}


# ---------------------------------------------------------------- decompose 入口分支

def test_decompose_empty_goal():
    p = P.LlmPlanner(_FakeClient())
    plan = p.decompose('   ')
    assert plan.error == 'goal_empty'
    assert plan.steps == () and plan.goal == ''
    assert plan.source == 'llm'


def test_decompose_client_none_or_unavailable():
    plan = P.LlmPlanner(None).decompose('build')
    assert plan.error and plan.steps == () and plan.goal == 'build'
    assert '不可用' in plan.error
    plan = P.LlmPlanner(_FakeClient(avail=False)).decompose('build')
    assert plan.error and '不可用' in plan.error


def test_decompose_resp_none_and_failed():
    # resp=None：契约要求 error 提到模型调用失败
    plan = P.LlmPlanner(_FakeClient(resp=None)).decompose('build')
    assert plan.steps == () and '模型调用失败' in plan.error
    # resp.failed（stop_reason='error'）：error 带错误码与 detail
    bad = LLMResponse(content='boom', stop_reason='error',
                      raw={'code': 'dependency_missing'})
    plan = P.LlmPlanner(_FakeClient(resp=bad)).decompose('build')
    assert plan.steps == () and '模型调用失败' in plan.error
    assert 'dependency_missing' in plan.error and 'boom' in plan.error
    # raw 无 code → 走 llm_error_code('bad_response') 归一为 'internal'
    bad2 = LLMResponse(content='', stop_reason='error')
    plan = P.LlmPlanner(_FakeClient(resp=bad2)).decompose('build')
    assert 'internal' in plan.error


def test_decompose_unparsable_returns_error_not_guess():
    # "不做猜一个计划的兜底" 契约：解析不出步骤 → error 非空
    p = P.LlmPlanner(_FakeClient(resp=_resp('我认为该分三步')), _catalog())
    plan = p.decompose('build')
    assert plan.error == '模型未给出可解析的步骤' and plan.steps == ()


def test_decompose_success_end_to_end():
    cat = _catalog('cli.echo')
    client = _FakeClient(resp=_resp(STEPS_JSON))
    p = P.LlmPlanner(client, cat)
    plan = p.decompose('发一句话', max_steps=5)
    assert plan.error == '' and plan.source == 'llm'
    assert len(plan.steps) == 2
    s1, s2 = plan.steps
    assert s1.target_action == 'cli.echo' and s1.arguments == {'q': 'hi'}
    assert s2.target_action == ''          # 未知动作清空，步骤保留
    # prompt 契约：system 提示词 + user 目标/步数上限/动作清单
    assert len(client.calls) == 1
    roles = [m.role for m in client.calls[0]]
    assert roles == ['system', 'user']
    assert '任务拆解器' in client.calls[0][0].content
    assert '发一句话' in client.calls[0][1].content
    assert '步数上限：5' in client.calls[0][1].content
    assert 'cli.echo' in client.calls[0][1].content


def test_decompose_empty_catalog_placeholder_in_prompt():
    # 动作清单为空 → prompt 用占位文案，不炸
    client = _FakeClient(resp=_resp(json.dumps({'steps': [
        {'id': 'a', 'title': 't'}]})))
    plan = P.LlmPlanner(client, ToolCatalog(())).decompose('g')
    assert plan.error == '' and plan.steps[0].id == 'a'
    assert '（动作清单为空）' in client.calls[0][1].content


def test_decompose_lazy_catalog_build(monkeypatch):
    # catalog=None → 惰性 build_catalog()；字符串寻址 patch（bootstrap 规则 3）
    sentinel = _catalog('cli.lazy')
    calls = []

    def fake_build(meta_dir=None, include_deprecated=False):
        calls.append(meta_dir)
        return sentinel

    monkeypatch.setattr(P, 'build_catalog', fake_build)  # 对象寻址：identity-proof（sys.modules 在跨文件收集期被换成 namespace stub，字符串寻址会打空）
    client = _FakeClient(resp=_resp(json.dumps({'steps': [
        {'id': 'x', 'title': 't', 'target_action': 'cli.lazy'}]})))
    plan = P.LlmPlanner(client, catalog=None).decompose('g')
    assert plan.error == '' and calls == [None]
    assert plan.steps[0].target_action == 'cli.lazy'
    # 同一实例内缓存：第二次 decompose 不再重建
    p2 = P.LlmPlanner(client, catalog=None)
    assert p2.decompose('g').error == ''     # 记账：p2 首次重建 → calls==2
    assert len(calls) == 2
    assert p2.decompose('g').error == ''     # p2 复用缓存 → 仍为 2
    assert len(calls) == 2


# ---------------------------------------------------------------- _parse_steps 契约

def test_parse_steps_strips_code_fences_and_noise():
    text = '好的，以下是计划：\n```json\n' + STEPS_JSON + '\n```\n以上。'
    steps = P.LlmPlanner._parse_steps(text, {'cli.echo'}, 8)
    assert len(steps) == 2 and steps[0].id == 's1'
    # 无 json 标记的裸围栏
    steps = P.LlmPlanner._parse_steps('```\n' + STEPS_JSON + '\n```',
                                       {'cli.echo'}, 8)
    assert len(steps) == 2
    # 围栏里没有闭合（parts<=1）→ 取 raw[3:] 兜底
    steps = P.LlmPlanner._parse_steps('```' + STEPS_JSON, {'cli.echo'}, 8)
    assert len(steps) == 2
    # 未闭合围栏且无 JSON 主体：raw[3:] 后 find('{')<0 → 空列表
    assert P.LlmPlanner._parse_steps('```no json here', set(), 8) == []
    # 未闭合 ```json 前缀：parts<=1 走 raw[3:]，json 标记剥除后可解析
    steps = P.LlmPlanner._parse_steps(
        '```json {"steps": [{"id": "a", "title": "t"}]}', set(), 8)
    assert [s.id for s in steps] == ['a']


def test_parse_steps_rejects_garbage_shapes():
    # 退步护栏：坏输入必须返回空列表而不是抛
    for bad in ('', '   ', 'no braces', '{{ not json',
                '[1,2,3]', '"scalar"', '{"steps": "not-a-list"}',
                '{"other": []}'):
        assert P.LlmPlanner._parse_steps(bad, set(), 8) == [], bad
    # 只有前括号没有后括号
    assert P.LlmPlanner._parse_steps('{"steps": []', set(), 8) == []
    # 括号配对但内容非法 JSON：json.loads 抛 ValueError → 空列表不炸
    assert P.LlmPlanner._parse_steps('{"steps": [}', set(), 8) == []
    # 未闭合的围栏里是不完整 JSON：走 find/rfind 兜底后仍解析失败
    assert P.LlmPlanner._parse_steps('```{{{{{', set(), 8) == []


def test_parse_steps_filters_and_normalizes():
    text = json.dumps({'steps': [
        {'title': '无 id', 'target_action': 'cli.a'},          # 补 stepN
        {'id': 'b'},                                            # 无 title → 丢弃
        'not-a-dict',                                           # 非 dict → 丢弃
        {'id': 'c', 'title': 't', 'arguments': 'bad'},          # args 归一 {}
        {'id': 'd', 'title': 'u', 'target_action': 'cli.a',
         'verify': 'ok'},
    ]})
    steps = P.LlmPlanner._parse_steps(text, {'cli.a'}, 8)
    assert [s.id for s in steps] == ['step1', 'c', 'd']
    assert steps[0].target_action == 'cli.a'
    assert steps[1].arguments == {}
    assert steps[2].verify == 'ok'
    # 未知动作 id：清空 target_action 但保留步骤（"清空不丢弃"契约）
    steps = P.LlmPlanner._parse_steps(text, {'other'}, 8)
    assert [s.target_action for s in steps if s.id == 'd'] == ['']
    # known 为空集 → 不做未知过滤（全放行）
    steps = P.LlmPlanner._parse_steps(text, (), 8)
    assert [s.id for s in steps] == ['step1', 'c', 'd']


def test_parse_steps_limit_truncates():
    items = [{'id': str(i), 'title': 't%d' % i} for i in range(10)]
    steps = P.LlmPlanner._parse_steps(json.dumps({'steps': items}), set(), 3)
    assert len(steps) == 3 and steps[-1].id == '2'


# ---------------------------------------------------------------- plan_from_intent

def test_plan_from_intent_empty_goal_first():
    # 空 goal 先校验，不被 provider 错误掩盖（错误归因契约）
    plan = P.plan_from_intent('  ')
    assert plan.error == 'goal_empty'


def test_plan_from_intent_no_client_tries_openai(monkeypatch):
    # client=None → 走 registry.get_provider('openai')；这里让它失败，
    # 验证 error 里带 '无可用 provider' 而不是炸
    def boom(name):
        raise RuntimeError('no key')

    monkeypatch.setattr('vools.actus.ai.registry.get_provider', boom)
    plan = P.plan_from_intent('build a thing')
    assert '无可用 provider' in plan.error and plan.steps == ()
    assert plan.goal == 'build a thing'


def test_plan_from_intent_with_client_passthrough():
    client = _FakeClient(resp=_resp(json.dumps({'steps': [
        {'id': 'a', 'title': 't'}]})))
    plan = P.plan_from_intent('g', client=client, max_steps=3)
    assert plan.error == '' and plan.steps[0].id == 'a'
    assert '步数上限：3' in client.calls[0][1].content


def test_doctest_example_shape():
    # docstring 中的契约示例：空目录 + 返回 '{}' 的 Fake → steps 为空 tuple
    class _Fake(LLMClient):
        name = 'fake'

        def complete(self, messages, tools=None, temperature=0.0,
                     max_tokens=None, stream=False):
            return LLMResponse(content='{}')

        def available(self):
            return True

    plan = P.LlmPlanner(_Fake()).decompose('x')
    assert plan.steps == ()
