"""
Worker 引擎 — 对标 look_upon.run_until_done 的常驻执行循环。

职责：
    1. 从 backend.acquire(worker_id) 领任务（原子竞争）
    2. 执行任务：payload['cli'] → CLI 通道；否则调 task_function(task_value)
    3. 成功 → backend.complete(task_id, worker_id, back_info)
    4. 失败 → backend.fail(task_id, worker_id, error)（自动重试）
    5. clean_stale_locks 定期回收过期锁

用法：
    from vools.task.core.worker_engine import WorkerEngine
    engine = WorkerEngine(backend, task_function=my_fn, worker_id="w1")
    engine.run_until_done(timeout_min=5, interval=10)

    # 或用 CLI 通道（payload['cli']）
    engine = WorkerEngine(backend, worker_id="w1")   # 无 task_function 时走 CLI
"""

__all__ = ['WorkerEngine', 'TaskFunctionError']

import logging
import time
from typing import Any, Callable, Dict, Optional

from .cli_exec import cli_execute

logger = logging.getLogger(__name__)


class TaskFunctionError(Exception):
    """任务函数执行异常。"""
    pass


class WorkerEngine:
    """常驻 Worker 引擎。"""

    def __init__(self, backend, task_function: Optional[Callable[[str], Any]] = None,
                 worker_id: str = "worker_1", timeout_min: int = 5,
                 interval: float = 10.0, max_idle_loops: Optional[int] = None,
                 task_type: Optional[str] = None):
        """
        backend: 后端实例（pg / sqlite / memory）
        task_function: 用户提供的单参数函数，接受 task_value（可选，CLI 通道不需要）
        worker_id: 本 Worker 标识
        timeout_min: 任务租约分钟数
        interval: 空闲轮询间隔秒
        max_idle_loops: 最大空闲轮次（None=无限常驻）
        task_type: 默认 task_type（CLI 通道推断用）
        """
        self.backend = backend
        self.task_function = task_function
        self.worker_id = worker_id
        self.timeout_min = timeout_min
        self.interval = interval
        self.max_idle_loops = max_idle_loops
        self.task_type = task_type
        self._running = False

    # ---------- 单任务执行 ----------
    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个任务，返回 back_info。

        优先级：payload['cli'] 走 CLI 通道；否则调 task_function(task_value)。
        """
        payload = task.get("payload") or {}
        task_value = task.get("task_value") or payload.get("value") or ""
        t0 = time.time()

        # CLI 通道
        if isinstance(payload, dict) and isinstance(payload.get("cli"), dict):
            cli_payload = dict(payload)
            cli_payload.setdefault("task_type",
                                   task.get("task_type") or self.task_type or "PYTHON")
            result = cli_execute(cli_payload)
            result["duration_ms"] = (time.time() - t0) * 1000.0
            if not result.get("ok"):
                raise TaskFunctionError(
                    "CLI 执行失败: %s" % (result.get("error") or result.get("stderr") or "未知错误"))
            return result

        # 函数通道
        if self.task_function is None:
            raise TaskFunctionError(
                "任务 %s 无 cli 配置且未提供 task_function" % task_value)
        result = self.task_function(task_value)
        if isinstance(result, dict):
            result = dict(result)
        else:
            result = {"status": "ok", "task_value": task_value, "result": result}
        result["duration_ms"] = (time.time() - t0) * 1000.0
        return result

    # ---------- 常驻循环 ----------
    def run_until_done(self, timeout_min: Optional[int] = None,
                       interval: Optional[float] = None,
                       states: Optional[list] = None) -> int:
        """常驻：领任务 → 执行 → 回写，直到队列清空。

        返回执行任务数。
        """
        timeout_min = timeout_min or self.timeout_min
        interval = interval or self.interval
        self._running = True
        executed = 0
        idle = 0

        try:
            while self._running:
                # 定期清理过期锁
                if idle > 0 and idle % 6 == 0:
                    n = self.backend.clean_stale_locks(timeout_min=timeout_min)
                    if n:
                        logger.info("clean_stale_locks 回收 %d 个过期锁", n)

                task = self.backend.acquire(self.worker_id, timeout_min=timeout_min,
                                            states=states)
                if task is None:
                    idle += 1
                    if self.max_idle_loops is not None and idle >= self.max_idle_loops:
                        break
                    time.sleep(interval)
                    continue

                idle = 0
                tid = task.get("id")
                try:
                    back_info = self.execute_task(task)
                    self.backend.complete(tid, self.worker_id, back_info)
                    logger.info("任务 %s 完成 (%s)", tid, back_info.get("duration_ms"))
                except Exception as e:
                    logger.warning("任务 %s 失败: %s", tid, e)
                    self.backend.fail(tid, self.worker_id, str(e))
                executed += 1
        finally:
            self._running = False

        return executed

    # ---------- 单轮 ----------
    def run_once(self, timeout_min: Optional[int] = None,
                 states: Optional[list] = None) -> Optional[Dict[str, Any]]:
        """跑一轮（领一个任务并执行）。无任务返回 None。"""
        timeout_min = timeout_min or self.timeout_min
        task = self.backend.acquire(self.worker_id, timeout_min=timeout_min, states=states)
        if task is None:
            return None
        tid = task.get("id")
        try:
            back_info = self.execute_task(task)
            self.backend.complete(tid, self.worker_id, back_info)
        except Exception as e:
            self.backend.fail(tid, self.worker_id, str(e))
            back_info = {"ok": False, "error": str(e)}
        return {"task_id": tid, "back_info": back_info}

    def stop(self):
        self._running = False