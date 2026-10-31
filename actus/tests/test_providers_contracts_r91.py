# -*- coding: utf-8 -*-
"""r91 — ai/providers/openai_compat.py + anthropic.py 契约测试。

覆盖两家用 urllib 直连的 LLM 客户端（本模块此前仅 registry 假件触达）：
- openai_compat：消息/工具序列化、_parse 全形状、complete 错误矩阵、available 探测
- anthropic：Messages API 三差异（system 顶层 / content 块数组 / input_schema）、
  严格交替约束（连续 tool 合并进同一 user 回合）、_parse、complete 错误矩阵

外部端点全部用 monkeypatch 假件（urllib.request.urlopen 全局替换，pytest 还原），
零真网络。所有断言只读公开行为，不改产品代码。
"""

import _ai_local_bootstrap  # noqa: F401  必须先于 vools 导入（见 docstring）

import json
import urllib.error
import urllib.request

import pytest

import vools.actus.ai.providers.anthropic as ant_mod
import vools.actus.ai.providers.openai_compat as oai_mod
from vools.actus.ai.base import Message, ToolSpec
from vools.actus.ai.providers.anthropic import (API_VERSION, DEFAULT_BASE_URL,
                                                DEFAULT_ENV, DEFAULT_MODEL,
                                                AnthropicClient)
from vools.actus.ai.providers.openai_compat import OpenAICompatClient


# ──────────────────────────── 假件 ────────────────────────────


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode('utf-8') \
            if not isinstance(payload, (bytes, str)) else (
                payload if isinstance(payload, bytes)
                else payload.encode('utf-8'))

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code, reason='denied'):
    return urllib.error.HTTPError('http://x', code, reason, {}, None)


class _Ctx:
    """可入 with 的假 urlopen 抛件（HTTPError/URLError/OSError 均可）。"""

    def __init__(self, exc):
        self._exc = exc

    def __call__(self, *a, **kw):
        raise self._exc


# ──────────────────── openai_compat：构造与序列化 ────────────────────


class TestOaiConstruct:
    def test_base_url_rstrip(self):
        assert OpenAICompatClient(
            base_url='http://h/v1/').base_url == 'http://h/v1'

    def test_name_override(self):
        c = OpenAICompatClient(name='deepseek')
        assert c.name == 'deepseek'

    def test_env_name_default(self):
        assert OpenAICompatClient().env_name == 'OPENAI_API_KEY'

    def test_resolve_key_explicit_first(self, monkeypatch):
        monkeypatch.setenv('MY_KEY', 'from-env')
        c = OpenAICompatClient(api_key='explicit', env_name='MY_KEY')
        assert c._resolve_key() == 'explicit'

    def test_resolve_key_env_fallback(self, monkeypatch):
        monkeypatch.setenv('MY_KEY', 'from-env')
        assert OpenAICompatClient(env_name='MY_KEY')._resolve_key() == 'from-env'

    def test_resolve_key_missing(self, monkeypatch):
        monkeypatch.delenv('NOPE', raising=False)
        assert OpenAICompatClient(env_name='NOPE')._resolve_key() == ''


class TestOaiBuildMessages:
    def test_plain_roles(self):
        out = OpenAICompatClient._build_messages(
            [Message(role='system', content='s'),
             Message(role='user', content='hi')])
        assert out == [{'role': 'system', 'content': 's'},
                       {'role': 'user', 'content': 'hi'}]

    def test_assistant_tool_calls_serialized(self):
        from vools.actus.ai.base import ToolCall
        m = Message(role='assistant', content='',
                    tool_calls=(ToolCall(id='t1', name='f',
                                         arguments={'x': 1}),))
        (item,) = OpenAICompatClient._build_messages([m])
        assert item['tool_calls'] == [
            {'id': 't1', 'type': 'function',
             'function': {'name': 'f', 'arguments': '{"x": 1}'}}]

    def test_tool_message_ids(self):
        m = Message(role='tool', content='res', tool_call_id='t9', name='f')
        (item,) = OpenAICompatClient._build_messages([m])
        assert item['tool_call_id'] == 't9' and item['name'] == 'f'

    def test_none_content_becomes_empty(self):
        (item,) = OpenAICompatClient._build_messages(
            [Message(role='user', content=None)])
        assert item['content'] == ''


def test_oai_build_tools_shape():
    t = ToolSpec(name='f', description='d',
                 parameters={'type': 'object', 'properties': {}})
    (spec,) = OpenAICompatClient._build_tools([t])
    assert spec == {'type': 'function',
                    'function': {'name': 'f', 'description': 'd',
                                 'parameters': {'type': 'object',
                                                'properties': {}}}}


# ──────────────────── openai_compat：_parse 全形状 ────────────────────


class TestOaiParse:
    def _ok_payload(self, **over):
        msg = {'role': 'assistant', 'content': 'hi'}
        msg.update(over.pop('message_over', {}))
        p = {'choices': [{'message': msg}], 'model': 'm1',
             'usage': {'prompt_tokens': 3, 'completion_tokens': 5}}
        p.update(over)
        return p

    def test_non_dict_payload(self):
        r = OpenAICompatClient(model='m')._parse([1])
        assert r.stop_reason == 'error' and 'JSON object' in r.content

    def test_missing_choices(self):
        r = OpenAICompatClient()._parse({})
        assert 'choices' in r.content

    def test_empty_choices(self):
        r = OpenAICompatClient()._parse({'choices': []})
        assert 'choices' in r.content

    def test_message_not_dict(self):
        r = OpenAICompatClient()._parse({'choices': [{'message': 'x'}]})
        assert 'message' in r.content

    def test_success_stop(self):
        r = OpenAICompatClient(model='m0')._parse(self._ok_payload())
        assert r.content == 'hi' and r.stop_reason == 'stop'
        assert (r.prompt_tokens, r.completion_tokens) == (3, 5)
        assert r.model == 'm1'

    def test_model_fallback_to_self(self):
        r = OpenAICompatClient(model='m0')._parse(
            self._ok_payload(model=None))
        assert r.model == 'm0'

    def test_tool_calls_stop_reason(self):
        r = OpenAICompatClient()._parse(self._ok_payload(
            message_over={'tool_calls': [
                {'id': 't1', 'function':
                    {'name': 'f', 'arguments': '{"a": 1}'}}]}))
        assert r.stop_reason == 'tool_calls'
        tc = r.tool_calls[0]
        assert (tc.id, tc.name, tc.arguments) == ('t1', 'f', {'a': 1})

    def test_tool_call_empty_args_string(self):
        r = OpenAICompatClient()._parse(self._ok_payload(
            message_over={'tool_calls': [
                {'id': '', 'function': {'name': 'f', 'arguments': '  '}}]}))
        assert r.tool_calls[0].arguments == {}

    def test_tool_call_bad_json_is_bad_response(self):
        r = OpenAICompatClient()._parse(self._ok_payload(
            message_over={'tool_calls': [
                {'id': 't', 'function': {'name': 'f', 'arguments': '{bad'}}]}))
        assert r.stop_reason == 'error' and '不是合法 JSON' in r.content

    def test_tool_call_dict_args_passthrough(self):
        r = OpenAICompatClient()._parse(self._ok_payload(
            message_over={'tool_calls': [
                {'id': 't', 'function': {'name': 'f',
                                         'arguments': {'a': 1}}}]}))
        assert r.tool_calls[0].arguments == {'a': 1}

    def test_tool_call_json_string_args_wrapped(self):
        # arguments 是 JSON 字符串 '"plain"' → 解析成 str（非 dict）→ {'_raw': ...}
        r = OpenAICompatClient()._parse(self._ok_payload(
            message_over={'tool_calls': [
                {'id': 't', 'function': {'name': 'f',
                                         'arguments': '"plain"'}}]}))
        assert r.tool_calls[0].arguments == {'_raw': 'plain'}

    def test_tool_call_non_str_non_dict_args_default_empty(self):
        # arguments=7（非 str 非 dict）→ args={} 兜底（167）
        p = self._ok_payload(message_over={'tool_calls': [
            {'id': 't', 'function': {'name': 'f', 'arguments': 7}}]})
        r = OpenAICompatClient()._parse(p)
        assert r.tool_calls[0].arguments == {}

    def test_no_usage_defaults_zero(self):
        p = self._ok_payload()
        p.pop('usage')
        r = OpenAICompatClient()._parse(p)
        assert (r.prompt_tokens, r.completion_tokens) == (0, 0)

    def test_missing_content_empty(self):
        p = self._ok_payload()
        p['choices'][0]['message'].pop('content')
        assert OpenAICompatClient()._parse(p).content == ''


# ──────────────────── openai_compat：complete 错误矩阵 ────────────────────


class TestOaiComplete:
    def test_stream_rejected(self):
        r = OpenAICompatClient(base_url='http://h').complete([], stream=True)
        assert r.stop_reason == 'error' and 'stream=True' in r.content
        assert r.raw['code'] == 'param_invalid'

    def test_missing_base_url(self):
        r = OpenAICompatClient().complete([])
        assert 'base_url' in r.content and r.raw['error_kind'] == 'param_invalid'

    def test_missing_env_key(self, monkeypatch):
        monkeypatch.delenv('K1', raising=False)
        r = OpenAICompatClient(base_url='http://h',
                               env_name='K1').complete([])
        assert r.raw['error_kind'] == 'auth' and 'K1' in r.content

    def test_success_request_shape(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured['url'] = req.full_url
            captured['body'] = json.loads(req.data.decode('utf-8'))
            captured['headers'] = dict(req.header_items())
            captured['timeout'] = timeout
            return _Resp({'choices': [{'message': {'content': 'ok'}}]})
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        tools = [ToolSpec(name='f', description='', parameters=None)]
        r = OpenAICompatClient(base_url='http://h/', model='m',
                               api_key='k1', env_name='').complete(
            [Message(role='user', content='q')], tools=tools,
            max_tokens=99)
        assert r.content == 'ok'
        assert captured['url'] == 'http://h/chat/completions'
        assert captured['timeout'] == 60
        assert captured['body']['max_tokens'] == 99
        assert captured['body']['tools'][0]['function']['name'] == 'f'
        assert any('Bearer k1' in v for v in captured['headers'].values())

    def test_no_key_no_auth_header(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured['headers'] = dict(req.header_items())
            return _Resp({'choices': [{'message': {'content': ''}}]})
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        OpenAICompatClient(base_url='http://h', env_name='').complete([])
        assert not any('Authorization' in k or 'Bearer' in v
                       for k, v in captured['headers'].items())

    def test_http_401_auth(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request, 'urlopen', _Ctx(_http_error(401)))
        r = OpenAICompatClient(base_url='http://h',
                               env_name='').complete([])
        assert r.raw['error_kind'] == 'auth'

    def test_http_403_auth(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request, 'urlopen', _Ctx(_http_error(403)))
        assert OpenAICompatClient(base_url='http://h', env_name='').complete(
            []).raw['error_kind'] == 'auth'

    def test_http_429_quota(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request, 'urlopen', _Ctx(_http_error(429)))
        assert OpenAICompatClient(base_url='http://h', env_name='').complete(
            []).raw['error_kind'] == 'quota'

    def test_http_500_unreachable(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request, 'urlopen', _Ctx(_http_error(500)))
        assert OpenAICompatClient(base_url='http://h', env_name='').complete(
            []).raw['error_kind'] == 'unreachable'

    def test_url_error_unreachable(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request, 'urlopen',
            _Ctx(urllib.error.URLError('refused')))
        r = OpenAICompatClient(base_url='http://h', env_name='').complete([])
        assert r.raw['error_kind'] == 'unreachable' and '端点不可达' in r.content

    def test_os_error_unreachable(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(OSError('reset')))
        assert OpenAICompatClient(base_url='http://h', env_name='').complete(
            []).raw['error_kind'] == 'unreachable'

    def test_bad_json_response(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            lambda *a, **k: _Resp('{oops'))
        r = OpenAICompatClient(base_url='http://h', env_name='').complete([])
        assert '不是合法 JSON' in r.content

    def test_available_env_key_present(self, monkeypatch):
        monkeypatch.setenv('K9', 'x')
        assert OpenAICompatClient(env_name='K9').available() is True

    def test_available_env_key_missing(self, monkeypatch):
        monkeypatch.delenv('K9', raising=False)
        assert OpenAICompatClient(env_name='K9').available() is False

    def test_available_local_probe_ok(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            lambda *a, **k: _Resp({}))
        assert OpenAICompatClient(base_url='http://h',
                                  env_name='').available() is True

    def test_available_local_probe_down(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(OSError('down')))
        assert OpenAICompatClient(base_url='http://h',
                                  env_name='').available() is False


def test_oai_tail_prefers_reason():
    assert oai_mod._tail(urllib.error.URLError('boom')) == 'boom'


class _Evil:
    """getattr 即抛的异常替身 → _tail 兜底 ''（265-266）。"""

    def __getattr__(self, name):
        raise RuntimeError('nope')


def test_oai_tail_getattr_raise_returns_empty():
    assert oai_mod._tail(_Evil()) == ''


# ──────────────────── anthropic：构造与 _build_body ────────────────────


class TestAntConstruct:
    def test_defaults(self):
        c = AnthropicClient()
        assert c.base_url == DEFAULT_BASE_URL
        assert c.model == DEFAULT_MODEL
        assert c.env_name == DEFAULT_ENV
        assert c.max_tokens == 4096

    def test_api_version_constant(self):
        assert API_VERSION == '2023-06-01'

    def test_name_override(self):
        assert AnthropicClient(name='x').name == 'x'

    def test_resolve_key_explicit(self, monkeypatch):
        monkeypatch.setenv(DEFAULT_ENV, 'env-k')
        assert AnthropicClient(api_key='ex')._resolve_key() == 'ex'


class TestAntBuildBody:
    def _msg(self, role, content, **kw):
        return Message(role=role, content=content, **kw)

    def test_system_top_level(self):
        body = AnthropicClient()._build_body(
            [self._msg('system', 'sys1'), self._msg('system', 'sys2'),
             self._msg('user', 'q')], None, 0.0, None)
        assert body['system'] == 'sys1\n\nsys2'
        assert body['messages'] == [{'role': 'user', 'content': 'q'}]

    def test_strict_alternation_tools_merged_into_user_turn(self):
        from vools.actus.ai.base import ToolCall
        msgs = [
            self._msg('user', 'run it'),
            self._msg('assistant', '',
                      tool_calls=(ToolCall(id='t1', name='f',
                                           arguments={'x': 1}),
                                  ToolCall(id='t2', name='g',
                                           arguments={}))),
            self._msg('tool', 'r1', tool_call_id='t1'),
            self._msg('tool', 'r2', tool_call_id='t2'),
            self._msg('user', 'thanks'),
        ]
        body = AnthropicClient()._build_body(msgs, None, 0.0, None)
        m = body['messages']
        # user / assistant / user(2 tool_result + 1 text) —— 无第二条 user
        assert [x['role'] for x in m] == ['user', 'assistant', 'user']
        assert [b['type'] for b in m[2]['content']] == \
            ['tool_result', 'tool_result', 'text']

    def test_assistant_blocks_have_tool_use(self):
        from vools.actus.ai.base import ToolCall
        msgs = [self._msg('user', 'go'),
                self._msg('assistant', 'thinking',
                          tool_calls=(ToolCall(id='t1', name='f',
                                               arguments={'a': []}),))]
        body = AnthropicClient()._build_body(msgs, None, 0.0, None)
        blocks = body['messages'][1]['content']
        assert blocks == [
            {'type': 'text', 'text': 'thinking'},
            {'type': 'tool_use', 'id': 't1', 'name': 'f',
             'input': {'a': []}}]

    def test_temperature_zero_kept(self):
        body = AnthropicClient()._build_body(
            [self._msg('user', 'q')], None, 0.0, None)
        assert body['temperature'] == 0.0        # 137：is not None，不落默认 1.0

    def test_max_tokens_override(self):
        body = AnthropicClient()._build_body(
            [self._msg('user', 'q')], None, 0.0, 123)
        assert body['max_tokens'] == 123

    def test_tools_use_input_schema(self):
        t = ToolSpec(name='f', description='d', parameters=None)
        body = AnthropicClient()._build_body(
            [self._msg('user', 'q')], [t], 0.0, None)
        assert body['tools'] == [{'name': 'f', 'description': 'd',
                                  'input_schema': {'type': 'object'}}]


# ──────────────────── anthropic：_parse / complete / available ────────────────────


class TestAntParse:
    def test_non_dict(self):
        assert AnthropicClient()._parse('x').stop_reason == 'error'

    def test_missing_content(self):
        assert 'content' in AnthropicClient()._parse({}).content

    def test_blocks_mixed(self):
        r = AnthropicClient(model='m0')._parse({
            'content': [
                {'type': 'text', 'text': 'a'},
                {'type': 'text', 'text': ''},        # 空文本被 join 前滤掉
                'junk',                              # 非 dict 跳过
                {'type': 'tool_use', 'id': 't1', 'name': 'f',
                 'input': {'k': 1}},
                {'type': 'tool_use', 'id': 't2', 'name': 'g',
                 'input': 'bad'},                    # 非 dict input → {}
            ],
            'usage': {'input_tokens': 7, 'output_tokens': 9},
            'model': 'm1'})
        assert r.content == 'a'
        assert r.stop_reason == 'tool_calls'
        assert (r.tool_calls[0].arguments, r.tool_calls[1].arguments) == \
            ({'k': 1}, {})
        assert (r.prompt_tokens, r.completion_tokens) == (7, 9)
        assert r.model == 'm1'

    def test_text_only_stop(self):
        r = AnthropicClient()._parse({'content': [{'type': 'text',
                                                   'text': 'hi'}]})
        assert r.stop_reason == 'stop' and r.content == 'hi'


class TestAntComplete:
    def test_stream_rejected(self):
        r = AnthropicClient(api_key='k').complete([], stream=True)
        assert r.raw['error_kind'] == 'param_invalid'

    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv(DEFAULT_ENV, raising=False)
        assert AnthropicClient().complete([]).raw['error_kind'] == 'auth'

    def test_success_headers_and_url(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured['url'] = req.full_url
            captured['headers'] = {k.lower(): v
                                   for k, v in req.header_items()}
            return _Resp({'content': [{'type': 'text', 'text': 'ok'}]})
        monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
        r = AnthropicClient(api_key='k1').complete(
            [Message(role='user', content='q')])
        assert r.content == 'ok'
        assert captured['url'] == DEFAULT_BASE_URL + '/messages'
        assert captured['headers']['x-api-key'] == 'k1'
        assert captured['headers']['anthropic-version'] == API_VERSION

    def test_http_401_auth(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(_http_error(401)))
        assert AnthropicClient(api_key='k').complete([]).raw['error_kind'] \
            == 'auth'

    def test_http_429_quota(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(_http_error(429)))
        assert AnthropicClient(api_key='k').complete([]).raw['error_kind'] \
            == 'quota'

    def test_http_500_unreachable(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(_http_error(500)))
        assert AnthropicClient(api_key='k').complete([]).raw['error_kind'] \
            == 'unreachable'

    def test_url_error(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            _Ctx(urllib.error.URLError('down')))
        r = AnthropicClient(api_key='k').complete([])
        assert r.raw['error_kind'] == 'unreachable' and '端点不可达' in r.content

    def test_bad_json(self, monkeypatch):
        monkeypatch.setattr(urllib.request, 'urlopen',
                            lambda *a, **k: _Resp('not json'))
        assert '不是合法 JSON' in AnthropicClient(api_key='k').complete(
            []).content

    def test_available(self, monkeypatch):
        monkeypatch.delenv(DEFAULT_ENV, raising=False)
        assert AnthropicClient().available() is False
        assert AnthropicClient(api_key='k').available() is True


def test_ant_tail_prefers_reason():
    assert ant_mod._tail(urllib.error.URLError('boom')) == 'boom'


def test_ant_tail_getattr_raise_returns_empty():
    assert ant_mod._tail(_Evil()) == ''


def test_ant_error_response_carries_code():
    r = ant_mod._error_response('auth', 'm', 'claude')
    assert r.raw['code'] == 'auth_required' and r.model == 'claude'
