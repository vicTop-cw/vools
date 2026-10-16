# -*- coding: utf-8 -*-
"""tests/core/test_sys_cli.py — vools sys CLI 在「核心不含 vools-bridges」时必须可用。

回归锁（BUG-57）：vools/sys/dll_cmd.py 曾在【模块顶层】
`from ..bridge.core.loader import _LIB_DIR, _IS_WINDOWS`。而 vools.bridge 是**可选**
分发（pip install 'vools[bridges]'）——标准安装（核心不含 bridges）下
`python -m vools sys` 直接 ModuleNotFoundError 崩溃（实测 exit=1），违反
「桥接不可用则优雅降级」的既定契约（BUG-3 同族）。

之所以长期漏网：全仓没有任何测试引用 DllCommands / SysCLI / `vools sys`，
CLI 面完全裸奔。本文件钉两格：
  1. 纯核心隔离环境里 import vools.sys.dll_cmd 不再抛异常；
  2. 同一环境下 `python -m vools sys` 退出码为 0（复现原始崩溃点）。

隔离方式：子进程只把【仓库根】挂进 PYTHONPATH，不挂 bridges/ 等 namespace 子包
目录（仓库根 vools/ 下本就没有 bridges 子目录，pkgutil.extend_path 也发现不了它），
于是 vools.bridge 确实不可用——正是用户的标准安装形态。
"""

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _core_only_env():
    """只暴露核心仓库根的子进程环境（不含 vools-bridges）。"""
    env = dict(os.environ)
    env['PYTHONPATH'] = REPO_ROOT
    env['PYTHONUTF8'] = '1'
    return env


def _run(args, code=None):
    """跑一个子进程，返回 (returncode, stdout, stderr)。"""
    cmd = [sys.executable] + args
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       cwd=REPO_ROOT, env=_core_only_env(),
                       universal_newlines=True, timeout=180)
    return r.returncode, (r.stdout or ''), (r.stderr or '')


def test_vools_bridge_absent_in_isolated_env():
    """前置确认：隔离环境里 vools.bridge 真的不可用（否则下面两格测的是别的东西）。"""
    code = (
        'import sys\n'
        'sys.path.insert(0, r"%s")\n'
        'try:\n'
        '    import vools.bridge\n'
        '    print("BRIDGE_PRESENT")\n'
        'except ImportError:\n'
        '    print("BRIDGE_ABSENT")\n'
    ) % REPO_ROOT
    rc, out, err = _run(['-c', code])
    assert rc == 0, err[-400:]
    assert 'BRIDGE_ABSENT' in out, (
        '隔离环境里 vools.bridge 竟然可用，本文件的前提失效，需重写隔离方式')


def test_dll_cmd_imports_without_bridges():
    """核心不含 bridges 时 vools.sys.dll_cmd 必须能 import（BUG-57 原始崩溃点）。"""
    code = (
        'import sys\n'
        'sys.path.insert(0, r"%s")\n'
        'import vools.sys.dll_cmd as dc\n'
        'assert dc._IS_WINDOWS in (True, False)\n'
        'assert dc._find_dll_path("vools_crypto") is None\n'
        'dc.DllCommands().list()\n'
        'dc.DllCommands().func("vools_seq", "seq_map_int")\n'
        'print("DLLCMD_OK")\n'
    ) % REPO_ROOT
    rc, out, err = _run(['-c', code])
    assert rc == 0, 'dll_cmd 在无 bridges 的核心安装里崩了:\n%s\n%s' % (err[-600:], out[-300:])
    assert 'DLLCMD_OK' in out


def test_sys_cli_module_runs_without_bridges():
    """`python -m vools sys` 在无 bridges 时必须退 0（修复前实测 exit=1）。"""
    rc, out, err = _run(['-m', 'vools', 'sys'])
    assert rc == 0, 'python -m vools sys 崩了 (exit=%s):\n%s' % (rc, (err or out)[-600:])


def test_sys_package_imports_without_bridges():
    """整个 vools.sys 包（含 fire_app→dll_cmd 链）在无 bridges 时必须可导入。"""
    code = (
        'import sys\n'
        'sys.path.insert(0, r"%s")\n'
        'import vools.sys\n'
        'import vools.sys.env_cmd\n'
        'print("SYSPKG_OK")\n'
    ) % REPO_ROOT
    rc, out, err = _run(['-c', code])
    assert rc == 0, 'vools.sys 包在无 bridges 时崩了:\n%s\n%s' % (err[-600:], out[-300:])
    assert 'SYSPKG_OK' in out
