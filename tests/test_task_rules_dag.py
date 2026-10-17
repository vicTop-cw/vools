# -*- coding: utf-8 -*-
"""测试 vools.task.rules.dag — DagScheduler。

使用 MagicMock 模拟 TaskQueue / storage，聚焦调度器自身的状态机与错误传播逻辑。
"""

from unittest.mock import MagicMock, patch

import pytest

from vools.functional import Result

__all__ = ["TestDagSchedulerInit", "TestDagSchedulerLifecycle", "TestDagSchedulerDispatch",
           "TestDagSchedulerFailure", "TestDagSchedulerContext"]


def _make_scheduler(**kwargs):
    """构建 DagScheduler + mock queue/storage。"""
    from vools.task.rules.dag import DagScheduler
    queue = MagicMock()
    storage = MagicMock()
    queue.storage = storage
    kwargs.setdefault("poll_interval", 0.01)
    return DagScheduler(queue=queue, **kwargs), queue, storage


class TestDagSchedulerInit:
    """构造器行为测试。"""

    def test_defaults(self):
        s, _, _ = _make_scheduler()
        assert s._running is False
        assert s._thread is None
        assert s._executor is None
        assert s._pending == set()
        assert s._completed == set()
        assert s._failed == set()
        assert s._skipped == set()

    def test_custom_params(self):
        from vools.task.rules.dag import DagScheduler
        queue = MagicMock()
        s = DagScheduler(queue=queue, mode="process", max_workers=2,
                         poll_interval=0.1, propagate_failure=False)
        assert s._mode == "process"
        assert s._max_workers == 2
        assert s._poll_interval == 0.1
        assert s._propagate_failure is False

    def test_status_empty(self):
        s, _, _ = _make_scheduler()
        st = s.status
        assert st["running"] is False
        assert st["pending"] == 0
        assert st["completed"] == 0
        assert st["failed"] == 0
        assert st["skipped"] == 0

    def test_register_task(self):
        s, _, _ = _make_scheduler()
        s.register_task(1)
        assert 1 in s._pending
        assert s.status["pending"] == 1

    def test_register_tasks(self):
        s, _, _ = _make_scheduler()
        s.register_tasks(1, 2, 3)
        assert s._pending == {1, 2, 3}

    def test_register_duplicate(self):
        s, _, _ = _make_scheduler()
        s.register_task(1)
        s.register_task(1)
        assert s._pending == {1}

    def test_import_all(self):
        from vools.task.rules.dag import __all__
        assert "DagScheduler" in __all__


class TestDagSchedulerLifecycle:
    """启动/停止行为测试。"""

    def test_start_twice(self):
        s, _, _ = _make_scheduler()
        s.start()
        # 第二次 start 应告警不重启
        s.start()
        assert s._running is True

    def test_start_stop(self):
        s, _, _ = _make_scheduler()
        s.start()
        assert s._running is True
        assert s._executor is not None
        assert s._thread is not None
        s.stop()
        assert s._running is False
        assert s._thread is None or not s._thread.is_alive()

    def test_stop_not_started(self):
        s, _, _ = _make_scheduler()
        # 未启动时 stop 应安全无异常
        s.stop()
        assert s._running is False

    def test_create_executor_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        s, _, _ = _make_scheduler()
        exec = s._create_executor()
        assert isinstance(exec, ThreadPoolExecutor)
        exec.shutdown()

    def test_create_executor_process(self):
        from concurrent.futures import ProcessPoolExecutor
        s, _, _ = _make_scheduler(mode="process")
        exec = s._create_executor()
        assert isinstance(exec, ProcessPoolExecutor)
        exec.shutdown()

    def test_await_completion_success(self):
        s, _, _ = _make_scheduler()
        # 无 pending 时立即成功
        result = s.await_completion(timeout=0.1)
        assert result.is_success
        assert result.unwrap() == {"completed": 0, "failed": 0, "skipped": 0}

    def test_await_completion_timeout(self):
        s, _, _ = _make_scheduler()
        s.register_task(999)  # 永不完成
        result = s.await_completion(timeout=0.1)
        assert result.is_failure
        assert isinstance(result.unwrap_or(None), TimeoutError) is False  # unwrap_or returns None

    def test_collect_finished_noop(self):
        s, _, _ = _make_scheduler()
        # 纯 no-op，不应抛异常
        s._collect_finished()


class TestDagSchedulerDispatch:
    """任务分派行为测试。"""

    def test_dispatch_success(self):
        s, queue, storage = _make_scheduler()
        task = MagicMock()
        task.id = 1
        storage.get_ready_tasks.return_value = [task]
        queue.execute_task.return_value = "done"

        # mock executor
        future = MagicMock()
        future.result.return_value = Result.success("done")
        s._executor = MagicMock()
        s._executor.submit.return_value = future

        s._dispatch_task(task)
        # 成功 → 状态更新 SUCCESS
        storage.update_task_status.assert_called()
        # 应该已从 pending 移除
        assert task.id in s._completed

    def test_dispatch_failure(self):
        s, queue, storage = _make_scheduler()
        task = MagicMock()
        task.id = 1
        future = MagicMock()
        future.result.side_effect = ValueError("boom")
        s._executor = MagicMock()
        s._executor.submit.return_value = future

        s._dispatch_task(task)
        assert task.id in s._failed

    def test_tick_ready(self):
        s, queue, storage = _make_scheduler()
        s.register_task(1)
        task = MagicMock()
        task.id = 1
        storage.get_ready_tasks.return_value = [task]
        future = MagicMock()
        future.result.return_value = Result.success("ok")
        s._executor = MagicMock()
        s._executor.submit.return_value = future

        s._tick()
        assert 1 in s._completed

    def test_tick_no_ready(self):
        s, queue, storage = _make_scheduler()
        s.register_task(1)
        storage.get_ready_tasks.return_value = []
        s._executor = MagicMock()
        s._tick()
        assert 1 in s._pending  # 仍在 pending

    def test_schedule_loop_stops(self):
        s, _, _ = _make_scheduler()
        s._running = False
        # 应立即退出
        s._schedule_loop()
        assert s._running is False


class TestDagSchedulerFailure:
    """失败传播行为测试。"""

    def test_on_task_complete_success(self):
        s, _, storage = _make_scheduler()
        s.register_task(1)
        s._on_task_complete(1, Result.success("ok"))
        assert 1 in s._completed
        assert 1 not in s._pending

    def test_on_task_complete_failure(self):
        s, _, storage = _make_scheduler()
        s.register_task(1)
        s._on_task_complete(1, Result.failure(ValueError("boom")))
        assert 1 in s._failed
        assert 1 not in s._pending

    def test_skip_downstream(self):
        s, _, storage = _make_scheduler()
        s.register_task(1)
        s.register_task(2)
        s.register_task(3)
        # 2 和 3 依赖 1
        storage.get_dependents.return_value = [2, 3]
        s._skip_downstream(1)
        assert 2 in s._skipped
        assert 3 in s._skipped
        assert 2 not in s._pending
        assert 3 not in s._pending

    def test_skip_downstream_recursive(self):
        s, _, storage = _make_scheduler()
        s.register_task(1)
        s.register_task(2)
        s.register_task(3)
        # 1 → 2 → 3（递归）
        storage.get_dependents.side_effect = lambda tid: [2] if tid == 1 else ([3] if tid == 2 else [])
        s._skip_downstream(1)
        assert 2 in s._skipped
        assert 3 in s._skipped

    def test_no_propagate(self):
        s, _, storage = _make_scheduler(propagate_failure=False)
        s.register_task(1)
        s.register_task(2)
        storage.get_dependents.return_value = [2]
        s._on_task_complete(1, Result.failure(ValueError("boom")))
        assert 1 in s._failed
        # 不传播 → 2 仍在 pending
        assert 2 in s._pending


class TestDagSchedulerContext:
    """上下文管理器行为测试。"""

    def test_enter_exit(self):
        s, _, _ = _make_scheduler()
        with s as ctx:
            assert ctx is s
            assert s._running is True
        assert s._running is False

    def test_do_chain(self):
        s, _, _ = _make_scheduler()
        seen = []
        r2 = s.do(pre_f=lambda x: (seen.append("pre"), x)[1],
                  f=lambda x: (seen.append("f"), x)[1],
                  sub_f=lambda x: seen.append("sub"))
        assert r2 is s
        assert seen == ["pre", "f", "sub"]
