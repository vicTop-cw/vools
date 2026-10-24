"""
任务模块完整测试套件
覆盖：任务队列、优先级、并行执行、执行模式、装饰器、生命周期等
"""

import sys
import os
import time
import tempfile
import threading
import pytest

from vools.task import (
    TaskQueue, WorkerPool, ThreadPool, TaskStatus, Task,
    task, batch_execute
)


# ============================================================================
# 模块级别函数（用于任务队列测试，必须在模块级别定义）
# ============================================================================

def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


def slow_function(delay=0.1):
    time.sleep(delay)
    return "completed"


def record_interval(start_path, end_path, delay=0.1):
    """记录任务执行的起止时刻到两个文件（用于并行性判定）。

    每个任务写**自己的**文件，避免多进程写同一文件时的交错问题。
    """
    with open(start_path, 'w') as f:
        f.write(repr(time.time()))
    time.sleep(delay)
    with open(end_path, 'w') as f:
        f.write(repr(time.time()))
    return "completed"


def failing_function(should_fail=True):
    if should_fail:
        raise ValueError("Intentional failure")
    return "success"


def identity(x):
    return x


def process_large_data(data):
    """处理大数据的函数"""
    return len(data)


# ============================================================================
# 测试类
# ============================================================================

class TestTaskQueueBasic:
    """任务队列基础功能测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_task_submit_and_execute(self):
        """测试任务提交和执行"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(add, 2, 3)
        
        assert task_id is not None
        status = queue.get_task_status(task_id)
        assert status == TaskStatus.PENDING

    def test_task_status_flow(self):
        """测试任务状态流转"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(add, 1, 1)
        
        assert queue.get_task_status(task_id) == TaskStatus.PENDING
        queue.cancel_task(task_id)
        assert queue.get_task_status(task_id) == TaskStatus.CANCEL

    def test_task_result_retrieval(self):
        """测试任务结果获取"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(add, 10, 20)
        
        with WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.1) as pool:
            result = queue.get_result(task_id, timeout=30)
            assert result == 30

    def test_multiple_tasks(self):
        """测试多个任务并发执行"""
        queue = TaskQueue(self.db_path)
        
        task_ids = []
        for i in range(10):
            task_ids.append(queue.submit(add, i, i))
        
        with WorkerPool(num_workers=3, db_path=self.db_path, poll_interval=0.1) as pool:
            results = [queue.get_result(tid, timeout=30) for tid in task_ids]
            assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]


class TestTaskPriority:
    """任务优先级机制测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_default_priority(self):
        """测试默认优先级"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(add, 1, 1)
        task = queue.get_task(task_id)
        assert task.priority == 0

    def test_priority_boundaries(self):
        """测试优先级边界值"""
        queue = TaskQueue(self.db_path)
        
        task_id1 = queue.submit(add, 1, 1, priority=-100)
        task_id2 = queue.submit(add, 2, 2, priority=0)
        task_id3 = queue.submit(add, 3, 3, priority=100)
        
        with WorkerPool(num_workers=3, db_path=self.db_path, poll_interval=0.1) as pool:
            result1 = queue.get_result(task_id1, timeout=30)
            result2 = queue.get_result(task_id2, timeout=30)
            result3 = queue.get_result(task_id3, timeout=30)
            
            assert result1 == 2
            assert result2 == 4
            assert result3 == 6


class TestTaskParallelExecution:
    """并行执行性能测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_worker_pool_size(self):
        """测试多 worker 真的并行执行（确定性判据，不依赖墙钟比值）

        BUG-4：本用例原来断言「4 workers 耗时 < 1 worker 耗时 × 0.75」。这是**墙钟
        比值**判据，在负载波动的机器上必然抖动：8 个 0.2s 任务只有 1.6s 真实工作量，
        而 WorkerPool 的启动/轮询固定开销就有 ~0.8s，加速比只剩 1.3~1.5 倍，稍一波动
        就跌破阈值；作者用 @pytest.mark.flaky(reruns=2) 兜底，但那个标记是**空标记**
        （pytest-rerunfailures 未安装/未声明/未注册），于是表现为套件随机红绿。

        现改为**确定性**判据：让每个任务把自己的起止时刻写到独立文件，然后直接检验
        「同一时刻是否有多个任务在运行」。只要有任意一对任务的执行区间**重叠**，
        就证明并行真实发生——这个判据与机器负载无关（负载只会让区间更长、更容易重叠），
        不会因为一次调度抖动翻红。
        """
        num_tasks = 8
        delay = 0.4

        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        f.close()
        db_path = f.name
        workdir = tempfile.mkdtemp(prefix='vools_parallel_')
        try:
            q = TaskQueue(db_path)
            tids = []
            for i in range(num_tasks):
                sp = os.path.join(workdir, 'start_%d' % i)
                ep = os.path.join(workdir, 'end_%d' % i)
                tids.append(q.submit(record_interval, sp, ep, delay))

            with WorkerPool(num_workers=4, db_path=db_path, poll_interval=0.01):
                for tid in tids:
                    q.get_result(tid, timeout=60)

            intervals = []
            for i in range(num_tasks):
                sp = os.path.join(workdir, 'start_%d' % i)
                ep = os.path.join(workdir, 'end_%d' % i)
                assert os.path.exists(sp) and os.path.exists(ep), "任务 %d 未落起止时刻" % i
                with open(sp) as fh:
                    s = float(fh.read())
                with open(ep) as fh:
                    e = float(fh.read())
                intervals.append((s, e, i))

            # 并行性判据：存在一对任务的执行区间重叠
            intervals.sort()
            max_end = intervals[0][1]
            max_end_task = intervals[0][2]
            overlap = None
            for s, e, i in intervals[1:]:
                if s < max_end:            # 后一个任务在前一个还没结束时就开始
                    overlap = (max_end_task, i, max_end - s)
                    break
                if e > max_end:
                    max_end, max_end_task = e, i

            assert overlap is not None, (
                "4 workers 未观测到任何并发重叠——任务被串行执行了。"
                "各任务区间(起,止,序号)=%s" % [(round(s, 3), round(e, 3), i) for s, e, i in intervals]
            )
        finally:
            for ext in ['', '-wal', '-shm']:
                try:
                    os.unlink(db_path + ext)
                except Exception:
                    pass
            try:
                import shutil
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass


class TestTaskDecorators:
    """装饰器功能测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_batch_execute_decorator_args(self):
        """测试batch_execute装饰器参数模式"""
        @batch_execute(task_args=[(1,), (2,), (3,)])
        def double(x):
            return x * 2
        
        result = double()
        assert result == [2, 4, 6]

    def test_batch_execute_call_args(self):
        """测试batch_execute调用时参数模式"""
        @batch_execute
        def double(x):
            return x * 2
        
        result = double(task_args=[(1,), (2,), (3,)])
        assert result == [2, 4, 6]

    def test_batch_execute_kwargs(self):
        """测试batch_execute关键字参数"""
        @batch_execute(task_kwargs=[{'a': 1}, {'a': 2}, {'a': 3}])
        def square(a):
            return a ** 2
        
        result = square()
        assert result == [1, 4, 9]

    def test_batch_execute_simple_parallel(self):
        """测试batch_execute多进程模式（简化版）"""
        @batch_execute(task_args=[(1,), (2,), (3,)], worker_nums=2)
        def simple_double(x):
            time.sleep(0.05)
            return x * 2
        
        result = simple_double()
        assert result == [2, 4, 6]


class TestTaskLifecycle:
    """任务生命周期测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_task_completion(self):
        """测试任务正常完成"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(add, 5, 5)
        
        with WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.1) as pool:
            result = queue.get_result(task_id, timeout=30)
        
        assert result == 10
        task = queue.get_task(task_id)
        assert task.status == TaskStatus.SUCCESS
        assert task.result is not None

    def test_task_failure(self):
        """测试任务失败处理"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(failing_function, max_retries=1)
        
        with WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.1) as pool:
            with pytest.raises(Exception):
                queue.get_result(task_id, timeout=30)
        
        task = queue.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert task.retry_count == 1

    def test_task_cancellation(self):
        """测试任务取消"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(slow_function, 1.0)
        
        queue.cancel_task(task_id)
        
        task = queue.get_task(task_id)
        assert task.status == TaskStatus.CANCEL

    def test_task_timeout(self):
        """测试任务超时"""
        queue = TaskQueue(self.db_path)
        task_id = queue.submit(slow_function, 2.0)
        
        with WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.1) as pool:
            with pytest.raises(TimeoutError):
                queue.get_result(task_id, timeout=0.5)


class TestEdgeCases:
    """边界条件测试"""

    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

    def teardown_method(self):
        for ext in ['', '-wal', '-shm']:
            try:
                os.unlink(self.db_path + ext)
            except:
                pass

    def test_empty_queue(self):
        """测试空队列操作"""
        queue = TaskQueue(self.db_path)
        
        task = queue.get_task(999)
        assert task is None
        
        with pytest.raises(ValueError):
            queue.get_result(999, timeout=1)

    def test_large_payload(self):
        """测试大负载任务"""
        queue = TaskQueue(self.db_path)
        large_data = "x" * 100000
        
        task_id = queue.submit(process_large_data, large_data)
        
        with WorkerPool(num_workers=1, db_path=self.db_path, poll_interval=0.1) as pool:
            result = queue.get_result(task_id, timeout=30)
            assert result == 100000

    def test_concurrent_submissions(self):
        """测试并发提交任务"""
        queue = TaskQueue(self.db_path)
        task_ids = []
        
        def submit_tasks():
            for i in range(10):
                task_ids.append(queue.submit(add, i, i))
        
        threads = []
        for _ in range(5):
            t = threading.Thread(target=submit_tasks)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(task_ids) == 50
        
        # 50 个任务串行等待，每个独立 timeout 窗口。WorkerPool 启动（10 线程 +
        # SQLite 初始化）与 claim 竞争会吃掉部分窗口，5s 在慢机器上偶发不足
        # （实测单轮 50 任务约 1.7-2.1s，但启动抖动可叠加），放宽到 20s。
        with WorkerPool(num_workers=10, db_path=self.db_path, poll_interval=0.1) as pool:
            results = [queue.get_result(tid, timeout=20) for tid in task_ids]
            assert len(results) == 50


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
