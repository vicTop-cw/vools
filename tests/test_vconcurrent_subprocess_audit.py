# -*- coding: utf-8 -*-
"""审计锁定：vools.vconcurrent.subprocess_mod 的调用与校验契约。

本轮审计确认该模块行为一致、校验完备（无需修复），在此锁定防回归：

1. ``run_command(list)`` → ``(returncode, stdout, stderr)``；
2. ``run_command(str)`` 在 ``shell=False``（默认）时把整串当可执行名 → 响亮
   ``FileNotFoundError``（不会静默把 "echo hi" 当命令拆词执行）；``shell=True`` 才走 shell；
3. ``timeout`` 超时 → ``TimeoutExpired`` 向上抛（不静默返回 -1）；
4. 参数校验：``cmd`` 非 str/序列 → TypeError、空序列 → ValueError、
   ``timeout`` 负数 → ValueError、非数字 → TypeError（均带参数名）；
5. ``which``：命中返回路径、未命中返回 ``None``；
6. 异步 ``run_command_async`` → ``VProcess``，``communicate()`` 收集输出、``returncode`` 可用。
"""

import sys
import time

import pytest

from vools.vconcurrent.subprocess_mod import (
    run_command,
    run_command_async,
    which,
)

PY = sys.executable


class TestRunCommandList:
    def test_returns_code_out_err(self):
        code, out, err = run_command([PY, "-c", "print('hi')"])
        assert code == 0
        assert out.strip() == "hi"
        assert err == ""

    def test_nonzero_exit(self):
        code, _, _ = run_command([PY, "-c", "raise SystemExit(3)"])
        assert code == 3

    def test_stderr_captured(self):
        code, out, err = run_command([PY, "-c", "import sys; sys.stderr.write('boom')"])
        assert code == 0
        assert "boom" in err


class TestShellSemantics:
    def test_string_without_shell_is_loud(self):
        """默认 shell=False：整串当可执行名，响亮 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            run_command("echo hi")

    def test_string_with_shell_works(self):
        code, out, _ = run_command("echo hi", shell=True)
        assert code == 0
        assert "hi" in out


class TestTimeout:
    def test_timeout_raises(self):
        from subprocess import TimeoutExpired

        t0 = time.time()
        with pytest.raises(TimeoutExpired):
            run_command([PY, "-c", "import time; time.sleep(2)"], timeout=0.2)
        assert time.time() - t0 < 3.0


class TestValidation:
    @pytest.mark.parametrize("bad", [None, 123, 1.5])
    def test_bad_cmd_type(self, bad):
        with pytest.raises(TypeError) as ei:
            run_command(bad)
        assert "cmd" in str(ei.value)

    def test_empty_cmd(self):
        with pytest.raises(ValueError) as ei:
            run_command([])
        assert "cmd" in str(ei.value)

    def test_negative_timeout(self):
        with pytest.raises(ValueError) as ei:
            run_command([PY, "-c", "print(1)"], timeout=-1)
        assert "timeout" in str(ei.value)

    def test_non_numeric_timeout(self):
        with pytest.raises(TypeError) as ei:
            run_command([PY, "-c", "print(1)"], timeout="x")
        assert "timeout" in str(ei.value)


class TestWhich:
    def test_found(self):
        assert which(PY)

    def test_missing_returns_none(self):
        assert which("no-such-cmd-xyz") is None


class TestAsync:
    def test_communicate_and_returncode(self):
        vp = run_command_async([PY, "-c", "print('done')"])
        out, err = vp.communicate()
        assert "done" in out
        assert vp.returncode == 0

    def test_is_running_flag(self):
        vp = run_command_async([PY, "-c", "import time; time.sleep(0.3); print('x')"])
        try:
            assert vp.is_running is True
        finally:
            vp.communicate()
