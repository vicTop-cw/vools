"""provider 注册表与客户端实现的判据。

**全程不依赖网络与 API key。** 本组测的是「没有密钥 / 端点不可达时
必须干净返回 False 而不是抛异常」—— 这是 doctor 与动作前置校验会
无保护调用的路径，抛异常会让整条决策链炸掉。
"""

import json

import pytest

import _ai_local_bootstrap as _boot   # noqa: F401  —— 必须先于 vools.actus

_boot.install()

from vools.actus.ai.base import LLMClient, LLMResponse, ToolCall, llm_error_code
from vools.actus.ai.registry import (get_provider, available_providers,
                                      PRESETS, register_provider)
from vools.actus.ai.providers.openai_compat import OpenAICompatClient
from vools.actus.ai.providers.anthropic import AnthropicClient

_NO_KEY_ENV = ('OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'GROQ_API_KEY',
               'ANTHROPIC_API_KEY')


@pytest.fixture(autouse=True)
def _clean_keys(monkeypatch):
    """清掉所有相关密钥环境变量，保证「无密钥」路径可复现。"""
    for name in _NO_KEY_ENV:
        monkeypatch.delenv(name, raising=False)


# ── 协议与错误码 ──

def test_llm_error_code_maps_to_existing_codes():
    """LLM 语义必须归一到 errors.ERROR_CODES 里的既有码，不新增码。"""
    from vools.actus.errors import ERROR_CODES
    for kind in ('auth', 'quota', 'unreachable', 'bad_response', 'param_invalid',
                 'unknown_provider'):
        assert llm_error_code(kind) in ERROR_CODES
    assert llm_error_code('auth') == 'auth_required'
    assert llm_error_code('不存在的类别') == 'internal'


def test_response_failed_property():
    """failed 只看 stop_reason，便于调用方一行判成败。"""
    assert LLMResponse(stop_reason='error').failed is True
    assert LLMResponse(content='x').failed is False
    assert LLMResponse(prompt_tokens=3, completion_tokens=4).total_tokens == 7


# ── 注册表 ──

def test_available_providers_includes_impls_and_presets():
    """惰性加载后，实现名与 preset 别名都应可见。"""
    names = available_providers()
    assert 'openai_compat' in names
    assert 'anthropic' in names
    for preset in PRESETS:
        assert preset in names


def test_get_provider_resolves_preset_to_compat_impl():
    """preset 别名解析后落到 openai_compat 实现，且带上 base_url/model。"""
    for name in ('openai', 'deepseek', 'groq'):
        client = get_provider(name)
        assert isinstance(client, OpenAICompatClient)
        assert client.base_url == PRESETS[name][0]
        assert client.model == PRESETS[name][1]


def test_get_provider_kwargs_override_preset():
    """显式构造参数优先于 preset 解析出的值。"""
    client = get_provider('openai', base_url='http://x/v1', model='my-model')
    assert client.base_url == 'http://x/v1'
    assert client.model == 'my-model'


def test_get_provider_is_case_insensitive():
    """名字大小写不敏感，避免调用方因为大小写白跑一趟。"""
    assert get_provider('OpenAI').base_url == PRESETS['openai'][0]


def test_unknown_provider_raises_action_error():
    """未登记的 provider 报既有错误码，并把已知名字带进 details。"""
    from vools.actus.errors import ActionError
    with pytest.raises(ActionError) as ei:
        get_provider('nope')
    assert ei.value.code == 'param_invalid'
    assert 'openai' in ei.value.details['known']


def test_empty_provider_name_raises():
    """空名同样要报结构化错误，不能返回 None 让后面 AttributeError。"""
    from vools.actus.errors import ActionError
    with pytest.raises(ActionError):
        get_provider('')


def test_register_provider_rejects_non_client():
    """注册非 LLMClient 子类必须报错，否则注册表会被污染。"""
    from vools.actus.errors import ActionError

    class NotAClient(object):
        name = 'nope'

    with pytest.raises(ActionError):
        register_provider(NotAClient)


# ── 无密钥路径（关键安全判据） ──

def test_available_returns_false_without_key():
    """**核心判据**：无密钥时 available() 返回 False，不得抛异常。"""
    for name in ('openai', 'deepseek', 'groq'):
        assert get_provider(name).available() is False


def test_local_preset_available_false_when_endpoint_down():
    """本地端点不可达时返回 False，不得抛 URLError。"""
    # 指向一个必然连不上的端口
    client = OpenAICompatClient(base_url='http://127.0.0.1:1/v1', env_name='')
    assert client.available() is False


def test_complete_without_key_returns_error_response():
    """无密钥时 complete() 返回错误响应而不是抛异常（契约上永不抛）。"""
    resp = get_provider('openai').complete([_msg('hi')])
    assert resp.failed is True
    assert resp.raw['error_kind'] == 'auth'
    assert resp.raw['code'] == 'auth_required'


def test_anthropic_available_without_key():
    """Anthropic 的 available() 只看密钥，不做网络探测。"""
    assert AnthropicClient().available() is False


# ── 响应解析（用真实形状的响应体，不发请求） ──

def _msg(content, role='user'):
    from vools.actus.ai.base import Message
    return Message(role=role, content=content)


def test_parse_tool_calls_with_json_string_arguments():
    """**关键形状**：tool_calls[].function.arguments 是 JSON **字符串**，必须解析。"""
    payload = {
        'model': 'gpt-4o-mini',
        'choices': [{'message': {
            'content': None,
            'tool_calls': [{'id': 'call_1', 'type': 'function',
                            'function': {'name': 'cli_jq',
                                         'arguments': '{"input":"{}","filter":".a"}'}}],
        }}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 7},
    }
    resp = OpenAICompatClient(base_url='http://x/v1')._parse(payload)
    assert resp.stop_reason == 'tool_calls'
    assert len(resp.tool_calls) == 1
    call = resp.tool_calls[0]
    assert isinstance(call, ToolCall)
    assert call.name == 'cli_jq'
    assert call.arguments == {'input': '{}', 'filter': '.a'}, 'arguments 未被 json 解析'
    assert resp.total_tokens == 19


def test_parse_rejects_invalid_arguments_json():
    """arguments 非法 JSON 时归一为 bad_response，**不抛异常**。"""
    payload = {'choices': [{'message': {'content': None, 'tool_calls': [
        {'id': 'c1', 'function': {'name': 'x', 'arguments': '{not json'}}]}}]}
    resp = OpenAICompatClient(base_url='http://x/v1')._parse(payload)
    assert resp.failed is True
    assert resp.raw['error_kind'] == 'bad_response'


def test_missing_usage_yields_zero_tokens():
    """响应无 usage 时 token 数填 0 —— 不猜、不估算。"""
    payload = {'choices': [{'message': {'content': 'hi'}}]}
    resp = OpenAICompatClient(base_url='http://x/v1')._parse(payload)
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0
    assert resp.content == 'hi'
    assert resp.stop_reason == 'stop'


def test_parse_rejects_missing_choices():
    """缺 choices / 非 object / 空数组都归一为 bad_response。"""
    client = OpenAICompatClient(base_url='http://x/v1')
    for payload in ([], {'choices': []}, {'choices': [{}]}, 'not a dict'):
        resp = client._parse(payload)
        assert resp.failed is True
        assert resp.raw['error_kind'] == 'bad_response'


def test_stream_true_is_rejected_explicitly():
    """stream=True 必须显式报未实现，不许静默降级成非流式结果。"""
    resp = OpenAICompatClient(base_url='http://x/v1', env_name='').complete(
        [_msg('hi')], stream=True)
    assert resp.failed is True
    assert 'stream' in resp.content.lower()


def test_messages_serialization_round_trip():
    """assistant 的 tool_calls 与 tool 结果要能正确序列化回 provider 形状。"""
    from vools.actus.ai.base import Message
    msgs = [
        Message(role='user', content='hi'),
        Message(role='assistant', content='', tool_calls=(
            ToolCall(id='c1', name='cli_jq', arguments={'filter': '.a'}),)),
        Message(role='tool', content='result', tool_call_id='c1', name='cli_jq'),
    ]
    out = OpenAICompatClient._build_messages(msgs)
    assert out[1]['tool_calls'][0]['function']['name'] == 'cli_jq'
    assert json.loads(out[1]['tool_calls'][0]['function']['arguments']) == {'filter': '.a'}
    assert out[2]['tool_call_id'] == 'c1'


def test_tools_serialization_uses_function_shape():
    """ToolSpec 要转成 OpenAI 的 function-calling 形状。"""
    from vools.actus.ai.base import ToolSpec
    tools = [ToolSpec(name='cli_jq', description='d',
                      parameters={'type': 'object'})]
    out = OpenAICompatClient._build_tools(tools)
    assert out[0]['type'] == 'function'
    assert out[0]['function']['name'] == 'cli_jq'


def test_anthropic_body_shape():
    """Anthropic 的 system 是顶层字段、参数键是 input_schema。"""
    from vools.actus.ai.base import Message, ToolSpec
    body = AnthropicClient()._build_body(
        [Message(role='system', content='be nice'), Message(role='user', content='hi')],
        [ToolSpec(name='t', description='d', parameters={'type': 'object'})],
        0.5, None)
    assert body['system'] == 'be nice'
    assert body['messages'] == [{'role': 'user', 'content': 'hi'}]
    assert body['tools'][0]['input_schema'] == {'type': 'object'}
    assert 'max_tokens' in body


def test_anthropic_multiple_tool_results_share_one_user_turn():
    """一次 assistant 多个 tool_use 的回传必须合并到同一个 user 回合。

    否则出现连续两条 role=user 消息，Anthropic Messages API 返回
    400 roles must alternate。
    """
    from vools.actus.ai.base import Message
    msgs = [
        Message(role='user', content='do two things'),
        Message(role='assistant', content='', tool_calls=(
            ToolCall(id='c1', name='a', arguments={}),
            ToolCall(id='c2', name='b', arguments={}),
        )),
        Message(role='tool', content='r1', tool_call_id='c1', name='a'),
        Message(role='tool', content='r2', tool_call_id='c2', name='b'),
    ]
    body = AnthropicClient()._build_body(msgs, None, 0.0, None)
    roles = [m['role'] for m in body['messages']]
    assert roles == ['user', 'assistant', 'user']       # 不是 user,assistant,user,user
    last = body['messages'][-1]
    assert isinstance(last['content'], list)
    blocks = [b for b in last['content'] if b['type'] == 'tool_result']
    assert [b['tool_use_id'] for b in blocks] == ['c1', 'c2']
    assert [b['content'] for b in blocks] == ['r1', 'r2']


def test_anthropic_zero_temperature_is_preserved():
    """temperature=0.0 是合法的确定性取值，不得因真值判断被丢弃（否则退回默认 1.0）。"""
    from vools.actus.ai.base import Message
    body = AnthropicClient()._build_body([Message(role='user', content='hi')],
                                         None, 0.0, None)
    assert body['temperature'] == 0.0


def test_anthropic_parse_content_blocks():
    """Anthropic 响应是 content 块数组，要抽出 text 与 tool_use。"""
    payload = {'model': 'claude-x', 'content': [
        {'type': 'text', 'text': 'hello'},
        {'type': 'tool_use', 'id': 'tu1', 'name': 'cli_jq',
         'input': {'filter': '.a'}},
    ], 'usage': {'input_tokens': 5, 'output_tokens': 3}}
    resp = AnthropicClient()._parse(payload)
    assert resp.content == 'hello'
    assert resp.stop_reason == 'tool_calls'
    assert resp.tool_calls[0].arguments == {'filter': '.a'}
    assert resp.total_tokens == 8


def test_base_llmclient_is_protocol_only():
    """基类不应被误当成可用实现。"""
    client = LLMClient()
    assert client.name == 'abstract'
    assert client.available() is False
    with pytest.raises(NotImplementedError):
        client.complete([])
