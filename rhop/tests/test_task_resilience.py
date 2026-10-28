# -*- coding: utf-8 -*-
"""常驻健壮性回归（BUG-365 / BUG-366 / BUG-367）。

三条缺陷都属于「异常/边界路径没有门控」：
- BUG-365：执行期间任务被 force 改写（requeue）→ 收尾写终态抛 StoreError；常驻循环无隔离 → 整侧停摆。
- BUG-366：租约过期回收不计入 max_retries → 毒任务无限重跑。
- BUG-367：renew_interval_sec 无校验且被静默 clamp 到 ttl。
"""

import pytest

from vools.rhop.task.config import DEFAULT_QUEUE, TaskConfig
from vools.rhop.task.errors import SecretError, StoreError
from vools.rhop.task.exec import HANDLERS, register_handler
from vools.rhop.task.models import TaskState, iso_add_seconds, utcnow_iso
from vools.rhop.task.queue import TaskQueue


def _config(tmp_path, **queue_over):
    queue = {"store": {"kind": "sqlite-shared"}, "poll_interval_sec": 0.01}
    queue.update(queue_over)
    return TaskConfig.from_dict(
        {"name": "resilience", "role": "B", "key": "res-key",
         "shared": {"write": str(tmp_path)}, "queue": queue,
         "exec": {"allow": ["handler:*", "action:*"]}},
        base_dir=str(tmp_path), warn_plaintext=False)


@pytest.fixture()
def handler_registry():
    """注册/清理测试处理器（exec.HANDLERS 是模块级全局）。"""
    registered = []

    def _register(name, fn):
        register_handler(name, fn)
        registered.append(name)
        return name

    yield _register
    for name in registered:
        HANDLERS.pop(name, None)


class TestFinishOwnershipGate:
    """BUG-365：执行期间被 requeue，收尾必须丢弃结果而不是抛异常。"""

    def test_requeue_during_execution_does_not_raise(self, tmp_path, handler_registry):
        holder = {}

        def requeue_self(payload):
            holder["q"].store.requeue(payload["task_name"])
            return "done"

        hname = handler_registry("probe:requeue-self", requeue_self)
        q = TaskQueue(_config(tmp_path))
        holder["q"] = q
        try:
            q.handlers[hname] = HANDLERS[hname]
            q.submit([{"task_name": "t", "handler": hname}])
            result = q.run_once("w-1")            # 不得抛 StoreError
            assert result["action"] == "discarded"
            rec = q.store.get_task("t")
            # 运维重跑意图保留：仍是 PENDING，等下一轮被领取
            assert rec.state == TaskState.PENDING
            assert "requeue" in (result.get("reason") or "").lower() or result.get("reason")
        finally:
            q.close()

    def test_normal_completion_still_writes_completed(self, tmp_path, handler_registry):
        hname = handler_registry("probe:ok-self", lambda payload: "ok")
        q = TaskQueue(_config(tmp_path))
        try:
            q.handlers[hname] = HANDLERS[hname]
            q.submit([{"task_name": "t", "handler": hname}])
            assert q.run_once("w-1")["action"] == "completed"
            assert q.store.get_task("t").state == TaskState.COMPLETED
        finally:
            q.close()


class TestResidentLoopIsolation:
    """BUG-365 后半：单次迭代异常不得打死常驻循环。"""

    def test_resident_survives_transient_store_error(self, tmp_path):
        q = TaskQueue(_config(tmp_path))
        real = q.store.claim_next
        calls = {"n": 0}

        def flaky(wid, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise StoreError("瞬时数据库错误")
            return real(wid, **kw)

        q.store.claim_next = flaky
        try:
            stats = q.run_resident(max_iterations=4, interval=0.01)
            assert stats["iterations"] >= 3
            assert stats.get("errors", 0) >= 1
        finally:
            q.close()


class TestLeaseReclaimCountsRetry:
    """BUG-366：崩溃回收必须计入重试预算，毒任务最终 FAILED。

    **场景必须是 RUNNING**：worker 领取后立刻把任务置 RUNNING（`queue.run_once`
    里 `claim_next` 与 `set_state(RUNNING)` 是紧邻两行），之后进程被 kill
    （OOM / 段错误 / 死循环）时，行内状态停在 **RUNNING** —— 这才是 BUG-366 的
    实际形态，也是回收要计入重试的那条路径。只 claim 不进 RUNNING 是 LOCKED，
    它表示「领到了但一行用户代码都没跑」，按契约只回 PENDING、不扣重试
    （见 `store/base.py::TaskStore.clean_stale_locks` 与本文件
    `test_locked_reclaim_does_not_charge_retry` 的对照断言）。
    """

    def test_reclaim_increments_retry_count(self, tmp_path):
        q = TaskQueue(_config(tmp_path, lock_ttl_sec=1, max_retries=3))
        try:
            q.submit([{"task_name": "crashy", "handler": "noop"}])
            assert q.store.claim_next("w-1") is not None
            # 模拟「已开始执行、随后进程被 kill」：RUNNING 才是崩溃现场
            q.store.set_state("crashy", TaskState.RUNNING, worker_id="w-1")
            future = iso_add_seconds(utcnow_iso(), 7200)
            assert q.store.clean_stale_locks(now=future) == 1
            rec = q.store.get_task("crashy")
            assert rec.state == TaskState.RETRY_PENDING
            assert rec.retry_count == 1
            assert rec.last_err and "租约" in rec.last_err
        finally:
            q.close()

    def test_reclaim_exhausts_max_retries_to_failed(self, tmp_path):
        q = TaskQueue(_config(tmp_path, lock_ttl_sec=1, max_retries=1))
        try:
            q.submit([{"task_name": "poison", "handler": "noop", "max_retries": 1}])
            future = iso_add_seconds(utcnow_iso(), 7200)
            # 第 1 次：retry_count 0 -> 1，仍 RETRY_PENDING
            assert q.store.claim_next("w-1") is not None
            q.store.set_state("poison", TaskState.RUNNING, worker_id="w-1")
            assert q.store.clean_stale_locks(now=future) == 1
            assert q.store.get_task("poison").state == TaskState.RETRY_PENDING
            # 第 2 次：retry_count 1 -> 2 > max_retries(1) ⇒ FAILED
            assert q.store.claim_next("w-2") is not None
            q.store.set_state("poison", TaskState.RUNNING, worker_id="w-2")
            assert q.store.clean_stale_locks(now=future) == 1
            rec = q.store.get_task("poison")
            assert rec.state == TaskState.FAILED
            assert rec.retry_count == 2
        finally:
            q.close()

    def test_locked_reclaim_does_not_charge_retry(self, tmp_path):
        """对照面（契约锁定）：LOCKED 到期只回 PENDING，不扣重试预算。

        LOCKED 只存在于「领取 → 置 RUNNING」之间的一瞬，到期说明 worker 在开始
        执行前就没了，用户代码一行未跑 —— 这种情况不该烧任务的重试预算，否则
        一次基础设施抖动就会把一个本来正常的任务推向 FAILED。
        """
        q = TaskQueue(_config(tmp_path, lock_ttl_sec=1, max_retries=1))
        try:
            q.submit([{"task_name": "claimed-only", "handler": "noop"}])
            assert q.store.claim_next("w-1") is not None      # → LOCKED，不进 RUNNING
            assert q.store.clean_stale_locks(
                now=iso_add_seconds(utcnow_iso(), 7200)) == 1
            rec = q.store.get_task("claimed-only")
            assert rec.state == TaskState.PENDING
            assert rec.retry_count == 0
            assert rec.last_err is None
        finally:
            q.close()


class TestRenewIntervalValidation:
    """BUG-367：续期间隔必须受管、受校验，不再静默 clamp。"""

    def test_renew_interval_is_managed_key(self):
        assert "renew_lock" in DEFAULT_QUEUE
        assert "renew_interval_sec" in DEFAULT_QUEUE
        assert DEFAULT_QUEUE["renew_lock"] is False
        assert float(DEFAULT_QUEUE["renew_interval_sec"]) == 0.0   # 0 = 自动 = ttl/2

    def test_renew_interval_too_large_is_rejected(self, tmp_path):
        with pytest.raises(SecretError) as excinfo:
            _config(tmp_path, renew_lock=True, renew_interval_sec=100000,
                    lock_ttl_sec=60)
        msg = str(excinfo.value)
        assert "renew_interval_sec" in msg and "lock_ttl_sec" in msg

    def test_renew_interval_at_half_ttl_is_accepted(self, tmp_path):
        cfg = _config(tmp_path, renew_lock=True, renew_interval_sec=30,
                      lock_ttl_sec=60)
        assert float(cfg.queue["renew_interval_sec"]) == 30.0

    def test_negative_renew_interval_is_rejected(self, tmp_path):
        with pytest.raises(SecretError):
            _config(tmp_path, renew_lock=True, renew_interval_sec=-1,
                    lock_ttl_sec=60)
