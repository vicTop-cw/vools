# -*- coding: utf-8 -*-
"""mcp_server.py 契约测试 batch 2（r74b）：_call_tool_inner 全部分发臂 +
模块级 _handle_* 处理函数（vault/registry/team/visibility/triggers/deps/
execute/records/artifacts/bug/evolve/webhook/project/highlight/动态动作）。

**BUG-M1（现状佐证，未修）**：`_call_tool_inner` 的 `actus_triggers_add`
分支（mcp_server.py:2238）引用局部变量 `meta_dir`，但该名字只在
`actus_workflow_run`（:2055）与 `actus_workflow_status`（:2072）分支内赋值
—— 同一次调用的互斥 if 分支不可能先执行，`meta_dir` 在 triggers_add
分支里**必然未定义** → NameError。后果：MCP 的 `actus_triggers_add`
工具从上线起不可用（错误被 _call_tool 收敛成 internal/NameError）。
"""
import importlib
import io
import json
import os
import sys
import types

import pytest

import _ai_local_bootstrap  # noqa: F401

mcp = importlib.import_module('vools.actus.mcp_server')
pkg = importlib.import_module('vools.actus')
err_mod = importlib.import_module('vools.actus.errors')


def _server():
    return mcp.MCPServer(stdin=io.BytesIO(), stdout=io.BytesIO())


def _call(name, args=None):
    r = _server()._call_tool({'name': name, 'arguments': args or {}})
    return json.loads(r['content'][0]['text']), r['isError']


def _patch_module_fn(monkeypatch, module_name, fn_name, fn):
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(mod, fn_name, fn)


# ── 环境隔离 ──

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    meta = tmp_path / 'meta'
    # _save_trigger_registry 直接 open() 不建目录 → 预先建好
    meta.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('ACTUS_META_DIR', str(meta))
    monkeypatch.setenv('ACTUS_CONFIG_DIR', str(tmp_path / 'config'))
    mcp._webhook_receiver['instance'] = None
    mcp._project_orchestrators.clear()
    # 前序测试模块可能已创建绑定旧 meta 目录的单例引擎 →
    # setup 时先停掉并清空，保证本模块每个测试拿到新引擎
    stale = getattr(pkg, '_trigger_engine', None)
    if stale is not None:
        try:
            stale.stop()
        except Exception:
            pass
        try:
            delattr(pkg, '_trigger_engine')
        except AttributeError:
            pass
    yield
    mcp._webhook_receiver['instance'] = None
    mcp._project_orchestrators.clear()
    cur = getattr(pkg, '_trigger_engine', None)
    if cur is not None:
        try:
            cur.stop()
        except Exception:
            pass
        try:
            delattr(pkg, '_trigger_engine')
        except AttributeError:
            pass


class _FakeReport:
    def __init__(self, items=None):
        self.items = items or []

    def to_dict(self):
        return {'overall': 'ok', 'items': [i.to_dict() for i in self.items]}


class _Item:
    def __init__(self, category):
        self.category = category

    def to_dict(self):
        return {'category': self.category}


class _FakeReceiver:
    def __init__(self):
        self.is_running = True
        self.routes = {}
        self.stopped = False
        self._logs = [{'ts': 't', 'event': 'e'}]

    def start_background(self):
        pass

    def stop(self):
        self.stopped = True

    def get_status(self):
        return {'running': self.is_running, 'routes': len(self.routes)}

    def register_route(self, event_type, action_id):
        self.routes[event_type] = action_id

    def unregister_route(self, event_type):
        return self.routes.pop(event_type, None)

    def get_logs(self, limit=50):
        return self._logs[:limit]


# ── recommend / validate / health / info / status / cost ──

class TestRecommendValidateHealth:
    def test_recommend(self):
        payload, err = _call('actus_recommend',
                             {'description': 'zzz-没有匹配的描述'})
        assert err is False
        assert payload['status'] == 'ok'
        assert 'recommendations' in payload['data']

    def test_validate_repo_scope(self):
        payload, err = _call('actus_validate', {})
        assert err is False
        assert payload['scope'] == 'repo'
        assert payload['checked'] > 0

    def test_validate_single(self):
        payload, err = _call('actus_validate',
                             {'action_id': 'actus.basics.calculator'})
        assert err is False
        assert payload['scope'] == 'action' and payload['valid'] is True

    def test_validate_unknown_action(self):
        payload, err = _call('actus_validate', {'action_id': 'zzz-ghost'})
        assert err is True  # get_action 抛 ActionError → 保留错误码

    def test_health(self):
        payload, err = _call('actus_health', {})
        assert payload['overall'] in ('ok', 'warn', 'error')
        assert isinstance(payload['counts'], dict)
        assert isinstance(payload['checks'], list)

    def test_info_ok_and_unknown(self):
        payload, err = _call('actus_info',
                             {'action_id': 'actus.basics.calculator'})
        assert err is False and payload['data']['name'] == 'Calculator'
        payload, err = _call('actus_info', {'action_id': 'zzz-ghost'})
        assert err is True

    def test_status_default_and_exec(self):
        payload, err = _call('actus_status', {})
        assert err is False
        assert 'event_subscribers' in payload['data']
        payload, err = _call('actus_status', {'exec_id': 'ghost-exec'})
        assert err is True
        assert payload['error']['code'] == 'action_not_found'

    def test_cost(self):
        payload, err = _call('actus_cost', {})
        assert err is False
        assert payload['data']['recorded'] is False
        assert '暂无记账' in payload['data']['message']
        assert 'budget' in payload['data']


# ── preview / confirm / scaffold / author / publish ──

class TestPreviewConfirmScaffold:
    def test_preview_ok_and_unknown(self):
        payload, err = _call('actus_preview',
                             {'action_id': 'actus.basics.calculator'})
        assert err is False and payload['status'] == 'ok'
        payload, err = _call('actus_preview', {'action_id': 'zzz-ghost'})
        assert err is True

    def test_confirm_not_implemented(self):
        # 现状佐证：根模块没有 confirm() API → AttributeError 分支 → 诚实错误
        payload, err = _call('actus_confirm', {'exec_id': 'x'})
        assert err is True
        assert payload['error']['code'] == 'internal'
        assert '未实现' in payload['error']['message']

    def test_scaffold_real(self, monkeypatch, tmp_path):
        monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
        payload, err = _call('actus_scaffold',
                             {'description': '计算两数之和', 'trust': 'sandbox'})
        assert err is False
        assert payload['validation']['valid'] is True
        assert os.path.isdir(os.path.join(str(tmp_path), 'actions'))

    def test_author_ok_and_action_error(self, monkeypatch):
        def fake_ok(aid, instruction, repo_root=None):
            return {'status': 'ok', 'action_id': aid}
        _patch_module_fn(monkeypatch, 'vools.actus.author',
                         'author_action', fake_ok)
        payload, err = _call('actus_author',
                             {'action_id': 'a', 'instruction': 'i'})
        assert err is False and payload['status'] == 'ok'

        def fake_raise(aid, instruction, repo_root=None):
            raise err_mod.ActionError('nope', 'x')
        _patch_module_fn(monkeypatch, 'vools.actus.author',
                         'author_action', fake_raise)
        payload, err = _call('actus_author',
                             {'action_id': 'a', 'instruction': 'i'})
        assert err is True and payload['error']['code'] == 'nope'

    def test_publish_ok_and_error(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.author', 'publish_action',
                         lambda aid, repo_root=None, force=False:
                         {'status': 'published'})
        payload, err = _call('actus_publish', {'action_id': 'a'})
        assert err is False and payload['status'] == 'published'

        def fake_raise(aid, repo_root=None, force=False):
            raise err_mod.ActionError('nope', 'x')
        _patch_module_fn(monkeypatch, 'vools.actus.author', 'publish_action',
                         fake_raise)
        payload, err = _call('actus_publish', {'action_id': 'a'})
        assert err is True


# ── workflow ──

class TestWorkflow:
    def test_run_ok_and_error(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.workflow', 'run_workflow',
                         lambda wf_id, meta_dir='', max_workers=4,
                         confirmed=True: {'status': 'ok'})
        payload, err = _call('actus_workflow_run', {'workflow_id': 'w'})
        assert err is False

        def fake_raise(wf_id, meta_dir='', max_workers=4, confirmed=True):
            raise err_mod.ActionError('wf', 'x')
        _patch_module_fn(monkeypatch, 'vools.actus.workflow', 'run_workflow',
                         fake_raise)
        payload, err = _call('actus_workflow_run', {'workflow_id': 'w'})
        assert err is True and payload['error']['code'] == 'wf'

    def test_status_found_and_missing(self, monkeypatch, tmp_path):
        wf_dir = os.path.join(str(tmp_path), 'meta', 'workflows')
        os.makedirs(wf_dir)
        with open(os.path.join(wf_dir, 'w1.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'status': 'ok'}, f)
        payload, err = _call('actus_workflow_status', {'workflow_id': 'w1'})
        assert err is False and payload['status'] == 'ok'
        payload, err = _call('actus_workflow_status', {'workflow_id': 'w2'})
        assert err is True and payload['status'] == 'not_found'


# ── vault ──

class TestVault:
    def test_set_ok_and_refused_hint(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'write_secret',
                         lambda key, value, scope, meta_dir='',
                         allow_v1_write=False: {'status': 'ok'})
        payload, err = _call('actus_vault_set', {'key': 'k', 'value': 'v'})
        assert err is False

        def fake_refused(key, value, scope, meta_dir='',
                         allow_v1_write=False):
            return {'status': 'refused', 'code': 'vault2_unavailable'}
        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'write_secret',
                         fake_refused)
        payload, err = _call('actus_vault_set', {'key': 'k', 'value': 'v'})
        assert '出路' in payload['hint']

    def test_get_three_shapes(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'resolve_secret',
                         lambda key, scope, meta_dir='':
                         {'status': 'ok', 'value': 'v', 'source': 'v2'})
        payload, err = _call('actus_vault_get', {'key': 'k'})
        assert err is False and payload['value'] == 'v'

        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'resolve_secret',
                         lambda key, scope, meta_dir='': {'status': 'conflict'})
        payload, err = _call('actus_vault_get', {'key': 'k'})
        assert err is True

        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'resolve_secret',
                         lambda key, scope, meta_dir='':
                         {'status': 'missing', 'message': 'gone'})
        payload, err = _call('actus_vault_get', {'key': 'k'})
        assert payload['status'] == 'not_found' and payload['message'] == 'gone'

    def test_list_and_delete(self, monkeypatch):
        monkeypatch.setattr(mcp, '_vault_list_merged',
                            lambda md, scope: {'status': 'ok', 'items': []})
        payload, err = _call('actus_vault_list', {})
        assert err is False and payload['items'] == []

        seen = {}

        def fake_delete(key, scope, meta_dir='', include_v1=False,
                        caller=''):
            seen['include_v1'] = include_v1
            return {'status': 'ok', 'hint': 'orig'}
        # patch 底层 vault.delete_secret，保留 _vault_delete_merged 的
        # hint 改写逻辑（那才是被测对象）
        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'delete_secret',
                         fake_delete)
        payload, err = _call('actus_vault_delete', {'key': 'k'})
        assert err is False and seen['include_v1'] is False
        assert '默认只删 v2' in payload['hint']
        _call('actus_vault_delete', {'key': 'k', 'include_v1': True})
        assert seen['include_v1'] is True

    def test_migrate(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.vault',
                         'migrate_legacy_secrets',
                         lambda dry_run=False, meta_dir='', scope='global':
                         {'status': 'ok', 'migrated': 0})
        payload, err = _call('actus_vault_migrate', {})
        assert err is False

    def test_rotate_seed(self, monkeypatch):
        # schema required ['confirm'] → 头部校验先命中 param_invalid
        payload, err = _call('actus_vault_rotate_seed', {})
        assert err is True and payload['error']['code'] == 'param_invalid'
        # 分支级确认门：confirm 非真值
        payload, err = _call('actus_vault_rotate_seed', {'confirm': False})
        assert err is True and payload['error']['code'] == \
            'confirmation_required'

        _patch_module_fn(monkeypatch, 'vools.actus.vault',
                         'rotate_seed_key_v2',
                         lambda caller='': {'status': 'ok'})
        payload, err = _call('actus_vault_rotate_seed', {'confirm': True})
        assert err is False

        def fake_raise(caller=''):
            raise RuntimeError('boom')
        _patch_module_fn(monkeypatch, 'vools.actus.vault',
                         'rotate_seed_key_v2', fake_raise)
        payload, err = _call('actus_vault_rotate_seed', {'confirm': True})
        assert payload['error']['code'] == 'rotate_failed'

    def test_rotate_kek(self, monkeypatch):
        # schema required ['confirm'] → 缺参 param_invalid
        payload, err = _call('actus_vault_rotate_kek', {})
        assert err is True and payload['error']['code'] == 'param_invalid'

        seen = {}

        def fake_rotate(dry_run=False, mode=None, caller=''):
            seen.update({'dry_run': dry_run, 'mode': mode})
            return {'status': 'ok'}
        _patch_module_fn(monkeypatch, 'vools.actus.vault', 'rotate_kek_v2',
                         fake_rotate)
        payload, err = _call('actus_vault_rotate_kek',
                             {'confirm': True, 'dry_run': True,
                              'mode': 'pin'})
        assert err is False and seen == {'dry_run': True, 'mode': 'pin'}


# ── runtimes / probe / deps / triggers ──

class TestRuntimesProbeDepsTriggers:
    def test_runtimes(self):
        payload, err = _call('actus_runtimes', {})
        assert err is False and 'python' in payload['available']

    def test_probe(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.probe', 'probe',
                         lambda force_refresh=False, max_age=3600:
                         _FakeReport([_Item('python'), _Item('node')]))
        payload, err = _call('actus_probe', {})
        assert err is False and payload['report']['overall'] == 'ok'
        payload, err = _call('actus_probe', {'category': 'python'})
        assert err is False and payload['total'] == 1

        def fake_raise(force_refresh=False, max_age=3600):
            raise RuntimeError('x')
        _patch_module_fn(monkeypatch, 'vools.actus.probe', 'probe', fake_raise)
        payload, err = _call('actus_probe', {})
        assert payload['error']['code'] == 'probe_error'

    def test_deps_and_tree(self, monkeypatch):
        # 真 check_action_deps 依赖其自身 actions root 解析（环境相关），
        # 这里 patch 掉被委托函数，验证分派臂 + 结果透传
        _patch_module_fn(monkeypatch, 'vools.actus.dependency',
                         'check_action_deps',
                         lambda action_id, **kw: {'status': 'ok',
                                                  'deps': []})
        payload, err = _call('actus_deps',
                             {'action_id': 'actus.basics.calculator'})
        assert err is False and payload['status'] == 'ok'

        class _FakeResolver:
            def get_dep_tree(self, action_id):
                return {'name': action_id, 'children': []}
        _patch_module_fn(monkeypatch, 'vools.actus.dependency',
                         'get_resolver', lambda: _FakeResolver())
        payload, err = _call('actus_dep_tree',
                             {'action_id': 'actus.basics.calculator'})
        assert err is False and 'tree' in payload

    def test_triggers_list_status(self):
        payload, err = _call('actus_triggers_list', {})
        assert err is False and payload['triggers'] == {}
        payload, err = _call('actus_triggers_status', {})
        assert err is False and 'running' in payload['engine']

    def test_triggers_add_nameerror_bug_m1(self):
        # BUG-M1：分支引用未定义的局部 meta_dir → UnboundLocalError
        # （收敛成 internal；details 只带 tool）
        payload, err = _call('actus_triggers_add',
                             {'action_id': 'a', 'type': 'cron',
                              'expr': '* * * * *'})
        assert err is True
        assert payload['error']['code'] == 'internal'
        assert 'meta_dir' in payload['error']['message']
        assert payload['error']['details'] == {'tool': 'actus_triggers_add'}

    def test_triggers_remove(self):
        payload, err = _call('actus_triggers_remove', {'action_id': 'a'})
        assert err is False and payload['removed'] == 'a'


# ── execute / records / artifacts / bug ──

class TestExecuteRecordsArtifactsBug:
    def test_execute_param_errors(self):
        # schema required ['language','code'] → 缺参在头部命中 param_invalid
        payload, err = _call('actus_execute', {})
        assert err is True
        assert payload['error']['code'] == 'param_invalid'
        assert payload['error']['details']['missing'] == ['language', 'code']
        payload, err = _call('actus_execute', {'language': 'python'})
        assert err is True
        assert payload['error']['details']['missing'] == ['code']
        payload, err = _call('actus_execute',
                             {'language': 'cobol', 'code': 'x'})
        assert payload['error']['code'] == 'unsupported_language'
        payload, err = _call('actus_execute',
                             {'language': 'python', 'code': 'x',
                              'timeout': 'x'})
        assert payload['error']['code'] == 'param_invalid'

    def test_execute_python_real(self):
        payload, err = _call('actus_execute',
                             {'language': 'python', 'code': 'print("hi")'})
        assert err is False and payload['exit_code'] == 0
        assert 'hi' in payload['stdout']

    def test_execute_timeout_zero_runs(self):
        payload, err = _call('actus_execute',
                             {'language': 'python', 'code': 'print(1)',
                              'timeout': 0})
        assert err is False

    def test_records_list_and_export(self):
        payload, err = _call('actus_records_list', {})
        assert err is False and payload['total'] == 0
        payload, err = _call('actus_records_export',
                             {'format': 'bogus'})
        assert payload['error']['code'] == 'invalid_format'
        payload, err = _call('actus_records_export', {'format': 'json'})
        assert err is False

    def test_artifacts(self):
        payload, err = _call('actus_artifacts_list', {})
        assert err is False and payload['total'] == 0
        payload, err = _call('actus_artifacts_cleanup', {})
        assert err is False

    def test_bug_list_and_report(self, tmp_path):
        payload, err = _call('actus_bug_list',
                             {'project_dir': str(tmp_path)})
        assert err is False and payload['count'] == 0
        real_note = tmp_path / 'notes.md'
        real_note.write_text('evidence', encoding='utf-8')
        payload, err = _call('actus_bug_report',
                             {'project_dir': str(tmp_path),
                              'summary': 'r74b bug',
                              # source 必须是 project_dir 内真实存在的文件
                              'source': str(real_note)})
        assert err is False
        assert payload['bug_status'] == 'OPEN' and payload['id'] == 'BUG-0001'
        payload, err = _call('actus_bug_report',
                             {'project_dir': str(tmp_path), 'summary': ''})
        assert err is True and payload['error']['code'] == 'param_invalid'


# ── evolve ──

class TestEvolve:
    def test_missing_params(self):
        # schema required 先命中 → 全部收敛为 param_invalid + missing 明细
        payload, err = _call('actus_evolve', {})
        assert err is True
        assert payload['error']['code'] == 'param_invalid'
        assert payload['error']['details']['missing'] == ['description']
        payload, err = _call('actus_evolve_repair', {})
        assert payload['error']['details']['missing'] == ['action_id']
        payload, err = _call('actus_evolve_history', {})
        assert payload['error']['details']['missing'] == ['action_id']
        payload, err = _call('actus_evolve_rollback', {'action_id': 'a'})
        assert payload['error']['details']['missing'] == ['version']
        payload, err = _call('actus_evolve_compare', {'action_id': 'a'})
        assert payload['error']['details']['missing'] == ['v1', 'v2']

    def test_status_and_history_and_list(self):
        payload, err = _call('actus_evolve_status', {'action_id': 'zzz'})
        assert err is True and payload['status'] == 'not_found'
        payload, err = _call('actus_evolve_history', {'action_id': 'zzz'})
        assert err is False and payload['history'] == []
        payload, err = _call('actus_evolve_list', {})
        assert err is False and payload['total'] == 0

    def test_rollback_and_compare_real(self):
        payload, err = _call('actus_evolve_rollback',
                             {'action_id': 'zzz', 'version': 1})
        assert isinstance(payload, dict)  # 版本不存在 → 错误 dict
        payload, err = _call('actus_evolve_compare',
                             {'action_id': 'zzz', 'v1': 1, 'v2': 2})
        assert isinstance(payload, dict)

    def test_evolve_and_repair_no_llm(self):
        payload, err = _call('actus_evolve', {'description': '做一个加法'})
        assert isinstance(payload, dict)  # 无 LLM → 失败 dict
        payload, err = _call('actus_evolve_repair', {'action_id': 'zzz'})
        assert isinstance(payload, dict)


# ── webhook ──

class TestWebhook:
    def test_start_and_stop(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.webhook',
                         'create_receiver',
                         lambda host='', port=0, secret='',
                         require_signature=True: _FakeReceiver())
        payload, err = _call('actus_webhook_start', {'port': 1})
        assert err is False and 'started' in payload['message']
        payload, err = _call('actus_webhook_start_background', {})
        assert err is False
        payload, err = _call('actus_webhook_stop', {})
        assert err is False and 'stopped' in payload['message']
        payload, err = _call('actus_webhook_stop', {})
        assert err is True  # 已停 → error

    def test_status_register_unregister_logs(self, monkeypatch):
        mcp._webhook_receiver['instance'] = _FakeReceiver()
        payload, err = _call('actus_webhook_status', {})
        assert err is False and payload['running'] is True
        payload, err = _call('actus_webhook_register',
                             {'event_type': 'e', 'action_id': 'a'})
        assert err is False and payload['registered'] is True
        payload, err = _call('actus_webhook_unregister',
                             {'event_type': 'e'})
        assert err is False and payload['removed'] is True
        payload, err = _call('actus_webhook_unregister',
                             {'event_type': 'zz'})
        assert err is False and payload['removed'] is False
        payload, err = _call('actus_webhook_logs', {})
        assert err is False and payload['total'] == 1

    def test_no_receiver_errors(self):
        for tool, args in (('actus_webhook_status', {}),
                           ('actus_webhook_register', {}),
                           ('actus_webhook_unregister', {}),
                           ('actus_webhook_logs', {})):
            payload, err = _call(tool, args)
            if tool != 'actus_webhook_status':
                assert err is True, tool


# ── project ──

class _FakeOrch:
    def __init__(self):
        self.config = types.SimpleNamespace(name='P', modules={},
                                            languages=['python'])
        self.phases = []

    def run_pipeline(self, phase=None):
        self.phases.append(phase)
        return {'status': 'ok', 'phase': phase}

    def validate(self):
        return True, []

    def add_module(self, module):
        self.config.modules[module.id] = module

    def remove_module(self, module_id):
        self.config.modules.pop(module_id, None)

    def get_status(self):
        return {'status': 'ok'}


class _FakeModule:
    def __init__(self, id='', language='', path='', build_cmd='',
                 test_cmd=''):
        self.id = id


class TestProject:
    def _patch(self, monkeypatch):
        orch = _FakeOrch()
        monkeypatch.setattr(mcp, '_get_orchestrator', lambda wd: orch)
        _patch_module_fn(monkeypatch, 'vools.actus.project', 'load_project',
                         lambda pf, wd: orch)
        _patch_module_fn(monkeypatch, 'vools.actus.project',
                         'detect_modules', lambda wd: {})
        _patch_module_fn(monkeypatch, 'vools.actus.project',
                         'detect_languages', lambda wd: ['python'])
        _patch_module_fn(monkeypatch, 'vools.actus.project', 'ModuleConfig',
                         _FakeModule)
        return orch

    def test_load_detect_build_test_validate(self, monkeypatch):
        orch = self._patch(monkeypatch)
        payload, err = _call('actus_project_load', {})
        assert err is False and payload['project'] == 'P'
        payload, err = _call('actus_project_detect', {})
        assert err is False and payload['total_modules'] == 0
        payload, err = _call('actus_project_build', {'phase': 'build'})
        assert err is False and payload['status'] == 'ok'
        payload, err = _call('actus_project_test', {})
        assert err is False
        assert orch.phases[-1] == 'test'
        payload, err = _call('actus_project_validate', {})
        assert err is False and payload['valid'] is True

    def test_load_error_and_validate_invalid(self, monkeypatch):
        self._patch(monkeypatch)
        _patch_module_fn(monkeypatch, 'vools.actus.project', 'load_project',
                         lambda pf, wd: (_ for _ in ()).throw(
                             RuntimeError('bad file')))
        payload, err = _call('actus_project_load', {})
        assert err is True and payload['status'] == 'error'
        _patch_module_fn(monkeypatch, 'vools.actus.project', 'load_project',
                         lambda pf, wd: _FakeOrch())

        class _Bad(_FakeOrch):
            def validate(self):
                return False, ['e1']
        _patch_module_fn(monkeypatch, 'vools.actus.project', 'load_project',
                         lambda pf, wd: _Bad())
        payload, err = _call('actus_project_validate', {})
        assert err is True and payload['status'] == 'invalid'

    def test_status_add_remove_module(self, monkeypatch):
        orch = self._patch(monkeypatch)
        payload, err = _call('actus_project_status', {})
        assert err is False and payload['status'] == 'ok'
        # required: module_id/language/path
        payload, err = _call('actus_project_add_module',
                             {'module_id': 'm1', 'language': 'python',
                              'path': 'src'})
        assert err is False and payload['module_id'] == 'm1'
        assert 'm1' in orch.config.modules
        payload, err = _call('actus_project_remove_module',
                             {'module_id': 'm1'})
        assert err is False and payload['removed'] == 'm1'


# ── highlight + 动态动作工具 ──

class TestHighlightAndDynamic:
    def test_highlight_unavailable(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.highlight',
                         'check_shiki_available', lambda: False)
        payload, err = _call('actus_highlight', {'code': 'x'})
        assert err is True
        assert payload['error']['code'] == 'shiki_unavailable'

    def test_highlight_ok(self, monkeypatch):
        _patch_module_fn(monkeypatch, 'vools.actus.highlight',
                         'check_shiki_available', lambda: True)
        _patch_module_fn(monkeypatch, 'vools.actus.highlight', 'highlight_code',
                         lambda code, lang, theme='', mode='': '<b>%s</b>'
                         % code)
        payload, err = _call('actus_highlight', {'code': 'x=1'})
        assert err is False and payload['highlighted'] == '<b>x=1</b>'
        assert payload['lang'] == 'python'

    def test_dynamic_tool_reverse_lookup(self, monkeypatch):
        # 真实 calculator 动作是 webview2 GUI 块（执行会开窗口）——
        # 这里 patch 掉 actuscore.execute，只验证反查 + inner 参数透传 + 收敛
        seen = {}

        def fake_execute(aid, params):
            seen['aid'] = aid
            seen['params'] = params
            return {'status': 'ok', 'echo': True}
        _patch_module_fn(monkeypatch, 'vools.actus', 'execute', fake_execute)
        payload, err = _call('actus_basics_calculator',
                             {'expression': '1+1'})
        assert err is False and payload['status'] == 'ok'
        assert seen['aid'] == 'actus.basics.calculator'
        assert seen['params'] == {'expression': '1+1'}

    def test_unknown_tool(self):
        payload, err = _call('actus_zzz_ghost_tool', {})
        assert err is True
        assert payload['error']['code'] == 'action_not_found'
