"""复核修复回归测试。

覆盖 MCP-复核发现的 C1 / M1 / M2 / M3 / m1 / m4 修复。
"""
import os
import sys
import time
import tempfile
import subprocess

import pytest

from vools.bridge.md.parser import CodeBlock, parse_md
from vools.bridge.md.runner import _execute_block, resolve_imports


def _block(lang, content="", directives=None, index=0):
    return CodeBlock(index, lang, directives or {}, content)


def _ctx(tmp_path):
    return {"workdir": str(tmp_path), "build_dir": str(tmp_path)}


def _config():
    return {"env": {}, "timeout": 30}


# ── C1：bridge timeout 兜底 ──

class TestBridgeTimeout:
    def test_python_timeout(self, tmp_path):
        # python 走进程内 exec，thread 级软超时应返回 rc=124
        content = "import time; time.sleep(5)"
        block = _block("python", content, {"timeout": "1"}, index=0)
        start = time.time()
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 2)
        elapsed = time.time() - start
        assert rc == 124, f"expected timeout rc=124, got {rc}, stderr={stderr!r}"
        assert elapsed < 4, f"expected quick timeout, got {elapsed}s"
        assert "超时" in stderr

    def test_shell_timeout(self, tmp_path):
        # shell 走 subprocess，子进程硬 kill
        content = "sleep 5"
        block = _block("shell", content, {"timeout": "1"}, index=1)
        start = time.time()
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 2)
        elapsed = time.time() - start
        assert rc != 0, f"expected non-zero rc, got {rc}"
        assert elapsed < 4, f"expected quick timeout, got {elapsed}s"


# ── M1：shell 不再 shell=True ──

class TestShellInjection:
    def test_shell_no_shell_true(self, tmp_path):
        # 用 argv 数组，不 shell=True；内容里的 $(...) 不应被 shell 解释
        # 实际上内容会被作为 -c 脚本执行，$(...) 仍是 shell 语法
        # 这里只验证执行成功（不因注入报错）
        import shutil
        if sys.platform == "win32":
            # Windows 上 bash.exe 是 WSL stub，输出 UTF-16 无法 text 解码
            pytest.skip("shell blocks not well-supported on Windows (WSL bash stub)")
        if not (shutil.which("bash") or shutil.which("sh")):
            pytest.skip("bash/sh not installed")
        content = "echo 'hello world'"
        block = _block("shell", content, {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        assert "hello world" in stdout

    def test_shell_no_bash_installed(self, tmp_path, monkeypatch):
        # 如果 bash/sh 都找不到，应明确报错不硬跑
        monkeypatch.setattr("vools.bridge.md.runner._shutil_which", lambda cmd: None)
        block = _block("shell", "echo hi", {}, index=1)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1
        assert "shell" in stderr or "bash" in stderr or "sh" in stderr


# ── M2：MySQL 密码不再 argv ──

class TestMysqlPassword:
    def test_password_not_in_argv(self, tmp_path):
        # 打桩 subprocess.run，检查 argv 里没有 -p<password>
        import vools.bridge.md.runner as R

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env", {})
            captured["text"] = True
            class Proc:
                stdout = ""
                stderr = ""
                returncode = 0
            return Proc()

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(R, "_shutil_which", lambda cmd: "/usr/bin/mysql" if cmd == "mysql" else None)
        monkeypatch.setattr(R.subprocess, "run", fake_run)

        try:
            block = _block("sql", "SELECT 1", {"target": "mysql://user:secret@localhost:3306/db"}, index=0)
            # 注意：_execute_database_block 需要走 database kind
            # 但这里直接测 cmd 组装更直接 —— 通过 _execute_block 走完整路径
            with tempfile.TemporaryDirectory() as td:
                stdout, stderr, rc = _execute_block(block, _ctx(td), _config(), None, 10)
            assert rc == 0, stderr
            cmd_str = " ".join(captured["cmd"])
            assert "-psecret" not in cmd_str, f"password leaked in argv: {cmd_str}"
            assert captured["env"].get("MYSQL_PWD") == "secret", "MYSQL_PWD env not set"
        finally:
            monkeypatch.undo()


# ── m1：target 白名单含 mcp ──

class TestTargetWhitelist:
    def test_mcp_target_allowed(self):
        from vools.bridge.md.directives import validate_directives
        block = _block("mcp", "", {"target": "filesystem"}, index=0)
        errors = validate_directives(block.directives, block.language)
        assert "target" not in " ".join(errors), f"mcp target should be allowed: {errors}"


# ── m4：菱形导入不重复展开 ──

class TestDiamondImport:
    def test_diamond_import(self, tmp_path):
        # A imports B and C; B imports D; C imports D
        # D should only be resolved once
        F = "```"
        d_md = tmp_path / "d.md"
        d_md.write_text(f"{F}python\nprint('D')\n{F}\n", encoding="utf-8")

        b_md = tmp_path / "b.md"
        b_md.write_text(f"{F}python #!import d.md\nprint('B')\n{F}\n", encoding="utf-8")

        c_md = tmp_path / "c.md"
        c_md.write_text(f"{F}python #!import d.md\nprint('C')\n{F}\n", encoding="utf-8")

        a_md = tmp_path / "a.md"
        a_md.write_text(
            f"{F}python #!import b.md\nprint('A')\n{F}\n"
            f"{F}python #!import c.md\nprint('A2')\n{F}\n",
            encoding="utf-8",
        )

        parsed = parse_md(str(a_md))
        blocks = resolve_imports(parsed, str(tmp_path), str(tmp_path / ".build"), root_path=str(a_md))
        d_blocks = [b for b in blocks if "D" in b.content]
        assert len(d_blocks) == 1, f"D should be resolved once, got {len(d_blocks)}"

    def test_cyclic_import(self, tmp_path):
        # A imports B; B imports A — 循环应被截断不无限递归
        F = "```"
        b_md = tmp_path / "b.md"
        b_md.write_text(
            f"{F}python #!import a.md\nprint('B')\n{F}\n",
            encoding="utf-8",
        )

        a_md = tmp_path / "a.md"
        a_md.write_text(
            f"{F}python #!import b.md\nprint('A')\n{F}\n",
            encoding="utf-8",
        )

        parsed = parse_md(str(a_md))
        # 不应抛 RecursionError；visited 正确截断后，
        # 每个块都带 import（被 resolve_imports 剔除），可能返回空列表
        blocks = resolve_imports(parsed, str(tmp_path), str(tmp_path / ".build"), root_path=str(a_md))
        # 核心断言：不 RecursionError（pytest 会报 RecursionError 若失败）
        # visited 生效：所有块都已被剔除（或至少没重复展开）
        a_blocks = [b for b in blocks if b.content == "print('A')"]
        assert len(a_blocks) <= 1, f"A should appear at most once, got {len(a_blocks)}"


# ── 其他 m4：bridge 返回假绿检测 ──

class TestBridgeErrorDetection:
    def test_bridge_error_marker(self, tmp_path, monkeypatch):
        # 打桩 helper 返回错误字符串，应 rc=1
        import vools.bridge as _vb

        class FakeHelper:
            def is_available(self):
                return True

            def execute_code(self, code, func_name="__main__"):
                return "Error: compilation failed at line 1"

        monkeypatch.setattr(_vb, "get_helper", lambda lang: FakeHelper())

        block = _block("fake-lang", "code", {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 1, f"expected rc=1 on error marker, got {rc}"
        assert "compilation failed" in stderr

    def test_bridge_clean_success(self, tmp_path, monkeypatch):
        import vools.bridge as _vb

        class FakeHelper:
            def is_available(self):
                return True

            def execute_code(self, code, func_name="__main__"):
                return "hello world"

        monkeypatch.setattr(_vb, "get_helper", lambda lang: FakeHelper())

        block = _block("fake-lang", "code", {}, index=0)
        stdout, stderr, rc = _execute_block(block, _ctx(tmp_path), _config(), None, 10)
        assert rc == 0, stderr
        assert "hello world" in stdout