# -*- coding: utf-8 -*-
"""测试 vools.vconcurrent.subprocess_mod — VProcess / Pipeline / run_command 等。"""

import sys
import subprocess
import threading
import time
import pytest

from vools.vconcurrent.subprocess_mod import (
    VProcess, Pipeline, run_command, run_command_async,
    capture_output, which, _normalize_command, _normalize_env,
)

__all__ = ["TestNormalizeCommand", "TestNormalizeEnv", "TestVProcess",
           "TestPipeline", "TestRunCommand", "TestRunCommandAsync",
           "TestCaptureOutput", "TestWhich", "TestImport"]


class TestNormalizeCommand:
    """_normalize_command 测试。"""

    def test_str_shell(self):
        assert _normalize_command("echo hi", shell=True) == "echo hi"

    def test_list_shell(self):
        assert _normalize_command(["echo", "hi"], shell=True) == "echo hi"

    def test_list_shell_quoted(self):
        assert _normalize_command(["echo", "a b"], shell=True) == "echo 'a b'"

    def test_str_no_shell(self):
        assert _normalize_command("echo hi", shell=False) == ["echo", "hi"]

    def test_list_no_shell(self):
        assert _normalize_command(["echo", "hi"], shell=False) == ["echo", "hi"]

    def test_tuple_no_shell(self):
        assert _normalize_command(("echo", "hi"), shell=False) == ["echo", "hi"]


class TestNormalizeEnv:
    """_normalize_env 测试。"""

    def test_none(self):
        assert _normalize_env(None) is None

    def test_dict(self):
        assert _normalize_env({"PATH": "/usr/bin", "A": 1}) == {"PATH": "/usr/bin", "A": "1"}


class TestVProcess:
    """VProcess 测试。"""

    def test_init_and_pid(self):
        proc = VProcess(["python", "-c", "print('hi')"])
        assert proc.pid is not None
        assert proc.is_running is True

    def test_communicate(self):
        proc = VProcess(["python", "-c", "print('hello')"])
        out, err = proc.communicate()
        assert proc.returncode == 0
        assert "hello" in out

    def test_wait(self):
        proc = VProcess(["python", "-c", "print('hi')"])
        rc = proc.wait()
        assert rc == 0

    def test_shell(self):
        proc = VProcess("python -c \"print('hi')\"", shell=True)
        out, err = proc.communicate()
        assert "hi" in out

    def test_stdin(self):
        proc = VProcess(["python", "-c", "import sys; print(sys.stdin.read().strip())"])
        out, err = proc.communicate()
        # stdin 无数据时 python -c 会等待 stdin EOF，此处验证不崩溃
        assert proc.returncode == 0

    def test_context_manager(self):
        with VProcess(["python", "-c", "print('hi')"]) as proc:
            proc.wait()

    def test_iter_stdout(self):
        proc = VProcess(["python", "-c", "for i in range(3): print(i)"])
        lines = list(proc.iter_stdout())
        assert len(lines) >= 3
        proc.wait()

    def test_iter_stderr(self):
        proc = VProcess(["python", "-c", "import sys; sys.stderr.write('x\\n')"])
        lines = list(proc.iter_stderr())
        assert len(lines) >= 1
        proc.wait()

    def test_terminate(self):
        proc = VProcess(["python", "-c", "import time; time.sleep(10)"])
        proc.terminate()
        time.sleep(0.1)
        assert not proc.is_running or proc.returncode is not None

    def test_kill(self):
        proc = VProcess(["python", "-c", "import time; time.sleep(10)"])
        proc.kill()
        assert proc.returncode is not None

    def test_returncode_none(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v._returncode = None
        v._stdout = None
        v._stderr = None
        v._killed = False
        assert v.returncode is None

    def test_communicate_raises_not_started(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v._stdout = None
        v._stderr = None
        v._returncode = None
        v._killed = False
        v._timeout = None
        v._stdin_data = None
        with pytest.raises(RuntimeError):
            v.communicate()

    def test_wait_raises_not_started(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v._stdout = None
        v._stderr = None
        v._returncode = None
        v._killed = False
        v._timeout = None
        with pytest.raises(RuntimeError):
            v.wait()

    def test_process_none_pid(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v._returncode = None
        assert v.pid is None

    def test_iter_stdout_none_proc(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        assert list(v.iter_stdout()) == []

    def test_iter_stderr_none_proc(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        assert list(v.iter_stderr()) == []

    def test_kill_none_proc(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v._killed = False
        v.kill()

    def test_terminate_none_proc(self):
        v = VProcess.__new__(VProcess)
        v._proc = None
        v.terminate()

    def test_repr(self):
        proc = VProcess(["python", "-c", "print('hi')"])
        assert "VProcess" in repr(proc)
        proc.wait()

    def test_read_stdout_stderr(self):
        proc = VProcess(["python", "-c", "print('hello')"])
        proc.communicate()
        assert "hello" in proc.read_stdout()

    def test_exit_nonrunning(self):
        proc = VProcess(["python", "-c", "print('hi')"])
        proc.wait()
        with proc:
            pass

    def test_iter_stdout_with_timeout(self):
        proc = VProcess(["python", "-c", "for i in range(5): print(i)"])
        lines = list(proc.iter_stdout(timeout=5))
        assert len(lines) >= 5
        proc.wait()


class TestPipeline:
    """Pipeline 测试。"""

    def test_basic(self):
        pipe = Pipeline(["python", "-c", "print('hello world')"])
        rc, out, err = pipe.run()
        assert rc == 0
        assert "hello world" in out

    def test_or_operator(self):
        pipe = Pipeline(["python", "-c", "print('hello')"]) | ["python", "-c", "import sys; print(sys.stdin.read().strip().upper())"]
        rc, out, err = pipe.run()
        assert rc == 0
        assert "HELLO" in out

    def test_string_cmd(self):
        pipe = Pipeline("python -c \"print('hi')\"", shell=True)
        rc, out, err = pipe.run()
        assert rc == 0
        assert "hi" in out

    def test_env(self):
        pipe = Pipeline(["python", "-c", "print('hi')"]).env({"X": "1"})
        assert pipe._env == {"X": "1"}

    def test_cwd(self):
        pipe = Pipeline(["python", "-c", "print('hi')"]).cwd(".")
        assert pipe._cwd == "."

    def test_timeout_set(self):
        pipe = Pipeline(["python", "-c", "print('hi')"]).timeout(5)
        assert pipe._timeout == 5

    def test_stage(self):
        pipe = Pipeline(["python", "-c", "print('a')"]).stage(["python", "-c", "print('b')"], shell=False)
        rc, out, err = pipe.run()
        assert rc == 0

    def test_pipe_chain(self):
        p1 = Pipeline(["python", "-c", "print('hi')"])
        p2 = Pipeline(["python", "-c", "print('bye')"])
        p3 = p1 | p2
        assert len(p3._stages) == 2

    def test_empty(self):
        # 空 Pipeline（无 stages）返回 (0, "", "")
        pipe = Pipeline.__new__(Pipeline)
        pipe._stages = []
        pipe._env = None
        pipe._cwd = None
        pipe._timeout = None
        rc, out, err = pipe.run()
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_repr(self):
        pipe = Pipeline(["python", "-c", "print('hi')"])
        assert "Pipeline" in repr(pipe)


class TestRunCommand:
    """run_command 测试。"""

    def test_basic(self):
        rc, out, err = run_command(["python", "-c", "print('hello')"])
        assert rc == 0
        assert "hello" in out

    def test_shell(self):
        rc, out, err = run_command("python -c \"print('hello')\"", shell=True)
        assert rc == 0
        assert "hello" in out

    def test_env(self):
        rc, out, err = run_command(["python", "-c", "import os; print(os.environ.get('FOO',''))"], env={"FOO": "bar"})
        assert "bar" in out

    def test_fail(self):
        rc, out, err = run_command(["python", "-c", "import sys; sys.exit(3)"])
        assert rc == 3


class TestRunCommandAsync:
    """run_command_async 测试。"""

    def test_returns_vprocess(self):
        proc = run_command_async(["python", "-c", "print('hi')"])
        assert isinstance(proc, VProcess)
        proc.wait()


class TestCaptureOutput:
    """capture_output 测试。"""

    def test_basic(self):
        rc, out, err = capture_output(["python", "-c", "print('hello')"])
        assert rc == 0
        assert "hello" in out

    def test_callback(self):
        calls = []
        rc, out, err = capture_output(
            ["python", "-c", "print(1); print(2)"],
            callback=lambda line, stream: calls.append((line, stream)),
        )
        assert len(calls) >= 2

    def test_callback_exception_safe(self):
        def bad(line, stream):
            raise RuntimeError("boom")
        rc, out, err = capture_output(["python", "-c", "print('hi')"], callback=bad)
        assert rc == 0


class TestWhich:
    """which 测试。"""

    def test_find_python(self):
        assert which("python") is not None

    def test_not_found(self):
        assert which("nonexistent_prog_xyz_123") is None


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.vconcurrent.subprocess_mod import __all__
        assert "VProcess" in __all__
        assert "Pipeline" in __all__
        assert "run_command" in __all__
        assert "run_command_async" in __all__
        assert "capture_output" in __all__
        assert "which" in __all__
