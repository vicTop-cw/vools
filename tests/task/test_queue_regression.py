"""tests/task/test_queue_regression.py — TaskQueue 函数序列化回归测试"""
import pickle
import base64
import tempfile
import os
import time
import pytest

from vools.task import TaskQueue, WorkerPool, TaskStatus


class TestTaskQueueSerialize:
    """BUG-C 回归测试：lambda/__main__ 函数在 spawn 子进程中应可反序列化"""

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

    def test_lambda_serialize_format(self):
        """lambda 不可 pickle 时回退到 __registry__ 格式（同进程可用）"""
        q = TaskQueue(self.db_path)
        fn = lambda x: x + 1
        func_data = q._serialize_func(fn)
        # lambda 不可 pickle，回退到 __registry__
        assert func_data.startswith('__registry__:')

    def test_main_module_function_serialize(self):
        """__main__ 函数不可 pickle 时回退到 __registry__ 格式"""
        q = TaskQueue(self.db_path)

        def local_func(x):
            return x + 10

        local_func.__module__ = '__main__'
        func_data = q._serialize_func(local_func)
        # 局部函数不可 pickle，回退到 __registry__
        assert func_data.startswith('__registry__:')

    def test_pickleable_function_uses_pickle_format(self):
        """可 pickle 的函数应使用 __pickle__ 格式（跨进程安全）"""
        import math
        q = TaskQueue(self.db_path)
        # math.factorial 是 C 内置函数，序列化为路径格式
        func_data = q._serialize_func(math.factorial)
        assert ':' in func_data


class TestWorkerPoolCrossProcess:
    """BUG-C 回归测试：WorkerPool 在 spawn 模式下应能执行任务"""

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

    def test_spawn_worker_executes_module_func(self):
        """验证模块级可 pickle 函数序列化为 __pickle__ 格式（spawn 子进程可恢复）"""
        import operator
        q = TaskQueue(self.db_path)
        # operator.mul 是 C 内置函数，序列化为模块路径
        func_data = q._serialize_func(operator.mul)
        # 模块路径格式（跨进程安全，importlib 可恢复）
        assert ':' in func_data
        restored = q._deserialize_func(func_data)
        assert restored(3, 7) == 21
        # 提交并验证
        tid = q.submit(operator.mul, 3, 7)
        task = q.get_task(tid)
        assert task is not None
        assert task.status == TaskStatus.PENDING

    def test_thread_worker_executes_main_func(self):
        """线程模式 Worker（ThreadPool）应能执行 __main__ 函数"""
        from vools.task.core.worker import ThreadPool

        def double(x):
            return x * 2
        double.__module__ = '__main__'
        q = TaskQueue(self.db_path)
        tid = q.submit(double, 5)
        # 使用 ThreadPool（线程共享 _func_registry 和 __pickle__ 反序列化）
        pool = ThreadPool(num_workers=1, db_path=self.db_path, poll_interval=0.05)
        pool.start()
        time.sleep(2)
        task = q.get_task(tid)
        assert task is not None
        # 线程模式下应成功
        pool.stop()
