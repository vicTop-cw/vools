# -*- coding: utf-8 -*-
"""回归测试：TaskStorage / TaskQueue / WorkerPool 构造参数校验（BUG-430）。

修复前：

    TaskStorage(db_path='')      # sqlite3 接受空串并连到**无名临时库**
    TaskQueue(db_path='')        # 同上（静默，数据不落盘到指定文件）
    WorkerPool(num_workers=0)    # 静默接受，start() 时不启动任何 worker
    WorkerPool(num_workers=-1)   # 同上
    WorkerPool(lease_seconds=-1) # 租约负数，语义不明
    WorkerPool(poll_interval=0)  # 零间隔轮询（忙等）

修复后入口即校验：TaskStorage 的 db_path 为非空 str/PathLike；WorkerPool 的
num_workers/lease_seconds 为正整数、poll_interval 为正数（bool 均排除）；
ThreadPool 等其他类不受影响。
"""

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.core.storage import TaskStorage
from vools.task.core.worker import ThreadPool, WorkerPool


class TestTaskStorageDbPath:
    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    def test_blank(self, bad):
        with pytest.raises(ValueError) as ei:
            TaskStorage(db_path=bad)
        assert "db_path" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None, [], {}])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            TaskStorage(db_path=bad)
        assert "db_path" in str(ei.value)

    def test_valid(self, tmp_path):
        db = str(tmp_path / "q.db")
        assert TaskStorage(db_path=db).db_path == db

    def test_taskqueue_validates_too(self):
        with pytest.raises(ValueError):
            TaskQueue(db_path="")


class TestWorkerPoolOptions:
    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_num_workers_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            WorkerPool(num_workers=bad)
        assert "num_workers" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_num_workers_bad_type(self, bad):
        with pytest.raises(TypeError) as ei:
            WorkerPool(num_workers=bad)
        assert "num_workers" in str(ei.value)

    def test_lease_seconds_non_positive(self):
        with pytest.raises(ValueError):
            WorkerPool(lease_seconds=0)

    def test_lease_seconds_bad_type(self):
        with pytest.raises(TypeError):
            WorkerPool(lease_seconds="x")

    @pytest.mark.parametrize("bad", [0, -0.1, -1])
    def test_poll_interval_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            WorkerPool(poll_interval=bad)
        assert "poll_interval" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", True, None])
    def test_poll_interval_bad_type(self, bad):
        with pytest.raises(TypeError):
            WorkerPool(poll_interval=bad)

    def test_valid(self):
        p = WorkerPool(num_workers=2, db_path="t.db", lease_seconds=30,
                       poll_interval=0.1)
        assert p.num_workers == 2
        assert p.lease_seconds == 30
        assert p.poll_interval == 0.1

    def test_threadpool_untouched(self):
        # BUG-430 补丁必须只作用于 WorkerPool
        assert ThreadPool(num_workers=2).num_workers == 2
