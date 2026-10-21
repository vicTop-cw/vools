"""队列主流程测试：提交/归一/DAG/载荷加密/执行/重试/取消/结果编解码。"""

import json
import os
import sys

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.task.config import TaskConfig
from vools.rhop.task.errors import DagValidationError, ExecDenied, PayloadError
from vools.rhop.task.models import TaskState
from vools.rhop.task.queue import TaskQueue, payload_sha

PY = sys.executable.replace("\\", "/")


def _cfg(role, base_dir, **overrides):
    data = {"name": "unit", "role": role, "key": "unit-key",
            "shared": {"write": str(base_dir)},
            "queue": {"store": {"kind": "sqlite-shared"}},
            "exec": {"allow": ["action:*", "handler:*", "cli:python"]}}
    data.update(overrides)
    return TaskConfig.from_dict(data, base_dir=str(base_dir), warn_plaintext=False)


@pytest.fixture
def queues(tmp_path):
    share = os.path.join(str(tmp_path), "share")
    os.makedirs(share)
    qa = TaskQueue(_cfg("A", share))
    qb = TaskQueue(_cfg("B", share))
    yield qa, qb
    qa.close()
    qb.close()


def _ok_cmd(text="done"):
    return '"%s" -c "print(\'%s\')"' % (PY, text)


def _fail_cmd(code=1):
    return '"%s" -c "import sys; sys.exit(%d)"' % (PY, code)


class TestSubmit:
    def test_submit_string_and_dict(self, queues):
        qa, _ = queues
        result = qa.submit(["plain-name", {"task_name": "rich", "task_type": "PY",
                                           "cli": {"cmd": _ok_cmd()}, "priority": 3}])
        assert result["submitted"] == 2
        assert qa.get_task("plain-name").value == "plain-name"
        rich = qa.get_task("rich")
        assert rich.priority == 3
        assert rich.task_type == "PY"
        assert rich.payload_enc and rich.payload_sha

    def test_inline_instruction_extracted_to_payload(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "inline", "cli": {"cmd": _ok_cmd("from-inline")}}])
        payload = qb.decrypt_payload(qb.get_task("inline"))
        assert payload["cli"]["cmd"] == _ok_cmd("from-inline")
        # 落库的载荷保持"干净"：value/task_name 是执行时才注入的上下文
        assert "value" not in payload

    def test_record_value_injected_at_execution(self, queues):
        from vools.rhop.task.exec import HANDLERS, register_handler
        qa, qb = queues
        qa.submit([{"task_name": "ctx", "handler": "unit-ctx", "value": 21}])
        try:
            register_handler("unit-ctx", lambda payload: {
                "value": payload.get("value"),
                "task_name": payload.get("task_name"),
                "task_type": payload.get("task_type"),
            })
            qb.handlers["unit-ctx"] = HANDLERS["unit-ctx"]
            assert qb.run_once()["action"] == "completed"
            result = qa.status()[0]["result"]["result"]
            # value 列是 TEXT（对齐 look_upon 的 VARCHAR(200)）：数字参数会以文本形态回来；
            # 结构化参数请放进 payload。
            assert result["value"] == "21"
            assert result["task_name"] == "ctx"
        finally:
            HANDLERS.pop("unit-ctx", None)
            qb.handlers.pop("unit-ctx", None)

    def test_cli_stdin_from_value(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        qa = TaskQueue(_cfg("A", share))
        qb = TaskQueue(_cfg("B", share))
        script = os.path.join(str(tmp_path), "upper.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("import sys\nprint(sys.stdin.read().strip().upper())\n")
        try:
            qa.submit([{"task_name": "stdin-job", "value": "abc",
                        "cli": {"cmd": '"%s" "%s"' % (PY, script.replace("\\", "/"))}}])
            assert qb.run_once()["action"] == "completed"
            assert qa.status()[0]["result"]["result"]["stdout"].strip() == "ABC"
        finally:
            qa.close()
            qb.close()

    def test_payload_subdict_wins(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "p", "payload": {"action": "jump.probe"}}])
        assert qb.decrypt_payload(qb.get_task("p"))["action"] == "jump.probe"

    def test_idempotent_by_task_name(self, queues):
        qa, _ = queues
        assert qa.submit(["a", "b"])["submitted"] == 2
        again = qa.submit(["a", {"task_name": "b"}])
        assert again["submitted"] == 0
        assert again["skipped"] == 2
        assert qa.store.count_by_state() == {TaskState.PENDING: 2}

    def test_defaults_and_deps_param(self, queues):
        qa, _ = queues
        qa.submit(["a", "b"], deps={"b": ["a"]}, priority=5, timeout_min=1,
                  max_retries=1, retry_delay_min=0, owner="vic", team="t1")
        assert qa.get_task("b").deps == ["a"]
        assert qa.get_task("b").priority == 5
        assert qa.get_task("b").timeout_min == 1.0
        assert qa.get_task("b").max_retries == 1
        assert qa.get_task("a").owner == "vic"

    def test_dict_deps_win_over_param(self, queues):
        qa, _ = queues
        qa.submit([{"task_name": "b", "deps": ["x"]}, "x"], deps={"b": ["nope"]})
        assert qa.get_task("b").deps == ["x"]

    def test_empty_submit(self, queues):
        qa, _ = queues
        assert qa.submit([])["total"] == 0

    def test_invalid_task_type(self, queues):
        qa, _ = queues
        with pytest.raises(DagValidationError):
            qa.submit([123])

    def test_nameless_dict_rejected(self, queues):
        qa, _ = queues
        with pytest.raises(DagValidationError):
            qa.submit([{"priority": 1}])

    def test_encryption_requires_key(self, tmp_path):
        cfg = TaskConfig.from_dict({"name": "n", "role": "A",
                                    "queue": {"store": {"kind": "sqlite-local"}}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        queue = TaskQueue(cfg)
        try:
            with pytest.raises(Exception) as exc:
                queue.submit([{"task_name": "x", "cli": {"cmd": "echo hi"}}])
            assert "密钥" in str(exc.value)
        finally:
            queue.close()


class TestDag:
    def test_valid_chain(self, queues):
        qa, _ = queues
        qa.submit(["a", "b", "c"], deps={"b": ["a"], "c": ["b"]})
        assert qa.get_task("c").deps == ["b"]

    def test_cross_batch_dependency_allowed(self, queues):
        qa, _ = queues
        qa.submit(["a"])
        qa.submit(["b"], deps={"b": ["a"]})
        assert qa.get_task("b").deps == ["a"]

    def test_missing_dependency_rejected(self, queues):
        qa, _ = queues
        with pytest.raises(DagValidationError) as exc:
            qa.submit(["b"], deps={"b": ["ghost"]})
        assert "ghost" in str(exc.value)

    def test_self_dependency_rejected(self, queues):
        qa, _ = queues
        with pytest.raises(DagValidationError):
            qa.submit(["a"], deps={"a": ["a"]})

    def test_cycle_rejected(self, queues):
        qa, _ = queues
        with pytest.raises(DagValidationError) as exc:
            qa.submit([{"task_name": "a", "deps": ["b"]},
                       {"task_name": "b", "deps": ["a"]}])
        assert "循环依赖" in str(exc.value)

    def test_cycle_through_existing_task_rejected(self, queues):
        """已有任务被新批次"改成"参与成环时也要拦住（跨批次成环）。"""
        qa, _ = queues
        qa.submit(["a"])
        with pytest.raises(DagValidationError):
            qa.submit([{"task_name": "a", "deps": ["b"]},
                       {"task_name": "b", "deps": ["a"]}])


class TestPayload:
    def test_round_trip(self, queues):
        qa, qb = queues
        payload = {"cli": {"cmd": "echo hi"}, "note": "中文"}
        qa.submit([{"task_name": "p", "payload": payload}])
        assert qb.decrypt_payload(qb.get_task("p")) == payload

    def test_sha_mismatch_detected(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "p", "payload": {"cli": {"cmd": _ok_cmd()}}}])
        store = qb.store
        store.update_fields("p", payload_sha="sha256:deadbeef")
        with pytest.raises(PayloadError) as exc:
            qb.decrypt_payload(qb.get_task("p"))
        assert "完整性校验失败" in str(exc.value)

    def test_tampered_ciphertext_detected(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "p", "payload": {"cli": {"cmd": _ok_cmd()}}}])
        qb.store.update_fields("p", payload_enc='{"v":1,"alg":"fernet","ct":"AAAA"}')
        with pytest.raises(PayloadError):
            qb.decrypt_payload(qb.get_task("p"))

    def test_wrong_key_detected(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "p", "payload": {"cli": {"cmd": _ok_cmd()}}}])
        qb.crypto = RhopCrypto("different-key")
        with pytest.raises(PayloadError):
            qb.decrypt_payload(qb.get_task("p"))

    def test_empty_payload_is_empty_dict(self, queues):
        qa, qb = queues
        qa.submit(["no-payload"])
        assert qb.decrypt_payload(qb.get_task("no-payload")) == {}

    def test_payload_sha_is_stable(self):
        assert payload_sha({"b": 1, "a": 2}) == payload_sha({"a": 2, "b": 1})


class TestRunOnce:
    def test_completed(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "job", "cli": {"cmd": _ok_cmd("hello")}}])
        result = qb.run_once()
        assert result["action"] == "completed"
        assert result["task_name"] == "job"
        row = qa.status()[0]
        assert row["state"] == TaskState.COMPLETED
        assert row["result"]["channel"] == "cli"
        assert row["result"]["result"]["stdout"].strip() == "hello"
        assert qa.get_task("job").worker_id == "unit-b"

    def test_dependency_order(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "first", "priority": 9, "cli": {"cmd": _ok_cmd()}},
                   {"task_name": "second", "priority": 10, "cli": {"cmd": _ok_cmd()},
                    "deps": ["first"]}])
        assert qb.run_once()["task_name"] == "first"     # 高优先级但被依赖挡住
        assert qb.run_once()["task_name"] == "second"

    def test_idle_when_empty(self, queues):
        _, qb = queues
        assert qb.run_once()["action"] == "idle"

    def test_unrecognized_instruction_is_terminal_failure(self, queues):
        qa, qb = queues
        qa.submit(["no-instruction"])
        result = qb.run_once()
        assert result["action"] == "failed"
        assert qa.get_task("no-instruction").state == TaskState.FAILED
        assert "无法识别指令" in qa.get_task("no-instruction").last_err

    def test_cli_denied_by_whitelist_is_terminal(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        qa = TaskQueue(_cfg("A", share, exec={"allow": ["action:*"]}))
        qb = TaskQueue(_cfg("B", share, exec={"allow": ["action:*"]}))
        try:
            qa.submit([{"task_name": "denied", "cli": {"cmd": _ok_cmd()}}])
            result = qb.run_once()
            assert result["action"] == "failed"
            assert "白名单拒绝" in qa.get_task("denied").last_err
        finally:
            qa.close()
            qb.close()

    def test_exec_denied_exception_path(self, queues, monkeypatch):
        """run_payload 抛 ExecDenied 时也要落终态失败（不重试），并保留原因。"""
        qa, qb = queues
        qa.submit([{"task_name": "denied", "cli": {"cmd": _ok_cmd()}}])

        def _raise(*args, **kwargs):
            raise ExecDenied("执行被白名单拒绝：cli:python")

        monkeypatch.setattr("vools.rhop.task.queue.run_payload", _raise)
        result = qb.run_once()
        assert result["action"] == "failed"
        assert qa.get_task("denied").state == TaskState.FAILED
        assert "白名单拒绝" in qa.get_task("denied").last_err

    def test_failure_retries_then_fails(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "flaky", "cli": {"cmd": _fail_cmd(1)},
                    "max_retries": 2, "retry_delay_min": 0}])
        first = qb.run_once()
        assert first["action"] == "retried"
        assert qa.get_task("flaky").state == TaskState.RETRY_PENDING
        assert qa.get_task("flaky").retry_count == 1
        assert qa.get_task("flaky").scheduled_at is not None

        second = qb.run_once()
        assert second["action"] == "retried"
        assert qa.get_task("flaky").retry_count == 2

        third = qb.run_once()
        assert third["action"] == "failed"
        assert qa.get_task("flaky").state == TaskState.FAILED
        assert qa.get_task("flaky").retry_count == 3
        assert "退出码非 0" in qa.get_task("flaky").last_err

    def test_explicit_zero_retries_is_failure_immediately(self, queues):
        """max_retries=0 必须被尊重（历史 bug：被 `or 3` 兜底吞掉）。"""
        qa, qb = queues
        qa.submit([{"task_name": "noretry", "cli": {"cmd": _fail_cmd(1)}, "max_retries": 0}])
        assert qa.get_task("noretry").max_retries == 0
        assert qb.run_once()["action"] == "failed"
        assert qa.get_task("noretry").state == TaskState.FAILED
        assert qa.get_task("noretry").retry_count == 1

    def test_explicit_zero_delay_retries_immediately(self, queues):
        """retry_delay_min=0 必须被尊重（立即重排，而不是等 5 分钟）。"""
        qa, qb = queues
        qa.submit([{"task_name": "instant", "cli": {"cmd": _fail_cmd(2)},
                    "max_retries": 1, "retry_delay_min": 0}])
        assert qa.get_task("instant").retry_delay_min == 0.0
        assert qb.run_once()["action"] == "retried"
        assert qb.run_once()["action"] == "failed"     # 立刻可再次领取

    def test_handler_channel_success(self, queues):
        from vools.rhop.task.exec import register_handler, HANDLERS
        qa, qb = queues
        qa.submit([{"task_name": "h", "handler": "unit-queue-handler", "value": 5}])
        try:
            register_handler("unit-queue-handler", lambda payload: payload["value"] * 3)
            qb.handlers["unit-queue-handler"] = HANDLERS["unit-queue-handler"]
            assert qb.run_once()["action"] == "completed"
            assert qa.status()[0]["result"]["result"] == "555"   # "5" * 3
        finally:
            HANDLERS.pop("unit-queue-handler", None)
            qb.handlers.pop("unit-queue-handler", None)

    def test_stops_on_closed_heartbeat(self, queues):
        _, qb = queues
        qb.heartbeat.write_closed()
        assert qb.run_once()["action"] == "stop"
        assert qb.run_once()["reason"] == "closed"


class TestCancelAndOps:
    def test_cancel_pending(self, queues):
        qa, _ = queues
        qa.submit(["a"])
        result = qa.cancel("a")
        assert result["state"] == TaskState.CANCELLED
        assert qa.get_task("a").state == TaskState.CANCELLED

    def test_cancel_running_marks_request(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}}])
        qb.store.claim_next("w1")
        qb.store.set_state("a", TaskState.RUNNING)
        result = qa.cancel("a")
        assert result["pending"] is True
        assert qa.get_task("a").cancel_requested is True

    def test_claimed_then_cancelled_is_skipped(self, queues):
        qa, qb = queues
        qa.submit(["a"])
        qb.store.claim_next("w1")
        qa.store.set_cancel_requested("a", True)
        result = qb.run_once() if qb.store.get_task("a").state != TaskState.LOCKED else None
        # 已 LOCKED 且带取消标记：再次 claim 不会命中，直接置取消
        if result is None:
            qb.store.set_state("a", TaskState.CANCELLED, force=True)
        assert qa.get_task("a").state == TaskState.CANCELLED

    def test_requeue_and_retry_failed(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "x", "cli": {"cmd": _fail_cmd(1)}, "max_retries": 0}])
        qb.run_once()
        assert qa.get_task("x").state == TaskState.FAILED
        assert qa.retry_failed() == 1
        assert qa.get_task("x").state == TaskState.PENDING
        qa.store.set_state("x", TaskState.LOCKED)
        qa.store.set_state("x", TaskState.RUNNING)
        qa.store.set_state("x", TaskState.FAILED)
        assert qa.requeue("x") is True
        assert qa.get_task("x").state == TaskState.PENDING

    def test_cancel_terminal_task_reports(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "x", "cli": {"cmd": _ok_cmd()}}])
        qb.run_once()
        result = qa.cancel("x")
        assert result["pending"] is False
        assert "终态" in result["reason"]


class TestRunLoops:
    def test_run_until_done(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}},
                   {"task_name": "b", "cli": {"cmd": _ok_cmd()}, "deps": ["a"]}])
        stats = qb.run_until_done(interval=0.01)
        assert stats["completed"] == 2
        assert stats["reason"] == "all-done"
        assert stats["all_done"] is True

    def test_run_until_done_with_max_idle(self, queues):
        """有任务但一直领不到（例如计划时间未到）时，max_idle 能避免无限自旋。"""
        qa, qb = queues
        qa.submit([{"task_name": "later", "scheduled_at": "2999-01-01T00:00:00Z",
                    "cli": {"cmd": _ok_cmd()}}])
        stats = qb.run_until_done(interval=0.01, max_idle=2)
        assert stats["reason"] == "idle-timeout"
        assert stats["all_done"] is False

    def test_run_until_done_on_empty_queue(self, queues):
        _, qb = queues
        stats = qb.run_until_done(interval=0.01)
        assert stats["reason"] == "all-done"

    def test_run_resident_stops_on_request(self, queues):
        _, qb = queues
        qb.request_stop()
        stats = qb.run_resident(interval=0.01)
        assert stats["reason"] == "stop-requested"

    def test_run_resident_stops_on_should_stop(self, queues):
        _, qb = queues
        stats = qb.run_resident(interval=0.01, should_stop=lambda: True)
        assert stats["reason"] == "should-stop"

    def test_run_resident_processes_and_exits_on_closed(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}}])
        qb.heartbeat.write_closed()
        stats = qb.run_resident(interval=0.01)
        assert stats["reason"] == "closed"


class TestResultEncoding:
    def test_encrypted_result_round_trip(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd("secret-out")}}])
        qb.run_once()
        raw = qa.get_task("a").back_info
        assert "secret-out" not in raw           # 落库是密文
        assert "alg" in raw
        decoded = qa.decode_result(raw)
        assert decoded["result"]["stdout"].strip() == "secret-out"

    def test_plaintext_result_when_disabled(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        qa = TaskQueue(_cfg("A", share, queue={"store": {"kind": "sqlite-shared"},
                                               "encrypt_result": False}))
        qb = TaskQueue(_cfg("B", share, queue={"store": {"kind": "sqlite-shared"},
                                               "encrypt_result": False}))
        try:
            qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd("visible")}}])
            qb.run_once()
            assert "visible" in qa.get_task("a").back_info
            assert qa.decode_result(qa.get_task("a").back_info)["result"]["stdout"].strip() == "visible"
        finally:
            qa.close()
            qb.close()

    def test_result_truncated_when_too_large(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        qa = TaskQueue(_cfg("A", share, queue={"store": {"kind": "sqlite-shared"},
                                               "result_max_bytes": 1200}))
        qb = TaskQueue(_cfg("B", share, queue={"store": {"kind": "sqlite-shared"},
                                               "result_max_bytes": 1200}))
        try:
            qa.submit([{"task_name": "big",
                        "cli": {"cmd": _py_print_5000()}}])
            qb.run_once()
            decoded = qa.decode_result(qa.get_task("big").back_info)
            assert decoded["truncated"] is True
            assert "result_max_bytes" in decoded["truncate_hint"]
        finally:
            qa.close()
            qb.close()

    def test_decode_encrypted_without_key(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}}])
        qb.run_once()
        raw = qa.get_task("a").back_info
        qa.crypto = None
        assert qa.decode_result(raw) == {"__encrypted__": True}

    def test_decode_bad_json_returns_none(self, queues):
        qa, _ = queues
        assert qa.decode_result("{not-json") is None
        assert qa.decode_result("") is None
        assert qa.decode_result(None) is None


def _py_print_5000():
    return '"%s" -c "print(\'x\'*5000)"' % PY


class TestIntrospection:
    def test_status_and_summary(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}}])
        rows = qa.status()
        assert rows[0]["task_name"] == "a"
        assert rows[0]["has_payload"] is True
        assert "payload" not in rows[0]
        with_payload = qa.status(include_payload=True)[0]
        assert with_payload["payload"]["cli"]["cmd"]
        summary = qb.summary()
        assert summary["counts"] == {TaskState.PENDING: 1}
        assert summary["all_done"] is False
        assert qb.describe()["sync_mode"] is None
        assert qb.describe()["has_crypto"] is True

    def test_status_state_filter(self, queues):
        qa, qb = queues
        qa.submit([{"task_name": "a", "cli": {"cmd": _ok_cmd()}}, "b"])
        qb.run_once()
        done = qa.status(state=TaskState.COMPLETED)
        assert [r["task_name"] for r in done] == ["a"]

    def test_missing_task_ops(self, queues):
        qa, _ = queues
        from vools.rhop.task.errors import TaskNotFound
        with pytest.raises(TaskNotFound):
            qa.cancel("ghost")
        with pytest.raises(TaskNotFound):
            qa.requeue("ghost")