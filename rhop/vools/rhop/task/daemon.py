"""vools.rhop.task.daemon - 常驻进程（A 提交侧 / B 执行侧，同一份配置驱动）

行为完全由配置里的方向决定，没有 P0/P1/P2/P3 跳板角色：

* ``role = "B"``（执行方）：起 **心跳后台线程**（每 5 秒写时间戳，与任务执行解耦），
  然后跑 ``TaskQueue.run_resident()``；一旦心跳文件出现 ``closed``（运维/A 端停机指令）
  或收到 SIGINT/SIGTERM，就停止领取新任务、等当前任务收尾，最后把心跳写成 ``closed`` 退出。
* ``role = "A"``（提交方）：可提交一批任务，然后（可选）盯着"全部完成 + B 心跳活着"；
  B 心跳一直不动（``stale``）超过宽限次数，就判定服务挂了并退出，而不是无限等。
* ``role = "C"``（中转）：不参与队列消费，只保留介质角色。

本模块把「存储 / 加密 / 心跳 / 同步」按配置一次性接好线，CLI 与嵌入式调用共用
``build_queue()`` 这一个入口。
"""

from __future__ import absolute_import

import logging
import signal
import time
from typing import Any, Callable, Dict, Optional

from ..session import Role
from .config import TaskConfig
from .heartbeat import HeartbeatPump
from .queue import TaskQueue
from .sync import TaskSync

log = logging.getLogger("vools.rhop.task.daemon")

#: 心跳读数的异常状态（判定 B 是否还活着）
DEAD_STATES = ("stale", "missing", "unknown")


def build_queue(config: TaskConfig, handlers: Optional[Dict[str, Callable]] = None,
                logger: Optional[Any] = None) -> TaskQueue:
    """按配置接好 store / crypto / heartbeat / syncer，返回 TaskQueue。

    本地库模式（``store.kind = sqlite-local``）会自动挂上 TaskSync。
    """
    store = config.build_store()
    crypto = config.build_crypto()
    heartbeat = config.build_heartbeat()
    syncer = None
    spec = dict(config.queue.get("store") or {})
    if str(spec.get("kind") or "").strip().lower() == "sqlite-local":
        syncer = TaskSync(store, crypto, config.role,
                          shared=config.build_shared(), name=config.name)
    return TaskQueue(config, store=store, crypto=crypto, heartbeat=heartbeat,
                     handlers=handlers, syncer=syncer, logger=logger)


class TaskDaemon(object):
    """A/B 常驻进程封装。"""

    def __init__(self, config: TaskConfig, queue: Optional[TaskQueue] = None,
                 handlers: Optional[Dict[str, Callable]] = None,
                 logger: Optional[Any] = None):
        self.config = config
        self.queue = queue if queue is not None else build_queue(config, handlers=handlers,
                                                                 logger=logger)
        self.log = logger or log
        self._pump = None  # type: Optional[HeartbeatPump]
        self._stop = False
        self._installed_signals = []

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def install_signals(self) -> None:
        """装 SIGINT/SIGTERM 处理：第一次请求优雅停止，第二次直接退出。"""
        def _handler(signum, frame):  # pragma: no cover - 信号路径不易在单测覆盖
            if self._stop:
                self.log.warning("再次收到信号 %s，直接退出", signum)
                raise SystemExit(1)
            self.log.info("收到信号 %s，优雅停止中…", signum)
            self.stop()

        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                previous = signal.signal(sig, _handler)
                self._installed_signals.append((sig, previous))
            except (ValueError, OSError):  # 非主线程等
                pass

    def start_pump(self) -> Optional[HeartbeatPump]:
        """启动心跳后台线程（仅当配置里有 shared path）。"""
        if self.queue.heartbeat is None or not self.queue.heartbeat.enabled:
            self.log.info("未配置 shared path，跳过心跳线程")
            return None
        if self._pump is not None:
            return self._pump
        self._pump = HeartbeatPump(self.queue.heartbeat,
                                   on_close=self._on_remote_close)
        self._pump.start()
        return self._pump

    def _on_remote_close(self) -> None:
        """心跳文件被写成 closed：请求队列循环退出。"""
        self.log.warning("检测到停机指令（心跳文件为 closed），准备退出")
        self.queue.request_stop()

    def stop(self) -> None:
        """请求停止（可由信号处理器调用）。"""
        self._stop = True
        self.queue.request_stop()

    def close(self, write_closed: bool = True) -> None:
        """收尾：停心跳线程（默认写 closed）并关闭队列。"""
        if self._pump is not None:
            self._pump.stop(write_closed=write_closed)
            self._pump = None
        self.queue.close()

    # ------------------------------------------------------------------
    # A 侧
    # ------------------------------------------------------------------

    def run_sender(self, tasks: Optional[list] = None, deps: Optional[dict] = None,
                   wait: bool = False, timeout: Optional[float] = None,
                   poll: Optional[float] = None, dead_grace: int = 3,
                   **defaults) -> Dict[str, Any]:
        """提交（可选）任务并（可选）盯着完成 + B 心跳。

        Args:
            tasks:      任务列表；None 表示只查状态
            deps:       依赖映射
            wait:       是否等待全部完成
            timeout:    等待超时（秒）
            poll:       轮询间隔（秒）
            dead_grace: B 心跳连续异常多少次判定"服务挂了"
        """
        result = {"role": "A", "worker_id": self.config.worker_id()}  # type: Dict[str, Any]
        if tasks:
            result["submit"] = self.queue.submit(tasks, deps=deps, **defaults)
        if not wait:
            result["status"] = self.queue.status()
            result["summary"] = self.queue.summary()
            return result

        interval = float(poll if poll is not None else self.config.poll_interval())
        wait_sec = max(interval * 0.05, 0.01)
        deadline = (time.time() + float(timeout)) if timeout else None
        dead_count = 0
        while True:
            self.queue.pull_sync()
            if self.queue.is_all_done():
                result["reason"] = "all-done"
                break
            heartbeat = self.queue.heartbeat.read() if self.queue.heartbeat else {"state": "missing"}
            state = heartbeat.get("state")
            if state == "closed":
                result["reason"] = "executor-closed"
                result["heartbeat"] = heartbeat
                break
            if state in DEAD_STATES:
                dead_count += 1
                if dead_count >= int(dead_grace):
                    result["reason"] = "executor-dead"
                    result["heartbeat"] = heartbeat
                    result["message"] = (
                        "B 侧心跳文件连续 %d 次读数异常（%s），判定执行服务已停止；"
                        "请检查 B 端进程 / 心跳文件 %s。" % (
                            dead_count, state, self.queue.heartbeat.filename))
                    break
            else:
                dead_count = 0
            if deadline is not None and time.time() >= deadline:
                result["reason"] = "timeout"
                break
            time.sleep(wait_sec)
        result["status"] = self.queue.status()
        result["summary"] = self.queue.summary()
        return result

    # ------------------------------------------------------------------
    # B 侧
    # ------------------------------------------------------------------

    def run_executor(self, once: bool = False, max_iterations: Optional[int] = None,
                     write_closed_on_exit: bool = True) -> Dict[str, Any]:
        """执行侧：心跳线程 + 常驻消费（once=True 时只跑一轮）。"""
        if once:
            result = self.queue.run_once()
            result["worker_id"] = self.config.worker_id()
            return result
        self.start_pump()
        try:
            stats = self.queue.run_resident(max_iterations=max_iterations)
        finally:
            self.close(write_closed=write_closed_on_exit)
        return stats

    # ------------------------------------------------------------------

    def start(self, once: bool = False, tasks: Optional[list] = None,
              deps: Optional[dict] = None, wait: bool = False,
              timeout: Optional[float] = None, max_iterations: Optional[int] = None,
              install_signals: bool = True, **defaults) -> Dict[str, Any]:
        """按方向分派执行（CLI 与嵌入式共用的总入口）。"""
        if install_signals:
            self.install_signals()
        if self.config.role == Role.RECV:
            return self.run_executor(once=once, max_iterations=max_iterations)
        if self.config.role == Role.SEND:
            return self.run_sender(tasks=tasks, deps=deps, wait=wait, timeout=timeout,
                                   **defaults)
        return {"role": "C", "message": "中转角色不消费队列（仅提供介质/中转能力）",
                "summary": self.queue.summary()}


__all__ = ["TaskDaemon", "build_queue", "DEAD_STATES"]