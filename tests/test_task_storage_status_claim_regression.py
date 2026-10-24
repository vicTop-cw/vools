# -*- coding: utf-8 -*-
"""回归测试：legacy TaskStorage 对 TaskStatus 全状态集的认领/提升（BUG-433）。

共享的 ``TaskStatus`` 有 11 个状态，但 legacy ``TaskStorage`` 的 SQL 原先只
处理 6 个：

    claim_task 只看 status = 'PENDING'
    retry_task 只接受 ('FAILED', 'SKIPPED')
    过期租约回收只看 ('RUNNING', 'RETRYING')

而 ``insert_task`` 接受任意 TaskStatus → 直接插入 ``READY`` 的任务会被
``claim_task`` **静默跳过、永远不执行**；``RETRY_PENDING`` 也无法被
``retry_task`` 提升（同样永久卡住）。

修复：
* claim 选择 ``('PENDING', 'READY')``——两者都是"可运行"；
* retry 增加 ``RETRY_PENDING``（提升为 PENDING，与新后端 RETRY_PENDING→READY
  语义一致，且 READY 现在可领取）；
* 过期租约回收增加 ``LOCKED``（LOCKED 也持有租约）。

"""

import sqlite3

import pytest

from vools.task.core.models import Task, TaskStatus
from vools.task.core.storage import TaskStorage


def _work(x):
    return x


def _make_task(name, status):
    return Task(task_name=name, task_func="tests.probe_ready:_work",
                args=[1], kwargs={}, status=status, priority=0)


@pytest.fixture()
def storage(tmp_path):
    st = TaskStorage(db_path=str(tmp_path / "t.db"))
    yield st
    try:
        st.close()
    except Exception:
        pass


class TestReadyClaimable:
    def test_ready_task_is_claimed(self, storage):
        """BUG-433：READY 任务必须能被领取（否则静默不执行）。"""
        tid = storage.insert_task(_make_task("ready", TaskStatus.READY))
        claimed = storage.claim_task("w1", 30)
        assert claimed is not None
        assert claimed.id == tid
        assert storage.get_task(tid).status == TaskStatus.RUNNING

    def test_pending_still_claimable(self, storage):
        tid = storage.insert_task(_make_task("pending", TaskStatus.PENDING))
        assert storage.claim_task("w1", 30).id == tid


class TestRetryPendingContract:
    def test_not_claimable_until_retried(self, storage):
        tid = storage.insert_task(_make_task("rp", TaskStatus.RETRY_PENDING))
        assert storage.claim_task("w1", 30) is None

    def test_retry_promotes_to_pending(self, storage):
        tid = storage.insert_task(_make_task("rp", TaskStatus.RETRY_PENDING))
        assert storage.retry_task(tid) is True
        assert storage.get_task(tid).status == TaskStatus.PENDING
        assert storage.claim_task("w1", 30).id == tid


class TestLockedLeaseReclaim:
    def test_expired_locked_lease_reclaimed(self, storage, tmp_path):
        db = str(tmp_path / "t.db")
        from vools.task.core.queue import TaskQueue

        q = TaskQueue(db_path=db)
        q.submit(_work, 1)
        claimed = q.storage.claim_task("w9", 30)
        assert claimed is not None

        # 用第二个连接把租约改成过期，并置为 LOCKED
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE tasks SET status='LOCKED', lease_timeout='2000-01-01T00:00:00'"
            " WHERE id=?", (claimed.id,))
        conn.commit()
        conn.close()

        again = q.storage.claim_task("w10", 30)
        assert again is not None
        assert again.id == claimed.id
        assert storage.get_task(claimed.id).status == TaskStatus.RUNNING
