"""
vools-reactive Schedulers

调度器用于控制 Observable 操作的执行上下文。
支持多种调度策略：
- ImmediateScheduler: 立即执行
- CurrentThreadScheduler: 当前线程执行
- AsyncIOScheduler: asyncio 事件循环
- ThreadPoolScheduler: 线程池
- NewThreadScheduler: 新线程
"""

from typing import TypeVar, Callable, Optional, Any, Generic, Union, Iterable
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
import time

from .observable import Observable, Observer, Subscription
__all__ = ['T', 'Scheduler', 'ImmediateScheduler', 'CurrentThreadScheduler', 'AsyncIOScheduler', 'ThreadPoolScheduler', 'NewThreadScheduler', 'immediate', 'current_thread', 'asyncio_scheduler', 'immediate_scheduler', 'current_thread_scheduler', 'asyncio_scheduler', 'thread_pool_scheduler', 'new_thread_scheduler']

T = TypeVar('T')


class Scheduler(Generic[T]):
    """调度器抽象基类"""
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        """调度一个操作"""
        raise NotImplementedError
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        """延迟调度一个操作"""
        raise NotImplementedError
    

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
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        """在指定时间调度一个操作"""
        raise NotImplementedError


class ImmediateScheduler(Scheduler):
    """立即调度器 - 同步执行"""
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        action()
        return Subscription(lambda: None)
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        time.sleep(delay)
        action()
        return Subscription(lambda: None)
    
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        delay = max(0, time - time.time())
        return self.schedule_relative(delay, action)
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



class CurrentThreadScheduler(Scheduler):
    """当前线程调度器 - 在当前线程的调度队列中执行"""
    
    def __init__(self):
        self._queue = []
        self._is_running = False
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        self._queue.append(action)
        if not self._is_running:
            self._run()
        return Subscription(lambda: None)
    
    def _run(self):
        self._is_running = True
        while self._queue:
            action = self._queue.pop(0)
            action()
        self._is_running = False
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        def delayed_action():
            time.sleep(delay)
            action()
        return self.schedule(delayed_action)
    

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
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        delay = max(0, time - time.time())
        return self.schedule_relative(delay, action)


class AsyncIOScheduler(Scheduler):
    """AsyncIO 调度器 - 使用 asyncio 事件循环"""
    
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        task = self._loop.call_soon(action)
        
        def unsubscribe():
            task.cancel()
        
        return Subscription(unsubscribe)
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        task = self._loop.call_later(delay, action)
        
        def unsubscribe():
            task.cancel()
        
        return Subscription(unsubscribe)
    
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        delay = max(0, time - self._loop.time())
        return self.schedule_relative(delay, action)
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



class ThreadPoolScheduler(Scheduler):
    """线程池调度器 - 使用线程池执行"""
    
    def __init__(self, max_workers: Optional[int] = None):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        future: Future = self._executor.submit(action)
        
        def unsubscribe():
            future.cancel()
        
        return Subscription(unsubscribe)
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        def delayed_action():
            time.sleep(delay)
            action()
        
        return self.schedule(delayed_action)
    
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        delay = max(0, time - time.time())
        return self.schedule_relative(delay, action)
    

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
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        self._executor.shutdown(wait=wait)


class NewThreadScheduler(Scheduler):
    """新线程调度器 - 在新线程中执行"""
    
    def schedule(self, action: Callable[[], None]) -> Subscription:
        thread = threading.Thread(target=action, daemon=True)
        thread.start()
        
        def unsubscribe():
            pass
        
        return Subscription(unsubscribe)
    
    def schedule_relative(self, delay: float, action: Callable[[], None]) -> Subscription:
        def delayed_action():
            time.sleep(delay)
            action()
        
        return self.schedule(delayed_action)
    
    def schedule_absolute(self, time: float, action: Callable[[], None]) -> Subscription:
        delay = max(0, time - time.time())
        return self.schedule_relative(delay, action)
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



# ========== 全局调度器实例 ==========

immediate = ImmediateScheduler()
current_thread = CurrentThreadScheduler()
asyncio_scheduler = AsyncIOScheduler()


def _subscribe_on(scheduler: Scheduler) -> Callable[[Observable[T]], Observable[T]]:
    """在指定调度器上订阅"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def schedule_subscribe():
                return source.subscribe(observer)
            
            return scheduler.schedule(schedule_subscribe)
        
        return Observable(subscribe)
    
    return operator


def _observe_on(scheduler: Scheduler) -> Callable[[Observable[T]], Observable[T]]:
    """在指定调度器上观察"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T):
                scheduler.schedule(lambda: observer.on_next(value))
            
            def on_error(error: Exception):
                scheduler.schedule(lambda: observer.on_error(error))
            
            def on_completed():
                scheduler.schedule(lambda: observer.on_completed())
            
            return source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 工厂函数 ==========

def immediate_scheduler() -> ImmediateScheduler:
    """创建立即调度器"""
    return ImmediateScheduler()


def current_thread_scheduler() -> CurrentThreadScheduler:
    """创建当前线程调度器"""
    return CurrentThreadScheduler()


def asyncio_scheduler(loop: Optional[asyncio.AbstractEventLoop] = None) -> AsyncIOScheduler:
    """创建 AsyncIO 调度器"""
    return AsyncIOScheduler(loop)


def thread_pool_scheduler(max_workers: Optional[int] = None) -> ThreadPoolScheduler:
    """创建线程池调度器"""
    return ThreadPoolScheduler(max_workers)


def new_thread_scheduler() -> NewThreadScheduler:
    """创建新线程调度器"""
    return NewThreadScheduler()