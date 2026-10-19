# -*- coding: utf-8 -*-
"""测试 vools.sys.exe — exe 装饰器。"""

import asyncio
import os
import shutil
import sys
import pytest

from vools.sys.exe import (
    exe, _build_command, _run_command, _run_sync,
    _function_body_is_pass, _get_executor,
)

__all__ = ["TestBuildCommand", "TestRunCommand", "TestBodyPass",
           "TestExeDecorator", "TestExecutor", "TestImport"]


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
        cmd = _build_command("echo", _echo, ("hello",), {})
        assert cmd == ["echo", "hello"]

    def test_short_option(self):
        cmd = _build_command("prog", _short, ("5",), {})
        assert cmd == ["prog", "-v", "5"]

    def test_short_option_none(self):
        cmd = _build_command("prog", _short, (None,), {})
        assert cmd == ["prog", "-v"]

    def test_long_option(self):
        cmd = _build_command("prog", _long, ("/tmp",), {})
        assert cmd == ["prog", "--path", "/tmp"]

    def test_long_option_none(self):
        cmd = _build_command("prog", _long, (None,), {})
        assert cmd == ["prog", "--path"]

    def test_var_positional(self):
        # sig.bind((1,2,3)) → items = ((1,2,3),)，迭代取到 (1,2,3) 作为单个元素
        cmd = _build_command("prog", _vargs, ((1, 2, 3),), {})
        assert cmd == ["prog", "(1, 2, 3)"]

    def test_var_positional_multi(self):
        cmd = _build_command("prog", _vargs, (1, 2, 3), {})
        assert cmd == ["prog", "1", "2", "3"]

    def test_keyword_args(self):
        cmd = _build_command("prog", _short, (), {"_v": "x"})
        assert cmd == ["prog", "-v", "x"]

    def test_typeerror_fallback(self):
        def f(a, b):
            pass
        cmd = _build_command("prog", f, ("1",), {})
        assert cmd == ["prog", "1"]


class TestRunCommand:
    """_run_command 测试。"""

    def test_success(self):
        code, out, err = _run_command([sys.executable, "-c", "print('hi')"])
        assert code == 0
        assert "hi" in out

    def test_nonzero(self):
        code, out, err = _run_command([sys.executable, "-c", "import sys; sys.exit(3)"])
        assert code == 3

    def test_not_found(self):
        with pytest.raises(FileNotFoundError):
            _run_command(["definitely_not_a_real_cmd_xyz"])

    def test_other_exception(self):
        # 传非字符串元素 → 触发 subprocess 异常 → 走 except Exception 分支
        code, out, err = _run_command([None])
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
        # 无法 inspect 的函数（如 lambda）返回 False
        f = lambda x: x
        assert _function_body_is_pass(f) is False


class TestExeDecorator:
    """exe 装饰器测试。"""

    def test_success_call(self):
        @exe(sys.executable)
        def run_py(_c=None):
            pass
        code, out, err = run_py(_c="print('works')")
        assert code == 0
        assert "works" in out

    def test_fallback_explicit(self):
        @exe("Z:/nonexistent_prog_xyz", fallback=lambda *a, **kw: (7, "fb", ""))
        def f():
            pass
        code, out, err = f()
        assert code == 7
        assert out == "fb"

    def test_fallback_body(self):
        @exe("Z:/nonexistent_prog_xyz")
        def f():
            return (0, "body", "")
        code, out, err = f()
        assert code == 0
        assert out == "body"

    def test_no_fallback_raises(self):
        @exe("Z:/nonexistent_prog_xyz")
        def f():
            pass
        with pytest.raises(FileNotFoundError):
            f()

    def test_async_mode(self):
        @exe(sys.executable, async_mode=True)
        async def run_py(_c=None):
            pass
        assert asyncio.iscoroutinefunction(run_py)

    def test_async_call(self):
        @exe(sys.executable, async_mode=True)
        async def run_py(_c=None):
            pass
        result = asyncio.run(run_py(_c="print('async')"))
        code, out, err = result
        assert code == 0
        assert "async" in out


class TestExecutor:
    """线程池测试。"""

    def test_get_executor(self):
        e = _get_executor()
        assert e is not None
        # 幂等
        assert _get_executor() is e


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.exe import __all__
        assert "exe" in __all__


# BUG-184 回归：函数定义在模块级，避免 Python 类作用域对 `__version`
# 这类双下划线参数名做私有名称改写（会变成 `_Cls__version`，导致
# _build_command 误判为短选项 `-version`，git 收到非法参数而 rc=1）。
def _git_run(__version=None):
    pass


def _unknown_run():
    pass


def _path_run(__version=None):
    pass


class TestPathCommandName:
    """BUG-184 回归：@exe 应支持 PATH 中的命令名（如 git/python），
    而非因 os.path.exists 恒 False 误判为不存在。"""

    def _pick_path_command(self):
        for name in ("git", "python", "where"):
            if shutil.which(name):
                return name
        pytest.skip("PATH 中无可用探测命令")

    def test_path_command_name_resolves(self):
        name = self._pick_path_command()
        run = exe(name)(_path_run)

        assert not os.path.exists(name)
        assert shutil.which(name) is not None

        rc, _out, _err = run(__version=None)
        assert isinstance(rc, int)

    def test_path_command_name_long_option_success(self):
        """git --version 类长选项应真正执行成功（exit 0）。"""
        if not shutil.which("git"):
            pytest.skip("git 不在 PATH")

        run = exe("git")(_git_run)
        rc, out, _err = run(__version=None)
        assert rc == 0
        assert "version" in out.lower()

    def test_unknown_path_command_still_raises(self):
        @exe("vools_definitely_not_a_cmd_xyz_123")
        def run():
            pass
        with pytest.raises(FileNotFoundError):
            run()
