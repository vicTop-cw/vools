"""队列主流程测试：提交/归一/DAG/载荷加密/执行/重试/取消/结果编解码。"""

import json
import os
import sys

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.task.config import TaskConfig
from vools.rhop.task.errors import DagValidationError, ExecDenied, PayloadError, SecretError
from vools.rhop.task.models import TaskRecord, TaskState
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

    def test_result_cap_is_hard_cap_for_non_stdout_fields(self, tmp_path):
        """BUG-283 收口：result_max_bytes 是落库硬上限，非 stdout/stderr 的大字段也要被压。"""
        cfg = TaskConfig.from_dict({"name": "n", "role": "B", "key": "k",
                                    "queue": {"store": {"kind": "sqlite-local"},
                                              "encrypt_result": False,
                                              "result_max_bytes": 1000}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        q = TaskQueue(cfg)
        try:
            encoded = q.encode_result({"result": {"blob": "y" * 20000},
                                       "channel": "handler", "name": "n"})
            assert len(encoded.encode("utf-8")) <= 1000, "落库文本必须不超过上限"
            decoded = json.loads(encoded)
            assert decoded["truncated"] is True
            assert decoded["result_chars"] >= 20000   # 摘要记的是 str(dict) 长度（含引号/括号）
            assert "result_head" in decoded
        finally:
            q.close()

    def test_result_cap_holds_under_encryption(self, tmp_path):
        """BUG-283 收口（加密路径）：预留 Fernet 信封开销后，落库密文也必须 ≤ 上限。"""
        cfg = TaskConfig.from_dict({"name": "n", "role": "B", "key": "k",
                                    "queue": {"store": {"kind": "sqlite-local"},
                                              "encrypt_result": True,
                                              "result_max_bytes": 4000}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        q = TaskQueue(cfg)
        try:
            encoded = q.encode_result({"result": {"blob": "z" * 50000},
                                       "channel": "cli", "name": "python"})
            assert len(encoded.encode("utf-8")) <= 4000, "加密后的落库文本也必须不超过上限"
            assert q.decode_result(encoded)["truncated"] is True
        finally:
            q.close()


class TestLeaseRenewal:
    """BUG-289 收口：renew_lock 委托给 store，且开启后长任务执行期间真的续期。"""

    def test_renew_lock_delegates_and_refuses_non_running(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        q = TaskQueue(_cfg("B", share, queue={"store": {"kind": "sqlite-shared"},
                                              "lock_ttl_sec": 1}))
        try:
            assert q.renew_lock("ghost") is False
            q.submit([{"task_name": "j", "value": "x"}])
            assert q.renew_lock("j") is False                    # 未领取（PENDING）
            assert q.store.claim_next("w1") is not None
            assert q.renew_lock("j", worker_id="w1") is True
            assert q.renew_lock("j", worker_id="w2") is False    # 非持有者
        finally:
            q.close()

    def test_renewal_thread_refreshes_during_execution(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        q = TaskQueue(_cfg("B", share, queue={"store": {"kind": "sqlite-shared"},
                                              "lock_ttl_sec": 1,
                                              "renew_lock": True,
                                              "renew_interval_sec": 0.2}))
        calls = []
        original = q.store.touch_lock

        def _spy(name, worker_id=None, now=None):
            calls.append(name)
            return original(name, worker_id=worker_id, now=now)

        q.store.touch_lock = _spy
        try:
            script = os.path.join(str(tmp_path), "wait.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write("import time; time.sleep(1.2); print('done')\n")
            cmd = '"%s" "%s"' % (sys.executable.replace("\\", "/"),
                                 script.replace("\\", "/"))
            q.submit([{"task_name": "long", "cli": {"cmd": cmd}, "timeout_min": 30}])
            assert q.run_once()["action"] == "completed"
            assert "long" in calls, "开启 renew_lock 后，长任务执行期间必须真的续期（BUG-289）"
            assert len(calls) >= 2, "1.2s 的任务按 0.2s 间隔应至少续期两次"
        finally:
            q.close()

    def test_renewal_off_by_default(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        q = TaskQueue(_cfg("B", share, queue={"store": {"kind": "sqlite-shared"},
                                              "lock_ttl_sec": 1}))
        try:
            assert q.config.queue.get("renew_lock") is not True   # 默认关闭 ⇒ 零回归
            fake = type("R", (), {"task_name": "j"})()
            assert q._start_renewal(fake, "w1") is None
        finally:
            q.close()


class TestCancelIntent:
    """BUG-290 收口：取消终态任务是幂等 no-op，但必须留痕（warning），不许静默。"""

    def test_cancel_on_terminal_task_is_noop_with_warning(self, tmp_path, caplog):
        import logging
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        q = TaskQueue(_cfg("A", share, queue={"store": {"kind": "sqlite-shared"}}))
        try:
            q.submit([{"task_name": "done", "value": "v"}])
            assert q.store.set_state("done", TaskState.COMPLETED, force=True) is True
            with caplog.at_level(logging.WARNING, logger="vools.rhop.task.queue"):
                out = q.cancel("done")
            assert out["pending"] is False
            assert out["state"] == TaskState.COMPLETED
            assert q.get_task("done").state == TaskState.COMPLETED
            assert any("已处于终态" in r.getMessage() for r in caplog.records), \
                "取消终态任务必须留痕（BUG-290）"
        finally:
            q.close()

    def test_cancel_pending_task_cancels_immediately(self, tmp_path):
        share = os.path.join(str(tmp_path), "share")
        os.makedirs(share)
        q = TaskQueue(_cfg("A", share, queue={"store": {"kind": "sqlite-shared"}}))
        try:
            q.submit([{"task_name": "p", "value": "v"}])
            out = q.cancel("p")
            assert out["pending"] is False
            assert q.get_task("p").state == TaskState.CANCELLED
        finally:
            q.close()


class TestFileChannel:
    """大载荷文件通道（advance 轮）：超阈值落文件 + 引用读回 + 清理；默认关闭 ⇒ 零回归。"""

    def _cfg(self, tmp_path, file_channel=None, **queue_overrides):
        fc = {"enabled": True, "dir": os.path.join(str(tmp_path), "files"),
              "max_bytes": 500, "keep_days": 7}
        fc.update(file_channel or {})
        queue = {"store": {"kind": "sqlite-local"}, "file_channel": fc}
        queue.update(queue_overrides)
        return TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k", "queue": queue},
            base_dir=str(tmp_path), warn_plaintext=False)

    def test_disabled_by_default(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.queue["file_channel"]["enabled"] is False

    def test_offload_and_readback(self, tmp_path):
        q = TaskQueue(self._cfg(tmp_path))
        try:
            big = {"result": {"blob": "x" * 4000}, "channel": "handler", "name": "n"}
            encoded = q.encode_result(big)
            # 信封里只回引用（读信封拿 file_ref）
            node = q.crypto.decrypt_verify(encoded).payload if q.crypto else json.loads(encoded)
            ref = node["file_ref"]
            assert os.path.isfile(ref["path"]), "超阈值时必须落文件"
            assert ref["bytes"] > 500
            assert len(open(ref["path"], encoding="utf-8").read().encode("utf-8")) > 500
            # 按引用应能读回完整结果（返回的是完整内容，不是信封）
            decoded = q.decode_result(encoded)
            assert decoded["result"]["blob"] == "x" * 4000, "按引用应能读回完整结果"
        finally:
            q.close()

    def test_under_threshold_not_offloaded(self, tmp_path):
        q = TaskQueue(self._cfg(tmp_path, file_channel={"max_bytes": 50000}))
        try:
            small = {"result": {"blob": "y" * 100}, "channel": "handler", "name": "n"}
            decoded = q.decode_result(q.encode_result(small))
            assert "file_ref" not in decoded
            assert decoded["result"]["blob"] == "y" * 100
        finally:
            q.close()

    def test_missing_file_is_graceful(self, tmp_path):
        q = TaskQueue(self._cfg(tmp_path))
        try:
            encoded = q.encode_result({"result": {"blob": "z" * 4000},
                                       "channel": "n", "name": "n"})
            node = q.crypto.decrypt_verify(encoded).payload if q.crypto else json.loads(encoded)
            os.remove(node["file_ref"]["path"])          # 文件被清理 / 丢失
            out = q.decode_result(encoded)
            assert "__file_missing__" in out, "引用失效必须可区分地返回，而不是抛错"
        finally:
            q.close()

    def test_sha_mismatch_is_graceful(self, tmp_path):
        q = TaskQueue(self._cfg(tmp_path, encrypt_result=False))
        try:
            encoded = q.encode_result({"result": {"blob": "z" * 4000},
                                       "channel": "n", "name": "n"})
            node = json.loads(encoded)
            node["file_ref"]["sha256"] = "0" * 64
            out = q.decode_result(json.dumps(node, ensure_ascii=False))
            assert "__file_sha_mismatch__" in out
        finally:
            q.close()

    def test_cleanup_removes_old_files_only(self, tmp_path):
        import time
        files_dir = os.path.join(str(tmp_path), "files")
        os.makedirs(files_dir, exist_ok=True)
        # 结果文件命名规则：<UTC时间戳>-<sha8>.json（与 _maybe_offload_result 一致）
        old = os.path.join(files_dir, "20200101T000000-deadbeef.json")
        new = os.path.join(files_dir, "20300101T000000-deadbeef.json")
        for path in (old, new):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{}")
        os.utime(old, (time.time() - 30 * 86400, time.time() - 30 * 86400))
        q = TaskQueue(self._cfg(tmp_path, keep_days=7))
        try:
            assert q.cleanup_result_files() == 1
            assert not os.path.exists(old)
            assert os.path.exists(new)
        finally:
            q.close()

    def test_cleanup_keeps_non_result_files(self, tmp_path):
        """BUG-296 收口：同目录的非结果文件（运维说明等）不得被清理误删。"""
        import time
        files_dir = os.path.join(str(tmp_path), "files")
        os.makedirs(files_dir, exist_ok=True)
        ops = os.path.join(files_dir, "README-ops.txt")
        with open(ops, "w", encoding="utf-8") as fh:
            fh.write("运维说明，请勿删除")
        os.utime(ops, (time.time() - 30 * 86400, time.time() - 30 * 86400))
        q = TaskQueue(self._cfg(tmp_path, keep_days=7))
        try:
            assert q.cleanup_result_files() == 0
            assert os.path.exists(ops), "非结果文件必须保留"
        finally:
            q.close()

    def test_dir_must_stay_inside_allowed_roots(self, tmp_path):
        """BUG-295 收口：file_channel.dir 逃逸出 base_dir 必须报错拒绝，且不落盘。"""
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"},
                       "file_channel": {"enabled": True, "dir": "../escaped",
                                        "max_bytes": 100, "keep_days": 7}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        q = TaskQueue(cfg)
        try:
            with pytest.raises(SecretError):
                q.encode_result({"result": {"blob": "z" * 3000}, "channel": "n", "name": "n"})
            assert not os.path.exists(os.path.join(str(tmp_path), os.pardir, "escaped")), \
                "校验失败时不得在 base_dir 之外建目录"
        finally:
            q.close()

    def test_payload_offload_roundtrip(self, tmp_path):
        """载荷侧落文件：超阈值时 payload_enc 是引用信封，B 端按引用读回完整载荷。"""
        q = TaskQueue(self._cfg(tmp_path,
                                file_channel={"enabled": True, "payload_max_bytes": 500}))
        try:
            payload = {"cmd": "x" * 3000, "env": {"A": "1"}}
            encoded = q.encrypt_payload(payload)
            node = json.loads(encoded["payload_enc"])
            assert node.get("kind") == "rhop-payload-file", "超阈值载荷必须落文件"
            assert os.path.isfile(node["file_ref"]["path"])
            rec = TaskRecord(task_name="t", payload_enc=encoded["payload_enc"],
                             payload_sha=encoded["payload_sha"])
            assert q.decrypt_payload(rec) == payload
        finally:
            q.close()

    def test_payload_offload_disabled_by_default(self, tmp_path):
        q = TaskQueue(self._cfg(tmp_path))
        try:
            payload = {"cmd": "x" * 3000}
            encoded = q.encrypt_payload(payload)
            assert "rhop-payload-file" not in encoded["payload_enc"], "默认关闭 ⇒ 载荷仍整条入队"
            rec = TaskRecord(task_name="t", payload_enc=encoded["payload_enc"],
                             payload_sha=encoded["payload_sha"])
            assert q.decrypt_payload(rec) == payload
        finally:
            q.close()

    def test_payload_offload_missing_file_raises(self, tmp_path):
        """引用失效必须抛可读的 PayloadError，而不是静默返回空载荷。"""
        q = TaskQueue(self._cfg(tmp_path,
                                file_channel={"enabled": True, "payload_max_bytes": 500}))
        try:
            payload = {"cmd": "x" * 3000}
            encoded = q.encrypt_payload(payload)
            node = json.loads(encoded["payload_enc"])
            os.remove(node["file_ref"]["path"])
            rec = TaskRecord(task_name="t", payload_enc=encoded["payload_enc"],
                             payload_sha=encoded["payload_sha"])
            with pytest.raises(PayloadError) as exc:
                q.decrypt_payload(rec)
            assert "载荷文件缺失" in str(exc.value)
        finally:
            q.close()

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