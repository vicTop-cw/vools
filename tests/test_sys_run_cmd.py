# -*- coding: utf-8 -*-
"""测试 vools.sys.run_cmd — RunCommands。"""

import os
import subprocess
import sys
import pytest

from vools.sys.run_cmd import RunCommands

__all__ = ["TestPython", "TestShell", "TestArgs", "TestImport"]


class TestPython:
    """python 子命令测试。"""

    def test_script_missing(self, monkeypatch, capsys):
        exits = []
        monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
        rc = RunCommands()
        with pytest.raises(SystemExit) as e:
            rc.python("no_such_file.py")
        out = capsys.readouterr().out
        assert "不存在" in out
        assert e.value.code == 1

    def test_script_exists_no_args(self, monkeypatch, capsys):
        fake_run = {"calls": []}

        def _run(cmd, *a, **kw):
            fake_run["calls"].append(cmd)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: fake_run["calls"].append(("exit", code)))
        with open("tmp_run_cmd_test.py", "w") as f:
            f.write("print(1)\n")
        try:
            rc = RunCommands()
            rc.python("tmp_run_cmd_test.py")
            assert fake_run["calls"][0][-1] == "tmp_run_cmd_test.py"
            assert ("exit", 0) in fake_run["calls"]
        finally:
            os.remove("tmp_run_cmd_test.py")

    def test_script_with_args(self, monkeypatch, capsys):
        fake_run = {"calls": []}

        def _run(cmd, *a, **kw):
            fake_run["calls"].append(cmd)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: None)
        with open("tmp_run_cmd_test.py", "w") as f:
            f.write("pass\n")
        try:
            rc = RunCommands()
            rc.python("tmp_run_cmd_test.py", args="--help --verbose")
            assert "--help" in fake_run["calls"][0]
            assert "--verbose" in fake_run["calls"][0]
        finally:
            os.remove("tmp_run_cmd_test.py")

    def test_script_run_error(self, monkeypatch, capsys):
        def _run(cmd, *a, **kw):
            raise OSError("boom")
        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
        with open("tmp_run_cmd_test.py", "w") as f:
            f.write("pass\n")
        try:
            rc = RunCommands()
            with pytest.raises(SystemExit):
                rc.python("tmp_run_cmd_test.py")
            assert "错误" in capsys.readouterr().out
        finally:
            os.remove("tmp_run_cmd_test.py")


class TestShell:
    """shell 子命令测试。"""

    def test_shell_no_args(self, monkeypatch, capsys):
        fake_run = {"calls": []}

        def _run(cmd, *a, **kw):
            fake_run["calls"].append((cmd, kw))
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: None)
        rc = RunCommands()
        rc.shell("echo hi")
        assert fake_run["calls"][0][0] == "echo hi"
        assert "executable" in fake_run["calls"][0][1]

    def test_shell_with_args(self, monkeypatch):
        fake_run = {"calls": []}

        def _run(cmd, *a, **kw):
            fake_run["calls"].append(cmd)
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: None)
        rc = RunCommands()
        rc.shell("dir", args="/b")
        assert fake_run["calls"][0] == "dir /b"

    def test_shell_error(self, monkeypatch, capsys):
        def _run(cmd, *a, **kw):
            raise OSError("nope")
        monkeypatch.setattr(subprocess, "run", _run)
        monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
        rc = RunCommands()
        with pytest.raises(SystemExit):
            rc.shell("echo hi")
        assert "错误" in capsys.readouterr().out


class TestArgs:
    """args 子命令测试。"""

    def test_args(self, capsys):
        rc = RunCommands()
        rc.args("--help")
        out = capsys.readouterr().out
        assert "--help" in out
        assert "用法示例" in out
        assert "run --python" in out
        assert "run --shell" in out


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.run_cmd import __all__
        assert "RunCommands" in __all__
