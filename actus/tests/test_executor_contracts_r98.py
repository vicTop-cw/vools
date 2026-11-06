# -*- coding: utf-8 -*-
"""executor.py execute() 主流程契约测试（Round 98）。

r69 已覆盖内部函数；本文件专攻 execute() 主体（L312-744）与其余 missed 段：
- 深度闸门 / 磁盘解析（_resolve_path + load_and_validate 接线）
- kind_unsupported / 依赖预检四分支（satisfied / lazy / hard_missing / resolver 炸）
- awaiting_confirmation / dev_auto_confirm / 并发上限（fake manager）
- 幂等 replay 命中（execute 级）/ Ω-gate 四分支（fake verify_output）
- 子进程路径：正常 result.json / 坏 JSON / wait 二次炸（fake Popen）
- secrets except-pass / vault.get_key 异常 / record_gate 异常吞掉
- _register_artifacts 主体 / failed 块 stdout_truncated / preview 正常路径
- ActionError→to_payload / 未知异常→internal

全部隔离：tmp 目录 + monkeypatch，patch 一律对象寻址（模块对象属性），不真跑
重量级外部进程（BUG-531）。产品代码零修改。
"""

import json
import os
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest

from vools.actus import executor as ex
from vools.actus.model import Action
from vools.actus import indexer as _indexer
from vools.actus import validate as _validate
from vools.actus import vault as _vault
from vools.actus import security as _security
from vools.actus import visibility as _visibility
from vools.actus import _proc as _proc_mod


# ── 测试基建 ───────────────────────────────────────────────

def _mkaction(aid='r98.exec', **meta):
    """构造真 Action（property 全部从 meta 推导，直接可进 execute 主流程）。"""
    base = {'id': aid, 'name': 'R98 Test', 'version': '1.0.0',
            'trust': 'trusted', 'entry': 'main', 'kind': 'exec',
            'platform': 'desktop'}
    base.update(meta)
    return Action(meta=base, path='r98/fake.actus.md', sha256='0' * 64)


class _FakeScanner:
    """安全扫描器桩：safe + 沙箱放行。"""

    def scan_action(self, action_id, meta, text):
        return {'safe': True, 'issues': [], 'sensitive_findings': []}

    class sandbox:
        @staticmethod
        def check_file_access(path, op):
            return True, []


@pytest.fixture()
def flow(tmp_path, monkeypatch):
    """execute() 主流程通用隔离：meta/artifacts 指 tmp、门禁全部放行。"""
    meta_dir = str(tmp_path / '_meta')
    art_dir = str(tmp_path / 'art')
    os.makedirs(meta_dir, exist_ok=True)

    monkeypatch.setattr(_security, 'get_security_scanner', lambda: _FakeScanner())
    monkeypatch.setattr(ex, '_find_omega_spec', lambda aid, ad=None: None)
    monkeypatch.setattr(ex, 'scan_actions', lambda d, validate=False: {})
    monkeypatch.setattr(ex, 'validate_graph', lambda sub: None)
    return {'meta_dir': meta_dir, 'art_dir': art_dir, 'tmp_path': tmp_path}


@pytest.fixture()
def r98_bridge(monkeypatch):
    """替换 vools.bridge.md.run_md，返回可编程 report（与 r69 同手势）。"""
    holder = {'report': {'blocks': []},
              'calls': []}

    def _run_md(path, only=None, force=False, build_dir=None, **kw):
        holder['calls'].append({'path': path, 'only': only,
                                'force': force, 'build_dir': build_dir})
        return holder['report']

    mod = types.ModuleType('vools.bridge.md')
    mod.run_md = _run_md
    monkeypatch.setitem(sys.modules, 'vools.bridge.md', mod)
    return holder


def _ok_block(stdout='{}', tag='main', **extra):
    blk = {'index': 0, 'language': 'python', 'tag': [tag], 'status': 'ok',
           'duration_ms': 3, 'exit_code': 0, 'stdout': stdout, 'stderr': ''}
    blk.update(extra)
    return blk


class _Chk:
    """DepCheckResult 桩。"""

    def __init__(self, satisfied=False, name='dep', message='missing',
                 fix_command='', ephemeral_cmd='', download_url=''):
        self.satisfied = satisfied
        self.name = name
        self.message = message
        self.fix_command = fix_command
        self.ephemeral_cmd = ephemeral_cmd
        self.download_url = download_url


class _FakeResolver:
    def __init__(self, chk=None, actions_root=None):
        self.chk = chk or _Chk()

    def check_dep(self, dep):
        if isinstance(self.chk, Exception):
            raise self.chk
        return self.chk


class _FakeMgr:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.released = []
        self.registered = []

    def register_action(self, aid, n):
        self.registered.append((aid, n))

    def acquire_slot(self, *a, **k):
        return (self.acquired, 'ok' if self.acquired else '等待超时 (30s)，当前 1')

    def release_slot(self, aid, eid):
        self.released.append(eid)

    def get_running_count(self, aid):
        return 0

    def get_waiting_count(self, aid):
        return 0


def _deep(d):
    cur = {}
    for _ in range(d):
        cur = {'n': cur}
    return cur


# ── execute() 入口与主流程 ─────────────────────────────────

class TestExecuteEntrance:
    def test_depth_gate_rejects(self, flow):
        r = ex.execute('r98.x', params=_deep(70), meta_dir=flow['meta_dir'])
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'param_invalid'
        assert '入参嵌套过深' in r['error']['message']
        assert r['error']['details']['max_depth'] == 64
        # 提前 return：无 exec_id、无留痕
        assert 'exec_id' not in r

    def test_disk_resolution_path(self, flow, r98_bridge, monkeypatch):
        """actions_dir 给定 → _resolve_path + load_and_validate 接线。"""
        r98_bridge['report'] = {'blocks': [_ok_block('{"n":1}')]}
        seen_load = []

        def fake_get_action(aid, ad=None):
            return SimpleNamespace(path='X:/fake/r98.actus.md')

        def fake_load(path):
            seen_load.append(path)
            return _mkaction()

        monkeypatch.setattr(_indexer, 'get_action', fake_get_action)
        monkeypatch.setattr(ex, 'load_and_validate', fake_load)
        r = ex.execute('r98.exec', params={}, meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'],
                       actions_dir=str(flow['tmp_path'] / 'actions'))
        assert r['status'] == 'ok'
        assert r['data'] == {'n': 1}
        # 依赖预检与主流程各解析一次（预检 + 主流程都调 load_and_validate）
        assert seen_load == ['X:/fake/r98.actus.md'] * 2

    def test_kind_unsupported(self, flow):
        a = _mkaction(kind='weird')
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       preparsed_action=a)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'kind_unsupported'
        assert r['error']['details']['kind'] == 'weird'

    def test_resources_and_env_prefix_recorded(self, flow, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction(resources={'timeout_ms': 0, 'max_memory_mb': 256,
                                 'max_processes': 2},
                      context={'env_prefix': 'R98X_'})
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        assert r['resources']['max_memory_mb'] == 256
        assert r['env_prefix'] == 'R98X_'
        assert r['mode'] == 'sync'
        # _run_md_in_env 注入并恢复：执行后无残留
        assert 'R98X_EXEC_ID' not in os.environ

    def test_run_md_receives_entry_only_and_build_dir(self, flow, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction()
        r = ex.execute('r98.exec', params={'p': 1}, meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        call = r98_bridge['calls'][0]
        assert call['only'] == ['main']
        assert call['force'] is True
        assert 'r98.exec' in call['build_dir'].replace('\\', '/')
        assert 'r98.exec' not in os.environ.get('ACTUS_EXEC_ID', 'x')


class TestExecuteTrust:
    def test_awaiting_confirmation(self, flow):
        a = _mkaction(trust='audit')
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       preparsed_action=a)
        assert r['status'] == 'awaiting_confirmation'
        assert r['data']['pending_ops'][0]['op'] == 'run'
        assert '确认' in r['data']['hint']
        rec = json.load(open(r['record'], encoding='utf-8'))
        states = [s['state'] for s in rec['state_transitions']]
        assert 'awaiting_confirmation' in states
        assert rec['pending_ops'] == r['data']['pending_ops']

    def test_dev_auto_confirm(self, flow, r98_bridge, monkeypatch):
        monkeypatch.setenv('ACTUS_DEBUG', '1')
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction(trust='audit')
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'  # 不再卡确认
        rec = json.load(open(r['record'], encoding='utf-8'))
        assert rec['dev_auto_confirm'] is True

    def test_confirmed_audit_runs(self, flow, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction(trust='audit')
        r = ex.execute('r98.exec', confirmed=True, meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'

    def test_sandbox_trust_runs_sandboxed(self, flow, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction(trust='sandbox')
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        assert r['sandboxed'] is True
        assert 'sandbox' in r['sandbox_root']


class TestExecuteConcurrency:
    def test_limit_reached(self, flow, monkeypatch):
        mgr = _FakeMgr(acquired=False)
        monkeypatch.setattr(ex, 'get_manager', lambda: mgr)
        a = _mkaction(max_instances=1)
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       preparsed_action=a)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'concurrency_limit'
        assert r['error']['details']['max_instances'] == 1
        assert mgr.registered == [('r98.exec', 1)]
        # 失败路径在 record['concurrency'] 赋值之前返回 → 无槽位可释放
        assert mgr.released == []
        assert 'concurrency' not in r

    def test_slot_acquired(self, flow, r98_bridge, monkeypatch):
        mgr = _FakeMgr(acquired=True)
        monkeypatch.setattr(ex, 'get_manager', lambda: mgr)
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        a = _mkaction(max_instances=2, resources={'max_processes': 5})
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        assert mgr.registered == [('r98.exec', 2)]  # min(2, 5)
        assert r['concurrency']['max'] == 2
        assert r['concurrency']['released'] is True


class TestExecuteIdempotent:
    def _prepare(self, flow, aid='r98.exec'):
        a = _mkaction(aid, idempotency_key_from='k')
        ex._idempotent_store(flow['meta_dir'], a, {'k': 'v1'}, 'e-prev',
                             {'status': 'ok', 'data': {'n': 9}, 'error': None})
        runs = os.path.join(flow['meta_dir'], 'runs')
        os.makedirs(runs, exist_ok=True)
        # run 记录形状须与 finish 落盘一致：exec_id 在顶层、result 含 data
        with open(os.path.join(runs, 'e-prev.json'), 'w', encoding='utf-8') as f:
            json.dump({'exec_id': 'e-prev',
                       'result': {'status': 'ok', 'data': {'n': 9},
                                  'exec_id': 'e-prev', 'error': None}}, f)
        return a

    def test_replay_hit_short_circuits(self, flow):
        a = self._prepare(flow)
        r = ex.execute('r98.exec', params={'k': 'v1'},
                       meta_dir=flow['meta_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        assert r['data']['idempotent_replay'] is True
        assert r['data']['replay_of'] == 'e-prev'
        assert r['data']['n'] == 9
        rec = json.load(open(r['record'], encoding='utf-8'))
        assert rec['idempotent_replay_of'] == 'e-prev'

    def test_ok_run_stores_idempotent_entry(self, flow, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block('{"n":1}')]}
        a = _mkaction(idempotency_key_from='k')
        r = ex.execute('r98.exec', params={'k': 'v2'},
                       meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        data = json.load(open(ex._idempotency_file(flow['meta_dir']),
                              encoding='utf-8'))
        assert 'r98.exec::v2' in data


# ── 依赖预检（L406-470）────────────────────────────────────

class TestExecuteDeps:
    def _run(self, flow, monkeypatch, chk, dep, force=False, **action_kw):
        monkeypatch.setattr(ex, 'DependencyResolver',
                            lambda actions_root=None: _FakeResolver(chk))
        a = _mkaction(deps=[dep], **action_kw)
        return ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                          artifacts_dir=flow['art_dir'],
                          preparsed_action=a, force=force)

    def test_hard_missing_rejected(self, flow, monkeypatch):
        chk = _Chk(satisfied=False, name='toolx', message='where: not found')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'toolx', 'type': 'system',
                       'strategy': 'fail', 'required': True})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'deps_missing'
        assert r['deps']['missing'] == [{'name': 'toolx',
                                         'message': 'where: not found'}]
        assert 'exec_id' not in r  # finish 之前直接 return

    def test_hard_missing_force_proceeds(self, flow, monkeypatch, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        chk = _Chk(satisfied=False, name='toolx', message='nope')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'toolx', 'type': 'system',
                       'strategy': 'fail', 'required': True}, force=True)
        assert r['status'] == 'ok'
        assert 'deps_hints' not in r  # 非 lazy，无 hints

    def test_lazy_hint_attached(self, flow, monkeypatch, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        chk = _Chk(satisfied=False, name='tooly', message='未安装',
                   fix_command='winget install tooly')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'tooly', 'type': 'system', 'strategy': 'hint'})
        assert r['status'] == 'ok'
        assert r['deps_hints'][0]['name'] == 'tooly'
        assert r['deps_hints'][0]['fix_command'] == 'winget install tooly'

    def test_no_strategy_actionable_is_lazy(self, flow, monkeypatch,
                                            r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        chk = _Chk(satisfied=False, name='dl', message='',
                   download_url='https://x/y.zip')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'dl', 'type': 'runtime', 'required': True})
        assert r['status'] == 'ok'
        assert r['deps_hints'][0]['name'] == 'dl'

    def test_satisfied_dep_records_state(self, flow, monkeypatch, r98_bridge):
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        chk = _Chk(satisfied=True, name='okd')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'okd', 'type': 'action', 'strategy': 'fail'})
        assert r['status'] == 'ok'
        assert 'deps_hints' not in r

    def test_resolver_exception_swallowed(self, flow, monkeypatch,
                                          r98_bridge):
        """依赖预检炸 → 吞掉继续（action_obj/dep_check 置 None）。"""
        r98_bridge['report'] = {'blocks': [_ok_block()]}
        chk = RuntimeError('resolver down')
        r = self._run(flow, monkeypatch, chk,
                      {'name': 'x', 'type': 'system'})
        assert r['status'] == 'ok'
        assert 'deps_hints' not in r


# ── Ω-gate（finish L514-553）───────────────────────────────

class TestExecuteOmegaGate:
    def _run(self, flow, monkeypatch, r98_bridge, verify_ret=None,
             verify_raise=None, entry_stdout='{"n":1}'):
        r98_bridge['report'] = {'blocks': [_ok_block(entry_stdout)]}
        monkeypatch.setattr(ex, '_find_omega_spec',
                            lambda aid, ad=None: 'X:/spec/omega/r98.json')

        def fake_verify(spec, result):
            if verify_raise is not None:
                raise verify_raise
            return verify_ret

        monkeypatch.setattr(ex, 'verify_output', fake_verify)
        return ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                          artifacts_dir=flow['art_dir'],
                          preparsed_action=_mkaction())

    def test_gate_passed_ok(self, flow, monkeypatch, r98_bridge):
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': True, 'accuracy': 100}})
        assert r['status'] == 'ok'
        assert r['omega']['gate']['passed'] is True

    def test_spec_error_report(self, flow, monkeypatch, r98_bridge):
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'spec_error',
                                  'errors': ['schema broken']})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'omega_spec_invalid'
        assert 'Ω 契约不可评估' in r['error']['message']

    def test_gate_failed_accuracy(self, flow, monkeypatch, r98_bridge):
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': False, 'accuracy': 42}})
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'omega_gate_failed'
        assert '42%' in r['error']['message']

    def test_gate_failed_preserves_inner_error_code(self, flow, monkeypatch,
                                                    r98_bridge):
        """动作自身失败时，外层 error.code 必须是动作的真实码，不是 omega_gate_failed。

        实测场景（jump_show 列不存在的目录）：动作回 permission_denied，而 Ω 断言
        data.status=='ok' 必然判不过。旧实现把外层码一律盖成 omega_gate_failed，
        于是「SSH 连不上 / 路径不存在」与「Ω 契约没过关」在回执里同形，调用方
        （CLI 的 _map_error_code、面板、重试策略）拿不到据以决策的根因。
        """
        failed_envelope = json.dumps({
            'status': 'failed', 'data': None,
            'error': {'code': 'permission_denied', 'message': 'no such path'}})
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': False, 'accuracy': 0}},
                      entry_stdout=failed_envelope)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'permission_denied', '真实错误码被 Ω 码盖掉了'
        assert '动作自身失败' in r['error']['message']
        # Ω 结论降为附加信息，不丢
        assert r['error']['details']['omega']['gate']['passed'] is False
        assert r['error']['details']['action_error']['code'] == 'permission_denied'

    def test_gate_failed_inner_ok_still_omega_gate_failed(self, flow, monkeypatch,
                                                          r98_bridge):
        """动作自身成功、纯粹 Ω 判不过 ⇒ 仍用 omega_gate_failed（不能误报根因）。"""
        ok_envelope = json.dumps({'status': 'ok', 'data': {'n': 1}, 'error': None})
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': False, 'accuracy': 50}},
                      entry_stdout=ok_envelope)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'omega_gate_failed'

    def test_gate_failed_inner_error_code_empty_string(self, flow, monkeypatch,
                                                       r98_bridge):
        """动作失败但 error.code 为空串 ⇒ 不能把空串当码，落回 omega_gate_failed。"""
        failed_envelope = json.dumps({
            'status': 'failed', 'data': None,
            'error': {'code': '', 'message': 'boom'}})
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': False, 'accuracy': 0}},
                      entry_stdout=failed_envelope)
        assert r['error']['code'] == 'omega_gate_failed'

    def test_gate_failed_inner_error_not_dict(self, flow, monkeypatch,
                                              r98_bridge):
        """动作失败但 error 不是 dict（字符串/None）⇒ 不炸，落回 omega_gate_failed。"""
        failed_envelope = json.dumps(
            {'status': 'failed', 'data': None, 'error': 'plain string'})
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_ret={'status': 'ok',
                                  'gate': {'passed': False, 'accuracy': 0}},
                      entry_stdout=failed_envelope)
        assert r['error']['code'] == 'omega_gate_failed'

    def test_verify_raises_spec_invalid(self, flow, monkeypatch, r98_bridge):
        r = self._run(flow, monkeypatch, r98_bridge,
                      verify_raise=ValueError('bad spec'))
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'omega_spec_invalid'
        assert 'Ω spec 加载失败' in r['error']['message']
        assert r['omega']['spec_path'].endswith('r98.json')
        assert r['omega']['errors'] == ['ValueError: bad spec']


# ── 子进程路径（execute 级）────────────────────────────────

class TestExecuteChildPath:
    def _popen(self, writer):
        """FakeProc.wait 时按 task.json 找 result 路径并写入。"""
        def fake_popen(cmd, *a, **k):
            task_path = cmd[3]

            class FakeProc:
                pid = 777
                returncode = 0

                def wait(self, timeout=None):
                    with open(task_path, encoding='utf-8') as f:
                        task = json.load(f)
                    writer(task['result'])
                    return 0

            return FakeProc()
        return fake_popen

    def test_child_returns_blocks(self, flow, monkeypatch):
        def writer(result_path):
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump({'blocks': [_ok_block('{"n":3}')]}, f)

        monkeypatch.setattr(subprocess, 'Popen', self._popen(writer))
        a = _mkaction(resources={'timeout_ms': 5000})
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'ok'
        assert r['data'] == {'n': 3}

    def test_child_bad_json_crashed(self, flow, monkeypatch):
        def writer(result_path):
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write('{broken json')

        monkeypatch.setattr(subprocess, 'Popen', self._popen(writer))
        a = _mkaction(resources={'timeout_ms': 5000})
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'block_failed'
        blk = r['error']['details']['blocks'][0]
        assert blk['stderr'].startswith('child_crashed')

    def test_child_timeout_kills_tree(self, flow, monkeypatch):
        killed = []

        def fake_popen(cmd, *a, **k):
            class FakeProc:
                pid = 888
                returncode = -9

                def wait(self, timeout=None):
                    if timeout is not None and timeout < 1:
                        raise subprocess.TimeoutExpired(cmd='x', timeout=timeout)
                    return -9
            return FakeProc()

        monkeypatch.setattr(subprocess, 'Popen', fake_popen)
        monkeypatch.setattr(_proc_mod, 'kill_tree',
                            lambda p: killed.append(p.pid))
        a = _mkaction(resources={'timeout_ms': 80})
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'], preparsed_action=a)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'block_failed'
        assert r['child_killed'] is True
        assert r['timeout_deferred'] is False
        assert killed == [888]
        blk = r['error']['details']['blocks'][0]
        assert '已杀整棵进程树' in blk['stderr']

    def test_wait_second_crash_swallowed(self, flow, tmp_path, monkeypatch):
        """kill_tree 之后的 wait(10) 再炸 → except pass（L1206-1209）。"""

        class FakeProc:
            pid = 999
            returncode = -9

            def wait(self, timeout=None):
                if timeout is not None and timeout < 1:
                    raise subprocess.TimeoutExpired(cmd='x', timeout=timeout)
                raise RuntimeError('second wait exploded')

        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakeProc())
        monkeypatch.setattr(_proc_mod, 'kill_tree', lambda p: None)
        a = _mkaction(aid='r98.child', resources={'timeout_ms': 50})
        report, build, deferred = ex._run_md_in_child(
            a, {}, 'e-w2', str(tmp_path / 'art'), False, False, None)
        assert report['status'] == 'timeout'
        assert deferred is False


# ── 产物登记 / 门禁异常分支 ────────────────────────────────

class TestRegisterArtifacts:
    def test_file_and_text_artifacts(self, flow, r98_bridge, monkeypatch):
        src = flow['tmp_path'] / 'out.txt'
        src.write_text('hello', encoding='utf-8')
        r98_bridge['report'] = {'blocks': [_ok_block('{}', artifacts=[
            {'name': 'out.txt', 'path': str(src)},          # 无 hash → 现算 sha256
            {'name': 'log.txt', 'block': 1},                # 无 path → text
        ])]}
        real = ex.records.register_artifact
        seen = []

        def spy(*a, **k):
            seen.append(k)
            return real(*a, **k)

        monkeypatch.setattr(ex.records, 'register_artifact', spy)
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       artifacts_dir=flow['art_dir'],
                       preparsed_action=_mkaction())
        assert r['status'] == 'ok'
        assert len(seen) == 2
        assert seen[0]['artifact_type'] == 'file'
        assert len(seen[0]['sha256']) == 64
        assert seen[0]['source_exec'] == r['exec_id']
        assert seen[0]['version'] == '1.0.0'
        assert seen[1]['artifact_type'] == 'text'
        assert seen[1]['name'] == 'log.txt'
        # _run_blocks 产物收集时以所属块 index 覆写 block 字段
        assert seen[1]['block'] == 0

    def test_failed_block_truncated_flag(self, flow, tmp_path, r98_bridge):
        r98_bridge['report'] = {'blocks': [
            _ok_block('setup', tag='setup'),
            {'index': 1, 'language': 'python', 'tag': ['main'],
             'status': 'failed', 'duration_ms': 2, 'exit_code': 1,
             'stdout': 'x' * 5000, 'stderr': 'boom'}]}
        r = ex._run_blocks(_mkaction(), {}, 'e-tf', str(tmp_path / 'art'),
                           sandboxed=False, meta_dir=None)
        assert r['status'] == 'failed'
        assert r['stdout_truncated'] is True


class TestGateExceptionBranches:
    def test_vault_get_key_raises_still_auth_required(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('vault down')

        class FakeAuditor:
            def record_visibility(self, **kw):
                pass

        monkeypatch.setattr(_visibility, 'SecretAuditor', FakeAuditor)
        monkeypatch.setattr(_vault, 'get_key', boom)
        monkeypatch.delenv('ACTUS_GATED_KEY', raising=False)
        a = _mkaction(aid='r98.g', meta_extra=None) if False else _mkaction(
            aid='r98.g', **{'visibility': 'gated'})
        with pytest.raises(Exception) as ei:
            ex._visibility_gate(a, 'r98.g', 'e1')
        assert ei.value.code == 'auth_required'

    def test_record_gate_auditor_raises_swallowed(self, tmp_path, monkeypatch):
        class BoomAuditor:
            def record_visibility(self, **kw):
                raise RuntimeError('audit sink down')

        monkeypatch.setattr(_visibility, 'SecretAuditor', BoomAuditor)
        monkeypatch.setattr(_visibility, 'is_internal_path', lambda p: True)
        a = _mkaction(aid='r98.i', **{'visibility': 'internal'})
        ex._visibility_gate(a, 'r98.i', 'e1')  # 审计炸不阻塞放行

    def test_secrets_resolve_failure_swallowed(self, flow, tmp_path,
                                               monkeypatch):
        """meta.secrets 解析炸 → except pass（L1053-1060），不注 env 不抛。"""

        def boom(*a, **k):
            raise RuntimeError('vault provider down')

        monkeypatch.setattr(_vault, 'resolve_secrets', boom)
        snap = ex._env_snapshot()
        try:
            build = ex._apply_env_injections(
                _mkaction(**{'secrets': [{'provider': 'p', 'env': 'R98_TOK'}]}),
                {}, 'e-s', str(tmp_path), sandboxed=False, meta_dir=None)
        finally:
            ex._env_restore(snap)
        assert build  # 正常返回 build_dir
        assert 'R98_TOK' not in os.environ


# ── 错误契约 / preview ─────────────────────────────────────

class TestErrorContracts:
    def test_actionerror_to_payload(self, flow):
        a = _mkaction(**{'visibility': 'internal'})  # path 不在 _internal/
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       preparsed_action=a)
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'visibility_denied'
        assert '未落在 _internal/ 目录' in r['error']['message']
        rec = json.load(open(r['record'], encoding='utf-8'))
        assert rec['state_transitions'][-1]['state'] == 'failed'

    def test_unknown_exception_internal(self, flow, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('disk boom')

        monkeypatch.setattr(ex, 'scan_actions', boom)
        r = ex.execute('r98.exec', meta_dir=flow['meta_dir'],
                       preparsed_action=_mkaction())
        assert r['status'] == 'failed'
        assert r['error']['code'] == 'internal'
        assert r['error']['message'] == 'disk boom'
        assert r['error']['details']['type'] == 'RuntimeError'

    def test_preview_normal_path(self, monkeypatch):
        monkeypatch.setattr(_indexer, 'get_action',
                            lambda aid, ad=None: SimpleNamespace(path='p.md'))
        monkeypatch.setattr(_validate, 'load_and_validate',
                            lambda path: _mkaction())
        out = ex.preview('r98.exec', params={'x': 1})
        assert out['action']['id'] == 'r98.exec'
        assert out['strategy'] == 'auto'
        assert out['deps'] == []
        assert out['pending_ops'][0]['op'] == 'run'

    def test_preview_with_actions_dir(self, monkeypatch):
        seen = {}

        def fake_get(aid, ad=None):
            seen['aid'] = aid
            return SimpleNamespace(path='X:/y.md')

        monkeypatch.setattr(_indexer, 'get_action', fake_get)
        # preview 走模块级 load_and_validate（executor 文件级绑定）→ 对象寻址 patch
        monkeypatch.setattr(ex, 'load_and_validate',
                            lambda path: _mkaction())
        ex.preview('r98.z', actions_dir='X:/actions')
        assert seen['aid'] == 'r98.z'
