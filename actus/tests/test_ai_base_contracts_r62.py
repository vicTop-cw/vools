# -*- coding: utf-8 -*-
"""ai/base.py 契约测试 (Round 56)。

覆盖：ERROR_MAP 归一表、llm_error_code、三个 frozen dataclass、
LLMClient 协议、_lookup_price_per_1k（精确/扫描/歧义/无价/bool 排除）、
_record_usage（三条 cost_source 分支）、records_usage 装饰器（成功/失败/
非 LLMResponse/记账异常吞掉 + failures 计数）。
"""

import dataclasses
import sys
import types

import pytest

from vools.actus.ai import base as bmod


# ---------------------------------------------------------------- exports

def test_all_exports():
    assert set(bmod.__all__) == {'Role', 'StopReason', 'ErrorKind', 'ERROR_MAP',
                                 'ToolSpec', 'ToolCall', 'Message', 'LLMResponse',
                                 'LLMClient', 'llm_error_code', 'records_usage',
                                 'usage_record_stats'}


# ---------------------------------------------------------------- ERROR_MAP

class TestErrorMap:
    def test_exact_mapping(self):
        assert bmod.ERROR_MAP == {
            'auth': 'auth_required',
            'quota': 'dependency_missing',
            'unreachable': 'dependency_missing',
            'bad_response': 'internal',
            'param_invalid': 'param_invalid',
            'unknown_provider': 'param_invalid',
        }

    @pytest.mark.parametrize("kind,expected", [
        ('auth', 'auth_required'),
        ('quota', 'dependency_missing'),
        ('unreachable', 'dependency_missing'),
        ('bad_response', 'internal'),
        ('param_invalid', 'param_invalid'),
        ('unknown_provider', 'param_invalid'),
    ])
    def test_llm_error_code_known(self, kind, expected):
        assert bmod.llm_error_code(kind) == expected

    def test_llm_error_code_unknown_is_internal(self):
        assert bmod.llm_error_code('nope') == 'internal'

    def test_llm_error_code_empty_is_internal(self):
        assert bmod.llm_error_code('') == 'internal'


# ---------------------------------------------------------------- dataclasses

class TestToolSpec:
    def test_defaults(self):
        s = bmod.ToolSpec(name='x')
        assert s.description == ''
        assert s.parameters == {}
        assert s.action_id == ''
        assert s.trust == 'audit'
        assert s.permissions == ()

    def test_full_and_action_id_passthrough(self):
        s = bmod.ToolSpec(name='cli_jq', description='jq JSON 处理',
                          parameters={'type': 'object'}, action_id='cli.jq')
        assert s.action_id == 'cli.jq'

    def test_frozen(self):
        s = bmod.ToolSpec(name='x')
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.name = 'y'

    def test_mutable_default_isolated(self):
        a, b = bmod.ToolSpec(name='a'), bmod.ToolSpec(name='b')
        assert a.parameters is not b.parameters
        assert a.permissions == b.permissions == ()


class TestToolCall:
    def test_defaults(self):
        c = bmod.ToolCall(id='1', name='t')
        assert c.arguments == {}

    def test_frozen(self):
        c = bmod.ToolCall(id='1', name='t')
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.id = '2'


class TestMessage:
    def test_defaults(self):
        m = bmod.Message(role='user', content='hi')
        assert m.tool_calls == ()
        assert m.tool_call_id == ''
        assert m.name == ''

    def test_tool_message(self):
        call = bmod.ToolCall(id='c1', name='t', arguments={'a': 1})
        m = bmod.Message(role='assistant', tool_calls=(call,))
        assert m.tool_calls[0].id == 'c1'

    def test_frozen(self):
        m = bmod.Message(role='user')
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.role = 'tool'


class TestLLMResponse:
    def test_defaults(self):
        r = bmod.LLMResponse()
        assert r.content == ''
        assert r.tool_calls == ()
        assert r.stop_reason == 'stop'
        assert r.prompt_tokens == 0
        assert r.completion_tokens == 0
        assert r.model == ''
        assert r.raw == {}

    def test_total_tokens(self):
        assert bmod.LLMResponse(prompt_tokens=10, completion_tokens=5).total_tokens == 15

    def test_failed_property(self):
        assert bmod.LLMResponse(stop_reason='error').failed is True
        assert bmod.LLMResponse(stop_reason='stop').failed is False

    def test_frozen(self):
        r = bmod.LLMResponse()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.stop_reason = 'error'


# ---------------------------------------------------------------- LLMClient

class TestLLMClient:
    def test_abstract_name(self):
        assert bmod.LLMClient.name == 'abstract'

    def test_complete_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            bmod.LLMClient().complete([])

    def test_available_default_false(self):
        assert bmod.LLMClient().available() is False

    def test_subclass_contract(self):
        class Fake(bmod.LLMClient):
            name = 'fake'

            def complete(self, messages, tools=None, temperature=0.0,
                         max_tokens=None):
                return bmod.LLMResponse(content='ok')

            def available(self):
                return True

        f = Fake()
        assert f.available() is True
        assert f.complete([]).content == 'ok'


# ---------------------------------------------------------------- usage stats

class TestUsageRecordStats:
    def test_shape(self):
        stats = bmod.usage_record_stats()
        assert set(stats) == {'attempts', 'failures', 'last_error'}
        assert isinstance(stats['attempts'], int)
        assert isinstance(stats['failures'], int)


# ---------------------------------------------------------------- price lookup

class TestLookupPrice:
    def _patch_table(self, monkeypatch, table):
        from vools.actus.ai import routing as rmod
        monkeypatch.setattr(rmod, 'PROVIDER_COST_PERF', table)

    def test_empty_model_no_import(self, monkeypatch):
        # model 为空直接短路（不 import routing 也可验证：给坏 sys.modules）
        monkeypatch.setitem(sys.modules, 'vools.actus.ai.routing', None)
        assert bmod._lookup_price_per_1k('prov', '') == (None, '')

    def test_routing_import_failure(self, monkeypatch):
        # from-import 对 None 的 sys.modules 项会抛 ImportError → (None, '')
        monkeypatch.setitem(sys.modules, 'vools.actus.ai.routing', None)
        assert bmod._lookup_price_per_1k('prov', 'm1') == (None, '')

    def test_exact_hit(self, monkeypatch):
        self._patch_table(monkeypatch, {
            'provA': {'m1': {'price_per_1k': 0.5}},
        })
        assert bmod._lookup_price_per_1k('provA', 'm1') == (0.5, 'provA/m1')

    def test_exact_entry_not_dict_falls_to_scan(self, monkeypatch):
        self._patch_table(monkeypatch, {
            'provA': {'m1': 'garbage'},
            'provB': {'m1': {'price_per_1k': 2}},
        })
        assert bmod._lookup_price_per_1k('provA', 'm1') == (2.0, 'provB/m1')

    def test_bool_price_excluded(self, monkeypatch):
        # bool 是 int 子类，必须排除
        self._patch_table(monkeypatch, {
            'provA': {'m1': {'price_per_1k': True}},
        })
        assert bmod._lookup_price_per_1k('provA', 'm1') == (None, '')

    def test_single_scan_hit(self, monkeypatch):
        self._patch_table(monkeypatch, {
            'provA': {'other': {}},
            'provB': {'m1': {'price_per_1k': 3}},
        })
        assert bmod._lookup_price_per_1k('zzz', 'm1') == (3.0, 'provB/m1')

    def test_multiple_hits_ambiguous(self, monkeypatch):
        self._patch_table(monkeypatch, {
            'provB': {'m1': {'price_per_1k': 3}},
            'provA': {'m1': {'price_per_1k': 9}},
        })
        price, matched = bmod._lookup_price_per_1k('zzz', 'm1')
        # matches[0] = 字典序第一个 provider（provA, 9.0），不是最低价 —— 记录现状
        assert price == 9.0
        assert matched == 'provA/m1(ambiguous:provA,provB)'

    def test_no_hits(self, monkeypatch):
        self._patch_table(monkeypatch, {'provA': {'m2': {}}})
        assert bmod._lookup_price_per_1k('provA', 'm1') == (None, '')

    def test_empty_table(self, monkeypatch):
        self._patch_table(monkeypatch, {})
        assert bmod._lookup_price_per_1k('provA', 'm1') == (None, '')


# ---------------------------------------------------------------- record usage

class _Rsp:
    def __init__(self, prompt=10, completion=5, model='m1', stop='stop'):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.model = model
        self.stop_reason = stop


class TestRecordUsage:
    def _patch_cost(self, monkeypatch):
        calls = []
        from vools.actus import cost as cmod
        monkeypatch.setattr(cmod, 'record_cost',
                            lambda *a, **k: calls.append((a, k)))
        return calls

    def test_with_price(self, monkeypatch):
        from vools.actus.ai import routing as rmod
        monkeypatch.setattr(rmod, 'PROVIDER_COST_PERF',
                            {'provA': {'m1': {'price_per_1k': 1.0}}})
        calls = self._patch_cost(monkeypatch)
        bmod._record_usage(types.SimpleNamespace(name='provA'), _Rsp())
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert args[0] == 'ai.llm.complete'
        assert args[1] == 'provA'
        assert args[2] == round(15 / 1000.0 * 1.0, 8)
        assert kwargs['tokens'] == 15
        assert kwargs['model'] == 'm1'
        extra = kwargs['extra']
        assert extra['cost_source'] == 'estimated:routing.PROVIDER_COST_PERF'
        assert extra['prompt_tokens'] == 10
        assert extra['completion_tokens'] == 5
        assert extra['price_per_1k'] == 1.0
        assert extra['price_source_matched'] == 'provA/m1'
        assert extra['stop_reason'] == 'stop'

    def test_no_usage_tokens_null_cost(self, monkeypatch):
        calls = self._patch_cost(monkeypatch)
        bmod._record_usage(types.SimpleNamespace(name='p'), _Rsp(prompt=0, completion=0))
        args, kwargs = calls[0]
        assert args[2] is None
        assert kwargs['extra']['cost_source'] == 'unknown:no-usage-tokens'

    def test_unknown_price_null_cost(self, monkeypatch):
        from vools.actus.ai import routing as rmod
        monkeypatch.setattr(rmod, 'PROVIDER_COST_PERF', {})
        calls = self._patch_cost(monkeypatch)
        bmod._record_usage(types.SimpleNamespace(name='p'), _Rsp())
        args, kwargs = calls[0]
        assert args[2] is None
        assert kwargs['extra']['cost_source'] == 'unknown:no-price-entry'
        assert kwargs['extra']['price_source_matched'] == ''

    def test_provider_and_model_fallbacks(self, monkeypatch):
        calls = self._patch_cost(monkeypatch)
        client = types.SimpleNamespace(model='fallback-model')  # 无 name
        bmod._record_usage(client, _Rsp(model=''))
        args, kwargs = calls[0]
        assert args[1] == 'unknown'
        assert kwargs['model'] == 'fallback-model'

    def test_non_int_tokens_coerced(self, monkeypatch):
        calls = self._patch_cost(monkeypatch)
        rsp = _Rsp()
        rsp.prompt_tokens = None
        rsp.completion_tokens = '7'
        bmod._record_usage(types.SimpleNamespace(name='p'), rsp)
        assert calls[0][1]['tokens'] == 7


# ---------------------------------------------------------------- decorator

class TestRecordsUsageDecorator:
    def _fresh_client(self, monkeypatch, rsp):
        calls = []
        from vools.actus import cost as cmod
        monkeypatch.setattr(cmod, 'record_cost',
                            lambda *a, **k: calls.append((a, k)))
        return calls

    def test_success_records(self, monkeypatch):
        calls = self._fresh_client(monkeypatch, None)
        stats0 = bmod.usage_record_stats()

        def _complete(self, messages):
            return bmod.LLMResponse(content='ok', model='m1')

        class C(bmod.LLMClient):
            name = 'provA'
            complete = bmod.records_usage(_complete)

        out = C().complete([])
        assert out.content == 'ok'
        assert len(calls) == 1
        stats1 = bmod.usage_record_stats()
        assert stats1['attempts'] == stats0['attempts'] + 1
        assert stats1['failures'] == stats0['failures']

    def test_failed_response_not_recorded(self, monkeypatch):
        calls = self._fresh_client(monkeypatch, None)
        stats0 = bmod.usage_record_stats()

        def _complete(self, messages):
            return bmod.LLMResponse(stop_reason='error', content='boom')

        class C(bmod.LLMClient):
            name = 'p'
            complete = bmod.records_usage(_complete)

        C().complete([])
        assert calls == []
        assert bmod.usage_record_stats()['attempts'] == stats0['attempts']

    def test_non_llmresponse_not_recorded(self, monkeypatch):
        calls = self._fresh_client(monkeypatch, None)

        def _complete(self, messages):
            return 'plain-string'

        class C(bmod.LLMClient):
            name = 'p'
            complete = bmod.records_usage(_complete)

        assert C().complete([]) == 'plain-string'
        assert calls == []

    def test_record_failure_swallowed_and_counted(self, monkeypatch):
        from vools.actus import cost as cmod

        def boom(*a, **k):
            raise RuntimeError('ledger down')

        monkeypatch.setattr(cmod, 'record_cost', boom)
        stats0 = bmod.usage_record_stats()

        def _complete(self, messages):
            return bmod.LLMResponse(content='ok', model='m1')

        class C(bmod.LLMClient):
            name = 'p'
            complete = bmod.records_usage(_complete)

        out = C().complete([])
        assert out.content == 'ok'  # 返回值不受记账失败影响
        stats1 = bmod.usage_record_stats()
        assert stats1['attempts'] == stats0['attempts'] + 1
        assert stats1['failures'] == stats0['failures'] + 1
        assert 'RuntimeError' in stats1['last_error']

    def test_wraps_preserves_metadata(self):
        def _complete(self, messages):
            """doc"""
            return bmod.LLMResponse()

        wrapped = bmod.records_usage(_complete)
        assert wrapped.__name__ == '_complete'
        assert wrapped.__doc__ == 'doc'
