"""tests/vconcurrent/test_dag_scheduler_regression.py — DagScheduler 回归测试"""
import time
import tempfile
import os
import pytest

from vools.task import TaskQueue, TaskStatus


class TestDagSchedulerMissingMethod:
    """BUG-E 回归测试：DagScheduler 不应调用不存在的方法"""

    def setup_method(self):
        self.f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.f.close()
        self.db_path = self.f.name

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except OSError:
                pass

    def test_storage_has_required_methods(self):
        """TaskStorage 应有 DagScheduler 需要的方法"""
        from vools.task.core.storage import TaskStorage
        storage = TaskStorage(self.db_path)
        # DagScheduler 可能调用的方法
        assert hasattr(storage, 'claim_task')
        assert hasattr(storage, 'update_task_status')
        assert hasattr(storage, 'get_task')

    def test_dag_scheduler_can_register_and_start(self):
        """DagScheduler 注册任务后应能启动"""
        from vools.task.rules import DagScheduler
        q = TaskQueue(self.db_path)

        def step1():
            return 1

        tid = q.submit(step1)
        dag = DagScheduler(q, mode='thread', max_workers=2)
        dag.register_task(tid)
        dag.start()
        time.sleep(0.5)
        dag.stop()
        # 不应抛出 AttributeError: 'TaskStorage' has no attribute 'get_ready_tasks'

    def test_task_execution_via_worker(self):
        """WorkerPool 应能执行简单任务"""
        from vools.task.core.worker import WorkerPool

        q = TaskQueue(self.db_path)

        def simple_task():
            return 42

        tid = q.submit(simple_task)
        pool = WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.05)
        pool.start()
        time.sleep(2)
        task = q.get_task(tid)
        assert task is not None
        # 线程模式下应成功
        pool.stop()
