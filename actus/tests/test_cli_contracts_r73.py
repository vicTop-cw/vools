# -*- coding: utf-8 -*-
"""cli.py 契约测试 batch 3（r73）：webhook/project-mgmt/omega/concurrency/deps/
desktop/events/viz/replay/notify/project_io/export/probe/cost/selfdrive/health/
selfheal/template/loop + dispatch 大分支（scan/list/validate/info/preview/
status/run）。"""
import importlib
import json
import os
import sys
import types

import pytest

import _ai_local_bootstrap  # noqa: F401

cli = importlib.import_module('vools.actus.cli')
webhook_mod = importlib.import_module('vools.actus.webhook')
project_mod = importlib.import_module('vools.actus.project')
omega_mod = importlib.import_module('vools.actus.omega')
dep_mod = importlib.import_module('vools.actus.dependency')
notify_mod = importlib.import_module('vools.actus.notify')
pio_mod = importlib.import_module('vools.actus.project_io')
export_mod = importlib.import_module('vools.actus.export')
probe_mod = importlib.import_module('vools.actus.probe')
cost_mod = importlib.import_module('vools.actus.cost')
sd_mod = importlib.import_module('vools.actus.selfdrive')
health_mod = importlib.import_module('vools.actus.health')
tmpl_mod = importlib.import_module('vools.actus.template')
eventbus = importlib.import_module('vools.actus.eventbus')
pkg = importlib.import_module('vools.actus')
paths_mod = importlib.import_module('vools.actus.paths')


def NS(**kw):
    return types.SimpleNamespace(**kw)


def _fake_mod(monkeypatch, name, **attrs):
    """在 sys.modules 里塞假模块并打上属性（供函数内 `import x` 命中）。"""
    real = sys.modules.get(name)
    fake = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(fake, k, v)
    monkeypatch.setitem(sys.modules, name, fake)
    return real


# ── _cmd_webhook ──

class _FakeReceiver:
    def __init__(self, running=True, routes=None):
        self.is_running = running
        self.calls = []
        self.routes = routes or {}

    def stop(self):
        self.calls.append('stop')
        self.is_running = False

    def get_status(self):
        return {'running': True, 'routes': len(self.routes)}

    def get_logs(self, limit=20):
        return [{'timestamp': 1700000000, 'client_ip': '1.2.3.4',
                 'event_type': 'e', 'action_id': 'a.b'}][:limit]

    def register_route(self, event_type, action_id):
        self.calls.append(('register', event_type, action_id))

    def unregister_route(self, event_type):
        self.calls.append(('unregister', event_type))
        return self.routes.pop(event_type, None)


class TestCmdWebhook:
    def test_stop_no_receiver(self, capsys):
        cli._cmd_webhook._receiver = None
        assert cli._cmd_webhook(NS(stop=True, status=False, logs=None,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert '没有运行中' in capsys.readouterr().out

    def test_stop_running(self, capsys):
        rec = _FakeReceiver()
        cli._cmd_webhook._receiver = rec
        assert cli._cmd_webhook(NS(stop=True, status=False, logs=None,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert rec.calls == ['stop']
        assert cli._cmd_webhook._receiver is None

    def test_status(self, tmp_path, monkeypatch, capsys):
        cli._cmd_webhook._receiver = None
        assert cli._cmd_webhook(NS(stop=False, status=True, logs=None,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert '未运行' in capsys.readouterr().out
        rec = _FakeReceiver(routes={'e': 'a'})
        cli._cmd_webhook._receiver = rec
        assert cli._cmd_webhook(NS(stop=False, status=True, logs=None,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['routes'] == 1

    def test_logs(self, capsys):
        cli._cmd_webhook._receiver = _FakeReceiver()
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=5,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        out = capsys.readouterr().out
        assert '最近 1 条' in out and 'a.b' in out

    def test_logs_no_receiver(self, capsys):
        cli._cmd_webhook._receiver = None
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=5,
                                   register=None, unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert '未运行' in capsys.readouterr().out

    def test_register(self, capsys):
        rec = _FakeReceiver()
        cli._cmd_webhook._receiver = rec
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=None,
                                   register=('evt', 'a.b'), unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert rec.calls == [('register', 'evt', 'a.b')]

    def test_register_not_running(self, capsys):
        cli._cmd_webhook._receiver = None
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=None,
                                   register=('evt', 'a.b'), unregister=None,
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 1

    def test_unregister(self, capsys):
        rec = _FakeReceiver(routes={'evt': 'a.b'})
        cli._cmd_webhook._receiver = rec
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=None,
                                   register=None, unregister='evt',
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert '路由移除' in capsys.readouterr().out
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=None,
                                   register=None, unregister='evt',
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 0
        assert '路由不存在' in capsys.readouterr().out

    def test_unregister_not_running(self, capsys):
        cli._cmd_webhook._receiver = None
        assert cli._cmd_webhook(NS(stop=False, status=False, logs=None,
                                   register=None, unregister='evt',
                                   host='h', port=1, secret=None,
                                   no_signature=False)) == 1

    def test_start(self, tmp_path, monkeypatch, capsys):
        cli._cmd_webhook._receiver = None
        started = {}

        class R:
            def __init__(self, **kw):
                started['kw'] = kw
                self.is_running = True

            def start(self):
                started['started'] = True

        monkeypatch.setattr(webhook_mod, 'create_receiver', R, raising=False)
        ns = NS(stop=False, status=False, logs=None, register=None,
                unregister=None, host='0.0.0.0', port=9999, secret='s3c',
                no_signature=True)
        assert cli._cmd_webhook(ns) == 0
        assert started['kw']['require_signature'] is False
        assert started['kw']['secret'] == 's3c'
        assert started['started'] is True
        assert cli._cmd_webhook._receiver is None


# ── _cmd_project（project-mgmt）──

class _FakeOrch:
    def __init__(self):
        self.modules = {}

    def validate(self):
        return (True, [])

    def get_status(self):
        return {'modules': 0}

    def add_module(self, mod):
        self.modules[mod.id] = mod

    def remove_module(self, mid):
        self.modules.pop(mid, None)

    def save_project(self, path):
        self.saved = path

    def run_pipeline(self, phase):
        return {'status': 'ok', 'phase': phase}


class TestCmdProjectMgmt:
    def _patch(self, monkeypatch, orch=None, detect=None):
        orch = orch or _FakeOrch()
        monkeypatch.setattr(project_mod, 'load_project',
                            lambda f, w: orch, raising=False)
        monkeypatch.setattr(project_mod, 'detect_modules',
                            lambda w: {'m1': types.SimpleNamespace(
                                language='py', path='p')},
                            raising=False)
        monkeypatch.setattr(project_mod, 'detect_languages',
                            lambda w: ['python'], raising=False)
        monkeypatch.setattr(project_mod, 'ModuleConfig',
                            lambda **kw: types.SimpleNamespace(**kw),
                            raising=False)
        return orch

    def test_detect(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_project(NS(detect=True, validate=False, status=False,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        out = capsys.readouterr().out
        assert '检测到 1 个模块' in out and 'python' in out

    def test_validate(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_project(NS(detect=False, validate=True, status=False,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert '项目定义有效' in capsys.readouterr().out

    def test_validate_invalid(self, tmp_path, monkeypatch, capsys):
        orch = _FakeOrch()
        orch.validate = lambda: (False, ['e1', 'e2'])
        self._patch(monkeypatch, orch)
        assert cli._cmd_project(NS(detect=False, validate=True, status=False,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert '无效' in capsys.readouterr().out

    def test_status(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_project(NS(detect=False, validate=False, status=True,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert 'modules' in capsys.readouterr().out

    def test_add_remove_module(self, tmp_path, monkeypatch, capsys):
        orch = self._patch(monkeypatch)
        ns = NS(detect=False, validate=False, status=False,
                add_module=('m1', 'python', 'p'), remove_module=None,
                test=False, phase=None, work_dir=None, project_file=None)
        assert cli._cmd_project(ns) == 0
        assert 'm1' in orch.modules
        ns2 = NS(detect=False, validate=False, status=False,
                 add_module=None, remove_module='m1', test=False,
                 phase=None, work_dir=None, project_file=None)
        assert cli._cmd_project(ns2) == 0
        assert 'm1' not in orch.modules

    def test_test_phase(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_project(NS(detect=False, validate=False, status=False,
                                   add_module=None, remove_module=None,
                                   test=True, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert 'ok' in capsys.readouterr().out

    def test_build_default(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_project(NS(detect=False, validate=False, status=False,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert 'build' in capsys.readouterr().out

    def test_load_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(project_mod, 'load_project',
                            lambda f, w: (_ for _ in ()).throw(
                                RuntimeError('bad')),
                            raising=False)
        assert cli._cmd_project(NS(detect=False, validate=True, status=False,
                                   add_module=None, remove_module=None,
                                   test=False, phase=None, work_dir=None,
                                   project_file=None)) == 0
        assert '加载失败' in capsys.readouterr().out


# ── _cmd_omega ──

class TestCmdOmega:
    def test_verify_no_spec(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(omega_mod, '_find_omega_spec',
                            lambda aid, d: None, raising=False)
        ns = NS(omega_command='verify', output='{"a": 1}', spec=None,
                action_id='a.b', loop=False, diff=False)
        assert cli._cmd_omega(ns) == 1
        assert '未找到 spec' in capsys.readouterr().out

    def test_verify_pass(self, tmp_path, monkeypatch, capsys):
        spec_file = tmp_path / 'spec.json'
        spec_file.write_text('{}', encoding='utf-8')
        monkeypatch.setattr(omega_mod, '_find_omega_spec',
                            lambda aid, d: str(spec_file), raising=False)
        monkeypatch.setattr(omega_mod, 'verify_output',
                            lambda *a, **k: {'status': 'pass'}, raising=False)
        monkeypatch.setattr(omega_mod, 'format_report',
                            lambda r: 'PASS', raising=False)
        ns = NS(omega_command='verify', output='{"a": 1}', spec=None,
                action_id='a.b', loop=False, diff=False)
        assert cli._cmd_omega(ns) == 0
        assert 'PASS' in capsys.readouterr().out

    def test_verify_fail_with_diff(self, tmp_path, monkeypatch, capsys):
        spec_file = tmp_path / 'spec.json'
        spec_file.write_text('{}', encoding='utf-8')
        monkeypatch.setattr(omega_mod, '_find_omega_spec',
                            lambda aid, d: str(spec_file), raising=False)
        monkeypatch.setattr(omega_mod, 'verify_output',
                            lambda *a, **k: {'status': 'fail'}, raising=False)
        monkeypatch.setattr(omega_mod, 'format_report',
                            lambda r: 'FAIL', raising=False)
        monkeypatch.setattr(omega_mod, 'load_spec',
                            lambda p: {}, raising=False)
        monkeypatch.setattr(omega_mod, 'generate_diff_report',
                            lambda s, o: {'status': 'diff',
                                          'missing_fields': ['m'],
                                          'extra_fields': ['e'],
                                          'type_mismatches': [
                                              {'field': 'f', 'expected': 'i',
                                               'actual': 's'}]},
                            raising=False)
        ns = NS(omega_command='verify', output='{"a": 1}', spec=None,
                action_id='a.b', loop=False, diff=True)
        assert cli._cmd_omega(ns) == 1
        out = capsys.readouterr().out
        assert '差异报告' in out and '类型不匹配' in out

    def test_template(self, tmp_path, monkeypatch, capsys):
        ns = NS(omega_command='template', action_id='a.b', example='{"n": 1}')
        assert cli._cmd_omega(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, dict)

    def test_learn(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            importlib.import_module('vools.actus.records'), 'list_run_records',
            lambda limit=50: [{'action_id': 'a', 'result': 1}], raising=False)
        ns = NS(omega_command='learn', action_id='a', limit=10)
        assert cli._cmd_omega(ns) == 0
        assert isinstance(json.loads(capsys.readouterr().out), dict)

    def test_batch(self, tmp_path, monkeypatch, capsys):
        inputs = tmp_path / 'inputs.json'
        inputs.write_text('[{"a": 1}]', encoding='utf-8')
        monkeypatch.setattr(omega_mod, 'load_spec', lambda p: {},
                            raising=False)
        monkeypatch.setattr(omega_mod, 'batch_verify',
                            lambda p, i: {'failed': 0}, raising=False)
        ns = NS(omega_command='batch', spec='s', inputs=str(inputs))
        assert cli._cmd_omega(ns) == 0
        monkeypatch.setattr(omega_mod, 'batch_verify',
                            lambda p, i: {'failed': 1}, raising=False)
        assert cli._cmd_omega(ns) == 1

    def test_format(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(omega_mod, 'format_report',
                            lambda r: 'FORMATTED', raising=False)
        ns = NS(omega_command='format', report='{"status": "pass"}')
        assert cli._cmd_omega(ns) == 0
        assert 'FORMATTED' in capsys.readouterr().out

    def test_unknown(self, capsys):
        assert cli._cmd_omega(NS(omega_command='zz')) == 2


# ── _cmd_concurrency / _cmd_deps ──

class TestCmdConcurrency:
    def test_status(self, capsys):
        assert cli._cmd_concurrency(NS(concurrency_command='status',
                                       action=None, max=None)) == 0
        assert isinstance(json.loads(capsys.readouterr().out), dict)

    def test_set_and_status_action(self, capsys):
        assert cli._cmd_concurrency(NS(concurrency_command='set',
                                       action='a.b', max=3)) == 0
        assert '并发上限' in capsys.readouterr().out
        assert cli._cmd_concurrency(NS(concurrency_command='status',
                                       action='a.b', max=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload.get('action_id') == 'a.b'
        # 清理
        cli._cmd_concurrency(NS(concurrency_command='reset', action='a.b',
                                max=None))

    def test_reset_all(self, capsys):
        assert cli._cmd_concurrency(NS(concurrency_command='reset',
                                       action=None, max=None)) == 0
        assert '清除所有' in capsys.readouterr().out

    def test_list(self, capsys):
        assert cli._cmd_concurrency(NS(concurrency_command='list',
                                       action=None, max=None)) == 0
        assert cli._cmd_concurrency(NS(concurrency_command='list',
                                       action='a.b', max=None)) == 0
        capsys.readouterr()

    def test_unknown(self, capsys):
        assert cli._cmd_concurrency(NS(concurrency_command='zz',
                                       action=None, max=None)) == 2


class TestCmdDeps:
    def test_ok(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(dep_mod, 'check_action_deps',
                            lambda aid, auto_install=False: {'ok': True},
                            raising=False)
        assert cli._cmd_deps(NS(action_id='a', auto_install=False)) == 0

    def test_fail(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(dep_mod, 'check_action_deps',
                            lambda aid, auto_install=False: {'ok': False},
                            raising=False)
        assert cli._cmd_deps(NS(action_id='a', auto_install=True)) == 1

    def test_tree(self, tmp_path, monkeypatch, capsys):
        class R:
            def get_dep_tree(self, aid):
                return {'id': aid}
        monkeypatch.setattr(dep_mod, 'get_resolver', lambda: R(),
                            raising=False)
        assert cli._cmd_dep_tree(NS(action_id='a')) == 0
        assert json.loads(capsys.readouterr().out)['id'] == 'a'


# ── _cmd_desktop ──

class TestCmdDesktop:
    def test_import_error(self, monkeypatch, capsys):
        monkeypatch.setitem(sys.modules, 'vools.actus.desktop', None)
        ns = NS(host='h', port=1, no_browser=True)
        assert cli._cmd_desktop(ns) == 1
        assert '依赖' in capsys.readouterr().out

    def test_start(self, monkeypatch, capsys):
        started = {}

        def start(**kw):
            started.update(kw)

        fake = types.ModuleType('vools.actus.desktop')
        fake.start = start
        monkeypatch.setitem(sys.modules, 'vools.actus.desktop', fake)
        ns = NS(host='127.0.0.1', port=8000, no_browser=True)
        assert cli._cmd_desktop(ns) == 0
        assert started['port'] == 8000 and started['open_browser'] is False


# ── _cmd_events（真 eventbus + 手写 events.jsonl）──

class TestCmdEvents:
    def _meta_dir(self):
        return paths_mod.meta_dir()

    def test_no_file_human(self, tmp_path, monkeypatch, capsys):
        md = self._meta_dir()
        ev_file = os.path.join(md, 'events.jsonl')
        if os.path.exists(ev_file):
            os.remove(ev_file)
        ns = NS(limit=50, type=None, as_json=False)
        assert cli._cmd_events(ns) == 0
        assert '从未有事件落盘' in capsys.readouterr().out

    def test_with_events_human(self, tmp_path, capsys):
        md = self._meta_dir()
        ev_file = os.path.join(md, 'events.jsonl')
        os.makedirs(md, exist_ok=True)
        with open(ev_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'timestamp': 1.5, 'type': 't1',
                                'source': 'cli', 'data': {'k': 'v'}}) + '\n')
            f.write('not-json\n')
        ns = NS(limit=50, type=None, as_json=False)
        assert cli._cmd_events(ns) == 0
        out = capsys.readouterr().out
        assert 't1' in out and 'k: v' in out and '1 行无法解析' in out

    def test_json_mode(self, tmp_path, capsys):
        md = self._meta_dir()
        os.makedirs(md, exist_ok=True)
        with open(os.path.join(md, 'events.jsonl'), 'w', encoding='utf-8') as f:
            f.write(json.dumps({'timestamp': 'bad-ts', 'type': 't2',
                                'source': 'x', 'data': {}}) + '\n')
        ns = NS(limit=50, type=None, as_json=True)
        assert cli._cmd_events(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['count'] == 1 and payload['history_exists'] is True


# ── _cmd_viz ──

class TestCmdViz:
    def test_missing_workflow(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
        ns = NS(action=None, format='mermaid', output=None, sample=False)
        assert cli._cmd_viz(ns) == 1
        assert '未找到工作流定义' in capsys.readouterr().err

    def test_sample(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
        ns = NS(action=None, format='mermaid', output=None, sample=True)
        assert cli._cmd_viz(ns) == 0
        captured = capsys.readouterr()
        assert '示例' in captured.err
        assert 'trigger' in captured.out

    def test_output_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
        out = tmp_path / 'sub' / 'viz.txt'
        ns = NS(action=None, format='mermaid', output=str(out), sample=True)
        assert cli._cmd_viz(ns) == 0
        assert out.exists() and 'trigger' in out.read_text(encoding='utf-8')

    def test_action_missing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
        ns = NS(action='ghost.action', format='mermaid', output=None,
                sample=False)
        assert cli._cmd_viz(ns) == 1
        assert '动作不存在' in capsys.readouterr().out


# ── _cmd_replay ──

class TestCmdReplay:
    def _patch_history(self, monkeypatch, records=None, corrupt=False):
        if corrupt:
            def load(meta_dir):
                raise export_mod.RunHistoryCorruptError('bad')
        else:
            def load(meta_dir):
                return records or []
        monkeypatch.setattr(export_mod, 'load_run_history', load,
                            raising=False)

    def test_corrupt(self, tmp_path, monkeypatch, capsys):
        self._patch_history(monkeypatch, corrupt=True)
        assert cli._cmd_replay(NS(run_id=None, limit=None, dry_run=True)) == 1
        assert '损坏' in capsys.readouterr().err

    def test_empty(self, tmp_path, monkeypatch, capsys):
        self._patch_history(monkeypatch, [])
        assert cli._cmd_replay(NS(run_id=None, limit=None, dry_run=True)) == 0
        assert '暂无执行历史' in capsys.readouterr().out

    def test_run_id_miss(self, tmp_path, monkeypatch, capsys):
        self._patch_history(monkeypatch, [{'action_id': 'a', 'timestamp': 1}])
        assert cli._cmd_replay(NS(run_id='zzz', limit=None,
                                  dry_run=True)) == 1
        assert '未找到执行记录' in capsys.readouterr().out

    def test_dry_run(self, tmp_path, monkeypatch, capsys):
        rec = {'action_id': 'a.b', 'timestamp': 1, 'status': 'ok',
               'run_id': 'r1', 'params': {}}
        self._patch_history(monkeypatch, [rec])
        assert cli._cmd_replay(NS(run_id=None, limit=None, dry_run=True)) == 0
        assert 'dry-run' in capsys.readouterr().out

    def test_execute_ok(self, tmp_path, monkeypatch, capsys):
        rec = {'action_id': 'a.b', 'timestamp': 1, 'status': 'ok',
               'run_id': 'r1', 'params': {'x': 1}}
        self._patch_history(monkeypatch, [rec])
        monkeypatch.setattr(pkg, 'execute',
                            lambda a, p, **k: {'status': 'ok',
                                               'exec_id': 'E1',
                                               'data': {'result': 'hi'}},
                            raising=False)
        assert cli._cmd_replay(NS(run_id=None, limit=None,
                                  dry_run=False)) == 0
        out = capsys.readouterr().out
        assert '成功 1 / 失败 0' in out and 'E1' in out

    def test_execute_raises(self, tmp_path, monkeypatch, capsys):
        rec = {'action_id': 'a.b', 'timestamp': 1, 'run_id': 'r1'}
        self._patch_history(monkeypatch, [rec])
        def boom(a, p, **k):
            raise RuntimeError('x')
        monkeypatch.setattr(pkg, 'execute', boom, raising=False)
        assert cli._cmd_replay(NS(run_id=None, limit=None,
                                  dry_run=False)) == 1
        out = capsys.readouterr().out
        assert '失败 1' in out and 'RuntimeError' in out

    def test_execute_not_ok(self, tmp_path, monkeypatch, capsys):
        rec = {'action_id': 'a.b', 'timestamp': 1, 'run_id': 'r1'}
        self._patch_history(monkeypatch, [rec])
        monkeypatch.setattr(pkg, 'execute',
                            lambda a, p, **k: {'status': 'failed',
                                               'error': {'code': 'c',
                                                         'message': 'm'}},
                            raising=False)
        assert cli._cmd_replay(NS(run_id=None, limit=None,
                                  dry_run=False)) == 1
        assert '失败 1' in capsys.readouterr().out

    def test_missing_action_id(self, tmp_path, monkeypatch, capsys):
        rec = {'timestamp': 1, 'run_id': 'r1'}
        self._patch_history(monkeypatch, [rec])
        assert cli._cmd_replay(NS(run_id=None, limit=None,
                                  dry_run=False)) == 1
        assert '缺少 action_id' in capsys.readouterr().out

    def test_limit(self, tmp_path, monkeypatch, capsys):
        recs = [{'action_id': 'a.%d' % i, 'timestamp': i, 'run_id': 'r%d' % i}
                for i in range(5)]
        self._patch_history(monkeypatch, recs)
        assert cli._cmd_replay(NS(run_id=None, limit=2, dry_run=True)) == 0
        assert '只处理最近 2 条' in capsys.readouterr().out


# ── _cmd_notify / _cmd_project_io ──

class _FakeNotify:
    def __init__(self):
        self.sent = []

    def notify(self, **kw):
        self.sent.append(kw)

    def get_history(self):
        return self.sent or [{'timestamp': 1, 'level': 'info',
                              'title': 'T', 'body': 'B'}]

    def stats(self):
        return {'total_sent': 2, 'channels': ['console']}


class TestCmdNotify:
    def _patch(self, monkeypatch, mgr=None):
        mgr = mgr or _FakeNotify()
        monkeypatch.setattr(notify_mod, 'get_notification_manager',
                            lambda: mgr, raising=False)
        return mgr

    def test_test(self, tmp_path, monkeypatch, capsys):
        mgr = self._patch(monkeypatch)
        assert cli._cmd_notify(NS(action='test')) == 0
        assert len(mgr.sent) == 1
        assert '测试通知' in capsys.readouterr().out

    def test_history_empty_then_full(self, tmp_path, monkeypatch, capsys):
        mgr = self._patch(monkeypatch)
        mgr.sent = []
        mgr.get_history = lambda: []
        assert cli._cmd_notify(NS(action='history')) == 0
        assert '暂无通知历史' in capsys.readouterr().out
        mgr.get_history = lambda: [{'timestamp': 1, 'level': 'info',
                                    'title': 'T', 'body': 'B'}]
        assert cli._cmd_notify(NS(action='history')) == 0
        assert '(info) T: B' in capsys.readouterr().out

    def test_stats(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_notify(NS(action='stats')) == 0
        assert 'console' in capsys.readouterr().out


class TestCmdProjectIO:
    def test_export_ok(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(pio_mod, 'export_project',
                            lambda root, out, include_meta=False: out,
                            raising=False)
        assert cli._cmd_project_io(NS(action='export', output='x.actus',
                                      meta=False, file=None)) == 0
        assert '已导出' in capsys.readouterr().out

    def test_export_fail(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(pio_mod, 'export_project',
                            lambda *a, **k: None, raising=False)
        # 默认 output（None）会命中 cli.py:3644 f"{root.name}.actus"，
        # 而 _repo_root() 返回 str（BUG-C1）——默认输出场景用 pytest.raises
        # 记录现状；可失败路径用显式 output 触发。
        with pytest.raises(AttributeError):
            cli._cmd_project_io(NS(action='export', output=None, meta=False,
                                   file=None))
        assert cli._cmd_project_io(NS(action='export', output='x.actus',
                                      meta=False, file=None)) == 1

    def test_import(self, tmp_path, monkeypatch, capsys):
        assert cli._cmd_project_io(NS(action='import', output=None,
                                      meta=False, file=None)) == 1
        monkeypatch.setattr(pio_mod, 'import_project',
                            lambda root, f: {'imported': 3}, raising=False)
        assert cli._cmd_project_io(NS(action='import', output=None,
                                      meta=False, file='f')) == 0
        assert '3 个文件' in capsys.readouterr().out
        monkeypatch.setattr(pio_mod, 'import_project',
                            lambda root, f: None, raising=False)
        assert cli._cmd_project_io(NS(action='import', output=None,
                                      meta=False, file='f')) == 1

    def test_validate(self, tmp_path, monkeypatch, capsys):
        assert cli._cmd_project_io(NS(action='validate', output=None,
                                      meta=False, file=None)) == 1
        monkeypatch.setattr(pio_mod, 'validate_project',
                            lambda f: {'valid': True,
                                       'manifest': {'actions_count': 2}},
                            raising=False)
        assert cli._cmd_project_io(NS(action='validate', output=None,
                                      meta=False, file='f')) == 0
        assert '2 个动作' in capsys.readouterr().out
        monkeypatch.setattr(pio_mod, 'validate_project',
                            lambda f: {'valid': False,
                                       'errors': ['e1']}, raising=False)
        assert cli._cmd_project_io(NS(action='validate', output=None,
                                      meta=False, file='f')) == 1


# ── _cmd_export ──

class TestCmdExport:
    def test_output_written(self, tmp_path, monkeypatch, capsys):
        out = tmp_path / 'hist.json'
        out.write_text('[]', encoding='utf-8')
        monkeypatch.setattr(export_mod, 'export_history',
                            lambda md, o, f, l: str(out), raising=False)
        assert cli._cmd_export(NS(output=str(out), format='json',
                                  limit=None)) == 0
        assert '已导出到' in capsys.readouterr().out

    def test_output_no_history(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(export_mod, 'export_history',
                            lambda md, o, f, l: None, raising=False)
        assert cli._cmd_export(NS(output='x', format='json',
                                  limit=None)) == 1
        assert '没有可导出' in capsys.readouterr().err

    def test_stdout_mode(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(export_mod, 'export_history',
                            lambda md, o, f, l: 'HIST', raising=False)
        assert cli._cmd_export(NS(output=None, format='json',
                                  limit=None)) == 0
        assert 'HIST' in capsys.readouterr().out
        monkeypatch.setattr(export_mod, 'export_history',
                            lambda md, o, f, l: None, raising=False)
        assert cli._cmd_export(NS(output=None, format='json',
                                  limit=None)) == 0
        assert '暂无执行历史' in capsys.readouterr().out

    def test_corrupt(self, tmp_path, monkeypatch, capsys):
        def load(md, o, f, l):
            raise export_mod.RunHistoryCorruptError('bad')
        monkeypatch.setattr(export_mod, 'export_history', load,
                            raising=False)
        assert cli._cmd_export(NS(output=None, format='json',
                                  limit=None)) == 1


# ── _cmd_probe / _cmd_cost ──

class TestCmdProbeCost:
    def test_probe_json(self, tmp_path, monkeypatch, capsys):
        report = types.SimpleNamespace(to_dict=lambda: {'os': 'win'})
        monkeypatch.setattr(probe_mod, 'probe',
                            lambda force_refresh=False, max_age=None,
                            verbose=False: report, raising=False)
        ns = NS(force_refresh=True, max_age=5, verbose=True, as_json=True)
        assert cli._cmd_probe(ns) == 0
        assert json.loads(capsys.readouterr().out) == {'os': 'win'}

    def test_probe_human(self, tmp_path, monkeypatch, capsys):
        report = types.SimpleNamespace(to_dict=lambda: {})
        monkeypatch.setattr(probe_mod, 'probe',
                            lambda force_refresh=False, max_age=None,
                            verbose=False: report, raising=False)
        monkeypatch.setattr(probe_mod, 'format_summary',
                            lambda r: 'SUMMARY', raising=False)
        assert cli._cmd_probe(NS(force_refresh=False, max_age=None,
                                 verbose=False, as_json=False)) == 0
        assert 'SUMMARY' in capsys.readouterr().out

    def test_cost_with_data(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cost_mod, 'get_cost_summary',
                            lambda month=None: {
                                'month': '2026-01', 'calls': 3,
                                'total_usd': 0.5, 'tokens_total': 100,
                                'by_provider': {'p': 1},
                                'by_model': {'m': 1},
                                'ledger_complete': True,
                                'incomplete_reasons': {}}, raising=False)
        monkeypatch.setattr(cost_mod, 'check_budget',
                            lambda: {'ok': True}, raising=False)
        assert cli._cmd_cost(NS(month=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        data = payload['data']['data']  # _out_result 包一层 data
        assert data['recorded'] is True and data['calls'] == 3
        assert 'budget' in data

    def test_cost_no_data(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cost_mod, 'get_cost_summary',
                            lambda month=None: {
                                'month': 'm', 'calls': 0, 'total_usd': 0,
                                'tokens_total': 0, 'by_provider': {},
                                'by_model': {}, 'ledger_complete': False,
                                'incomplete_reasons': {}}, raising=False)
        ns = NS(month='2026-01')
        assert cli._cmd_cost(ns) == 0
        data = json.loads(capsys.readouterr().out)['data']['data']
        assert data['recorded'] is False
        assert '暂无记账' in data['message']
        assert 'budget' not in data  # month 非空不算预算


# ── _cmd_selfdrive ──

class TestCmdSelfdrive:
    def test_status_not_found(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sd_mod, 'load_run', lambda rid, md: None,
                            raising=False)
        ns = NS(selfdrive_action='status', run_id='r1', goal=None, plan=None,
                plan_file=None, worker='echo', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['error']['code'] == 'not_found'

    def test_status_found(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sd_mod, 'load_run',
                            lambda rid, md: {'run_id': rid}, raising=False)
        ns = NS(selfdrive_action='status', run_id='r1', goal=None, plan=None,
                plan_file=None, worker='echo', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['run']['run_id'] == 'r1'

    def test_status_list(self, tmp_path, monkeypatch, capsys):
        runs = [{'run_id': 'r%d' % i, 'goal': 'g', 'strong': False,
                 'updated_at': str(i), 'summary': 's'} for i in range(3)]
        monkeypatch.setattr(sd_mod, 'list_runs', lambda md: runs,
                            raising=False)
        ns = NS(selfdrive_action='status', run_id=None, goal=None, plan=None,
                plan_file=None, worker='echo', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['count'] == 3
        assert payload['data']['runs'][0]['run_id'] == 'r2'  # updated_at 倒序

    def test_run_no_goal(self, tmp_path, monkeypatch, capsys):
        ns = NS(selfdrive_action='run', run_id=None, goal='', plan=None,
                plan_file=None, worker='echo', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['error']['code'] == 'param_invalid'

    def test_run_plan_file_missing(self, tmp_path, monkeypatch, capsys):
        ns = NS(selfdrive_action='run', run_id=None, goal='g', plan=None,
                plan_file=str(tmp_path / 'nope.json'), worker='echo',
                max_depth=2, max_rounds=3, strong=False)
        assert cli._cmd_selfdrive(ns) == 1
        assert 'plan-file' in json.loads(capsys.readouterr().out)['data']['error']['message']

    def test_run_echo(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sd_mod, 'SelfDrive',
                            lambda goal, **kw: types.SimpleNamespace(
                                run=lambda: {'goal': goal}),
                            raising=False)
        ns = NS(selfdrive_action='run', run_id=None, goal='g', plan=None,
                plan_file=None, worker='echo', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['worker_kind'] == 'echo' and payload['data']['status'] == 'ok'

    def test_run_action_needs_plan(self, tmp_path, monkeypatch, capsys):
        ns = NS(selfdrive_action='run', run_id=None, goal='g', plan=None,
                plan_file=None, worker='action', max_depth=2, max_rounds=3,
                strong=False)
        assert cli._cmd_selfdrive(ns) == 1
        assert 'action 需要' in json.loads(
            capsys.readouterr().out)['data']['error']['message']

    def test_run_action_from_plan_valueerror(self, tmp_path, monkeypatch,
                                             capsys):
        plan = tmp_path / 'p.json'
        plan.write_text('{"x": 1}', encoding='utf-8')
        aw_mod = importlib.import_module('vools.actus.selfdrive_worker')
        def from_plan(raw, actions_dir=None, meta_dir=None):
            raise ValueError('bad plan')
        monkeypatch.setattr(aw_mod.ActionWorker, 'from_plan',
                            staticmethod(from_plan), raising=False)
        ns = NS(selfdrive_action='run', run_id=None, goal='g', plan=None,
                plan_file=str(plan), worker='action', max_depth=2,
                max_rounds=3, strong=False)
        assert cli._cmd_selfdrive(ns) == 1
        assert 'bad plan' in json.loads(
            capsys.readouterr().out)['data']['error']['message']

    def test_run_action_ok(self, tmp_path, monkeypatch, capsys):
        plan = tmp_path / 'p.json'
        plan.write_text('{"x": 1}', encoding='utf-8')
        aw_mod = importlib.import_module('vools.actus.selfdrive_worker')
        def from_plan(raw, actions_dir=None, meta_dir=None):
            return types.SimpleNamespace(worker='W', spec_resolver='R')
        monkeypatch.setattr(aw_mod.ActionWorker, 'from_plan',
                            staticmethod(from_plan), raising=False)
        seen = {}
        class SD:
            def __init__(self, goal, **kw):
                seen['kw'] = kw
            def run(self):
                return {'goal': 'g'}
        monkeypatch.setattr(sd_mod, 'SelfDrive', SD, raising=False)
        ns = NS(selfdrive_action='run', run_id=None, goal='g', plan=None,
                plan_file=str(plan), worker='action', max_depth=2,
                max_rounds=3, strong=True)
        assert cli._cmd_selfdrive(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['worker_kind'] == 'action'
        assert seen['kw']['worker'] == 'W' and seen['kw']['strong'] is True


# ── _cmd_health / _cmd_selfheal / _cmd_template ──

class _FakeReport:
    def __init__(self, overall='ok'):
        self.overall = overall
        self.total_duration = 0.1
        self.status_counts = {'ok': 2}
        self.results = [types.SimpleNamespace(
            name='n1', status='ok', message='m', suggestion='s',
            duration=0.05)]

    def summary(self):
        return 'SUMMARY-LINE'


class TestCmdHealth:
    def test_check_found(self, monkeypatch, capsys):
        from vools.actus.health import HealthChecker
        checker = HealthChecker()
        if not checker._checks:
            pytest.skip('no checks registered')
        name0 = checker._checks[0][0]
        ns = NS(check=name0.split()[0] if ' ' in name0 else name0,
                json=False)
        assert cli._cmd_health(ns) == 0
        out = capsys.readouterr().out
        assert '[OK]' in out or '⚠' in out or '❌' in out or '❓' in out

    def test_check_miss(self, monkeypatch, capsys):
        assert cli._cmd_health(NS(check='zzz-no-such-check',
                                  json=False)) == 1
        assert '未找到检查项' in capsys.readouterr().out

    def test_full_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(health_mod, 'run_health_check',
                            lambda: _FakeReport('ok'), raising=False)
        assert cli._cmd_health(NS(check=None, json=True)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['overall'] == 'ok' and payload['results'][0]['name'] == 'n1'

    def test_full_human_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(health_mod, 'run_health_check',
                            lambda: _FakeReport('error'), raising=False)
        assert cli._cmd_health(NS(check=None, json=False)) == 1
        out = capsys.readouterr().out
        assert 'SUMMARY-LINE' in out and 'n1' in out


class TestCmdSelfheal:
    def test_status_reset(self, capsys):
        assert cli._cmd_selfheal(NS(action='status')) == 0
        out = capsys.readouterr().out
        assert '自愈引擎状态' in out and '错误模式' in out
        assert cli._cmd_selfheal(NS(action='reset')) == 0
        assert '已重置' in capsys.readouterr().out

    def test_patterns_empty_then_full(self, capsys):
        from vools.actus.selfheal import get_self_healing_engine
        engine = get_self_healing_engine()
        engine.reset()
        assert cli._cmd_selfheal(NS(action='patterns')) == 0
        assert '暂无错误模式' in capsys.readouterr().out
        engine.learner.learn('code_x', 'msg_x', resolution='fix it')
        assert cli._cmd_selfheal(NS(action='patterns')) == 0
        out = capsys.readouterr().out
        assert 'code_x' in out and 'fix it' in out


class TestCmdTemplate:
    def _patch(self, monkeypatch, templates=None, created=None):
        monkeypatch.setattr(tmpl_mod, 'list_templates',
                            lambda: templates or [], raising=False)
        monkeypatch.setattr(tmpl_mod, 'create_action_from_template',
                            lambda *a, **k: created, raising=False)

    def test_list(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch, templates=[
            {'id': 't1', 'name': 'N', 'description': 'D', 'tags': ['a']}])
        assert cli._cmd_template(NS(action='list', id=None, action_id=None,
                                    name=None, output=None, force=False)) == 0
        assert 't1' in capsys.readouterr().out

    def test_apply_missing_args(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_template(NS(action='apply', id=None, action_id=None,
                                    name=None, output=None, force=False)) == 1
        assert cli._cmd_template(NS(action='apply', id='t', action_id=None,
                                    name=None, output=None, force=False)) == 1

    def test_apply_ok_and_fail(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch, created='/x/y.actus.md')
        assert cli._cmd_template(NS(action='apply', id='t',
                                    action_id='a.b', name=None, output=None,
                                    force=False)) == 0
        self._patch(monkeypatch, created=None)
        assert cli._cmd_template(NS(action='apply', id='t',
                                    action_id='a.b', name=None, output=None,
                                    force=False)) == 1

    def test_unknown_action_is_noop(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch)
        assert cli._cmd_template(NS(action='zz', id=None, action_id=None,
                                    name=None, output=None, force=False)) == 0


# ── _dispatch_loop ──

class TestDispatchLoop:
    def _meta(self):
        return paths_mod.meta_dir()

    def _write_session(self, sid, project_dir=None, finished_at=None,
                       rounds=None):
        d = os.path.join(self._meta(), 'loops')
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, 'loop-%s.json' % sid)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'session_id': 'loop-%s' % sid,
                       'project_dir': project_dir,
                       'started_at': '2026-01-01T00:00:00',
                       'finished_at': finished_at,
                       'exit_reason': 'done' if finished_at else None,
                       'rounds': rounds or []}, f)
        return p

    def test_list_empty_and_full(self, capsys):
        d = os.path.join(self._meta(), 'loops')
        if os.path.isdir(d):
            import shutil
            shutil.rmtree(d)
        assert cli._dispatch_loop(NS(loop_command='list', session=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['count'] == 0
        self._write_session('a', rounds=[1, 2, 3])
        assert cli._dispatch_loop(NS(loop_command='list', session=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['count'] == 1
        row = payload['data']['sessions'][0]
        assert row['rounds_delivered'] == 3

    def test_list_skips_bad_json(self, capsys):
        d = os.path.join(self._meta(), 'loops')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'loop-bad.json'), 'w', encoding='utf-8') as f:
            f.write('{bad')
        assert cli._dispatch_loop(NS(loop_command='list', session=None)) == 0

    def test_status(self, tmp_path, capsys):
        d = os.path.join(self._meta(), 'loops')
        if os.path.isdir(d):
            import shutil
            shutil.rmtree(d)
        assert cli._dispatch_loop(NS(loop_command='status',
                                     session=None)) == 1
        capsys.readouterr()  # 排空第一次输出
        self._write_session('s1')
        assert cli._dispatch_loop(NS(loop_command='status',
                                     session=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['data']['session']['session_id'] == 'loop-s1'

    def test_status_session_prefix_and_miss(self, tmp_path, capsys):
        self._write_session('s2')
        assert cli._dispatch_loop(NS(loop_command='status',
                                     session='loop-s2')) == 0
        capsys.readouterr()
        assert cli._dispatch_loop(NS(loop_command='status',
                                     session='ghost')) == 1

    def test_status_ticks(self, tmp_path, capsys):
        p = self._write_session('s3')
        ticks = p[:-len('.json')] + '.ticks.jsonl'
        with open(ticks, 'w', encoding='utf-8') as f:
            for i in range(6):
                f.write(json.dumps({'tick': i}) + '\n')
        # 坏行放最前，保证「最后 5 行」全部可解析（坏行占位会吃掉一个名额）
        with open(ticks, 'r', encoding='utf-8') as f:
            body = f.read()
        with open(ticks, 'w', encoding='utf-8') as f:
            f.write('not-json\n' + body)
        assert cli._dispatch_loop(NS(loop_command='status',
                                     session='loop-s3')) == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload['data']['recent_ticks']) == 5
        assert payload['data']['recent_ticks'][-1]['tick'] == 5

    def test_stop_finished(self, tmp_path, capsys):
        self._write_session('s4', finished_at='2026-01-02')
        assert cli._dispatch_loop(NS(loop_command='stop',
                                     session='loop-s4')) == 1
        assert '会话已结束' in capsys.readouterr().out

    def test_stop_active(self, tmp_path, capsys):
        proj = tmp_path / 'proj'
        proj.mkdir()
        self._write_session('s5', project_dir=str(proj))
        assert cli._dispatch_loop(NS(loop_command='stop',
                                     session='loop-s5')) == 0
        assert (proj / '.loop_prompt.stop').exists()

    def test_stop_direct_dir(self, tmp_path, capsys):
        assert cli._dispatch_loop(NS(loop_command='stop',
                                     session=str(tmp_path))) == 0
        assert (tmp_path / '.loop_prompt.stop').exists()

    def test_stop_no_target(self, tmp_path, capsys):
        assert cli._dispatch_loop(NS(loop_command='stop',
                                     session='ghost')) == 1

    def test_unknown(self, capsys):
        assert cli._dispatch_loop(NS(loop_command='zz',
                                     session=None)) == 1


# ── dispatch 大分支 ──

class TestDispatchBig:
    def test_scan(self, capsys):
        assert cli._dispatch(NS(command='scan')) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok' and 'total' in payload['data']

    def test_list(self, capsys):
        assert cli._dispatch(NS(command='list', kind=None, purpose=None,
                                industry=None, tag=None, all=False)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok' and 'actions' in payload['data']

    def test_validate_all(self, capsys):
        rc = cli._dispatch(NS(command='validate', action_id=None))
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok'
        assert rc == (0 if payload['data']['valid'] else 1)

    def test_validate_unknown_target(self, capsys):
        assert cli._dispatch(NS(command='validate',
                                action_id='zzz-ghost')) == 1

    def test_info_unknown(self, capsys):
        assert cli._dispatch(NS(command='info',
                                action_id='zzz-ghost')) == 1

    def test_preview_file(self, tmp_path, capsys):
        f = tmp_path / 'x.py'
        f.write_text('print(1)\n', encoding='utf-8')
        assert cli._dispatch(NS(command='preview', file=str(f),
                                action_id=None, params=None, html=False,
                                lang=None, theme=None)) == 0

    def test_preview_unknown(self, capsys):
        assert cli._dispatch(NS(command='preview', file=None,
                                action_id='zzz-ghost', params=None,
                                html=False, lang=None, theme=None)) == 1

    def test_status_all(self, capsys):
        assert cli._dispatch(NS(command='status', exec_id=None)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok'

    def test_status_missing_exec(self, capsys):
        assert cli._dispatch(NS(command='status',
                                exec_id='no-such-exec')) == 1

    def test_run_unknown_target(self, capsys):
        assert cli._dispatch(NS(command='run', action_id='zzz-ghost',
                                params=None, confirm=False, yes=False,
                                force=False)) == 1
