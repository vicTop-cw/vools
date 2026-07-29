"""
vools.concurrent.sched_mod - 事件调度器高级封装

对 Python 标准库 sched 进行高级封装，提供更易用的调度 API：

- VScheduler: 增强调度器，支持延迟/绝对时间调度、批量取消
- Timer: 定时器，支持单次和循环模式
- PeriodicTask: 周期任务，支持动态修改间隔
- delayed_call: 延迟调用，可用作函数装饰器或直接调用
- cron_like: 简化版 cron 调度，支持 interval / at_time / daily / hourly
- SchedulerPool: 多调度器统一管理
"""

from __future__ import annotations

import sched
import time
import threading
import functools
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

__all__ = [
    'VScheduler', 'Timer', 'PeriodicTask', 'delayed_call',
    'cron_like', 'SchedulerPool',
]


class VScheduler:
    """
    增强事件调度器

    对 sched.scheduler 的高级封装，提供线程安全的调度 API。

    Usage:
        s = VScheduler()
        s.schedule(2.0, print, "hello")       # 2 秒后执行
        s.schedule_at(time.time() + 10, print, "timed")  # 10 秒后执行
        s.run(blocking=False)                  # 非阻塞运行
        s.cancel_all()                         # 取消全部
    """

    def __init__(
        self,
        time_func: Callable[[], float] = time.time,
        delay_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._scheduler: sched.scheduler = sched.scheduler(time_func, delay_func)
        self._lock = threading.RLock()

    def schedule(
        self,
        delay: float,
        action: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        延迟 delay 秒后执行 action(*args, **kwargs)

        Returns:
            sched.Event 对象，可用于 cancel()
        """
        with self._lock:
            return self._scheduler.enter(delay, 1, action, args, kwargs)

    def schedule_at(
        self,
        when: float,
        action: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        在绝对时间 when 执行 action（时间基准与 time_func 一致）

        Returns:
            sched.Event 对象，可用于 cancel()
        """
        now = self._scheduler.timefunc()
        delay = max(0.0, when - now)
        return self.schedule(delay, action, *args, **kwargs)

    def cancel(self, event: Any) -> bool:
        """
        取消指定事件

        Returns:
            True 表示取消成功；False 表示事件不存在或已执行
        """
        with self._lock:
            try:
                self._scheduler.cancel(event)
                return True
            except ValueError:
                return False

    def cancel_all(self) -> int:
        """
        取消所有待执行事件

        Returns:
            取消的事件数量
        """
        with self._lock:
            count = 0
            for event in list(self._scheduler.queue()):
                try:
                    self._scheduler.cancel(event)
                    count += 1
                except ValueError:
                    pass
            return count

    def run(self, blocking: bool = True) -> None:
        """
        运行调度器

        Args:
            blocking: True 时阻塞直到所有事件执行完毕；
                      False 时在守护线程中运行。
        """
        if blocking:
            self._scheduler.run()
        else:
            thread = threading.Thread(target=self._scheduler.run, daemon=True)
            thread.start()

    def empty(self) -> bool:
        """检查是否没有待执行事件"""
        with self._lock:
            return self._scheduler.empty()

    @property
    def queue(self) -> List[Any]:
        """当前待执行事件队列（副本）"""
        with self._lock:
            return list(self._scheduler.queue())

    def __repr__(self) -> str:
        return f'VScheduler(pending={len(self.queue)})'


class Timer:
    """
    定时器，支持单次和循环模式

    基于 threading.Timer 封装，在独立线程中执行回调。

    Usage:
        # 单次定时器
        t = Timer(5.0, print, "hello", repeat=False)
        t.start()
        t.is_running()  # True
        t.cancel()

        # 循环定时器
        t = Timer(5.0, print, "tick", repeat=True)
        t.start()
        # ... 每隔 5 秒打印 "tick" ...
        t.cancel()
    """

    def __init__(
        self,
        interval: float,
        callback: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        repeat: bool = False,
        daemon: bool = True,
    ) -> None:
        self._interval = interval
        self._callback = callback
        self._args = args
        self._kwargs = kwargs if kwargs is not None else {}
        self._repeat = repeat
        self._daemon = daemon
        self._thread: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def start(self) -> 'Timer':
        """启动定时器（如果已在运行则忽略）"""
        with self._lock:
            if self._thread is not None:
                return self
            self._thread = threading.Timer(self._interval, self._run)
            self._thread.daemon = self._daemon
            self._thread.start()
            return self

    def _run(self) -> None:
        """实际执行回调，循环模式会重新调度"""
        try:
            self._callback(*self._args, **self._kwargs)
        except Exception:
            pass
        if self._repeat:
            with self._lock:
                if self._thread is not None:
                    self._thread = threading.Timer(self._interval, self._run)
                    self._thread.daemon = self._daemon
                    self._thread.start()

    def cancel(self) -> None:
        """取消定时器"""
        with self._lock:
            if self._thread is not None:
                self._thread.cancel()
                self._thread = None

    def is_running(self) -> bool:
        """定时器是否正在运行"""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def interval(self) -> float:
        return self._interval

    @interval.setter
    def interval(self, value: float) -> None:
        self._interval = value

    @property
    def repeat(self) -> bool:
        return self._repeat

    def __repr__(self) -> str:
        mode = 'repeat' if self._repeat else 'single'
        return f'Timer({self._interval}s, {mode}, running={self.is_running()})'


class PeriodicTask:
    """
    周期任务

    在独立线程中按固定间隔重复执行回调，支持动态修改间隔和优雅停止。

    Usage:
        task = PeriodicTask(5.0, print, "tick")
        task.start()
        task.set_interval(10.0)  # 改为每 10 秒
        task.stop()
    """

    def __init__(
        self,
        interval: float,
        callback: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        daemon: bool = True,
    ) -> None:
        self._interval = interval
        self._callback = callback
        self._args = args
        self._kwargs = kwargs if kwargs is not None else {}
        self._daemon = daemon
        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def start(self) -> 'PeriodicTask':
        """启动周期任务（如果已在运行则忽略）"""
        with self._lock:
            if self._running:
                return self
            self._running = True
            self._stop_event.clear()
            self._schedule_next()
            return self

    def _schedule_next(self) -> None:
        """调度下一次执行"""
        self._timer = threading.Timer(self._interval, self._run)
        self._timer.daemon = self._daemon
        self._timer.start()

    def _run(self) -> None:
        """实际执行回调，若未停止则继续调度下一次"""
        if self._stop_event.is_set():
            return
        try:
            self._callback(*self._args, **self._kwargs)
        except Exception:
            pass
        if not self._stop_event.is_set():
            with self._lock:
                if not self._stop_event.is_set():
                    self._schedule_next()

    def stop(self) -> 'PeriodicTask':
        """停止周期任务"""
        with self._lock:
            self._running = False
            self._stop_event.set()
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            return self

    def set_interval(self, seconds: float) -> 'PeriodicTask':
        """
        修改执行间隔。

        修改后将在下一次调度时生效（不会中断当前等待中的定时器）。
        """
        with self._lock:
            self._interval = seconds
            return self

    @property
    def interval(self) -> float:
        return self._interval

    def is_running(self) -> bool:
        """任务是否正在运行"""
        return self._running

    def __repr__(self) -> str:
        return f'PeriodicTask({self._interval}s, running={self._running})'


def delayed_call(
    seconds: float,
    func: Optional[Callable] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    延迟调用

    可用作函数装饰器或直接调用：

    # 直接调用
    delayed_call(5.0, print, "hello")  # 5 秒后打印 "hello"

    # 装饰器用法
    @delayed_call(5.0)
    def greet(name):
        print(f"hello {name}")
    greet("world")  # 5 秒后打印 "hello world"

    Args:
        seconds: 延迟秒数
        func: 要延迟执行的函数（装饰器模式下为 None）
        *args: 传递给函数的位置参数
        **kwargs: 传递给函数的关键字参数

    Returns:
        直接调用：threading.Timer 实例
        装饰器模式：包装后的函数
    """
    if func is None:
        # 装饰器模式：delayed_call(5.0)(func)
        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*a: Any, **kw: Any) -> threading.Timer:
                thread = threading.Timer(seconds, fn, args=a, kwargs=kw)
                thread.daemon = True
                thread.start()
                return thread

            return wrapper

        return decorator
    else:
        # 直接调用模式：delayed_call(5.0, print, "hello")
        thread = threading.Timer(seconds, func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread


class cron_like:
    """
    简化版 cron 调度器

    提供类似 cron 的周期调度能力，支持固定间隔、每天定时、每小时等模式。

    Usage:
        c = cron_like()
        c.interval(30, print, "every 30s")        # 每 30 秒
        c.hourly(print, "hourly")                  # 每小时
        c.daily(print, "daily")                    # 每天
        c.at_time("09:30:00", print, "morning")    # 每天 9:30
        c.start()
        # ...
        c.stop()
    """

    def __init__(self, daemon: bool = True) -> None:
        self._daemon = daemon
        self._tasks: List[PeriodicTask] = []
        self._threads: List[threading.Thread] = []
        self._stop_events: List[threading.Event] = []
        self._running = False
        self._lock = threading.Lock()

    def interval(
        self,
        seconds: float,
        callback: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> 'cron_like':
        """按固定间隔（秒）执行"""
        task = PeriodicTask(seconds, callback, args, kwargs, daemon=self._daemon)
        self._tasks.append(task)
        if self._running:
            task.start()
        return self

    def hourly(self, callback: Callable, *args: Any, **kwargs: Any) -> 'cron_like':
        """每小时执行一次"""
        return self.interval(3600.0, callback, *args, **kwargs)

    def daily(self, callback: Callable, *args: Any, **kwargs: Any) -> 'cron_like':
        """每天执行一次"""
        return self.interval(86400.0, callback, *args, **kwargs)

    def at_time(
        self,
        time_str: str,
        callback: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> 'cron_like':
        """
        每天在指定时间执行

        Args:
            time_str: 时间字符串，格式为 "hh:mm:ss" 或 "hh:mm"
            callback: 要执行的回调
        """
        h, m, s = self._parse_time(time_str)
        stop_event = threading.Event()
        self._stop_events.append(stop_event)

        def runner() -> None:
            while not stop_event.is_set():
                now = datetime.now()
                target = now.replace(hour=h, minute=m, second=s, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                delay = (target - now).total_seconds()
                if stop_event.wait(delay):
                    break
                try:
                    callback(*args, **kwargs)
                except Exception:
                    pass

        thread = threading.Thread(target=runner, daemon=self._daemon)
        self._threads.append(thread)
        if self._running:
            thread.start()
        return self

    def start(self) -> 'cron_like':
        """启动所有调度任务"""
        with self._lock:
            self._running = True
            for task in self._tasks:
                task.start()
            for thread in self._threads:
                if not thread.is_alive():
                    thread.start()
            return self

    def stop(self) -> 'cron_like':
        """停止所有调度任务"""
        with self._lock:
            self._running = False
            for task in self._tasks:
                task.stop()
            for event in self._stop_events:
                event.set()
            for thread in self._threads:
                if thread.is_alive():
                    thread.join(timeout=1.0)
            return self

    @property
    def task_count(self) -> int:
        """已注册的任务总数"""
        return len(self._tasks) + len(self._threads)

    @staticmethod
    def _parse_time(time_str: str) -> Tuple[int, int, int]:
        """解析时间字符串为 (hour, minute, second)"""
        parts = time_str.strip().split(':')
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]), int(parts[1]), 0
        else:
            raise ValueError(
                f"Invalid time format: {time_str!r}. Expected 'hh:mm:ss' or 'hh:mm'"
            )

    def __repr__(self) -> str:
        return f'cron_like(running={self._running}, tasks={self.task_count})'


class SchedulerPool:
    """
    多调度器管理，统一启动和停止

    Usage:
        pool = SchedulerPool()
        pool.add(VScheduler())
        pool.add(VScheduler())
        pool.run_all(blocking=False)
        # ...
        pool.stop_all()
    """

    def __init__(self) -> None:
        self._schedulers: List[VScheduler] = []
        self._lock = threading.Lock()

    def add(self, scheduler: VScheduler) -> 'SchedulerPool':
        """添加一个调度器"""
        with self._lock:
            self._schedulers.append(scheduler)
        return self

    def remove(self, scheduler: VScheduler) -> bool:
        """移除一个调度器"""
        with self._lock:
            if scheduler in self._schedulers:
                self._schedulers.remove(scheduler)
                return True
            return False

    def run_all(self, blocking: bool = False) -> 'SchedulerPool':
        """
        运行所有调度器

        Args:
            blocking: True 时依次阻塞运行每个调度器；
                      False 时每个调度器在各自的守护线程中运行。
        """
        with self._lock:
            schedulers = list(self._schedulers)
        for s in schedulers:
            s.run(blocking=blocking)
        return self

    def stop_all(self) -> 'SchedulerPool':
        """取消所有调度器的全部事件"""
        with self._lock:
            schedulers = list(self._schedulers)
        for s in schedulers:
            s.cancel_all()
        return self

    def cancel_all(self) -> int:
        """取消所有调度器的全部事件，返回取消总数"""
        total = 0
        with self._lock:
            schedulers = list(self._schedulers)
        for s in schedulers:
            total += s.cancel_all()
        return total

    @property
    def schedulers(self) -> List[VScheduler]:
        """调度器列表（副本）"""
        with self._lock:
            return list(self._schedulers)

    def __len__(self) -> int:
        with self._lock:
            return len(self._schedulers)

    def __repr__(self) -> str:
        return f'SchedulerPool(count={len(self)})'
