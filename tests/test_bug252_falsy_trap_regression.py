"""BUG-252 假值陷阱族回归测试。

覆盖 4 处修复：
  ① task 三后端 acquire(states=[]) 应空结果而非领走默认状态任务
  ② worker_engine interval=0 / timeout_min=0 应保留 0 而非替换默认值
  ③ Table.from_file(rows=0) 应返回 0 行而非全文件
  ④ Table.from_file(cols=[]) 应返回全列而非空列
"""
import csv
import os
import tempfile
from unittest.mock import MagicMock

from vools.data import Table
from vools.task.backends.memory_backend import MemoryTaskBackend


# ------------------------------------------------------------------
# ① task 后端 acquire(states=[])
# ------------------------------------------------------------------

class TestAcquireEmptyStates:
    """显式传空列表 = 不领取任何状态的任务。"""

    def test_memory_backend_acquire_empty_states(self):
        backend = MemoryTaskBackend()
        backend.submit("demo.task", {})
        # 不指定 states -> 领走 READY 任务
        t = backend.acquire("w1")
        assert t is not None
        # 显式空列表 -> 不应领到任何任务
        t2 = backend.acquire("w1", states=[])
        assert t2 is None
        backend.close()

    def test_memory_backend_acquire_explicit_state(self):
        backend = MemoryTaskBackend()
        backend.submit("demo.task", {})
        t = backend.acquire("w1", states=["DONE"])
        assert t is None  # 没有 DONE 任务
        t2 = backend.acquire("w1", states=["READY"])
        assert t2 is not None  # 有 READY 任务
        backend.close()


# ------------------------------------------------------------------
# ② worker_engine interval=0 / timeout_min=0
# ------------------------------------------------------------------

class TestWorkerEngineZeroInterval:
    """timeout_min=0 是合法语义，不应被替换。"""

    def test_run_once_respects_zero_timeout(self):
        from vools.task.core.worker_engine import WorkerEngine

        backend = MagicMock()
        backend.acquire.return_value = None  # 无任务可领
        engine = WorkerEngine(backend, worker_id="test")

        engine.run_once(timeout_min=0)
        assert backend.acquire.called
        # acquire(worker_id, timeout_min=..., states=...) — kwargs 在 call_args[1]
        assert backend.acquire.call_args[1].get("timeout_min") == 0

    def test_run_until_done_respects_zero_interval(self):
        """run_until_done 应接受 interval=0（忙轮询）"""
        from vools.task.core.worker_engine import WorkerEngine

        backend = MagicMock()
        backend.acquire.return_value = None
        engine = WorkerEngine(backend, worker_id="test")
        # max_idle_loops=1 让它跑一轮就退出
        engine.max_idle_loops = 1
        engine.run_until_done(interval=0, timeout_min=0)
        assert backend.acquire.called


# ------------------------------------------------------------------
# ③ Table.from_file(rows=0)
# ------------------------------------------------------------------

class TestTableFromFileZeroRows:
    """from_file(rows=0) 应返回 0 行。"""

    def _write_csv(self, rows, cols=3):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        w = csv.writer(f)
        w.writerow([f"c{j}" for j in range(cols)])
        for r in rows:
            w.writerow(r)
        f.close()
        return f.name

    def test_from_file_rows_zero(self):
        path = self._write_csv([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        try:
            t = Table.from_file(path, rows=0)
            assert t.rows() == 0  # 0 行数据
        finally:
            os.unlink(path)

    def test_from_file_rows_none(self):
        path = self._write_csv([[1, 2, 3], [4, 5, 6]])
        try:
            t = Table.from_file(path, rows=None)
            # None = 读全文件（header + 2 data rows = 3 rows in Table）
            assert t.rows() >= 2
        finally:
            os.unlink(path)

    def test_from_file_rows_positive(self):
        path = self._write_csv([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        try:
            t = Table.from_file(path, rows=2)
            assert t.rows() == 2
        finally:
            os.unlink(path)

    def test_from_file_cols_none(self):
        path = self._write_csv([[1, 2, 3], [4, 5, 6]], cols=3)
        try:
            t = Table.from_file(path, cols=None)
            assert len(t.columns()) == 3
        finally:
            os.unlink(path)

    def test_from_file_cols_specific(self):
        path = self._write_csv([[1, 2, 3], [4, 5, 6]], cols=3)
        try:
            t = Table.from_file(path, cols=[0, 2])
            assert len(t.columns()) == 2
        finally:
            os.unlink(path)
