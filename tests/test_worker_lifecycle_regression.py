# -*- coding: utf-8 -*-
"""回归测试：Worker 运行时生命周期（BUG-432 之后的契约锁定）。

审计结论（本轮实测）：

* ``Worker.start()`` 是阻塞循环，``claim_task`` **非阻塞**（无任务立即返回
  None），因此 ``stop()`` 能在 ``poll_interval`` 内终止循环；
* 成功任务 -> ``SUCCESS`` 且结果回写；
* 失败任务 -> 按 ``max_retries`` 重试，耗尽后 ``FAILED`` 并记录错误；
* 停止后可重新启动。

这里把这些行为固化，防止后续重构（例如让 ``claim_task`` 阻塞等待任务）
悄悄改变生命周期语义。
"""

import threading
import time

import pytest

from vools.task.core.models import TaskStatus
from vools.task.core.queue import TaskQueue
from vools.task.core.worker import Worker


def double(x):
    return x * 2


def always_fail():
    raise RuntimeError("boom")


class WorkerHarness:
    """在线程中运行 Worker，便于断言 stop 的响应性。"""

    def __init__(self, db_path, worker_id="w1", **kwargs):
        self.queue = TaskQueue(db_path=db_path)
        self.worker = Worker(worker_id, db_path=db_path, **kwargs)
        self.thread = None

    def start_thread(self):
        self.thread = threading.Thread(target=self.worker.start, daemon=True)
        self.thread.start()
        return self.thread

    def stop(self):
        self.worker.stop()
        if self.thread is not None:
            self.thread.join(timeout=5)

    def wait_status(self, task_id, statuses, timeout=10):
        deadline = time.time() + timeout
        task = None
        while time.time() < deadline:
            task = self.queue.storage.get_task(task_id)
            if task is not None and task.status in statuses:
                return task
            time.sleep(0.05)
        return task


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "w.db")


def test_success_path(db):
    h = WorkerHarness(db, poll_interval=0.05)
    h.start_thread()
    try:
        tid = h.queue.submit(double, 5)
        task = h.wait_status(tid, (TaskStatus.SUCCESS, TaskStatus.FAILED))
        assert task.status == TaskStatus.SUCCESS
        assert task.result == 10
    finally:
        h.stop()


def test_failure_retries_then_failed(db):
    h = WorkerHarness(db, poll_interval=0.05)
    h.start_thread()
    try:
        tid = h.queue.submit(always_fail, max_retries=2)
        task = h.wait_status(tid, (TaskStatus.FAILED,))
        assert task.status == TaskStatus.FAILED
        assert task.retry_count == 2
        assert "boom" in (task.error_message or "")
    finally:
        h.stop()


def test_stop_is_prompt(db):
    h = WorkerHarness(db, poll_interval=0.05)
    h.start_thread()
    time.sleep(0.3)
    start = time.time()
    h.worker.stop()
    h.thread.join(timeout=5)
    assert h.thread.is_alive() is False
    # stop 后线程应在 poll_interval 的若干倍内退出（宽松上界）
    assert time.time() - start < 2.0


def test_restart_after_stop(db):
    h = WorkerHarness(db, poll_interval=0.05)
    h.start_thread()
    time.sleep(0.2)
    h.stop()
    assert h.thread.is_alive() is False

    # 重新启动应正常工作
    h.start_thread()
    time.sleep(0.2)
    assert h.thread.is_alive() is True
    try:
        tid = h.queue.submit(double, 3)
        task = h.wait_status(tid, (TaskStatus.SUCCESS, TaskStatus.FAILED))
        assert task.status == TaskStatus.SUCCESS
    finally:
        h.stop()
