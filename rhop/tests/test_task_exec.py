"""执行通道测试：白名单、CLI 执行、处理器注册与派发。"""

import os
import sys

import pytest

from vools.rhop.task.errors import ExecDenied
from vools.rhop.task.exec import (
    LANGUAGE_DEFAULT_CMD,
    ExecPolicy,
    cli_execute,
    detect_language,
    find_executable,
    get_handler,
    register_handler,
    resolve_channel,
    run_payload,
)

PY = sys.executable


def _py(code):
    return '"%s" -c "%s"' % (PY.replace("\\", "/"), code)


class TestPolicy:
    def test_default_allows_actions_and_handlers_only(self):
        policy = ExecPolicy()
        policy.check("action", "jump.probe")          # 不抛
        policy.check("handler", "anything")           # 不抛
        with pytest.raises(ExecDenied):
            policy.check("cli", "python")

    def test_denied_message_is_actionable(self):
        policy = ExecPolicy(allow=["action:*"])
        with pytest.raises(ExecDenied) as exc:
            policy.check("cli", "bash")
        message = str(exc.value)
        assert "cli:bash" in message
        assert "exec.allow" in message
        assert "allow_any" in message

    @pytest.mark.parametrize("pattern,name", [
        ("cli:python", "python"), ("cli:python", "python.exe"),
        ("cli:python.exe", "python.exe"), ("cli:*", "anything"),
        ("*", "anything"), ("cli:git", "git"),
    ])
    def test_allowed_patterns(self, pattern, name):
        ExecPolicy(allow=[pattern]).check("cli", name)

    @pytest.mark.parametrize("pattern,name", [
        ("cli:python", "bash"), ("action:jump.*", "shell.exec"),
    ])
    def test_denied_patterns(self, pattern, name):
        with pytest.raises(ExecDenied):
            ExecPolicy(allow=[pattern]).check(
                "action" if name.startswith("shell") else "cli", name)

    def test_allow_any_bypasses_everything(self):
        ExecPolicy(allow=[], allow_any=True).check("cli", "rm")

    def test_shell_gate(self):
        assert ExecPolicy(allow_any=True).allow_shell("cli") is True
        assert ExecPolicy(allow=["cli:shell"]).allow_shell("cli") is True
        assert ExecPolicy(allow=["cli:python"]).allow_shell("cli") is False
        assert ExecPolicy(shell=True).allow_shell("cli") is True

    def test_from_cfg(self):
        policy = ExecPolicy.from_cfg({"allow": ["cli:python"], "allow_any": True,
                                      "workdir": "/tmp", "timeout_sec": 5,
                                      "env": {"A": "1"}, "shell": True})
        assert policy.allow == ["cli:python"]
        assert policy.allow_any is True
        assert policy.workdir == "/tmp"
        assert policy.timeout_sec == 5.0
        assert policy.env == {"A": "1"}
        assert policy.shell is True
        assert "allow" in policy.describe()


class TestLanguageMapping:
    @pytest.mark.parametrize("given,expected", [
        ("PY", "python"), ("python", "python"), ("python3", "python3"),
        ("SCALA", "scala"), ("sc", "scala"), ("SQL", "sql"),
        ("SHELL", "shell"), ("bash", "bash"), ("NODE", "node"),
        ("golang", "go"), ("unknown-lang", None), ("", None),
    ])
    def test_detect_language(self, given, expected):
        assert detect_language(given) == expected

    def test_python_is_always_available(self):
        assert find_executable(["python"]) is not None

    def test_missing_interpreter_reported(self):
        assert find_executable(["definitely-not-a-real-binary-xyz"]) is None

    def test_mapping_is_not_enumerated(self):
        """无语言枚举限制：映射表可自由扩展，task_type 只是提示。"""
        assert len(LANGUAGE_DEFAULT_CMD) > 15


class TestCliExecute:
    def test_python_command(self):
        result = cli_execute({"cli": {"cmd": _py("print(1+1)")}})
        assert result["ok"] is True
        assert result["stdout"].strip() == "2"
        assert result["exit_code"] == 0
        assert result["duration_ms"] >= 0

    def test_lang_inference_from_task_type(self):
        result = cli_execute({"task_type": "PY", "cli": {"script": "print('inline')"}})
        assert result["ok"] is True
        assert result["stdout"].strip() == "inline"

    def test_unknown_language_error(self):
        result = cli_execute({"task_type": "brainfuck"})
        assert result["ok"] is False
        assert "无法推断命令" in result["error"]

    def test_no_cmd_no_lang_error(self):
        result = cli_execute({"cli": {"args": ["--x"]}})
        assert result["ok"] is False
        assert "无法推断命令" in result["error"]

    def test_missing_interpreter_error(self):
        result = cli_execute({"cli": {"cmd": "definitely-not-a-real-binary-xyz --x"}})
        assert result["ok"] is False
        assert "可执行文件不存在" in result["error"]

    def test_nonzero_exit_records_failure(self):
        result = cli_execute({"cli": {"cmd": _py("import sys; sys.exit(3)")}})
        assert result["ok"] is False
        assert result["exit_code"] == 3
        assert "退出码非 0" in result["error"]

    def test_check_true_converts_to_error(self):
        result = cli_execute({"cli": {"cmd": _py("import sys; sys.exit(4)"), "check": True}})
        assert result["ok"] is False
        assert "check=True" in result["error"]

    def test_timeout(self):
        result = cli_execute({"cli": {"cmd": _py("import time; time.sleep(3)"),
                                      "timeout_sec": 0.4}})
        assert result["ok"] is False
        assert "超时" in result["error"]

    def test_workdir_missing(self):
        result = cli_execute({"cli": {"cmd": _py("print(1)"), "workdir": "Z:/definitely/missing"}})
        assert result["ok"] is False
        assert "workdir 不存在" in result["error"]

    def test_env_and_stdin(self, tmp_path):
        script = os.path.join(str(tmp_path), "read_stdin.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import os, sys\n"
                     "print(os.environ.get('RHOP_UNIT', ''), sys.stdin.read().strip())\n")
        result = cli_execute({"cli": {"cmd": '"%s" "%s"' % (PY.replace("\\", "/"), script),
                                      "env": {"RHOP_UNIT": "env-ok"}, "stdin": "stdin-ok"}})
        assert result["ok"] is True
        assert "env-ok" in result["stdout"] and "stdin-ok" in result["stdout"]

    def test_workdir_is_used(self, tmp_path):
        result = cli_execute({"cli": {"cmd": _py("import os; print(os.getcwd())"),
                                      "workdir": str(tmp_path)}})
        assert result["ok"] is True
        assert os.path.normcase(str(tmp_path)) in os.path.normcase(result["stdout"])

    def test_stdin_from_value(self, tmp_path):
        script = os.path.join(str(tmp_path), "echo.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import sys\nprint(sys.stdin.read().strip().upper())\n")
        result = cli_execute({"value": "abc",
                              "cli": {"cmd": '"%s" "%s"' % (PY.replace("\\", "/"), script)}})
        assert result["stdout"].strip() == "ABC"


class TestHandlers:
    def test_register_and_dispatch_without_decorator(self):
        register_handler("unit-noop", lambda payload: {"v": payload.get("value")})
        try:
            assert get_handler("unit-noop") is not None
            out = run_payload({"handler": "unit-noop", "value": 7}, ExecPolicy())
            assert out["ok"] is True
            assert out["result"] == {"v": 7}
        finally:
            from vools.rhop.task.exec import HANDLERS
            HANDLERS.pop("unit-noop", None)

    def test_decorator_and_task_type_dispatch(self):
        @register_handler("unit-double")
        def _double(payload):
            return payload.get("value", 0) * 2

        try:
            out = run_payload({"task_type": "unit-double", "value": 21}, ExecPolicy())
            assert out["ok"] is True
            assert out["result"] == 42
        finally:
            from vools.rhop.task.exec import HANDLERS
            HANDLERS.pop("unit-double", None)

    def test_handler_exception_is_reported_not_raised(self):
        @register_handler("unit-boom")
        def _boom(payload):
            raise RuntimeError("handler blew up")

        try:
            out = run_payload({"handler": "unit-boom"}, ExecPolicy())
            assert out["ok"] is False
            assert "handler blew up" in out["error"]
        finally:
            from vools.rhop.task.exec import HANDLERS
            HANDLERS.pop("unit-boom", None)

    def test_empty_handler_name_rejected(self):
        with pytest.raises(ValueError):
            register_handler("", lambda p: None)


class TestCliAudit:
    """BUG-281 收口：cli 通道的白名单命中可读回 + 执行前必须留审计行。"""

    def test_matched_pattern_reads_back(self):
        p = ExecPolicy(allow=["action:*", "cli:python"])
        assert p.matched_pattern("cli", "python") == "cli:python"
        assert p.matched_pattern("cli", "python.exe") == "cli:python"     # 后缀归一
        assert p.matched_pattern("cli", "bash") is None
        assert p.matched_pattern("action", "jump.push") == "action:*"
        assert ExecPolicy(allow=[]).matched_pattern("cli", "x") is None
        assert ExecPolicy(allow_any=True).matched_pattern("cli", "rm") == "allow_any"
        assert ExecPolicy().matched_pattern("cli", "python") is None       # 默认白名单不放行 cli

    def test_cli_execution_writes_audit_line_before_running(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="vools.rhop.task.exec"):
            out = run_payload(
                {"task_name": "job-42",
                 "cli": {"cmd": '"%s" -c "print(1)"' % PY.replace("\\", "/")}},
                ExecPolicy(allow=["cli:python"]))
        assert out["ok"] is True
        hits = [r.getMessage() for r in caplog.records if "cli 审计" in r.getMessage()]
        assert hits, "cli 执行必须留审计行（BUG-281）"
        msg = hits[-1]
        assert "task=job-42" in msg
        assert "allow_hit=cli:python" in msg
        assert "allow_any=False" in msg
        assert "cmd=" in msg

    def test_audit_line_present_even_when_execution_fails(self, caplog):
        """超时/非零退出也必须有审计行 —— 所以审计必须写在执行之前。"""
        import logging
        with caplog.at_level(logging.INFO, logger="vools.rhop.task.exec"):
            out = run_payload(
                {"task_name": "job-timeout",
                 "cli": {"cmd": '"%s" -c "import time; time.sleep(5)"' % PY.replace("\\", "/"),
                         "timeout_sec": 0.3}},
                ExecPolicy(allow=["cli:python"]))
        assert out["ok"] is False
        assert any("job-timeout" in r.getMessage() for r in caplog.records)


class TestChannels:
    def test_resolve_channel_action(self):
        assert resolve_channel({"action": "jump.push"})["channel"] == "action"

    def test_resolve_channel_cli_by_lang(self):
        assert resolve_channel({"cli": {"lang": "python"}})["name"] == "python"

    def test_resolve_channel_cli_by_cmd(self):
        info = resolve_channel({"cli": {"cmd": "/usr/bin/env python -c x"}})
        assert info["channel"] == "cli"
        assert info["name"] == "python" or info["name"] == "env"

    def test_resolve_unknown(self):
        info = resolve_channel({"foo": "bar"})
        assert info["channel"] is None
        assert "无法识别指令" in info["reason"]

    def test_run_payload_action_channel(self):
        out = run_payload({"action": "jump.probe", "payload": {}}, ExecPolicy(),
                          action_cfg={"sftp": {}})
        assert out["channel"] == "action"
        assert out["name"] == "jump.probe"

    def test_run_payload_cli_denied_by_default(self):
        with pytest.raises(ExecDenied):
            run_payload({"cli": {"cmd": _py("print(1)")}}, ExecPolicy())

    def test_run_payload_cli_allowed_with_whitelist(self):
        out = run_payload({"cli": {"cmd": _py("print(9)")}},
                          ExecPolicy(allow=["cli:python"]))
        assert out["ok"] is True
        assert out["result"]["stdout"].strip() == "9"

    def test_run_payload_shell_blocked(self):
        with pytest.raises(ExecDenied):
            run_payload({"cli": {"cmd": "echo hi", "shell": True}},
                        ExecPolicy(allow=["cli:echo"]))

    def test_run_payload_unknown_returns_error(self):
        out = run_payload({"nope": 1}, ExecPolicy())
        assert out["ok"] is False
        assert "无法识别指令" in out["error"]


class TestBugRegressions:
    """BUG-303 回归：_sftp_cfg_of 不能在 media 非 dict 时抛 AttributeError。"""

    def test_sftp_cfg_of_media_is_string(self):
        """cfg['media'] 是字符串时不应抛 AttributeError。"""
        from vools.rhop.actions.jump import _sftp_cfg_of
        cfg = {"sftp": {"host": "h1"}, "media": "not-a-dict"}
        result = _sftp_cfg_of(cfg)
        assert result["host"] == "h1"

    def test_sftp_cfg_of_media_is_none(self):
        """cfg['media'] 是 None 时不应抛 AttributeError。"""
        from vools.rhop.actions.jump import _sftp_cfg_of
        cfg = {"sftp": {"host": "h2"}, "media": None}
        result = _sftp_cfg_of(cfg)
        assert result["host"] == "h2"

    def test_sftp_cfg_of_no_sftp_key(self):
        """cfg 没有 sftp 键且 media 是 dict 时走 media.sftp。"""
        from vools.rhop.actions.jump import _sftp_cfg_of
        cfg = {"media": {"sftp": {"host": "h3"}}}
        result = _sftp_cfg_of(cfg)
        assert result["host"] == "h3"

    def test_sftp_cfg_of_fallback_to_cfg(self):
        """cfg 没有 sftp/media 键时回退到整个 cfg。"""
        from vools.rhop.actions.jump import _sftp_cfg_of
        cfg = {"host": "h4", "port": 2222}
        result = _sftp_cfg_of(cfg)
        assert result["host"] == "h4"