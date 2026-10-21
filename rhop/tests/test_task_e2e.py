"""端到端测试：A 提交 → B 常驻执行 → A 看状态，含心跳判活、停机、崩溃恢复、两种存储拓扑。"""

import datetime
import json
import os
import sys
import time

import pytest

from vools.rhop.task.config import TaskConfig
from vools.rhop.task.daemon import TaskDaemon, build_queue
from vools.rhop.task.heartbeat import Heartbeat
from vools.rhop.task.models import TaskState
from vools.rhop.task.queue import TaskQueue

PY = sys.executable.replace("\\", "/")


def _config(role, base_dir, share, kind="sqlite-shared", **extra):
    queue = {"store": {"kind": kind},
             "heartbeat": {"file": "e2e.heartbeat", "interval_sec": 5, "stale_after_sec": 15}}
    queue.update(extra.pop("queue", {}))
    data = {"name": "e2e", "role": role, "key": "e2e-key",
            "shared": {"write": str(share)}, "queue": queue,
            "exec": {"allow": ["action:*", "handler:*", "cli:python"]}}
    data.update(extra)
    return TaskConfig.from_dict(data, base_dir=str(base_dir), warn_plaintext=False)


def _cmd(code="print('ok')", sleep=0.0):
    body = "import time; time.sleep(%s); %s" % (sleep, code) if sleep else code
    return '"%s" -c "%s"' % (PY, body)


@pytest.fixture
def workspace(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    work_a = tmp_path / "a"
    work_b = tmp_path / "b"
    work_a.mkdir()
    work_b.mkdir()
    return {"share": share, "a": work_a, "b": work_b, "root": tmp_path}


class TestSharedModeEndToEnd:
    def test_full_flow(self, workspace):
        share = workspace["share"]
        daemon_a = TaskDaemon(_config("A", workspace["a"], share))
        daemon_b = TaskDaemon(_config("B", workspace["b"], share))
        try:
            daemon_a.run_sender([
                {"task_name": "step1", "cli": {"cmd": _cmd("print('one')")}},
                {"task_name": "step2", "deps": ["step1"], "cli": {"cmd": _cmd("print('two')")}},
            ])
            # B 跑两轮把两个任务按依赖顺序做完
            for _ in range(4):
                if daemon_b.queue.is_all_done():
                    break
                daemon_b.run_executor(once=True)
            rows = {r["task_name"]: r for r in daemon_a.queue.status()}
            assert rows["step1"]["state"] == TaskState.COMPLETED
            assert rows["step2"]["state"] == TaskState.COMPLETED
            assert rows["step1"]["result"]["result"]["stdout"].strip() == "one"
            assert rows["step2"]["result"]["result"]["stdout"].strip() == "two"
            # 同一份共享库：A 端不需要任何同步步骤就看到状态
            assert daemon_a.queue.store.path == daemon_b.queue.store.path
            assert "sync_mode" in daemon_a.queue.describe()
        finally:
            daemon_a.close(write_closed=False)
            daemon_b.close(write_closed=False)

    def test_heartbeat_alive_during_long_task(self, workspace):
        share = workspace["share"]
        cfg_b = _config("B", workspace["b"], share,
                        queue={"heartbeat": {"file": "e2e.heartbeat", "interval_sec": 0.1,
                                             "stale_after_sec": 5}})
        daemon_b = TaskDaemon(cfg_b)
        daemon_a = TaskDaemon(_config("A", workspace["a"], share))
        try:
            daemon_a.queue.submit([{"task_name": "long",
                                    "cli": {"cmd": _cmd("print('done')", sleep=0.6)}}])
            pump = daemon_b.start_pump()
            assert pump is not None
            started = time.time()
            result = daemon_b.run_executor(once=True)      # 主线程被任务占住 ~0.6s
            elapsed = time.time() - started
            assert result["action"] == "completed"
            assert elapsed >= 0.5
            # 任务执行期间心跳并未停：读数是 alive 且刚刚更新过
            info = daemon_b.queue.heartbeat.read()
            assert info["state"] == "alive"
            assert info["age_sec"] < 5
        finally:
            daemon_b.close(write_closed=False)
            daemon_a.close(write_closed=False)

    def test_operator_close_stops_executor(self, workspace):
        share = workspace["share"]
        cfg_b = _config("B", workspace["b"], share,
                        queue={"heartbeat": {"file": "e2e.heartbeat", "interval_sec": 0.1}})
        daemon_b = TaskDaemon(cfg_b)
        try:
            daemon_b.queue.heartbeat.write_closed()
            stats = daemon_b.run_executor()
            assert stats["reason"] in ("closed", "stop-requested")
            assert daemon_b.queue.heartbeat.is_closed() is True
        finally:
            daemon_b.close(write_closed=False)

    def test_graceful_stop_writes_closed(self, workspace):
        share = workspace["share"]
        daemon_b = TaskDaemon(_config("B", workspace["b"], share))
        try:
            daemon_b.start_pump()
            daemon_b.stop()
            daemon_b.queue.request_stop()
            stats = daemon_b.run_executor()
            assert stats["reason"] == "stop-requested"
            assert daemon_b.queue.heartbeat.is_closed() is True
        finally:
            daemon_b.close()

    def test_stale_heartbeat_means_executor_dead(self, workspace):
        share = workspace["share"]
        cfg_a = _config("A", workspace["a"], share)
        daemon_a = TaskDaemon(cfg_a)
        try:
            daemon_a.queue.submit([{"task_name": "never",
                                    "cli": {"cmd": _cmd("print('x')")}}])
            # 心跳文件停在很久以前 → A 判死并退出等待
            daemon_a.queue.heartbeat.shared.write_text(daemon_a.queue.heartbeat.filename,
                                                       "2000-01-01T00:00:00Z")
            result = daemon_a.run_sender(wait=True, poll=0.01, dead_grace=1, timeout=5)
            assert result["reason"] == "executor-dead"
            assert result["heartbeat"]["state"] == "stale"
        finally:
            daemon_a.close(write_closed=False)

    def test_missing_heartbeat_means_executor_never_started(self, workspace):
        share = workspace["share"]
        daemon_a = TaskDaemon(_config("A", workspace["a"], share))
        try:
            daemon_a.queue.submit(["pending-forever"])
            result = daemon_a.run_sender(wait=True, poll=0.01, dead_grace=2, timeout=5)
            assert result["reason"] == "executor-dead"
            assert result["heartbeat"]["state"] == "missing"
        finally:
            daemon_a.close(write_closed=False)

    def test_closed_heartbeat_stops_a_side_wait(self, workspace):
        share = workspace["share"]
        daemon_a = TaskDaemon(_config("A", workspace["a"], share))
        try:
            daemon_a.queue.submit(["pending"])
            daemon_a.queue.heartbeat.write_closed()
            result = daemon_a.run_sender(wait=True, poll=0.01, timeout=5)
            assert result["reason"] == "executor-closed"
        finally:
            daemon_a.close(write_closed=False)

    def test_crash_recovery_reclaims_running_task(self, workspace):
        """worker 死在 RUNNING：锁过期后任务被回收重跑，不会丢。"""
        share = workspace["share"]
        cfg = _config("B", workspace["b"], share, queue={"store": {"kind": "sqlite-shared",
                                                                   "lock_ttl_sec": 1}})
        queue = build_queue(cfg)
        try:
            queue.submit([{"task_name": "crashy", "timeout_min": 0,
                           "cli": {"cmd": _cmd("print('recovered')")}}])
            rec = queue.store.claim_next("dead-worker")
            assert rec.task_name == "crashy"
            queue.store.set_state("crashy", TaskState.RUNNING)
            # 模拟锁过期（时间推到未来）
            reclaimed = queue.store.clean_stale_locks(now="2999-01-01T00:00:00Z")
            assert reclaimed == 1
            assert queue.store.get_task("crashy").state == TaskState.RETRY_PENDING
            assert queue.run_once()["action"] == "completed"
            assert queue.store.get_task("crashy").state == TaskState.COMPLETED
        finally:
            queue.close()


class TestLocalModeEndToEnd:
    def test_two_databases_converge(self, workspace):
        share = workspace["share"]
        daemon_a = TaskDaemon(_config("A", workspace["a"], share, kind="sqlite-local"))
        daemon_b = TaskDaemon(_config("B", workspace["b"], share, kind="sqlite-local"))
        try:
            assert daemon_a.queue.store.path != daemon_b.queue.store.path
            assert daemon_a.queue.syncer is not None
            assert daemon_b.queue.syncer is not None
            daemon_a.queue.submit([
                {"task_name": "l1", "cli": {"cmd": _cmd("print('l1')")}},
                {"task_name": "l2", "deps": ["l1"], "cli": {"cmd": _cmd("print('l2')")}},
            ])
            for _ in range(4):
                daemon_b.run_executor(once=True)
            # A 拉一次状态包即可看到结果（本地库模式）
            daemon_a.queue.pull_sync()
            rows = {r["task_name"]: r for r in daemon_a.queue.status()}
            assert rows["l1"]["state"] == TaskState.COMPLETED
            assert rows["l2"]["state"] == TaskState.COMPLETED
            assert rows["l1"]["result"]["result"]["stdout"].strip() == "l1"
        finally:
            daemon_a.close(write_closed=False)
            daemon_b.close(write_closed=False)

    def test_submit_pushes_without_explicit_sync(self, workspace):
        share = workspace["share"]
        daemon_a = TaskDaemon(_config("A", workspace["a"], share, kind="sqlite-local"))
        daemon_b = TaskDaemon(_config("B", workspace["b"], share, kind="sqlite-local"))
        try:
            daemon_a.queue.submit([{"task_name": "auto", "cli": {"cmd": _cmd("print(1)")}}])
            assert daemon_b.queue.store.count_by_state() == {}
            daemon_b.queue.pull_sync()
            assert daemon_b.queue.store.count_by_state() == {TaskState.PENDING: 1}
        finally:
            daemon_a.close(write_closed=False)
            daemon_b.close(write_closed=False)


class TestWiring:
    def test_build_queue_shared_has_no_syncer(self, workspace):
        queue = build_queue(_config("B", workspace["b"], workspace["share"]))
        try:
            assert queue.syncer is None
            assert queue.heartbeat.enabled is True
            assert queue.describe()["exec"]["allow"][0] == "action:*"
        finally:
            queue.close()

    def test_build_queue_local_has_syncer(self, workspace):
        queue = build_queue(_config("B", workspace["b"], workspace["share"],
                                    kind="sqlite-local"))
        try:
            assert queue.syncer is not None
            assert queue.describe()["sync_mode"] == "sqlite-local"
        finally:
            queue.close()

    def test_send_role_daemon_returns_status_without_waiting(self, workspace):
        daemon = TaskDaemon(_config("A", workspace["a"], workspace["share"]))
        try:
            result = daemon.start(install_signals=False)
            assert result["role"] == "A"
            assert "summary" in result
        finally:
            daemon.close(write_closed=False)

    def test_relay_role_daemon_is_inert(self, workspace):
        daemon = TaskDaemon(_config("C", workspace["a"], workspace["share"]))
        try:
            result = daemon.start(install_signals=False)
            assert result["role"] == "C"
            assert "中转角色" in result["message"]
        finally:
            daemon.close(write_closed=False)

    def test_no_shared_means_no_pump(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        daemon = TaskDaemon(cfg)
        try:
            assert daemon.start_pump() is None
        finally:
            daemon.close(write_closed=False)


class TestConfigRoundTrip:
    def test_two_config_files_shape(self, workspace):
        """两份额配置只差 role：这是"只配方向 + 相关配置"的最小落地面。"""
        share = workspace["share"]
        cfg_a = _config("A", workspace["a"], share)
        cfg_b = _config("B", workspace["b"], share)
        assert cfg_a.role_short() == "A" and cfg_b.role_short() == "B"
        assert cfg_a.worker_id() != cfg_b.worker_id()
        # 同一份介质 → 同一个共享库路径
        assert cfg_a.store_ctx()["shared_root"] == cfg_b.store_ctx()["shared_root"]
        store_a = cfg_a.build_store()
        store_b = cfg_b.build_store()
        try:
            assert store_a.path == store_b.path
        finally:
            store_a.close()
            store_b.close()
        for cfg in (cfg_a, cfg_b):
            dumped = cfg.to_dict(mask=True)
            assert dumped["key"] == "***"
            assert json.dumps(dumped, ensure_ascii=False)