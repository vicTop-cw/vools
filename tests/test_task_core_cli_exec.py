# -*- coding: utf-8 -*-
"""测试 vools.task.core.cli_exec — cli_execute / detect_language / find_executable。"""

import sys
import pytest

from vools.task.core.cli_exec import (
    cli_execute, detect_language, find_executable,
    LANGUAGE_DEFAULT_CMD, LANGUAGE_EXTENSIONS,
)

__all__ = ["TestDetectLanguage", "TestFindExecutable", "TestCliExecuteSuccess",
           "TestCliExecuteFail", "TestJsonDumps", "TestImport"]


class TestDetectLanguage:
    """detect_language 测试。"""

    def test_empty(self):
        assert detect_language(None) is None
        assert detect_language("") is None

    def test_normalize(self):
        assert detect_language("Python") == "python"
        assert detect_language("  PyThOn  ") == "python"
        assert detect_language("Scala") == "scala"

    def test_unknown(self):
        assert detect_language("brainfuck") == "brainfuck"  # 不筛，只归一化


class TestFindExecutable:
    """find_executable 测试。"""

    def test_empty(self):
        assert find_executable([]) is None

    def test_found(self):
        # 系统一定有 python
        path = find_executable(["python"])
        assert path is not None

    def test_not_found(self):
        assert find_executable(["definitely_not_a_real_cmd_xyz"]) is None


class TestCliExecuteSuccess:
    """cli_execute 成功路径测试。"""

    def test_cmd_str_simple(self):
        payload = {"cli": {"cmd": "python -c \"print('hello')\""}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "hello" in r["stdout"]
        assert r["exit_code"] == 0
        assert r["error"] is None
        assert r["duration_ms"] >= 0
        assert r["cmd"] is not None

    def test_cmd_with_check_nonzero(self):
        payload = {"cli": {"cmd": "python -c \"import sys; sys.exit(3)\"", "check": True}}
        r = cli_execute(payload)
        assert r["ok"] is False
        assert r["exit_code"] == 3

    def test_cmd_with_check_zero(self):
        payload = {"cli": {"cmd": "python -c \"print('x')\"", "check": True}}
        r = cli_execute(payload)
        assert r["ok"] is True

    def test_lang_python(self):
        payload = {"cli": {"lang": "python", "script": "print('from_script')"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "from_script" in r["stdout"]

    def test_lang_py_alias(self):
        payload = {"cli": {"lang": "py", "script": "print('alias')"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "alias" in r["stdout"]

    def test_task_type_fallback(self):
        payload = {"task_type": "python", "cli": {"script": "print('from_task_type')"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "from_task_type" in r["stdout"]

    def test_args(self):
        payload = {"cli": {"cmd": "python -c \"import sys; print(sys.argv[1:])\"",
                           "args": ["--flag"]}}
        r = cli_execute(payload)
        assert r["ok"] is True

    def test_stdin_from_value(self):
        payload = {"value": "line1\nline2",
                   "cli": {"cmd": "python -c \"import sys; data=sys.stdin.read(); print(len(data.splitlines()))\""}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "2" in r["stdout"]

    def test_env_override(self):
        payload = {"cli": {"cmd": "python -c \"import os; print(os.environ.get('MY_VAR',''))\"",
                           "env": {"MY_VAR": "hello"}}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "hello" in r["stdout"]

    def test_no_capture(self):
        payload = {"cli": {"cmd": "python -c \"print('x')\"", "capture": False}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert r["stdout"] == ""

    def test_timeout_param_override(self):
        payload = {"cli": {"cmd": "python -c \"print('x')\"", "timeout_sec": 5}}
        r = cli_execute(payload, timeout_sec=10)
        assert r["ok"] is True

    def test_workdir(self):
        payload = {"cli": {"cmd": "python -c \"import os; print(os.getcwd())\"",
                           "workdir": "."}}
        r = cli_execute(payload)
        assert r["ok"] is True

    def test_script_path(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("print('from_path')")
            payload = {"cli": {"lang": "python", "script_path": path}}
            r = cli_execute(payload)
            assert r["ok"] is True
            assert "from_path" in r["stdout"]
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_shell_true(self):
        payload = {"cli": {"cmd": "python -c \"print('shell_ok')\"", "shell": True}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "shell_ok" in r["stdout"]

    def test_script_dict_json(self):
        payload = {"cli": {"lang": "python",
                           "script": "import json,sys; d=json.loads('{\"a\": 1}'); print(d['a'])"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "1" in r["stdout"]

    def test_stdin_explicit(self):
        payload = {"cli": {"cmd": "python -c \"import sys; print(len(sys.stdin.read()))\"",
                           "stdin": "abcde"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "5" in r["stdout"]

    def test_stdin_from_value_false(self):
        payload = {"value": "should_not_use",
                   "cli": {"cmd": "python -c \"import sys; print(len(sys.stdin.read()))\"",
                           "stdin_from_value": False}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "0" in r["stdout"]

    def test_task_type_case_insensitive(self):
        payload = {"task_type": "PYTHON",
                   "cli": {"script": "print('upper')"}}
        r = cli_execute(payload)
        assert r["ok"] is True
        assert "upper" in r["stdout"]


class TestCliExecuteFail:
    """cli_execute 失败路径测试。"""

    def test_unknown_lang(self):
        payload = {"cli": {"lang": "brainfuck"}}
        r = cli_execute(payload)
        assert r["ok"] is False
        assert "未知语言" in r["stderr"]

    def test_missing_cmd_and_lang(self):
        payload = {"cli": {}}
        r = cli_execute(payload)
        assert r["ok"] is False
        assert "缺少 cli.cmd" in r["stderr"]

    def test_missing_cmd_unknown_task_type(self):
        payload = {"task_type": "weird", "cli": {}}
        r = cli_execute(payload)
        assert r["ok"] is False

    def test_interpreter_not_found(self):
        payload = {"cli": {"cmd": "definitely_not_a_real_cmd_xyz --help"}}
        r = cli_execute(payload)
        assert r["ok"] is False
        assert r["error"] is not None

    def test_payload_none(self):
        r = cli_execute(None)
        assert r["ok"] is False
        assert "缺少 cli.cmd" in r["stderr"]


class TestJsonDumps:
    """json_dumps 测试。"""

    def test_basic(self):
        from vools.task.core.cli_exec import json_dumps
        assert json_dumps({"a": 1}) == '{"a": 1}'
        assert json_dumps([1, 2]) == "[1, 2]"

    def test_unicode(self):
        from vools.task.core.cli_exec import json_dumps
        assert json_dumps({"k": "中文"}) == '{"k": "中文"}'


class TestImport:
    """导入与常量测试。"""

    def test_all(self):
        from vools.task.core.cli_exec import __all__
        assert "cli_execute" in __all__
        assert "detect_language" in __all__
        assert "find_executable" in __all__

    def test_lang_default_cmd(self):
        assert LANGUAGE_DEFAULT_CMD["python"] == ["python"]
        assert LANGUAGE_DEFAULT_CMD["go"] == ["go", "run"]
        assert LANGUAGE_DEFAULT_CMD["sh"] == ["bash"]

    def test_lang_extensions(self):
        assert LANGUAGE_EXTENSIONS["python"] == ".py"
        assert LANGUAGE_EXTENSIONS["scala"] == ".scala"
        assert LANGUAGE_EXTENSIONS["go"] == ".go"
