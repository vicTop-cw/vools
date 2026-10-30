# -*- coding: utf-8 -*-
"""mcp_server.py 契约测试（r74）：协议层/工具层/任务生命周期/异步转后台/
prompts/resources/complete/selfdrive_run + _call_tool_inner 头部。"""
import importlib
import io
import json
import os
import sys
import threading
import time
import types

import pytest

import _ai_local_bootstrap  # noqa: F401

mcp = importlib.import_module('vools.actus.mcp_server')
pkg = importlib.import_module('vools.actus')
err_mod = importlib.import_module('vools.actus.errors')


def _server():
    return mcp.MCPServer(stdin=io.BytesIO(), stdout=io.BytesIO())


def _out_bytes(server):
    return server.stdout.getvalue()


def _last_json(server):
    data = _out_bytes(server).decode('utf-8').strip().splitlines()
    return json.loads(data[-1])


# ── 模块级 helpers ──

class TestModuleHelpers:
    def test_tool_name(self):
        # 现状佐证：_tool_name 只做 id → 下划线归一，不加 actus_ 前缀
        assert mcp._tool_name('a.b') == 'a_b'

    def test_text_result_default_mapping(self):
        ok = mcp.text_result({'status': 'ok'})
        assert ok['isError'] is False
        assert ok['content'][0]['type'] == 'text'
        assert json.loads(ok['content'][0]['text'])['status'] == 'ok'
        bad = mcp.text_result({'status': 'failed'})
        assert bad['isError'] is True

    def test_text_result_explicit(self):
        assert mcp.text_result({'status': 'ok'}, True)['isError'] is True
        assert mcp.text_result({'status': 'failed'}, False)['isError'] is False

    def test_resolve_action_arg_unknown_passthrough(self):
        # resolver 对未知目标抛异常 → 原样返回
        assert mcp.resolve_action_arg('zzz-ghost-tool') == 'zzz-ghost-tool'

    def test_input_schema_passthrough_and_default(self):
        assert mcp._input_schema({'args': {'type': 'object'}}) == \
            {'type': 'object'}
        default = mcp._input_schema({})
        assert default['type'] == 'object'
        assert 'args' in default['properties']

    def test_action_tool_map(self):
        amap = mcp._action_tool_map()
        assert isinstance(amap, dict)
        again = mcp._action_tool_map()
        assert again == amap  # 缓存命中


class TestTaskLifecycle:
    def test_new_finish_snapshot(self):
        tid = mcp._new_task('actus_x', {'a': 1})
        snap = mcp._task_snapshot(tid)
        assert snap['status'] == 'running'
        mcp._finish_task(tid, status='ok', result={'r': 1})
        snap = mcp._task_snapshot(tid)
        assert snap['status'] == 'ok' and snap['result'] == {'r': 1}
        assert mcp._task_snapshot('task-nope') is None

    def test_running_count_and_evict(self, monkeypatch):
        monkeypatch.setattr(mcp, '_TASK_KEEP', 4, raising=False)
        for i in range(6):
            tid = mcp._new_task('actus_x', {})
            mcp._finish_task(tid, status='ok')
        mcp._evict_tasks_locked()
        assert len(mcp._TASKS) <= 6  # 收敛不变量：不超上限增长


# ── 协议层 handle() ──

class TestHandleProtocol:
    def test_initialize(self):
        s = _server()
        r = s.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        assert r['id'] == 1
        assert r['result']['protocolVersion'] == mcp.PROTOCOL_VERSION
        assert 'serverInfo' in r['result']

    def test_ping(self):
        assert _server().handle(
            {'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})['result'] == {}

    def test_unknown_method(self):
        r = _server().handle({'jsonrpc': '2.0', 'id': 3, 'method': 'zzz'})
        assert r['error']['code'] == -32601

    def test_notifications_no_reply(self):
        s = _server()
        assert s.handle({'jsonrpc': '2.0', 'method':
                         'notifications/progress'}) is None
        s.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        assert s._log_level == 'info'

    def test_logging_set_level(self):
        s = _server()
        r = s.handle({'jsonrpc': '2.0', 'id': 4, 'method':
                      'logging/setLevel', 'params': {'level': 'DEBUG'}})
        assert r['result'] == {} and s._log_level == 'debug'

    def test_prompts_list_and_get(self):
        s = _server()
        lst = s.handle({'jsonrpc': '2.0', 'id': 5, 'method': 'prompts/list'})
        names = [p['name'] for p in lst['result']['prompts']]
        assert 'actus_scaffold_guide' in names
        got = s.handle({'jsonrpc': '2.0', 'id': 6, 'method': 'prompts/get',
                        'params': {'name': 'actus_scaffold_guide',
                                   'arguments': {'description': 'D'}}})
        assert '骨架' in got['result']['messages'][0]['content']['text']

    def test_prompt_not_found_maps_to_internal(self):
        r = _server().handle({'jsonrpc': '2.0', 'id': 7, 'method':
                              'prompts/get',
                              'params': {'name': 'nope'}})
        assert r['error']['code'] == -32603
        assert r['error']['data']['type'] == 'ActionError'

    def test_completion(self):
        s = _server()
        r = s.handle({'jsonrpc': '2.0', 'id': 8, 'method':
                      'completion/complete',
                      'params': {'ref': {'name': 'trust', 'value': 'au'}}})
        vals = r['result']['completion']['values']
        assert vals == ['audit']

    def test_resources_list_and_read(self):
        s = _server()
        lst = s.handle({'jsonrpc': '2.0', 'id': 9, 'method':
                        'resources/list'})['result']['resources']
        uris = [r['uri'] for r in lst]
        assert 'actus://index' in uris and 'actus://status' in uris
        got = s.handle({'jsonrpc': '2.0', 'id': 10, 'method':
                        'resources/read',
                        'params': {'uri': 'actus://index'}})
        text = got['result']['contents'][0]['text']
        assert 'actions' in text

    def test_read_resource_unknown(self):
        r = _server().handle({'jsonrpc': '2.0', 'id': 11, 'method':
                              'resources/read',
                              'params': {'uri': 'actus://nope'}})
        assert r['error']['code'] == -32603

    def test_read_resource_missing_run(self):
        r = _server().handle({'jsonrpc': '2.0', 'id': 12, 'method':
                              'resources/read',
                              'params': {'uri': 'actus://runs/ghost-exec'}})
        assert r['error']['code'] == -32603

    def test_tools_call_sends_alive_notification(self):
        s = _server()
        s._call_tool_async = lambda p: {'ok': 1}
        r = s.handle({'jsonrpc': '2.0', 'id': 13, 'method': 'tools/call',
                      'params': {'name': 'actus_ping'}})
        assert r['result'] == {'ok': 1}
        lines = _out_bytes(s).decode('utf-8').strip().splitlines()
        note = json.loads(lines[0])
        assert note['method'] == 'notifications/message'

    def test_tools_call_valueerror_invalid_params(self):
        s = _server()
        def boom(p):
            raise ValueError('bad priority')
        s._call_tool_async = boom
        r = s.handle({'jsonrpc': '2.0', 'id': 14, 'method': 'tools/call',
                      'params': {'name': 'x'}})
        assert r['error']['code'] == -32602
        assert r['error']['data']['code'] == 'param_invalid'

    def test_tools_call_generic_internal(self):
        s = _server()
        def boom(p):
            raise RuntimeError('io')
        s._call_tool_async = boom
        r = s.handle({'jsonrpc': '2.0', 'id': 15, 'method': 'tools/call',
                      'params': {'name': 'x'}})
        assert r['error']['code'] == -32603
        assert r['error']['data']['type'] == 'RuntimeError'

    def test_write_lock_serializes(self):
        s = _server()
        s._write({'a': 1})
        s._notify('m/x', {})
        lines = _out_bytes(s).decode('utf-8').strip().splitlines()
        assert json.loads(lines[0]) == {'a': 1}
        assert json.loads(lines[1])['method'] == 'm/x'


class TestServeForever:
    def _run(self, data):
        s = mcp.MCPServer(stdin=io.BytesIO(data), stdout=io.BytesIO())
        s.serve_forever()
        return s, [json.loads(l) for l in
                   _out_bytes(s).decode('utf-8').strip().splitlines()]

    def test_parse_error_and_eof(self):
        s, outs = self._run(b'not-json\n')
        assert outs[0]['error']['code'] == -32700
        assert outs[0]['id'] is None

    def test_request_sequence_and_close(self):
        reqs = [
            json.dumps({'jsonrpc': '2.0', 'id': 1,
                        'method': 'initialize'}).encode(),
            json.dumps({'jsonrpc': '2.0', 'id': 2,
                        'method': 'ping'}).encode(),
        ]
        data = b'\n'.join(reqs) + b'\n'
        s, outs = self._run(data)
        assert outs[0]['result']['protocolVersion']
        assert outs[1]['result'] == {}
        assert outs[1]['id'] == 2
        assert mcp._EVENT_FORWARDING.get('server') is not s  # close 撤订阅

    def test_content_length_frame(self):
        body = json.dumps({'jsonrpc': '2.0', 'id': 9,
                           'method': 'ping'}).encode()
        frame = b'Content-Length: %d\r\n\r\n%s' % (len(body), body)
        s, outs = self._run(frame + b'\n')
        assert outs[-1]['id'] == 9 and outs[-1]['result'] == {}

    def test_empty_line_skipped(self):
        s, outs = self._run(b'\n\n' + json.dumps(
            {'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}).encode() + b'\n')
        assert len(outs) == 1


# ── 工具层 ──

class TestRequiredParams:
    def test_fixed_tools_have_required(self):
        s = _server()
        req = s._required_params('actus_registry_add')
        assert isinstance(req, tuple) and 'name' in req
        assert s._required_params('actus_no_such_tool') == ()
        assert s._required_params('actus_registry_add') is req  # 缓存

    def test_list_tools_fixed_no_index_io(self):
        s = _server()
        tools = s._list_tools(with_dynamic=False)
        names = [t['name'] for t in tools]
        assert 'actus_list' in names and 'actus_status' in names

    def test_list_tools_dynamic(self):
        s = _server()
        tools = s._list_tools(with_dynamic=True)
        assert isinstance(tools, list) and len(tools) >= 1


class TestCallToolConvergence:
    def test_action_error_keeps_code(self):
        s = _server()
        def boom(p):
            raise err_mod.ActionError('mycode', 'my message')
        s._call_tool_inner = boom
        r = s._call_tool({'name': 'x'})
        assert r['isError'] is True
        payload = json.loads(r['content'][0]['text'])
        assert payload['error']['code'] == 'mycode'
        assert payload['error']['details']['tool'] == 'x'

    def test_valueerror_param_invalid(self):
        s = _server()
        s._call_tool_inner = lambda p: (_ for _ in ()).throw(
            ValueError('bad'))
        payload = json.loads(s._call_tool({'name': 'x'})['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_other_internal(self):
        s = _server()
        s._call_tool_inner = lambda p: (_ for _ in ()).throw(
            RuntimeError('x'))
        payload = json.loads(s._call_tool({'name': 'x'})['content'][0]['text'])
        assert payload['error']['code'] == 'internal'


class TestCallToolInnerHead:
    def test_arguments_not_dict(self):
        # 空 list 会被 `or {}` 归一，非空非 dict 才触发收敛分支
        s = _server()
        r = s._call_tool({'name': 'actus_list', 'arguments': [1]})
        payload = json.loads(r['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_missing_required(self):
        s = _server()
        r = s._call_tool({'name': 'actus_registry_add', 'arguments': {}})
        payload = json.loads(r['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'
        assert 'name' in payload['error']['details']['missing']

    def test_info_alias_id_to_action_id(self):
        s = _server()
        r = s._call_tool({'name': 'actus_info',
                          'arguments': {'id': 'zzz-ghost'}})
        payload = json.loads(r['content'][0]['text'])
        # 走过了 alias 归一（否则报 missing action_id），落到动作不存在
        assert payload['status'] == 'failed'
        assert '缺少必需参数' not in payload['error']['message']

    def test_actus_list(self):
        s = _server()
        r = s._call_tool({'name': 'actus_list', 'arguments': {}})
        payload = json.loads(r['content'][0]['text'])
        assert payload['status'] == 'ok'
        rows = payload['data']['actions']
        assert isinstance(rows, list)
        if rows:
            assert rows[0]['tool'].startswith('actus_')

    def test_actus_search(self):
        s = _server()
        r = s._call_tool({'name': 'actus_search',
                          'arguments': {'query': 'zzz-no-match'}})
        payload = json.loads(r['content'][0]['text'])
        assert payload['status'] == 'ok'
        assert payload['data']['total'] == 0
        assert payload['data']['actions'] == []

    def test_actus_status_task(self):
        s = _server()
        tid = mcp._new_task('actus_x', {'k': 1})
        mcp._finish_task(tid, status='ok', result={'v': 2})
        r = s._call_tool({'name': 'actus_status',
                          'arguments': {'task_id': tid}})
        payload = json.loads(r['content'][0]['text'])
        data = payload.get('data') or payload
        assert json.dumps(data).find('actus_x') != -1


class TestCallToolAsync:
    def _as_action(self, monkeypatch):
        monkeypatch.setattr(mcp, '_action_tool_map',
                            lambda ttl=5.0: {'actus_basics_calculator':
                                             'basics.calculator'},
                            raising=False)

    def test_non_action_tool_sync(self, monkeypatch):
        s = _server()
        s._call_tool = lambda p: {'sync': 1}
        assert s._call_tool_async({'name': 'actus_list'}) == {'sync': 1}

    def test_capacity_full(self, monkeypatch):
        self._as_action(monkeypatch)
        monkeypatch.setattr(mcp, '_running_task_count', lambda: mcp._TASK_RUNNING_MAX,
                            raising=False)
        s = _server()
        r = s._call_tool_async({'name': 'actus_basics_calculator'})
        assert r['isError'] is True
        payload = json.loads(r['content'][0]['text'])
        assert payload['error']['code'] == 'task_capacity'

    def test_fast_inline_finish(self, monkeypatch):
        self._as_action(monkeypatch)
        class _Pool:
            def submit(self, fn, *a):
                class _F:
                    def result(self, timeout):
                        return fn(*a)
                return _F()
        monkeypatch.setattr(mcp, '_task_pool', lambda: _Pool(),
                            raising=False)
        s = _server()
        s._call_tool = lambda p: {'sync': 1}
        r = s._call_tool_async({'name': 'actus_basics_calculator',
                                'arguments': {}})
        assert r == {'sync': 1}  # grace 内完成 → 直接同步形状

    def test_slow_returns_running_handle(self, monkeypatch):
        self._as_action(monkeypatch)
        class _SlowF:
            def result(self, timeout):
                time.sleep(0.01)
                raise mcp.FutureTimeout()
        class _Pool:
            def submit(self, fn, *a):
                return _SlowF()
        monkeypatch.setattr(mcp, '_task_pool', lambda: _Pool(),
                            raising=False)
        s = _server()
        r = s._call_tool_async({'name': 'actus_basics_calculator',
                                'arguments': {}})
        assert r['isError'] is False
        payload = json.loads(r['content'][0]['text'])
        assert payload['status'] == 'running'
        assert payload['task_id'].startswith('task-')
        assert mcp._task_snapshot(payload['task_id'])['status'] == 'running'


class TestRunTask:
    def _s_with_out(self):
        s = _server()
        return s

    def test_ok(self):
        s = self._s_with_out()
        s._call_tool = lambda p: {'isError': False}
        tid = mcp._new_task('actus_x', {})
        result = s._run_task(tid, {'name': 'actus_x'})
        assert result == {'isError': False}
        assert mcp._task_snapshot(tid)['status'] == 'ok'

    def test_raises_marked_failed(self):
        s = self._s_with_out()
        def boom(p):
            raise RuntimeError('boom')
        s._call_tool = boom
        tid = mcp._new_task('actus_x', {})
        result = s._run_task(tid, {'name': 'actus_x'})
        assert result['isError'] is True
        assert mcp._task_snapshot(tid)['status'] == 'failed'


class TestSelfdriveRunTool:
    def _call(self, args):
        return _server()._call_tool({'name': 'actus_selfdrive_run',
                                     'arguments': args})

    def test_goal_required(self):
        payload = json.loads(self._call({})['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_bad_ints(self):
        payload = json.loads(self._call(
            {'goal': 'g', 'max_depth': 'x'})['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_dry_run(self):
        r = self._call({'goal': 'write a haiku', 'dry_run': True,
                        'max_depth': 1, 'max_rounds': 1})
        payload = json.loads(r['content'][0]['text'])
        assert payload['status'] == 'ok' and payload['dry_run'] is True
        assert payload['leaf_count'] >= 0

    def test_worker_action_needs_plan(self):
        payload = json.loads(self._call(
            {'goal': 'g', 'worker': 'action'})['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_plan_unserializable(self):
        payload = json.loads(self._call(
            {'goal': 'g', 'plan': {'bad': object()}})['content'][0]['text'])
        assert payload['error']['code'] == 'param_invalid'

    def test_echo_run(self):
        r = self._call({'goal': 'noop goal', 'max_depth': 0,
                        'max_rounds': 1})
        payload = json.loads(r['content'][0]['text'])
        assert payload['status'] == 'ok'
        assert payload['worker_kind'] == 'echo'


# ── 事件转发订阅管理 ──

class TestEventForwarding:
    def test_setup_and_close_idempotent(self):
        s = _server()
        assert mcp._EVENT_FORWARDING.get('server') is s
        s.close()
        assert mcp._EVENT_FORWARDING.get('server') is not s
        s.close()  # 幂等
