# -*- coding: utf-8 -*-
"""测试 vools.sys.compile_cmd — CompileCommands。"""

import os
import sys
import pytest

from vools.sys.compile_cmd import CompileCommands

__all__ = ["TestInit", "TestNim", "TestC", "TestCpp",
           "TestLang", "TestRun", "TestImport"]


def _make_result(returncode=0, stdout="", stderr=""):
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


class TestInit:
    """__init__ 测试。"""

    def test_compilers_map(self):
        cc = CompileCommands()
        assert set(cc._compilers.keys()) == {"nim", "c", "cpp"}
        assert callable(cc._compilers["nim"])
        assert callable(cc._compilers["c"])
        assert callable(cc._compilers["cpp"])


class TestNim:
    """nim 编译器分支。"""

    def test_missing_file(self, capsys):
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._nim_compiler("Z:/nonexistent.nim", "out.dll")
        out = capsys.readouterr().out
        assert "不存在" in out

    def test_success(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.nim"
        f.write_text("proc main() = discard")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: _make_result(0, "ok", ""))
        cc = CompileCommands()
        cc._nim_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out

    def test_failure(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.nim"
        f.write_text("bad")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: _make_result(1, "", "compile error"))
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._nim_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译失败" in out

    def test_not_found(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.nim"
        f.write_text("x")
        def _raise(*a, **kw):
            raise FileNotFoundError("nim not found")
        monkeypatch.setattr("subprocess.run", _raise)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._nim_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "未找到" in out


class TestC:
    """C 编译器分支。"""

    def test_missing_file(self, capsys):
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._c_compiler("Z:/nonexistent.c", "out.dll")
        out = capsys.readouterr().out
        assert "不存在" in out

    def test_no_compiler(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.c"
        f.write_text("int main(){return 0;}")
        def _raise(*a, **kw):
            raise FileNotFoundError("no compiler")
        monkeypatch.setattr("subprocess.run", _raise)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._c_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "未找到" in out

    def test_gcc_success(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.c"
        f.write_text("int main(){return 0;}")
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "gcc" and "--version" in cmd:
                return _make_result(0, "gcc (x) 1.0", "")
            if cmd[0] == "cl":
                raise FileNotFoundError("no cl")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        cc._c_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out
        assert any(c[0] == "gcc" and "-shared" in c for c in calls)

    def test_cl_success(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.c"
        f.write_text("int main(){return 0;}")
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "gcc":
                raise FileNotFoundError("no gcc")
            if cmd[0] == "cl" and "--version" in cmd:
                return _make_result(0, "cl 19.0", "")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        cc._c_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out
        assert any(c[0] == "cl" and "/LD" in c for c in calls)

    def test_c_failure(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.c"
        f.write_text("int main(){return 0;}")
        def fake_run(cmd, **kw):
            if cmd[0] == "gcc" and "--version" in cmd:
                return _make_result(0, "gcc", "")
            return _make_result(1, "", "compile err")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._c_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译失败" in out

    def test_c_generic_exception(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.c"
        f.write_text("int main(){return 0;}")
        def fake_run(cmd, **kw):
            if cmd[0] == "gcc" and "--version" in cmd:
                return _make_result(0, "gcc", "")
            if cmd[0] == "cl":
                raise FileNotFoundError("no cl")
            if cmd[0] == "gcc" and "-shared" in cmd:
                raise RuntimeError("boom")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._c_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "错误" in out


class TestCpp:
    """C++ 编译器分支。"""

    def test_missing_file(self, capsys):
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._cpp_compiler("Z:/nonexistent.cpp", "out.dll")
        out = capsys.readouterr().out
        assert "不存在" in out

    def test_no_compiler(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.cpp"
        f.write_text("int main(){return 0;}")
        def _raise(*a, **kw):
            raise FileNotFoundError("no compiler")
        monkeypatch.setattr("subprocess.run", _raise)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._cpp_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "未找到" in out

    def test_gpp_success(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.cpp"
        f.write_text("int main(){return 0;}")
        def fake_run(cmd, **kw):
            if cmd[0] == "g++" and "--version" in cmd:
                return _make_result(0, "g++ 1.0", "")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        cc._cpp_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out

    def test_cl_success(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.cpp"
        f.write_text("int main(){return 0;}")
        def fake_run(cmd, **kw):
            if cmd[0] == "g++":
                raise FileNotFoundError("no g++")
            if cmd[0] == "cl" and "--version" in cmd:
                return _make_result(0, "cl 19.0", "")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        cc._cpp_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out

    def test_cpp_failure(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.cpp"
        f.write_text("int main(){return 0;}")
        def fake_run(cmd, **kw):
            if cmd[0] == "g++" and "--version" in cmd:
                return _make_result(0, "g++", "")
            return _make_result(1, "", "err")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc._cpp_compiler(str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译失败" in out


class TestLang:
    """lang 子命令。"""

    def test_list(self, capsys, monkeypatch):
        # 所有编译器都不可用
        def _raise(*a, **kw):
            raise FileNotFoundError("none")
        monkeypatch.setattr("subprocess.run", _raise)
        cc = CompileCommands()
        cc.lang("nim")
        out = capsys.readouterr().out
        assert "支持的编译语言" in out
        assert "nim" in out
        assert "c" in out
        assert "cpp" in out

    def test_list_available(self, capsys, monkeypatch):
        def fake_run(cmd, **kw):
            if cmd[0] in ("nim", "gcc", "g++", "cl"):
                return _make_result(0, cmd[0] + " 1.0\nsecond\n", "")
            return _make_result(0, "", "")
        monkeypatch.setattr("subprocess.run", fake_run)
        cc = CompileCommands()
        cc.lang("nim")
        out = capsys.readouterr().out
        assert "✓ nim" in out
        assert "✓ gcc" in out


class TestRun:
    """run 子命令。"""

    def test_unknown_lang(self, capsys):
        cc = CompileCommands()
        with pytest.raises(SystemExit):
            cc.run("rust", "a.rs", "out.dll")
        out = capsys.readouterr().out
        assert "不支持的语言" in out

    def test_valid_lang(self, capsys, monkeypatch, tmp_path):
        f = tmp_path / "a.nim"
        f.write_text("x")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: _make_result(0, "", ""))
        cc = CompileCommands()
        cc.run("nim", str(f), "out.dll")
        out = capsys.readouterr().out
        assert "编译成功" in out


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.sys.compile_cmd import __all__
        assert "CompileCommands" in __all__
