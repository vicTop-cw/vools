"""意图选择与任务拆解的判据。

**三个安全判据是本组重点**（它们是「不许为了聪明而放松」的那部分）：

  1. test_select_rejects_hallucinated_action_id
     模型编造不存在的动作 id 时，必须降级为候选，**不得**当成有效选择返回
  2. test_selector_sends_bounded_candidates
     送给 LLM 的工具数必须 <= max_candidates，即使目录有 100+ 条
  3. test_low_confidence_requires_confirm
     置信度低于阈值时 needs_confirm=True 且候选非空，**不许瞎猜一个动作**

另有一条参数校验判据：模型多给的未知参数要被丢弃、漏给的必填要报出来。
"""

import json

import pytest

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.base import LLMClient, LLMResponse, Message, ToolCall
from vools.actus.ai.catalog import ToolCatalog, CatalogEntry
from vools.actus.ai.selector import Selector, Selection, validate_params
from vools.actus.ai.planner import LlmPlanner, Planner, plan_from_intent

_META = _boot.actus_meta_dir()
needs_index = pytest.mark.skipif(not _META, reason='找不到 Actus 仓库的 _meta 目录')


class FakeClient(LLMClient):
    """返回预设响应的假 client。不联网。"""

    name = 'fake'

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self._available = True

    def complete(self, messages, tools=None, temperature=0.0, max_tokens=None,
                 stream=False):
        self.calls.append({'messages': list(messages), 'tools': tools,
                           'temperature': temperature})
        if not self.responses:
            return LLMResponse(content='{}')
        item = self.responses.pop(0)
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(content=item)

    def available(self):
        return self._available


def _entry(action_id, description='', props=None, required=(), trust='trusted',
           tags=()):
    return CatalogEntry(
        tool_name=action_id.replace('.', '_'), action_id=action_id,
        description=description,
        parameters={'type': 'object', 'properties': props or {},
                    'required': list(required)},
        trust=trust, tags=tuple(tags))


JQ_SCHEMA = {'input': {'type': 'string', 'description': 'json 文本'},
             'filter': {'type': 'string', 'description': 'jq 表达式'}}


# ── 参数校验 ──

def test_validate_params_drops_unknown_and_reports_missing():
    """未知参数丢弃、必填缺失报出来、默认值补上。"""
    sc = {'type': 'object', 'required': ['a'],
          'properties': {'a': {'type': 'string'},
                         'b': {'type': 'integer', 'default': 7}}}
    cleaned, missing, errs = validate_params(sc, {'a': 'x', 'zzz': 1})
    assert cleaned == {'a': 'x', 'b': 7}
    assert missing == ()
    assert errs == []


def test_validate_params_reports_wrong_type():
    """类型不符要报错，且布尔不能被当成整数放行。"""
    sc = {'type': 'object', 'properties': {'n': {'type': 'integer'},
                                           's': {'type': 'string'}}}
    _, _, errs = validate_params(sc, {'n': True, 's': 3})
    assert len(errs) == 2
    assert any('boolean' in e for e in errs)


def test_validate_params_checks_enum_and_range():
    """enum 与 min/max 也要校验 —— 动作 schema 里确实用了。"""
    sc = {'type': 'object',
          'properties': {'mode': {'type': 'string', 'enum': ['a', 'b']},
                         'n': {'type': 'integer', 'minimum': 1, 'maximum': 5}}}
    _, _, errs = validate_params(sc, {'mode': 'z', 'n': 9})
    assert len(errs) == 2


def test_validate_params_missing_required():
    """必填缺失必须出现在 missing 里，交给调用方决定怎么办。"""
    sc = {'type': 'object', 'required': ['a'], 'properties': {'a': {'type': 'string'}}}
    cleaned, missing, _ = validate_params(sc, {})
    assert missing == ('a',)
    assert 'a' not in cleaned


def test_validate_params_tolerates_garbage_input():
    """schema 或 params 不是 dict 时不能崩 —— 模型输出不可控。"""
    for sc, pr in ((None, None), ('x', 'y'), ({}, []), ({'properties': 'bad'}, {})):
        cleaned, missing, errs = validate_params(sc, pr)
        assert cleaned == {} and missing == () and errs == []


def test_validate_params_respects_additional_properties():
    """additionalProperties=true 时保留未声明参数。"""
    sc = {'type': 'object', 'additionalProperties': True, 'properties': {}}
    cleaned, _, _ = validate_params(sc, {'free': 1})
    assert cleaned == {'free': 1}


# ── 安全判据 1：幻觉回查 ──

def test_select_rejects_hallucinated_action_id():
    """**安全判据**：模型返回目录外���动作 id 时不得当成有效选择。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq JSON 处理', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'action_id': 'actus.made.up',
                                     'arguments': {}, 'confidence': 0.99})])
    got = Selector(client, cat).select('处理 JSON')
    assert got.found is False
    assert got.error == 'hallucinated'
    assert got.tool_name == ''
    assert got.arguments == {}
    assert got.needs_confirm is True
    assert got.candidates, '降级后必须给出候选供人挑'


def test_select_rejects_hallucinated_tool_name_in_function_calling():
    """function-calling 模式下编造 tool_name 同样要拒。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([LLMResponse(tool_calls=(
        ToolCall(id='1', name='totally_made_up', arguments={'input': '{}'}),))])
    got = Selector(client, cat).select('处理 JSON')
    assert got.found is False
    assert got.error == 'hallucinated'


# ── 安全判据 2：候选集上限 ──

@needs_index
def test_selector_sends_bounded_candidates():
    """**安全判据**：候选数超限时必须截断，不能把全目录塞给模型。"""
    from vools.actus.ai.catalog import build_catalog
    cat = build_catalog(meta_dir=_META)
    assert len(cat) > 30, '真实索引应远大于 max_candidates，否则本判据无意义'
    client = FakeClient(['{}'])
    Selector(client, cat, max_candidates=8).select('把 JSON 转成表格')
    sent = client.calls[0]['tools']
    assert sent is not None
    assert len(sent) <= 8, '候选集未截断'


def test_selector_passes_tools_to_client():
    """工具声明必须真的传给 provider（function calling 需要它）。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient(['{}'])
    Selector(client, cat).select('处理 JSON')
    assert client.calls[0]['tools'][0].name == 'cli_jq'


# ── 安全判据 3：低置信度不瞎猜 ──

def test_low_confidence_requires_confirm():
    """**安全判据**：置信度低于阈值时必须要求确认并给候选。"""
    cat = ToolCatalog([
        _entry('cli.jq', 'jq JSON 处理', JQ_SCHEMA, ['input']),
        _entry('cli.pandoc', 'pandoc 文档转换'),
    ])
    client = FakeClient([json.dumps({'action_id': 'cli.jq', 'arguments': {},
                                     'confidence': 0.1, 'reason': '勉强'})])
    got = Selector(client, cat, threshold=0.25).select('处理 JSON')
    assert got.action_id == 'cli.jq'
    assert got.needs_confirm is True
    assert got.confidence == 0.1
    assert len(got.candidates) >= 1
    assert all(c['action_id'] != 'cli.jq' for c in got.candidates)


def test_audit_level_action_always_needs_confirm():
    """audit 级动作即使模型很有把握也要人工确认（trust.decide 的既有语义）。"""
    cat = ToolCatalog([_entry('dialog.alert', '弹窗', trust='audit')])
    client = FakeClient([json.dumps({'action_id': 'dialog.alert',
                                     'arguments': {}, 'confidence': 0.99})])
    got = Selector(client, cat).select('弹个窗')
    assert got.action_id == 'dialog.alert'
    assert got.needs_confirm is True


def test_trusted_action_high_confidence_no_confirm():
    """trusted 级 + 高置信度不该强制确认，否则确认提示会变成噪音。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'action_id': 'cli.jq',
                                     'arguments': {'input': '{}', 'filter': '.a'},
                                     'confidence': 0.95})])
    got = Selector(client, cat, threshold=0.25).select('处理 JSON')
    assert got.found is True
    assert got.needs_confirm is False
    assert got.arguments == {'input': '{}', 'filter': '.a'}


# ── 解析与错误路径 ──

def test_select_parses_json_wrapped_in_markdown_fence():
    """模型常把 JSON 包在 ```json 围栏里，必须容忍。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    body = '```json\n{"action_id": "cli.jq", "arguments": {"input": "{}"}, ' \
           '"confidence": 0.9}\n```'
    got = Selector(FakeClient([body]), cat).select('处理 JSON')
    assert got.action_id == 'cli.jq'
    assert got.arguments['input'] == '{}'


def test_select_supports_function_calling_response():
    """function-calling 返回也要能解析出动作与参数。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([LLMResponse(tool_calls=(
        ToolCall(id='1', name='cli_jq', arguments={'input': '{}', 'filter': '.a'}),
    ))])
    got = Selector(client, cat).select('处理 JSON')
    assert got.action_id == 'cli.jq'
    assert got.arguments['filter'] == '.a'


def test_select_reports_llm_failure_without_crashing():
    """模型调用失败时给出结构化 error，不是抛异常。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([LLMResponse(content='端点不可达', stop_reason='error',
                                     raw={'error_kind': 'unreachable',
                                          'code': 'dependency_missing'})])
    got = Selector(client, cat).select('处理 JSON')
    assert got.found is False
    assert got.error == 'llm_failed'
    assert got.needs_confirm is True
    assert '端点不可达' in got.reason


def test_select_handles_empty_action_id():
    """模型说「没有合适的」时如实返回 no_match。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'action_id': '', 'confidence': 0,
                                     'reason': '都不合适'})])
    got = Selector(client, cat).select('做量子计算')
    assert got.found is False
    assert got.error == 'no_match'


def test_select_handles_unparseable_reply():
    """模型返回垃圾文本时降级为 no_match，不能当成成功。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    got = Selector(FakeClient(['I think you should use jq maybe?']), cat).select('json')
    assert got.found is False
    assert got.error == 'no_match'


def test_select_reports_missing_required_args():
    """必填没给全时要报出来，并标 needs_confirm。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input', 'filter'])])
    client = FakeClient([json.dumps({'action_id': 'cli.jq',
                                     'arguments': {'input': '{}'},
                                     'confidence': 0.9})])
    got = Selector(client, cat).select('处理 JSON')
    assert got.missing_args == ('filter',)
    assert 'filter' in got.reason


def test_select_reports_param_type_mismatch():
    """参数类型不符要记 param_mismatch，便于排查是模型还是动作的问题。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'action_id': 'cli.jq',
                                     'arguments': {'input': 123},
                                     'confidence': 0.9})])
    got = Selector(client, cat).select('处理 JSON')
    assert got.error == 'param_mismatch'


def test_select_on_empty_catalog():
    """目录为空时要给 catalog_empty，而不是抛异常。"""
    got = Selector(FakeClient(['{}']), ToolCatalog(())).select('随便')
    assert got.error == 'catalog_empty'


def test_fill_args_returns_validated_dict():
    """已知动作只填参数时，返回值仍要过校验。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'arguments': {'input': '{}', 'bad': 1}})])
    got = Selector(client, cat).fill_args('cli.jq', '输入 {} 用 .a 过滤')
    assert got == {'input': '{}'}, '未知参数应被丢弃'


def test_fill_args_unknown_action_returns_empty():
    """动作不在目录里时返回空 dict。"""
    assert Selector(FakeClient(['{}']), ToolCatalog(())).fill_args('nope', 'x') == {}


def test_selection_found_property():
    """found 要求 action_id 与 tool_name 同时存在。"""
    assert Selection(action_id='a').found is False
    assert Selection(tool_name='t').found is False
    assert Selection(tool_name='t', action_id='a').found is True


# ── planner ──

def test_planner_decomposes_valid_steps():
    """拆解结果里的未知 target_action 要清空但保留该步骤。"""
    cat = ToolCatalog([_entry('cli.jq', 'jq', JQ_SCHEMA, ['input'])])
    client = FakeClient([json.dumps({'steps': [
        {'id': 's1', 'title': '读输入', 'target_action': 'cli.jq',
         'arguments': {'input': '{}'}, 'verify': '读到一行'},
        {'id': 's2', 'title': '写报告', 'target_action': 'actus.fake.step',
         'verify': '文件存在'},
    ]})])
    plan = LlmPlanner(client, cat).decompose('生成报告')
    assert len(plan.steps) == 2
    assert plan.steps[0].target_action == 'cli.jq'
    assert plan.steps[0].verify == '读到一行'
    assert plan.steps[1].target_action == '', '编造的动作 id 应被清空'
    assert plan.steps[1].title == '写报告'
    assert plan.source == 'llm'


def test_planner_refuses_to_guess_when_llm_unavailable():
    """**不做猜计划兜底** —— 错的计划比没有计划更贵（下游会照着执行）。"""
    client = FakeClient(['{}'])
    client._available = False
    plan = LlmPlanner(client, ToolCatalog(())).decompose('做点什么')
    assert plan.steps == ()
    assert 'llm 不可用' in plan.error


def test_planner_reports_unparseable_output():
    """模型给不可解析内容时报错，不返回半成品计划。"""
    plan = LlmPlanner(FakeClient(['抱歉我无法完成']), ToolCatalog(())).decompose('x')
    assert plan.steps == ()
    assert plan.error


def test_planner_empty_goal():
    """空目标直接报错，不去调模型。"""
    assert plan_from_intent('').error == 'goal_empty'


def test_planner_base_is_protocol():
    """Planner 基类是协议载体。"""
    with pytest.raises(NotImplementedError):
        Planner().decompose('x')
