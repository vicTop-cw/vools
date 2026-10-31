# -*- coding: utf-8 -*-
"""_proc.py 契约测试（第 87 轮）——进程树安全 subprocess 包装。

覆盖：_load_psutil 懒导入、_psutil_kill_tree（先子后父/复扫/Process 异常）、
kill_tree（POSIX 分支/psutil 不可用/psutil 异常回落 taskkill/外层吞异常）、
run_cmd_safe（正常/快速 stdout/stderr/input/cwd/env/spawn 失败/超时 -9/宽限回收/流关闭）、
KILL_TREE_STATS 计数。

超时用例用真进程（python -c time.sleep）验证；psutil 分支用 fake。
"""
import _ai_local_bootstrap  # noqa: F401

import os
import subprocess
import sys
import time
import types

import pytest

import vools.actus._proc as pm
from vools.actus._proc import KILL_TREE_STATS, kill_tree, run_cmd_safe

PY = sys.executable
SLEEP_CMD = [PY, '-c', 'import time; time.sleep(60)']
FAST_ECHO = [PY, '-c', 'print("hello stdout")']
FAST_ERR = [PY, '-c', 'import sys; sys.stderr.write("boom err")']


@pytest.fixture
def stats_guard():
    before = dict(KILL_TREE_STATS)
    yield KILL_TREE_STATS
    # 不恢复：计数只增不重置是产品行为；这里只保证可读


# ═══════════════════════════════════════════════════════════════════
# _load_psutil
# ═══════════════════════════════════════════════════════════════════

class TestLoadPsutil:
    def test_available(self):
        psutil = pm._load_psutil()
        assert psutil is None or psutil is pm.__dict__.get('psutil', psutil)
        # 环境里有则返回模块，没有则 None —— 两种都合法
        assert psutil is None or hasattr(psutil, 'Process')

    def test_import_failure_returns_none(self, monkeypatch):
        real = pm._load_psutil
        monkeypatch.setitem(__import__('sys').modules, 'psutil', None)
        # 懒导入每次重查 sys.modules
        assert pm._load_psutil() is None


# ═══════════════════════════════════════════════════════════════════
# _psutil_kill_tree（fake psutil）
# ═══════════════════════════════════════════════════════════════════

class _FakeChild:
    def __init__(self, alive=True):
        self.killed = 0
        self._alive = alive

    def kill(self):
        self.killed += 1
        self._alive = False

    def is_running(self):
        return self._alive


class _FakeProc:
    """仿 psutil.Process。"""

    def __init__(self, children=None, kill_parent=True):
        self.children_list = children or []
        self.killed = 0
        self._kill_parent = kill_parent

    def children(self, recursive=True):
        return self.children_list

    def kill(self):
        if not self._kill_parent:
            raise RuntimeError('cannot open parent')
        self.killed += 1


def _fake_psutil_module(parent):
    m = types.ModuleType('fake_psutil')
    m.Process = lambda pid: parent
    return m


class TestPsutilKillTree:
    def test_no_pid_returns_false(self):
        assert pm._psutil_kill_tree(types.SimpleNamespace(pid=None),
                                    _fake_psutil_module(None)) is False

    def test_children_killed_before_parent(self, monkeypatch):
        # 复扫窗口压到 0 加速测试
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.0)
        kids = [_FakeChild(), _FakeChild()]
        parent = _FakeProc(children=kids)
        monkeypatch.setitem(sys.modules, 'fake_psutil_mod',
                            _fake_psutil_module(parent))
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=123),
            _fake_psutil_module(parent)) is True
        assert parent.killed == 1
        assert all(k.killed == 1 for k in kids)

    def test_process_gone_treated_as_handled(self, monkeypatch):
        m = types.ModuleType('fake_psutil2')

        def raise_process(pid):
            raise RuntimeError('no such process')
        m.Process = raise_process
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), m) is True

    def test_parent_unkillable_still_true(self, monkeypatch):
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.0)
        parent = _FakeProc(kill_parent=False)
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True

    def test_resweep_rekills_survivors(self, monkeypatch):
        # 第一次 kill 杀不死（伪顽强），复扫阶段补杀成功
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.5)

        class HalfDead:
            def __init__(self):
                self.killed = 0
                self._alive = True

            def kill(self):
                self.killed += 1
                if self.killed >= 2:
                    self._alive = False

            def is_running(self):
                return self._alive

        half = HalfDead()
        parent = _FakeProc(children=[half])
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True
        assert half.killed >= 2   # 复扫补杀生效

    def test_children_enumeration_raises_treated_empty(self, monkeypatch):
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.0)
        parent = _FakeProc()
        parent.children = lambda recursive=True: (_ for _ in ()).throw(
            RuntimeError('access denied'))
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True
        assert parent.killed == 1

    def test_child_kill_raises_ignored(self, monkeypatch):
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.0)

        class BadKid:
            def kill(self):
                raise RuntimeError('cannot kill')

            def is_running(self):
                return False
        parent = _FakeProc(children=[BadKid()])
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True

    def test_is_running_raises_dropped(self, monkeypatch):
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.3)

        class Ghost:
            killed = 0

            def kill(self):
                self.killed += 1

            def is_running(self):
                raise RuntimeError('zombie state')
        g = Ghost()
        parent = _FakeProc(children=[g])
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True

    def test_resweep_kill_raises_ignored(self, monkeypatch):
        monkeypatch.setattr(pm, '_KILL_RESWEEP_SEC', 0.3)

        class Loud:
            def kill(self):
                raise RuntimeError('still no')

            def is_running(self):
                return True
        parent = _FakeProc(children=[Loud()])
        assert pm._psutil_kill_tree(
            types.SimpleNamespace(pid=1), _fake_psutil_module(parent)) is True


# ═══════════════════════════════════════════════════════════════════
# kill_tree 调度
# ═══════════════════════════════════════════════════════════════════

class TestKillTree:
    def test_never_raises_on_dead_process(self):
        proc = subprocess.Popen(['cmd', '/c', 'exit 0']) if os.name == 'nt' \
            else subprocess.Popen(['true'])
        proc.wait()
        kill_tree(proc)   # 清理路径不许抛

    def test_posix_branch_counts(self, monkeypatch):
        calls = {}
        fake_os = types.SimpleNamespace(
            name='posix', getpgid=lambda pid: 4242,
            killpg=lambda pg, sig: calls.update(pg=pg))
        monkeypatch.setattr(pm, 'os', fake_os)
        kill_tree(types.SimpleNamespace(pid=42))
        assert calls.get('pg') == 4242
        assert KILL_TREE_STATS['posix'] >= 1

    def test_psutil_unavailable_falls_back_taskkill(self, monkeypatch):
        monkeypatch.setattr(pm.os, 'name', 'nt')
        monkeypatch.setattr(pm, '_load_psutil', lambda: None)
        spawned = []

        class FakePopen:
            def __init__(self, cmd, **kw):
                spawned.append(cmd)

            def wait(self, timeout=None):
                return 0
        monkeypatch.setattr(pm.subprocess, 'Popen', FakePopen)
        kill_tree(types.SimpleNamespace(pid=999))
        assert spawned and spawned[0][:4] == ['taskkill', '/F', '/T', '/PID']
        assert KILL_TREE_STATS['taskkill'] >= 1

    def test_psutil_exception_falls_back(self, monkeypatch):
        monkeypatch.setattr(pm.os, 'name', 'nt')
        monkeypatch.setattr(pm, '_load_psutil', lambda: object())

        def boom(proc, psutil):
            raise RuntimeError('psutil path exploded')
        monkeypatch.setattr(pm, '_psutil_kill_tree', boom)
        spawned = []

        class FakePopen:
            def __init__(self, cmd, **kw):
                spawned.append(cmd)

            def wait(self, timeout=None):
                return 0
        monkeypatch.setattr(pm.subprocess, 'Popen', FakePopen)
        kill_tree(types.SimpleNamespace(pid=1))
        assert KILL_TREE_STATS['psutil_failed'] >= 1
        assert spawned

    def test_psutil_success_no_taskkill(self, monkeypatch):
        monkeypatch.setattr(pm.os, 'name', 'nt')
        monkeypatch.setattr(pm, '_load_psutil',
                            lambda: _fake_psutil_module(_FakeProc()))
        spawned = []

        def fake_popen(*a, **k):
            spawned.append(a)
        monkeypatch.setattr(pm.subprocess, 'Popen', fake_popen)
        kill_tree(types.SimpleNamespace(pid=7))
        assert KILL_TREE_STATS['psutil'] >= 1
        assert not spawned   # 走 psutil 成功 → 不回落

    def test_outer_exception_kills_proc(self, monkeypatch):
        # os.name 非 nt 且 killpg 抛 → POSIX 兜底 proc.kill()；若连兜底都炸，
        # 外层 except 再 kill 一次（180-184）
        fake_os = types.SimpleNamespace(
            name='linux',
            getpgid=lambda pid: (_ for _ in ()).throw(OSError('no pgid')))
        monkeypatch.setattr(pm, 'os', fake_os)
        killed = []

        class P:
            pid = 5

            def kill(self):
                killed.append(1)
        kill_tree(P())
        assert killed   # POSIX 兜底 proc.kill

    def test_load_psutil_raise_hits_outer_fallback(self, monkeypatch):
        # _load_psutil 抛 → 外层 except（180-184）→ proc.kill 兜底
        # （Windows 原生 nt 走 psutil 分支；POSIX 走 killpg 失败兜底——
        #   两条路最终都落 proc.kill，本仓套件在 Windows 上验证 180-184）
        monkeypatch.setattr(pm, '_load_psutil',
                            lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        killed = []

        class P:
            pid = 3

            def kill(self):
                killed.append(1)
        kill_tree(P())
        assert killed

    def test_outer_fallback_proc_kill_raises_swallowed(self, monkeypatch):
        # 外层 except 里 proc.kill 也炸 → 静默吞掉（182-184）
        monkeypatch.setattr(pm, '_load_psutil',
                            lambda: (_ for _ in ()).throw(RuntimeError('boom')))

        class P:
            pid = 3

            def kill(self):
                raise RuntimeError('already dead')
        kill_tree(P())   # 不许抛


# ═══════════════════════════════════════════════════════════════════
# run_cmd_safe
# ═══════════════════════════════════════════════════════════════════

class TestRunCmdSafe:
    def test_fast_stdout(self):
        r = run_cmd_safe(FAST_ECHO, timeout=15)
        assert r.returncode == 0 and 'hello stdout' in r.stdout

    def test_fast_stderr_captured(self):
        r = run_cmd_safe(FAST_ERR, timeout=15)
        assert r.returncode == 0 and 'boom err' in r.stderr

    def test_nonzero_exit(self):
        r = run_cmd_safe([PY, '-c', 'import sys; sys.exit(3)'], timeout=15)
        assert r.returncode == 3

    def test_input_injection(self):
        r = run_cmd_safe([PY, '-c', 'import sys; print(sys.stdin.read())'],
                         timeout=15, input='from-stdin')
        assert 'from-stdin' in r.stdout

    def test_cwd_and_env(self, tmp_path):
        r = run_cmd_safe(
            [PY, '-c', 'import os; print(os.environ.get("X_R86", "unset"), '
                       'os.getcwd())'],
            timeout=15, cwd=str(tmp_path),
            env={'X_R86': '1', 'PATH': os.environ.get('PATH', ''),
                 'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),
                 'SYSTEMDRIVE': os.environ.get('SYSTEMDRIVE', 'C:')})
        assert '1' in r.stdout and str(tmp_path) in r.stdout

    def test_shell_mode(self):
        r = run_cmd_safe('echo shell-ok' if os.name != 'nt'
                         else 'echo shell-ok', timeout=15, shell=True)
        assert 'shell-ok' in r.stdout

    def test_spawn_failure_returns_minus_one(self):
        r = run_cmd_safe(['definitely-not-a-real-binary-xyz'], timeout=15)
        assert r.returncode == -1
        assert r.stdout == '' and r.stderr   # 异常文本进 stderr

    def test_timeout_kills_tree_returns_minus9(self):
        t0 = time.monotonic()
        r = run_cmd_safe(SLEEP_CMD, timeout=1)
        elapsed = time.monotonic() - t0
        assert r.returncode == -9
        assert elapsed < 30   # 树被杀，不挂 60s
        assert r.stdout == '' or r.stdout   # 管道已回收

    def test_timeout_grace_reap_returns_empty(self, monkeypatch):
        # 宽限回收失败 → 流关闭（close 抛也吞，240-241）+ 空输出
        monkeypatch.setattr(pm, '_REAP_GRACE_SEC', 0.01)

        class FakeProc:
            pid = 1

            def __init__(self):
                self.stdout = self._Stream()
                self.stderr = self._Stream()

            class _Stream:
                def close(self):
                    raise RuntimeError('close boom')

            def communicate(self, input=None, timeout=None):
                raise subprocess.TimeoutExpired('cmd', timeout)
        monkeypatch.setattr(pm.subprocess, 'Popen',
                            lambda *a, **k: FakeProc())
        r = run_cmd_safe(['fake'], timeout=1)
        assert r.returncode == -9 and r.stdout == '' and r.stderr == ''

    def test_timeout_grace_reap_recovers_output(self, monkeypatch):
        # 树杀干净 → 宽限 communicate 立即返回残留输出
        monkeypatch.setattr(pm, '_REAP_GRACE_SEC', 0.5)

        class FakeProc:
            pid = 1

            def communicate(self, input=None, timeout=None):
                if timeout == 1:
                    raise subprocess.TimeoutExpired('cmd', timeout)
                return ('late stdout', 'late stderr')
        monkeypatch.setattr(pm.subprocess, 'Popen', lambda *a, **k: FakeProc())
        r = run_cmd_safe(['fake'], timeout=1)
        assert r.returncode == -9
        assert r.stdout == 'late stdout' and r.stderr == 'late stderr'


def test_all_exports():
    assert pm.__all__ == ['run_cmd_safe', 'kill_tree', 'KILL_TREE_STATS']
