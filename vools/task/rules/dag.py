"""
DagScheduler - DAG 拓扑调度器

基于现有 TaskQueue + WorkerPool/ThreadPool 的 DAG 依赖调度系统。

核心能力：
1. 拓扑排序：自动推导任务执行顺序
2. 循环检测：提交时验证无环路
3. 依赖感知：只有所有依赖成功才分派任务
4. 失败传播：任务失败自动跳过所有下游
5. 函数式风格：使用 Result 包装每一步状态

Example:
    >>> from vools.task import TaskQueue, WorkerPool
    >>> from vools.task.rules import DagScheduler

    >>> queue = TaskQueue("dag.db")
    >>> dag = DagScheduler(queue, mode="process", max_workers=4)

    >>> t1 = queue.submit(step1, depends_on=set())
    >>> t2 = queue.submit(step2, depends_on={t1})
    >>> t3 = queue.submit(step3, depends_on={t1})
    >>> t4 = queue.submit(step4, depends_on={t2, t3})

    >>> dag.start()
    >>> dag.await_completion()
    >>> dag.stop()
"""

__all__ = ['DagScheduler']

import time
import logging
import threading
from typing import Set, Dict, List, Optional, Literal, Callable, Any
from collections import deque
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future

from vools.functional import Result
from vools.task import TaskQueue, TaskStatus
from vools.task.core.models import Task

logger = logging.getLogger(__name__)


class DagScheduler:
    """
    DAG 拓扑调度器

    管理任务间的依赖关系，确保只有所有依赖完成的任务才被分派执行。

    Args:
        queue: TaskQueue 实例
        mode: 执行模式，"thread" 或 "process"
        max_workers: 最大并发 Worker 数
        poll_interval: 调度轮询间隔（秒）
        propagate_failure: 上游失败时是否跳过所有下游
    """

    def __init__(
        self,
        queue: TaskQueue,
        mode: Literal["thread", "process"] = "thread",
        max_workers: int = 4,
        poll_interval: float = 0.5,
        propagate_failure: bool = True,
    ):
        self._queue = queue
        self._storage = queue.storage
        self._mode = mode
        self._max_workers = max_workers
        self._poll_interval = poll_interval
        self._propagate_failure = propagate_failure

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executor: Any = None

        # 状态追踪
        self._pending: Set[int] = set()
        self._completed: Set[int] = set()
        self._failed: Set[int] = set()
        self._skipped: Set[int] = set()

    @property
    def status(self) -> Dict[str, Any]:
        """获取当前调度状态"""
        return {
            "running": self._running,
            "pending": len(self._pending),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "skipped": len(self._skipped),
        }

    def start(self) -> None:
        """
        启动调度器

        如果在主线程运行，会阻塞直到 stop() 被调用。
        推荐在独立线程中启动。
        """
        if self._running:
            logger.warning("DagScheduler already running")
            return

        self._running = True
        self._executor = self._create_executor()

        self._thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"DagScheduler started (mode={self._mode}, "
            f"max_workers={self._max_workers})"
        )

    def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("DagScheduler stopped")

    def await_completion(self, timeout: Optional[float] = None) -> Result:
        """
        等待所有已注册任务完成

        Args:
            timeout: 超时（秒），None 为无限等待

        Returns:
            Result: 所有任务完成后的状态摘要
        """
        start = time.time()
        while self._pending:
            if timeout is not None and (time.time() - start) > timeout:
                return Result.failure(TimeoutError(
                    f"Tasks not completed after {timeout}s: "
                    f"pending={len(self._pending)}"
                ))
            time.sleep(self._poll_interval)

        return Result.success({
            "completed": len(self._completed),
            "failed": len(self._failed),
            "skipped": len(self._skipped),
        })

    def register_task(self, task_id: int) -> None:
        """
        注册任务到调度器追踪

        Args:
            task_id: 任务 ID
        """
        self._pending.add(task_id)

    def register_tasks(self, *task_ids: int) -> None:
        """批量注册任务"""
        for tid in task_ids:
            self._pending.add(tid)

    # ================================================================
    # 内部方法
    # ================================================================

    def _create_executor(self):
        """创建执行器"""
        if self._mode == "process":
            return ProcessPoolExecutor(max_workers=self._max_workers)
        return ThreadPoolExecutor(max_workers=self._max_workers)

    def _schedule_loop(self) -> None:
        """调度主循环 - 在独立线程中运行"""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Schedule tick error: {e}")
            time.sleep(self._poll_interval)

    def _tick(self) -> None:
        """
        一次调度检查

        1. 扫描 PENDING 任务
        2. 检查哪些任务的依赖已全部 SUCCESS
        3. 标记为 READY 并提交执行
        4. 处理已完成任务的结果传播
        """
        # 处理已完成的 future
        self._collect_finished()

        # 检查是否有新就绪的任务
        ready_tasks = self._storage.get_ready_tasks(
            set(self._pending - self._completed - self._failed - self._skipped)
        )

        for task in ready_tasks:
            self._dispatch_task(task)

    def _dispatch_task(self, task: Task) -> None:
        """
        分派任务到执行器

        Args:
            task: 待执行的 Task
        """
        def execute_wrapper(tid: int) -> Result:
            """包装执行，捕获异常为 Result"""
            try:
                result = self._queue.execute_task(
                    self._storage.get_task(tid)
                )
                return Result.success(result)
            except Exception as e:
                return Result.failure(e)

        future = self._executor.submit(execute_wrapper, task.id)
        self._storage.update_task_status(
            task.id, TaskStatus.RUNNING,
            worker_id=f"scheduler_{self._mode}"
        )

        # 同步等待 future 完成
        try:
            result = future.result(timeout=3600)
            self._on_task_complete(task.id, result)
        except Exception as e:
            self._on_task_complete(
                task.id,
                Result.failure(e)
            )

    def _on_task_complete(self, task_id: int, result: Result) -> None:
        """
        任务完成的回调

        Args:
            task_id: 任务 ID
            result: 执行结果
        """
        if result.is_success:
            self._storage.update_task_status(
                task_id, TaskStatus.SUCCESS,
                result=result.unwrap(),
            )
            self._pending.discard(task_id)
            self._completed.add(task_id)
            logger.debug(f"Task {task_id} completed")
        else:
            error = result.unwrap_or(Exception("Unknown error"))
            self._storage.update_task_status(
                task_id, TaskStatus.FAILED,
                error_message=str(error),
            )
            self._pending.discard(task_id)
            self._failed.add(task_id)
            logger.warning(f"Task {task_id} failed: {error}")

            # 失败传播：跳过所有下游
            if self._propagate_failure:
                self._skip_downstream(task_id)

    def _skip_downstream(self, failed_task_id: int) -> None:
        """
        递归标记所有下游为 SKIPPED

        Args:
            failed_task_id: 失败的任务 ID
        """
        dependents = self._storage.get_dependents(failed_task_id)
        for dep_id in dependents:
            if dep_id in self._pending and dep_id not in self._failed:
                self._storage.update_task_status(
                    dep_id, TaskStatus.SKIPPED,
                    error_message=f"Upstream task {failed_task_id} failed",
                )
                self._pending.discard(dep_id)
                self._skipped.add(dep_id)
                logger.info(f"Task {dep_id} skipped (upstream {failed_task_id} failed)")
                # 递归
                self._skip_downstream(dep_id)

    def _collect_finished(self) -> None:
        """（兼容 Future 追踪的预留方法）"""
        pass

    # ================================================================
    # 上下文管理器
    # ================================================================

    def __enter__(self) -> 'DagScheduler':
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
