# -*- coding: utf-8 -*-
"""回归测试：TaskStorage 的 cancel / retry 契约（audit 锁定）。

本轮审计确认的既有契约（含 BUG-383 / BUG-384 的修复语义）：

* ``cancel_task`` 可取消 ``PENDING`` / ``RUNNING`` / ``RETRYING``，重复取消
  或任务不存在返回 False；
* 取消后 **worker 的完成写入不得把 CANCEL 覆盖回 SUCCESS**（BUG-383）；
* 取消会向下游级联 ``SKIPPED``（BUG-384）；
* ``retry_task`` 只接受 ``FAILED`` / ``SKIPPED``（后者用于上游修复后复活
  下游），其余状态与不存在的任务返回 False。

这里把这些语义固化，防止后续重构改变取消/重试行为。
"""

import pytest

from vools.task.core.models import TaskStatus
from vools.task.core.queue import TaskQueue


def _fn(x):
    return x


@pytest.fixture()
def queue(tmp_path):
    q = TaskQueue(db_path=str(tmp_path / "q.db"))
    yield q
    try:
        q.storage.close()
    except Exception:
        pass


def _claim(queue, worker="w1"):
    claimed = queue.storage.claim_task(worker, 30)
    assert claimed is not None
    return claimed


class TestCancelContract:
    def test_cancel_pending(self, queue):
        tid = queue.submit(_fn, 1)
        assert queue.cancel_task(tid) is True
        assert queue.get_task(tid).status == TaskStatus.CANCEL

    def test_cancel_twice_returns_false(self, queue):
        tid = queue.submit(_fn, 1)
        assert queue.cancel_task(tid) is True
        assert queue.cancel_task(tid) is False

    def test_cancel_running(self, queue):
        tid = queue.submit(_fn, 1)
        _claim(queue)
        assert queue.cancel_task(tid) is True
        assert queue.get_task(tid).status == TaskStatus.CANCEL

    def test_cancel_unknown_returns_false(self, queue):
        assert queue.cancel_task(999999) is False

    def test_cancelled_task_not_overwritten_by_worker_completion(self, queue):
        """BUG-383：worker 完成写入不得覆盖 CANCEL。"""
        tid = queue.submit(_fn, 1)
        _claim(queue)
        assert queue.cancel_task(tid) is True
        # 模拟 worker 稍后回写 SUCCESS
        queue.storage.update_task_status(tid, TaskStatus.SUCCESS, worker_id="w1")
        assert queue.get_task(tid).status == TaskStatus.CANCEL

    def test_cancel_cascades_skipped(self, queue):
        """BUG-384：取消会级联下游 SKIPPED。"""
        parent = queue.submit(_fn, 1)
        child = queue.submit(_fn, 1, depends_on=[parent])
        assert queue.cancel_task(parent) is True
        assert queue.get_task(child).status == TaskStatus.SKIPPED


class TestRetryContract:
    def test_retry_unknown_returns_false(self, queue):
        assert queue.retry_task(999999) is False

    def test_retry_pending_returns_false(self, queue):
        tid = queue.submit(_fn, 1)
        assert queue.retry_task(tid) is False

    def test_retry_running_returns_false(self, queue):
        tid = queue.submit(_fn, 1)
        _claim(queue)
        assert queue.retry_task(tid) is False

    def test_retry_failed(self, queue):
        tid = queue.submit(_fn, 1)
        _claim(queue)
        queue.storage.update_task_status(tid, TaskStatus.FAILED, worker_id="w1")
        assert queue.retry_task(tid) is True
        assert queue.get_task(tid).status == TaskStatus.PENDING

    def test_retry_skipped(self, queue):
        parent = queue.submit(_fn, 1)
        child = queue.submit(_fn, 1, depends_on=[parent])
        queue.cancel_task(parent)
        assert queue.get_task(child).status == TaskStatus.SKIPPED
        assert queue.retry_task(child) is True
        assert queue.get_task(child).status == TaskStatus.PENDING
