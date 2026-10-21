# -*- coding: utf-8 -*-
"""回归测试：@cmd 命令构建器参数引号与 None 处理（BUG-243）。

原 `_build_command` 把参数值 `str(v)` 直拼、空格/元字符不引号：
- 含空格的值（Windows 路径 `C:\\My Files\\x`、消息）被拆成多个参数；
- 含 `;`/`&`/`|`/`$(...)` 的值直接注入内层 shell；
- 非下划线参数为 None（未提供的可选参数）时被渲染成字面 `"None"`。

修复：`_build_command(..., shell=...)` 按目标 shell 规则加引号
（bash/sh/wsl 用 shlex.quote；powershell/pwsh 单引号双写；cmd 用
subprocess.list2cmdline），简单值原样返回保持既有输出兼容；None 跳过。
"""

import subprocess

import pytest

from vools.sys.cmd import _build_command


def _one(msg):
    pass


def _opt(msg=None):
    pass


def _short(_v=None):
    pass


def _long(__path=None):
    pass


def _varargs(*rest):
    pass


class TestExistingBehaviorKept:
    """简单值输出与既有约定 byte-identical（防修复过度）。"""

    def test_simple_value(self):
        assert _build_command('echo', _one, ('hello',), {}) == 'echo hello'

    def test_short_option(self):
        assert _build_command('prog', _short, (), {'_v': 'x'}) == 'prog -v x'

    def test_short_option_none_is_flag(self):
        assert _build_command('prog', _short, (), {'_v': None}) == 'prog -v'

    def test_long_option(self):
        assert _build_command('prog', _long, ('/tmp',), {}) == 'prog --path /tmp'

    def test_varargs(self):
        assert _build_command('prog', _varargs, (1, 2, 3), {}) == 'prog 1 2 3'


class TestNoneNotRendered:
    """BUG-243 ①：None 不渲染成字面 "None"。"""

    def test_default_none_skipped(self):
        assert _build_command('echo', _opt, (), {}) == 'echo'

    def test_explicit_none_skipped(self):
        assert _build_command('echo', _one, (None,), {}) == 'echo'

    def test_value_provided_kept(self):
        assert _build_command('echo', _opt, ('x',), {}) == 'echo x'


class TestQuotingPerShell:
    """BUG-243 ②：按目标 shell 规则加引号。"""

    def test_bash_space(self):
        assert _build_command('echo', _one, ('hello world',), {},
                              shell='bash') == "echo 'hello world'"

    def test_bash_metachar_neutralized(self):
        assert _build_command('echo', _one, ('a; echo INJECTED',), {},
                              shell='bash') == "echo 'a; echo INJECTED'"

    def test_powershell_space(self):
        assert _build_command('echo', _one, ('hello world',), {},
                              shell='powershell') == "echo 'hello world'"

    def test_powershell_quote_escaped(self):
        assert _build_command('echo', _one, ("it's",), {},
                              shell='powershell') == "echo 'it''s'"

    def test_cmd_space(self):
        assert _build_command('echo', _one, ('hello world',), {},
                              shell='cmd') == 'echo "hello world"'

    def test_option_value_quoted(self):
        assert _build_command('prog', _short, (), {'_v': 'a b'},
                              shell='bash') == "prog -v 'a b'"


class TestRealExecution:
    """真实 shell 执行：空格值成为单参数、注入被消解。"""

    def test_space_single_arg(self):
        cmd = _build_command('printf "[%s]"', _one, ('hello world',), {},
                             shell='bash')
        out = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
        assert out.stdout == '[hello world]'

    def test_injection_neutralized(self):
        cmd = _build_command('printf "[%s]"', _one, ('a; echo INJECTED',), {},
                             shell='bash')
        out = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
        assert out.stdout == '[a; echo INJECTED]'