# -*- coding: utf-8 -*-
"""回归测试：vools.sys 的 fallback 形同虚设 + 零校验（BUG-511）。

修复前：

    @cmd("no-such-cmd-xyz", fallback=lambda: "FB")
    def f(): pass
    f()      # → (1, '', "The term 'no-such-cmd-xyz' is not recognized...")
             #   **fallback 从未被调用**！因为 _run_sync 只在抛异常时回退，
             #   而 shell 里"命令不存在/执行失败"表现为**非零退出码**，不抛异常。

    @cmd("exit 3", shell="cmd", fallback=lambda: "FB")
    def g(): pass
    g()      # → (3, '', '')   同样不回退

    cmd("echo hi", fallback=123)   # 装饰期静默通过，失败时才炸 'int' object is not callable

修复：
- cmd/exe 的 _run_sync 在**非零退出码**时同样调用 fallback（与 docstring
  "命令执行失败时调用 / exe 不存在或执行失败时调用"一致）；
- cmd/exe/dll 入口校验 fallback 必须可调用或 None。
"""

import pytest

import vools.sys as vs


class TestCmdFallbackOnFailure:
    def test_missing_command_uses_fallback(self):
        @vs.cmd("no-such-cmd-xyz", fallback=lambda: "FB-CMD")
        def f():
            pass

        assert f() == "FB-CMD"

    def test_nonzero_exit_uses_fallback(self):
        @vs.cmd("exit 3", shell="cmd", fallback=lambda: "FB-NZ")
        def g():
            pass

        assert g() == "FB-NZ"

    def test_success_does_not_call_fallback(self):
        @vs.cmd("echo hi", fallback=lambda: "FB-OK")
        def h():
            pass

        code, out, err = h()
        assert code == 0
        assert "hi" in out

    def test_no_fallback_still_returns_tuple(self):
        @vs.cmd("no-such-cmd-xyz")
        def k():
            pass

        code, out, err = k()
        assert code != 0

    def test_fallback_receives_call_args(self):
        @vs.cmd("no-such-cmd-xyz", fallback=lambda x: f"FB:{x}")
        def m(_x):
            pass

        assert m("v") == "FB:v"


class TestExeFallback:
    def test_missing_exe_uses_fallback(self):
        @vs.exe("no-such-exe-xyz.exe", fallback=lambda: "FB-EXE")
        def f():
            pass

        assert f() == "FB-EXE"

    def test_missing_exe_raises_without_fallback(self):
        @vs.exe("no-such-exe-xyz.exe")
        def f():
            pass

        with pytest.raises(FileNotFoundError):
            f()


class TestFallbackValidation:
    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_cmd(self, bad):
        with pytest.raises(TypeError) as ei:
            vs.cmd("echo hi", fallback=bad)
        assert "fallback" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x"])
    def test_exe(self, bad):
        with pytest.raises(TypeError) as ei:
            vs.exe("echo", fallback=bad)
        assert "fallback" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x"])
    def test_dll(self, bad):
        with pytest.raises(TypeError) as ei:
            vs.dll("x.dll", fallback=bad)
        assert "fallback" in str(ei.value)

    def test_none_and_callable_allowed(self):
        assert callable(vs.cmd("echo hi", fallback=None))
        assert callable(vs.cmd("echo hi", fallback=lambda: 1))
        assert callable(vs.exe("echo", fallback=lambda: 1))
        assert callable(vs.dll("x.dll", fallback=lambda: 1))


class TestNormalPathsUnchanged:
    def test_cmd_echo(self):
        @vs.cmd("echo hi")
        def f():
            pass

        code, out, err = f()
        assert code == 0 and "hi" in out

    def test_cmd_bad_shell_loud(self):
        @vs.cmd("echo hi", shell="bogus")
        def f():
            pass

        code, out, err = f()
        # 无 fallback：保持返回三元组语义（stderr 说明 shell 不支持）
        assert code == 1
        assert "Unsupported shell" in err

    def test_body_fallback_still_works(self):
        @vs.cmd("no-such-cmd-xyz")
        def f():
            return (0, "body", "")

        assert f() == (0, "body", "")
