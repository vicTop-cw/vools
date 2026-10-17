# -*- coding: utf-8 -*-
"""测试 vools.sys.cmd — cmd 装饰器。"""

import asyncio
import os
import sys
import pytest

from vools.sys.cmd import (
    cmd, _build_command, _run_command, _run_sync,
    _snake_to_pascal, _get_shell_args, _function_body_is_pass, _get_executor,
)

__all__ = ["TestBuildCommand", "TestSnakeToPascal", "TestShellArgs",
           "TestRunCommand", "TestBodyPass", "TestCmdDecorator",
           "TestExecutor", "TestImport"]


# 模块级函数避免类内 name mangling
def _echo(msg):
    pass


def _short(_v):
    pass


def _long(__path):
    pass


def _vargs(*items):
    pass


class TestBuildCommand:
    """_build_command 测试。"""

    def test_positional(self):
        assert _build_command("echo", _echo, ("hello",), {}) == "echo hello"

    def test_short_option(self):
        assert _build_command("prog", _short, ("5",), {}) == "prog -v 5"

    def test_short_option_none(self):
        assert _build_command("prog", _short, (None,), {}) == "prog -v"

    def test_long_option(self):
        assert _build_command("prog", _long, ("/tmp",), {}) == "prog --path /tmp"

    def test_long_option_none(self):
        assert _build_command("prog", _long, (None,), {}) == "prog --path"

    def test_var_positional(self):
        assert _build_command("prog", _vargs, (1, 2, 3), {}) == "prog 1 2 3"

    def test_keyword_args(self):
        assert _build_command("prog", _short, (), {"_v": "x"}) == "prog -v x"

    def test_typeerror_fallback(self):
        def f(a, b):
            pass
        assert _build_command("prog", f, ("1",), {}) == "prog 1"


class TestSnakeToPascal:
    """_snake_to_pascal 测试。"""

    def test_single(self):
        assert _snake_to_pascal("echo") == "Echo"

    def test_two_words(self):
        assert _snake_to_pascal("get_childitem") == "Get-Childitem"

    def test_many_words(self):
        assert _snake_to_pascal("write_output") == "Write-Output"

    def test_empty(self):
        assert _snake_to_pascal("") == ""

    def test_leading_underscore(self):
        assert _snake_to_pascal("_foo") == "Foo"


class TestShellArgs:
    """_get_shell_args 测试。"""

    def test_cmd(self):
        assert _get_shell_args("cmd") == ("cmd.exe", ["/c"])

    def test_powershell(self):
        assert _get_shell_args("powershell") == ("powershell.exe", ["-Command"])

    def test_ps_alias(self):
        assert _get_shell_args("ps") == ("powershell.exe", ["-Command"])

    def test_bash(self):
        assert _get_shell_args("bash") == ("bash", ["-c"])

    def test_sh(self):
        assert _get_shell_args("sh") == ("sh", ["-c"])

    def test_wsl(self):
        assert _get_shell_args("wsl") == ("wsl", ["bash", "-c"])

    def test_pwsh(self):
        assert _get_shell_args("pwsh") == ("pwsh", ["-Command"])

    def test_unsupported(self):
        with pytest.raises(ValueError):
            _get_shell_args("unknown")

    def test_upper_case(self):
        assert _get_shell_args("CMD") == ("cmd.exe", ["/c"])


class TestRunCommand:
    """_run_command 测试。"""

    def test_success(self):
        code, out, err = _run_command("echo hello", "cmd")
        assert code == 0
        assert "hello" in out

    def test_shell_not_found(self):
        # "sh" 在 Windows 上通常不存在 → FileNotFoundError → "Shell not found"
        code, out, err = _run_command("echo hi", "sh")
        assert code == 1
        assert "not found" in err.lower()

    def test_other_exception(self):
        # 非支持的 shell → _get_shell_args 抛 ValueError → _run_command 捕获 → (1, '', ...)
        code, out, err = _run_command("echo hi", "unknownshell")
        assert code == 1
        assert err != ""


class TestBodyPass:
    """_function_body_is_pass 测试。"""

    def test_pass_body(self):
        def f():
            pass
        assert _function_body_is_pass(f) is True

    def test_real_body(self):
        def f():
            return "x"
        assert _function_body_is_pass(f) is False

    def test_none_body(self):
        def f():
            None
        assert _function_body_is_pass(f) is True

    def test_invalid_source(self):
        f = lambda x: x
        assert _function_body_is_pass(f) is False

    def test_async_function(self):
        async def f():
            pass
        assert _function_body_is_pass(f) is True


class TestCmdDecorator:
    """cmd 装饰器测试。"""

    def test_no_parens(self):
        @cmd
        def echo(msg):
            pass
        assert callable(echo)

    def test_powershell_success(self):
        @cmd("echo", shell="cmd")
        def echo(msg):
            pass
        code, out, err = echo("hello from cmd")
        assert code == 0
        assert "hello from cmd" in out

    def test_explicit_fallback_on_build_error(self, monkeypatch):
        import importlib
        cmd_mod = importlib.import_module("vools.sys.cmd")

        @cmd("echo", shell="cmd", fallback=lambda *a, **kw: (7, "fb", ""))
        def f():
            pass

        def _bad_build(*a, **kw):
            raise ValueError("build failed")
        monkeypatch.setattr(cmd_mod, "_build_command", _bad_build)
        code, out, err = f()
        assert code == 7
        assert out == "fb"

    def test_body_fallback_on_build_error(self, monkeypatch):
        import importlib
        cmd_mod = importlib.import_module("vools.sys.cmd")

        @cmd("echo", shell="cmd")
        def f():
            return (0, "body", "")

        def _bad_build(*a, **kw):
            raise ValueError("build failed")
        monkeypatch.setattr(cmd_mod, "_build_command", _bad_build)
        code, out, err = f()
        assert code == 0
        assert out == "body"

    def test_no_fallback_raises_on_build_error(self, monkeypatch):
        import importlib
        cmd_mod = importlib.import_module("vools.sys.cmd")

        @cmd("echo", shell="cmd")
        def f():
            pass

        def _bad_build(*a, **kw):
            raise ValueError("build failed")
        monkeypatch.setattr(cmd_mod, "_build_command", _bad_build)
        with pytest.raises(ValueError):
            f()

    def test_no_fallback_cmd_fail_returns(self):
        # _run_command 吞掉异常，_run_sync 正常返回 (1, '', ...)
        @cmd("nonexistent_cmd_xyz", shell="cmd")
        def f():
            pass
        code, out, err = f()
        assert code == 1

    def test_async_mode(self):
        @cmd("echo", shell="cmd", async_mode=True)
        async def echo(msg):
            pass
        assert asyncio.iscoroutinefunction(echo)

    def test_async_call(self):
        @cmd("echo", shell="cmd", async_mode=True)
        async def echo(msg):
            pass
        code, out, err = asyncio.run(echo("hi"))
        assert code == 0
        assert "hi" in out

    def test_no_parens_async(self):
        @cmd(async_mode=True)
        async def echo(msg):
            pass
        assert asyncio.iscoroutinefunction(echo)


class TestExecutor:
    """线程池测试。"""

    def test_get_executor(self):
        e = _get_executor()
        assert e is not None
        assert _get_executor() is e


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.cmd import __all__
        assert "cmd" in __all__
