# -*- coding: utf-8 -*-
"""回归测试：取消进行中任务后，完成回写不得撤销取消（BUG-383）。

`TaskStorage.update_task_status` 只按 `worker_id` 过滤，因此对一个
**已取消（CANCEL）** 的进行中任务，worker 的完成回写会把状态覆盖回去：

    st.claim_task('w1')                          # -> RUNNING
    q.cancel_task(tid)                           # -> CANCEL
    st.update_task_status(tid, SUCCESS, ...)     # -> 之前返回 True，状态变 SUCCESS

即「取消被静默撤销、结果仍被落库」。修复：SUCCESS / FAILED / RETRYING 终态
回写一律附加 `AND status != 'CANCEL'`，取消优先；回写返回 False（调用方可据此
丢弃结果）。

不受影响：正常任务的回写、`retry_task` 复活 FAILED、`cancel_task` 幂等性、
worker 端到端成功路径。
"""

import pytest

from vools.task.core.models import TaskStatus
from vools.task.core.queue import TaskQueue
from vools.task.core.storage import TaskStorage


@pytest.fixture()
def env(tmp_path):
    db = str(tmp_path / 'tasks.db')
    return TaskQueue(db), TaskStorage(db), db


class TestCancelWins:
    def test_success_write_rejected_after_cancel(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'x')
        st.claim_task('w1', lease_seconds=30)
        assert q.get_task(tid).status.value == 'RUNNING'
        assert q.cancel_task(tid) is True
        assert q.get_task(tid).status.value == 'CANCEL'
        # 修复前：返回 True 且状态被改回 SUCCESS
        assert st.update_task_status(tid, TaskStatus.SUCCESS,
                                     result='done', worker_id='w1') is False
        assert q.get_task(tid).status.value == 'CANCEL'

    def test_failed_write_rejected_after_cancel(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'x')
        st.claim_task('w1', 30)
        q.cancel_task(tid)
        assert st.update_task_status(tid, TaskStatus.FAILED,
                                     error_message='boom', worker_id='w1') is False
        assert q.get_task(tid).status.value == 'CANCEL'

    def test_retrying_write_rejected_after_cancel(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'x')
        st.claim_task('w1', 30)
        q.cancel_task(tid)
        assert st.update_task_status(tid, TaskStatus.RETRYING, worker_id='w1') is False
        assert q.get_task(tid).status.value == 'CANCEL'

    def test_worker_skips_cancelled_task(self, env):
        from vools.task.core.worker import Worker

        q, st, db = env
        tid = q.submit(lambda: 'x')
        st.claim_task('w1', 30)
        q.cancel_task(tid)
        Worker('w1', db, lease_seconds=30)._process_one_task()
        assert q.get_task(tid).status.value == 'CANCEL'


class TestNormalWritesUnaffected:
    def test_success(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'y')
        st.claim_task('w1', 30)
        assert st.update_task_status(tid, TaskStatus.SUCCESS,
                                     result='ok', worker_id='w1') is True
        assert q.get_task(tid).status.value == 'SUCCESS'

    def test_retrying_increments_count(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'z')
        st.claim_task('w1', 30)
        assert st.update_task_status(tid, TaskStatus.RETRYING, worker_id='w1') is True
        assert q.get_task(tid).retry_count == 1

    def test_retry_task_revives_failed(self, env):
        q, st, _ = env
        tid = q.submit(lambda: 'w')
        st.claim_task('w1', 30)
        st.update_task_status(tid, TaskStatus.FAILED, error_message='e', worker_id='w1')
        assert q.get_task(tid).status.value == 'FAILED'
        assert q.retry_task(tid) is True
        assert q.get_task(tid).status.value == 'PENDING'

    def test_worker_end_to_end(self, env):
        from vools.task.core.worker import Worker

        q, _, db = env
        tid = q.submit(lambda: 'ok')
        Worker('w1', db, lease_seconds=30)._process_one_task()
        assert q.get_result(tid, timeout=5) == 'ok'
        assert q.get_task(tid).status.value == 'SUCCESS'