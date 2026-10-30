"""adapter 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- 参数替换错误 → 命令注入或参数丢失
- _executable_of 解析错误 → 找不到可执行文件
- _has_shell_metachars 误判 → Windows 路径被当 shell 命令
- _quote_for_shell 错误 → 命令注入面
- AdapterSpec.from_dict 解析错误 → 适配器配置丢失
"""
import os
import shlex

import pytest


class TestExceptions:
    def test_adapter_spec_error(self):
        """退步了会怎样：AdapterSpecError 应携带 issues 和 install_hint。"""
        from vools.actus.adapter import AdapterSpecError
        err = AdapterSpecError("act.a", ["缺 command"], "安装指南")
        assert "act.a" in str(err)
        assert "缺 command" in str(err)
        assert "安装指南" in str(err)
        assert err.adapter_id == "act.a"
        assert err.issues == ["缺 command"]
        assert err.install_hint == "安装指南"

    def test_adapter_spec_error_no_hint(self):
        """退步了会怎样：无 install_hint 不应崩溃。"""
        from vools.actus.adapter import AdapterSpecError
        err = AdapterSpecError("act.a", ["缺 command"])
        assert "act.a" in str(err)
        assert err.install_hint == ""

    def test_adapter_unavailable_error(self):
        """退步了会怎样：AdapterUnavailableError 应携带 reason。"""
        from vools.actus.adapter import AdapterUnavailableError
        err = AdapterUnavailableError("act.a", "命令没装", "安装指南")
        assert "act.a" in str(err)
        assert "命令没装" in str(err)
        assert "安装指南" in str(err)
        assert err.adapter_id == "act.a"
        assert err.reason == "命令没装"


class TestAdapterSpec:
    def test_from_dict_minimal(self):
        """退步了会怎样：最小 dict 应正确解析。"""
        from vools.actus.adapter import AdapterSpec, AdapterType
        spec = AdapterSpec.from_dict({"id": "act.a"})
        assert spec.id == "act.a"
        assert spec.type == AdapterType.CLI
        assert spec.command == ""

    def test_from_dict_full(self):
        """退步了会怎样：完整 dict 应正确解析。"""
        from vools.actus.adapter import AdapterSpec, AdapterType
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {
                "type": "cli",
                "command": "python",
                "args": ["--version"],
                "timeout": 10,
                "preflight": True,
            },
            "output": {"type": "json", "path": "/tmp/out"},
        })
        assert spec.type == AdapterType.CLI
        assert spec.command == "python"
        assert spec.args == ["--version"]
        assert spec.timeout == 10
        assert spec.preflight is True
        assert spec.output_type == "json"
        assert spec.output_path == "/tmp/out"


class TestAdapterResult:
    def test_to_dict(self):
        """退步了会怎样：to_dict 应返回所有字段。"""
        from vools.actus.adapter import AdapterResult
        r = AdapterResult(success=True, stdout="ok", returncode=0)
        d = r.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "ok"
        assert d["returncode"] == 0


class TestSubstituteParams:
    def test_substitute_basic(self):
        """退步了会怎样：应替换 ${param} 占位符。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${name}", {"name": "world"})
        assert result == "echo world"

    def test_substitute_missing(self):
        """退步了会怎样：缺失参数应替换为空串。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${name}", {})
        assert result == "echo "

    def test_substitute_quote(self):
        """退步了会怎样：quote=True 应做 shell 引号。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${name}", {"name": "hello world"}, quote=True)
        # quote=True 时值被 shell 引号包裹（含空格的值应作为整体）
        assert "hello world" in result
        # 值应被引号包裹（不是裸空格）
        assert '"' in result or "'" in result

    def test_substitute_no_quote(self):
        """退步了会怎样：quote=False 时不应引号。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${name}", {"name": "hello world"})
        assert result == "echo hello world"


class TestSubstituteInArgs:
    def test_substitute_args(self):
        """退步了会怎样：应在 args 列表中替换占位符。"""
        from vools.actus.adapter import _substitute_in_args
        args = ["echo", "${name}"]
        result = _substitute_in_args(args, {"name": "world"})
        assert result == ["echo", "world"]


class TestExecutableOf:
    def test_executable_simple(self):
        """退步了会怎样：简单命令应提取可执行文件。"""
        from vools.actus.adapter import _executable_of
        assert _executable_of("python --version") == "python"

    def test_executable_empty(self):
        """退步了会怎样：空命令应返回空串。"""
        from vools.actus.adapter import _executable_of
        assert _executable_of("") == ""

    def test_executable_none(self):
        """退步了会怎样：None 应返回空串。"""
        from vools.actus.adapter import _executable_of
        assert _executable_of(None) == ""


class TestHasShellMetachars:
    def test_metachars_present(self):
        """退步了会怎样：应识别 shell 元字符。"""
        from vools.actus.adapter import _has_shell_metachars
        assert _has_shell_metachars("ls | grep foo") is True
        assert _has_shell_metachars("echo $HOME") is True

    def test_no_metachars(self):
        """退步了会怎样：无元字符应返回 False。"""
        from vools.actus.adapter import _has_shell_metachars
        assert _has_shell_metachars("python --version") is False
        assert _has_shell_metachars("") is False

    def test_backslash_not_metachar(self):
        """退步了会怎样：反斜杠不应被当作元字符（Windows 路径）。"""
        from vools.actus.adapter import _has_shell_metachars
        assert _has_shell_metachars("C:\\Program Files\\python.exe") is False


class TestQuoteForShell:
    def test_quote_simple(self):
        """退步了会怎样：应给值加引号。"""
        from vools.actus.adapter import _quote_for_shell
        result = _quote_for_shell("hello world")
        assert "hello world" in result
        # 值被引号包裹
        assert result != "hello world"  # 不应原样返回

    def test_quote_empty(self):
        """退步了会怎样：空串也应被引号包裹。"""
        from vools.actus.adapter import _quote_for_shell
        result = _quote_for_shell("")
        assert result != ""

    def test_quote_with_metachars(self):
        """退步了会怎样：含元字符的值应被引号包裹。"""
        from vools.actus.adapter import _quote_for_shell
        result = _quote_for_shell("a; rm -rf /")
        # 值被引号包裹，元字符不再有接单能力
        assert result != "a; rm -rf /"

    def test_executable_of_path(self):
        """退步了会怎样：路径型命令应按整串算。"""
        from vools.actus.adapter import _executable_of
        import os
        # 用 sys.executable（含空格的路径）
        import sys
        exe = _executable_of(sys.executable)
        assert exe == sys.executable

    def test_executable_of_with_param(self):
        """退步了会怎样：带 ${param} 的命令应提取 param 前的路径。"""
        from vools.actus.adapter import _executable_of
        import sys
        exe = _executable_of(sys.executable + " ${arg}")
        assert exe == sys.executable

    def test_substitute_multiple_params(self):
        """退步了会怎样：多个占位符应全部替换。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${a} ${b}", {"a": "1", "b": "2"})
        assert result == "echo 1 2"

    def test_substitute_partial_missing(self):
        """退步了会怎样：部分参数缺失应替换为空串。"""
        from vools.actus.adapter import _substitute_params
        result = _substitute_params("echo ${a} ${b}", {"a": "1"})
        assert result == "echo 1 "


class TestCLIAdapter:
    def test_check_available_no_check(self):
        """退步了会怎样：无 check 时应按 command 可执行文件判断。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"command": "python"}})
        ca = CLIAdapter(spec)
        ok, msg = ca.check_available()
        assert ok is True

    def test_check_available_bad_command(self):
        """退步了会怎样：不可用的命令应返回 False。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"command": "nonexistent_xyz"}})
        ca = CLIAdapter(spec)
        ok, msg = ca.check_available()
        assert ok is False
        assert "nonexistent_xyz" in msg

    def test_install_hint_with_install(self):
        """退步了会怎样：有 install 字段应返回 install 内容。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"command": "foo", "install": "pip install foo"}})
        ca = CLIAdapter(spec)
        assert ca.install_hint() == "pip install foo"

    def test_install_hint_no_install(self):
        """退步了会怎样：无 install 应返回通用提示。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"command": "foo"}})
        ca = CLIAdapter(spec)
        assert "foo" in ca.install_hint()

    def test_run_simple(self):
        """退步了会怎样：应能执行简单命令。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "print('hello')"]},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True
        assert "hello" in result.stdout

    def test_run_no_command(self):
        """退步了会怎样：无 command 应返回失败。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a"})
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is False
        assert "未指定" in result.stderr

    def test_run_with_params(self):
        """退步了会怎样：应能替换 ${param} 占位符。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "print('${msg}')"]},
        })
        ca = CLIAdapter(spec)
        result = ca.run(params={"msg": "hello world"})
        assert result.success is True
        assert "hello world" in result.stdout

    def test_run_json_output(self):
        """退步了会怎样：json 输出应被解析。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "import json; print(json.dumps({\"ok\": True}))"]},
            "output": {"type": "json"},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True
        assert result.data == {"ok": True}

    def test_run_shell_metachars(self):
        """退步了会怎样：shell 元字符命令应走 shell 路径。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "echo hello | grep hello"},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True

    def test_run_command_fails(self):
        """退步了会怎样：命令失败应返回失败结果。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "import sys; sys.exit(1)"]},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is False

    def test_run_with_check(self):
        """退步了会怎样：有 check 字段时应走 check 路径。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "check": "python --version"},
        })
        ca = CLIAdapter(spec)
        ok, msg = ca.check_available()
        assert ok is True

    def test_run_with_output_path(self, tmp_path):
        """退步了会怎样：output_path 为文件时应读取文件内容。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        out_file = tmp_path / "out.txt"
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "open('OUTFILE', 'w').write('file output')"]},
            "output": {"type": "file", "path": str(out_file)},
        })
        # 先执行生成文件
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True


class TestQuickerAdapter:
    def test_check_available_no_quicker(self):
        """退步了会怎样：无 Quicker 应返回 False。"""
        from vools.actus.adapter import QuickerAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "quicker"}})
        qa = QuickerAdapter(spec)
        ok, msg = qa.check_available()
        assert ok is False
        assert "Quicker" in msg

    def test_install_hint(self):
        """退步了会怎样：应返回 Quicker 安装提示。"""
        from vools.actus.adapter import QuickerAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "quicker"}})
        qa = QuickerAdapter(spec)
        assert "Quicker" in qa.install_hint()

    def test_run_no_action(self):
        """退步了会怎样：无 action 应返回失败。"""
        from vools.actus.adapter import QuickerAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "quicker"}})
        qa = QuickerAdapter(spec)
        result = qa.run()
        assert result.success is False
        assert "未指定" in result.stderr


class TestMCPAdapter:
    def test_check_available_no_server(self):
        """退步了会怎样：无 mcp_server 应返回 False。"""
        from vools.actus.adapter import MCPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "mcp"}})
        ma = MCPAdapter(spec)
        ok, msg = ma.check_available()
        assert ok is False
        assert "MCP" in msg

    def test_install_hint(self):
        """退步了会怎样：应返回 MCP 配置提示。"""
        from vools.actus.adapter import MCPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "mcp"}})
        ma = MCPAdapter(spec)
        assert "mcp_servers.json" in ma.install_hint()

    def test_run_no_tool(self):
        """退步了会怎样：无 mcp_tool 应返回失败。"""
        from vools.actus.adapter import MCPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "mcp"}})
        ma = MCPAdapter(spec)
        result = ma.run()
        assert result.success is False
        assert "MCP" in result.stderr


class TestHTTPAdapter:
    def test_check_available_no_url(self):
        """退步了会怎样：无 url 应返回 False。"""
        from vools.actus.adapter import HTTPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "http"}})
        ha = HTTPAdapter(spec)
        ok, msg = ha.check_available()
        assert ok is False
        assert "URL" in msg

    def test_install_hint(self):
        """退步了会怎样：应返回 HTTP 无需安装提示。"""
        from vools.actus.adapter import HTTPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "http"}})
        ha = HTTPAdapter(spec)
        assert "无需安装" in ha.install_hint()

    def test_run_no_url(self):
        """退步了会怎样：无 url 应返回失败。"""
        from vools.actus.adapter import HTTPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({"id": "act.a", "adapter": {"type": "http"}})
        ha = HTTPAdapter(spec)
        result = ha.run()
        assert result.success is False
        assert "URL" in result.stderr

    def test_run_success(self, monkeypatch):
        """退步了会怎样：HTTP 2xx 应返回成功。"""
        from vools.actus.adapter import HTTPAdapter, AdapterSpec

        class MockResp:
            status = 200
            def read(self):
                return b'{"ok": true}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: MockResp())
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "http", "url": "https://example.com/api"},
        })
        ha = HTTPAdapter(spec)
        result = ha.run()
        assert result.success is True
        assert result.returncode == 200
        assert result.data == {"ok": True}

    def test_run_http_error(self, monkeypatch):
        """退步了会怎样：HTTP 错误码应返回失败。"""
        import urllib.error
        from vools.actus.adapter import HTTPAdapter, AdapterSpec

        def mock_urlopen(*a, **kw):
            raise urllib.error.HTTPError("https://x", 404, "Not Found", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "http", "url": "https://example.com/api"},
        })
        ha = HTTPAdapter(spec)
        result = ha.run()
        assert result.success is False
        assert result.returncode == 404


class TestCLICheckCommand:
    def test_check_command_shell_metachars(self):
        """退步了会怎样：shell 元字符的 check 应走 shell。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "cli", "command": "python", "check": "python | grep x"},
        })
        ca = CLIAdapter(spec)
        cmd, use_shell = ca._check_command()
        assert use_shell is True

    def test_check_command_same_as_exe(self):
        """退步了会怎样：check == command 应走 argv。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "cli", "command": "python", "check": "python"},
        })
        ca = CLIAdapter(spec)
        cmd, use_shell = ca._check_command()
        assert use_shell is False
        assert cmd == ["python"]

    def test_check_command_exe_with_args(self):
        """退步了会怎样：check = exe + args 应切出 argv。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "cli", "command": "python", "check": "python --version"},
        })
        ca = CLIAdapter(spec)
        cmd, use_shell = ca._check_command()
        assert use_shell is False
        assert cmd == ["python", "--version"]

    def test_check_command_malformed_quote(self):
        """退步了会怎样：引号不闭合应走 shell。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "cli", "command": "python", "check": "\"unclosed"},
        })
        ca = CLIAdapter(spec)
        cmd, use_shell = ca._check_command()
        assert use_shell is True


class TestQuickerRun:
    def test_quicker_run_with_action(self, monkeypatch):
        """退步了会怎样：Quicker run 应构建正确命令。"""
        from vools.actus.adapter import QuickerAdapter, AdapterSpec

        class MockResult:
            returncode = 0
            stdout = '{"ok": true}'
            stderr = ""

        captured = {}
        def mock_run_cmd_safe(cmd, **kw):
            captured["cmd"] = cmd
            return MockResult()

        monkeypatch.setattr("vools.actus.adapter.run_cmd_safe", mock_run_cmd_safe)
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "quicker", "action": "my_action"},
        })
        qa = QuickerAdapter(spec)
        result = qa.run(params={"x": 1})
        assert result.success is True
        assert captured["cmd"][0] == "QuickerStarter.exe"
        assert captured["cmd"][1] == "runaction"

    def test_quicker_run_exception(self, monkeypatch):
        """退步了会怎样：Quicker run 抛异常应返回失败。"""
        from vools.actus.adapter import QuickerAdapter, AdapterSpec

        def mock_run_cmd_safe(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr("vools.actus.adapter.run_cmd_safe", mock_run_cmd_safe)
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "quicker", "action": "my_action"},
        })
        qa = QuickerAdapter(spec)
        result = qa.run()
        assert result.success is False


class TestRunAdapter:
    def test_run_adapter_not_found(self):
        """退步了会怎样：run_adapter 找不到适配器应返回失败。"""
        from vools.actus.adapter import run_adapter
        result = run_adapter("adapter.cli.nonexistent")
        assert result.success is False
        assert "不存在" in result.stderr

    def test_run_adapter_invalid_spec(self):
        """退步了会怎样：run_adapter 配置错应返回失败。"""
        from vools.actus.adapter import run_adapter
        # 创建一个无效 spec 的适配器文件
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.environ["ACTUS_REPO_ROOT"] = d
            # 这个适配器缺 command，会触发 AdapterSpecError
            spec_path = os.path.join(d, "actions", "adapters")
            os.makedirs(spec_path, exist_ok=True)
            with open(os.path.join(spec_path, "bad.actus.md"), "w", encoding="utf-8") as f:
                f.write("```json #!cfg\n{\"id\": \"adapter.cli.bad\", \"adapter\": {\"type\": \"cli\"}}\n```\n")
            result = run_adapter("adapter.cli.bad")
            assert result.success is False


class TestCLIRunOutput:
    def test_run_output_file_success(self, tmp_path, monkeypatch):
        """退步了会怎样：output_path 文件存在时应读取内容。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec

        class MockResult:
            returncode = 0
            stdout = "ignored"
            stderr = ""

        monkeypatch.setattr("vools.actus.adapter.run_cmd_safe", lambda *a, **kw: MockResult())

        out_file = tmp_path / "out.txt"
        out_file.write_text("file content", encoding="utf-8")

        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "pass"]},
            "output": {"type": "file", "path": str(out_file)},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True
        assert "file content" in result.stdout
        assert result.artifact_path == str(out_file)

    def test_run_output_file_missing(self, tmp_path, monkeypatch):
        """退步了会怎样：output_path 文件不存在应返回 stdout。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec

        class MockResult:
            returncode = 0
            stdout = "stdout content"
            stderr = ""

        monkeypatch.setattr("vools.actus.adapter.run_cmd_safe", lambda *a, **kw: MockResult())

        out_file = tmp_path / "missing.txt"

        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "pass"]},
            "output": {"type": "file", "path": str(out_file)},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is True
        assert "stdout content" in result.stdout

    def test_run_run_exception(self, monkeypatch):
        """退步了会怎样：run_cmd_safe 抛异常应返回失败。"""
        from vools.actus.adapter import CLIAdapter, AdapterSpec

        def mock_run_cmd_safe(*a, **kw):
            raise RuntimeError("spawn failed")

        monkeypatch.setattr("vools.actus.adapter.run_cmd_safe", mock_run_cmd_safe)

        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"command": "python", "args": ["-c", "pass"]},
        })
        ca = CLIAdapter(spec)
        result = ca.run()
        assert result.success is False
        assert "spawn failed" in result.stderr


class TestMCPAdapterConfig:
    def test_mcp_check_available_with_config(self, tmp_path, monkeypatch):
        """退步了会怎样：MCP 服务器在配置中应返回 True。"""
        from vools.actus.adapter import MCPAdapter, AdapterSpec
        import json
        mcp_config = tmp_path / ".actus" / "mcp_servers.json"
        mcp_config.parent.mkdir(parents=True, exist_ok=True)
        mcp_config.write_text(json.dumps({"myserver": {}}), encoding="utf-8")
        # Path.home() 在 Windows 用 USERPROFILE
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "mcp", "mcp_server": "myserver"},
        })
        ma = MCPAdapter(spec)
        ok, msg = ma.check_available()
        assert ok is True

    def test_mcp_run_with_tool(self, monkeypatch):
        """退步了会怎样：MCP run 带 tool 应返回框架结果。"""
        from vools.actus.adapter import MCPAdapter, AdapterSpec
        spec = AdapterSpec.from_dict({
            "id": "act.a",
            "adapter": {"type": "mcp", "mcp_server": "srv", "mcp_tool": "tool"},
        })
        ma = MCPAdapter(spec)
        result = ma.run()
        assert result.success is False
        assert "MCP" in result.stderr

