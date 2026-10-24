"""local_runner 测试：本地任务路由判定 + 执行 + 结果落盘 + 回写。"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, r'E:\IDEProjects\AI\vools')
sys.path.insert(0, r'E:\IDEProjects\AI\vools\rhop')

from vools.rhop.task.errors import ExecDenied
from vools.rhop.task.exec import ExecPolicy
from vools.rhop.task.local_runner import (
    mark_local_result,
    run_local_task,
    should_run_local,
)
from vools.rhop.task.models import TaskRecord
from vools.rhop.task.store import create_store


def _py_cmd(code):
    return '"%s" -c "%s"' % ((sys.executable or "python").replace("\\", "/"), code)


class TestShouldRunLocal:
    def test_explicit_exec_local_true_with_action(self):
        from vools.rhop.task.exec import register_handler
        register_handler("lr_srl_double", lambda payload: {"v": 1})
        task = {"task_name": "t", "exec_local": True,
                "payload": {"handler": "lr_srl_double"}}
        ok, reason = should_run_local(task)
        assert ok is True

    def test_explicit_exec_local_false(self):
        task = {"task_name": "t", "exec_local": False,
                "payload": {"handler": "noop"}}
        ok, reason = should_run_local(task)
        assert ok is False
        assert "exec_local=False" in reason

    def test_uppercase_keys_compat(self):
        task = {"TASK_NAME": "t", "EXEC_LOCAL": False,
                "payload": {"handler": "noop"}}
        ok, _ = should_run_local(task)
        assert ok is False

    def test_no_instruction_channel(self):
        task = {"task_name": "t", "value": "nothing actionable"}
        ok, reason = should_run_local(task)
        assert ok is False
        assert "无可识别" in reason

    def test_whitelist_denies_cli_by_default(self):
        task = {"task_name": "t", "payload": {"cli": {"cmd": _py_cmd("print(1)")}}}
        ok, reason = should_run_local(task)
        assert ok is False
        assert "白名单拒绝" in reason

    def test_whitelist_allows_cli_when_listed(self):
        task = {"task_name": "t", "payload": {"cli": {"cmd": _py_cmd("print(1)")}}}
        ok, reason = should_run_local(task, policy=ExecPolicy(allow=["cli:*"]))
        assert ok is True

    def test_runner_hint_mismatch(self):
        task = {"task_name": "t", "runner": "action:jump.probe",
                "payload": {"cli": {"cmd": _py_cmd("print(1)")}}}
        ok, reason = should_run_local(task, policy=ExecPolicy(allow=["cli:*"]))
        assert ok is False
        assert "runner" in reason

    def test_not_a_dict(self):
        ok, reason = should_run_local("nope")
        assert ok is False


class TestRunLocalTask:
    def test_run_cli_and_write_result_file(self, tmp_path):
        task = {"task_name": "job-1",
                "payload": {"cli": {"cmd": _py_cmd("print(42)")}}}
        out = run_local_task(task, policy=ExecPolicy(allow=["cli:*"]),
                             result_dir=str(tmp_path))
        assert out["ok"] is True, out.get("error")
        assert out["result"]["stdout"].strip() == "42"
        assert out["result_file"] is not None
        assert os.path.isfile(out["result_file"])
        with open(out["result_file"], encoding="utf-8") as fh:
            body = json.load(fh)
        assert body["task_name"] == "job-1"
        assert body["ok"] is True
        assert body["sha256"] == out["sha256"]

    def test_run_failure_recorded(self, tmp_path):
        task = {"task_name": "job-2",
                "payload": {"cli": {"cmd": _py_cmd("raise SystemExit(3)")}}}
        out = run_local_task(task, policy=ExecPolicy(allow=["cli:*"]),
                             result_dir=str(tmp_path))
        assert out["ok"] is False
        assert out["result_file"] is not None  # 失败也落盘，供回传诊断

    def test_denied_task_raises(self):
        task = {"task_name": "job-3",
                "payload": {"cli": {"cmd": "echo hi"}}}
        with pytest.raises(ExecDenied):
            run_local_task(task)  # 默认白名单不放行 cli

    def test_handler_channel(self):
        from vools.rhop.task.exec import register_handler
        register_handler("lr_test_double", lambda payload: {"v": 21 * 2})
        task = {"task_name": "job-4", "payload": {"handler": "lr_test_double"}}
        out = run_local_task(task)
        assert out["ok"] is True
        assert out["result"] == {"v": 42}

    def test_timeout_sec_wired_to_cli(self, tmp_path):
        """timeout_sec 必须真正生效（run_payload 无独立超时参数，经 cli.timeout_sec 接线）。"""
        slow = _py_cmd("import time; time.sleep(5); print('done')")
        task = {"task_name": "job-timeout",
                "payload": {"cli": {"cmd": slow}}}
        out = run_local_task(task, policy=ExecPolicy(allow=["cli:*"]),
                             result_dir=str(tmp_path), timeout_sec=0.5)
        assert out["ok"] is False
        assert "超时" in (out["error"] or "")

    def test_timeout_sec_none_keeps_payload_clean(self):
        """不传 timeout_sec 时不得往 payload 塞 cli 子键（污染原 task dict）。"""
        task = {"task_name": "job-clean", "payload": {"handler": "lr_test_double"}}
        run_local_task(task, timeout_sec=None)
        assert "cli" not in task["payload"]


class TestMarkLocalResult:
    def _store(self, tmp_path):
        spec = {"kind": "sqlite-local", "name": "lr", "path": str(tmp_path / "t.db")}
        return create_store(spec, {"name": "lr", "role": "B", "base_dir": str(tmp_path)})

    def test_mark_result_writes_back_info(self, tmp_path):
        store = self._store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="j")])
        summary = {"ok": True, "channel": "handler", "result": {"v": 1}}
        assert mark_local_result(store, "j", summary) is True
        rec = store.get_task("j")
        assert rec.back_info is not None
        body = json.loads(rec.back_info)
        assert body["ok"] is True
        assert body["result"] == {"v": 1}
        store.close()

    def test_mark_missing_task_returns_false(self, tmp_path):
        store = self._store(tmp_path)
        assert mark_local_result(store, "ghost", {"ok": True}) is False
        store.close()
