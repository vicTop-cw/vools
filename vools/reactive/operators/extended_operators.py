"""
vools-reactive 扩展操作符

补全 Rx 规范中的所有操作符，并添加创新功能。
"""

from typing import TypeVar, Callable, Optional, Any, Generic, List, Dict, Set, Tuple, Union, Iterable
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from ...core.asyncio_compat import create_task as _asyncio_create_task
from ..core.observable import Observable, Observer, Subscription
__all__ = ['T', 'K', 'V', 'U', 'from_range', 'from_callable', 'from_future', 'start', 'sample', 'skip_last', 'take_last', 'throttle_latest', 'ignore_elements', 'to_map', 'to_set', 'observe_on', 'subscribe_on', 'do_on_next', 'do_on_error', 'do_on_completed', 'time_interval', 'flat_map_latest', 'window', 'amb', 'switch', 'ConnectableObservable', 'backpressure_buffer', 'backpressure_drop', 'backpressure_error', 'backpressure_latest', 'retry_with_backoff', 'circuit_breaker', 'debounce_evolution', 'cache', 'parallel']

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')
U = TypeVar('U')


# ========== Creating 操作符 ==========

def from_range(start: int, stop: int = None, step: int = 1) -> Callable:
    """创建发出范围序列整数的 Observable
    
    Args:
        start: 起始值（包含）
        stop: 结束值（不包含），如果为 None 则从 0 到 start
        step: 步长
    
    Returns:
        Observable[int]: 发出整数序列
    
    Example:
        >>> Observable.from_range(5)  # 0, 1, 2, 3, 4
        >>> Observable.from_range(2, 6)  # 2, 3, 4, 5
        >>> Observable.from_range(0, 10, 2)  # 0, 2, 4, 6, 8
    """
    from ..core.observable import Observable
    
    def subscribe(observer):
        try:
            if stop is None:
                stop = start
                start_val = 0
            else:
                start_val = start
            
            for i in range(start_val, stop, step):
                observer.on_next(i)
            observer.on_completed()
        except Exception as e:
            observer.on_error(e)
        
        from ..core.observable import Subscription
        return Subscription(lambda: None)
    
    return Observable(subscribe)


def from_callable(func: Callable[[], T]) -> Callable:
    """从 Callable 创建 Observable
    
    Args:
        func: 返回值的 Callable
    
    Returns:
        Observable[T]: 发出 Callable 返回的值
    """
    from ..core.observable import Observable, Subscription
    
    def subscribe(observer):
        try:
            result = func()
            observer.on_next(result)
            observer.on_completed()
        except Exception as e:
            observer.on_error(e)
        
        return Subscription(lambda: None)
    
    return Observable(subscribe)


def from_future(future) -> Callable:
    """从 Future 创建 Observable
    
    Args:
        future: concurrent.futures.Future 对象
    
    Returns:
        Observable[T]: 发出 Future 结果
    """
    from ..core.observable import Observable, Subscription
    
    def subscribe(observer):
        def done_callback(f):
            try:
                observer.on_next(f.result())
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
        
        future.add_done_callback(done_callback)
        
        return Subscription(lambda: future.cancel() if hasattr(future, 'cancel') else None)
    
    return Observable(subscribe)


def start(factory: Callable[[], T]) -> Callable:
    """创建发出函数返回值的 Observable
    
    Args:
        factory: 返回值的工厂函数
    
    Returns:
        Observable[T]: 发出函数返回值
    """
    return from_callable(factory)


# ========== Filtering 操作符 ==========

def sample(period: float) -> Callable:
    """在周期时间间隔内发出最近一次发出的项目
    
    Args:
        period: 采样周期（秒）
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            latest_value = [None]
            has_value = [False]
            task = [None]
            is_closed = [False]
            
            async def emit_sample():
                while not is_closed[0]:
                    await asyncio.sleep(period)
                    if is_closed[0]:
                        break
                    if has_value[0]:
                        observer.on_next(latest_value[0])
            
            def on_next(value):
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err):
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_error(err)
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            task[0] = _asyncio_create_task(emit_sample())
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                source_sub.unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def skip_last(n: int) -> Callable:
    """跳过最后 n 个项目
    
    Args:
        n: 要跳过的项目数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            buffer = []
            
            def on_next(value):
                buffer.append(value)
                if len(buffer) > n:
                    observer.on_next(buffer.pop(0))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def take_last(n: int) -> Callable:
    """只取最后 n 个项目
    
    Args:
        n: 要取的项目数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            buffer = []
            
            def on_next(value):
                buffer.append(value)
                if len(buffer) > n:
                    buffer.pop(0)
            
            def on_completed():
                for value in buffer:
                    observer.on_next(value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def throttle_latest(period: float) -> Callable:
    """在时间窗口内取最新值
    
    Args:
        period: 时间窗口（秒）
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            latest_value = [None]
            has_value = [False]
            task = [None]
            is_closed = [False]
            
            async def emit_latest():
                while not is_closed[0]:
                    await asyncio.sleep(period)
                    if is_closed[0]:
                        break
                    if has_value[0]:
                        observer.on_next(latest_value[0])
                        has_value[0] = False
            
            def on_next(value):
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err):
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_error(err)
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            task[0] = _asyncio_create_task(emit_latest())
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                source_sub.unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def ignore_elements() -> Callable:
    """不发出任何项目，只传递终止通知
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            return source.subscribe(
                on_next=lambda _: None,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== Mathematical 操作符 ==========

def to_map(key_fn: Callable[[T], K] = None) -> Callable:
    """转换为 Map
    
    Args:
        key_fn: 键提取函数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            result = {}
            
            def on_next(value):
                try:
                    key = key_fn(value) if key_fn else value
                    result[key] = value
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                observer.on_next(result)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def to_set() -> Callable:
    """转换为 Set
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            result = set()
            
            def on_next(value):
                result.add(value)
            
            def on_completed():
                observer.on_next(result)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== Utility 操作符 ==========

def observe_on(scheduler) -> Callable:
    """指定观察者使用的调度器
    
    Args:
        scheduler: 调度器实例
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            def on_next(value):
                scheduler.schedule(lambda v=value: observer.on_next(v))
            
            def on_error(err):
                scheduler.schedule(lambda e=err: observer.on_error(e))
            
            def on_completed():
                scheduler.schedule(observer.on_completed)
            
            return source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def subscribe_on(scheduler) -> Callable:
    """指定订阅使用的调度器
    
    Args:
        scheduler: 调度器实例
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            def subscribe_inner():
                return source.subscribe(observer)
            
            scheduler.schedule(subscribe_inner)
            
            from ..core.observable import Subscription
            return Subscription(lambda: None)
        
        return Observable(subscribe)
    
    return operator


def do_on_next(fn: Callable[[T], None]) -> Callable:
    """在每个 next 事件时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            def on_next(value):
                try:
                    fn(value)
                except Exception as e:
                    observer.on_error(e)
                    return
                observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def do_on_error(fn: Callable[[Exception], None]) -> Callable:
    """在错误发生时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            def on_error(err):
                try:
                    fn(err)
                except Exception:
                    pass
                observer.on_error(err)
            
            return source.subscribe(
                on_next=observer.on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def do_on_completed(fn: Callable[[], None]) -> Callable:
    """在完成时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            def on_completed():
                try:
                    fn()
                except Exception as e:
                    observer.on_error(e)
                    return
                observer.on_completed()
            
            return source.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def time_interval() -> Callable:
    """转换为发出排放之间的时间
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            last_time = [time.time()]
            
            def on_next(value):
                current_time = time.time()
                elapsed = current_time - last_time[0]
                last_time[0] = current_time
                observer.on_next((value, elapsed))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== Transforming 操作符 ==========

def flat_map_latest(fn: Callable[[T], Observable]) -> Callable:
    """只处理最新的内部 Observable
    
    Args:
        fn: 映射函数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            inner_sub = [None]
            is_closed = [False]
            
            def on_next(value):
                nonlocal inner_sub
                if inner_sub[0]:
                    inner_sub[0].unsubscribe()
                
                inner = fn(value)
                inner_sub[0] = inner.subscribe(
                    on_next=observer.on_next,
                    on_error=observer.on_error,
                    on_completed=None
                )
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if inner_sub[0] is None:
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            def unsubscribe():
                if inner_sub[0]:
                    inner_sub[0].unsubscribe()
                source_sub.unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def window(window_size: int) -> Callable:
    """定期将项目细分为 Observable 窗口
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            buffer = []
            window_count = [0]
            is_closed = [False]
            
            def emit_window():
                if buffer:
                    window_obs = Observable.from_iterable(buffer[:])
                    observer.on_next(window_obs)
                    buffer.clear()
            
            def on_next(value):
                buffer.append(value)
                if len(buffer) >= window_size:
                    emit_window()
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if buffer:
                    emit_window()
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== Combining 操作符 ==========

def amb() -> Callable:
    """选择第一个发出项目的 Observable
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(*sources):
        def subscribe(observer):
            is_winner = [False]
            winner_sub = [None]
            others = [s.subscribe(
                on_next=lambda x: None,
                on_error=observer.on_error,
                on_completed=lambda: None
            ) for s in sources]
            
            def on_next(source, value):
                if not is_winner[0]:
                    is_winner[0] = True
                    for sub in others:
                        sub.unsubscribe()
                    winner_sub[0] = source.subscribe(
                        on_next=observer.on_next,
                        on_error=observer.on_error,
                        on_completed=observer.on_completed
                    )
            
            subscriptions = []
            for source in sources:
                subscriptions.append(source.subscribe(
                    on_next=lambda v, src=source: on_next(src, v),
                    on_error=observer.on_error,
                    on_completed=lambda: None
                ))
            
            def unsubscribe():
                for sub in subscriptions:
                    sub.unsubscribe()
                if winner_sub[0]:
                    winner_sub[0].unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def switch() -> Callable:
    """将发出 Observables 的 Observable 转换为单个
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            inner_sub = [None]
            is_closed = [False]
            
            def on_next(value):
                nonlocal inner_sub
                if inner_sub[0]:
                    inner_sub[0].unsubscribe()
                
                inner_sub[0] = value.subscribe(
                    on_next=observer.on_next,
                    on_error=observer.on_error,
                    on_completed=None
                )
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if inner_sub[0] is None:
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            def unsubscribe():
                if inner_sub[0]:
                    inner_sub[0].unsubscribe()
                source_sub.unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


# ========== Connectable Observable ==========

class ConnectableObservable(Generic[T]):
    """可连接的 Observable"""
    
    __slots__ = ('_source', '_subject', '_connection', '_ref_count')
    
    def __init__(self, source, subject=None):
        from ..core.subject import Subject
        self._source = source
        self._subject = subject or Subject()
        self._connection = None
        self._ref_count = [0]
    
    def connect(self):
        """指示可连接 Observable 开始发出"""
        self._connection = self._source.subscribe(self._subject)
        return self._connection
    
    def ref_count() -> Callable:
        """使可连接 Observable 像普通 Observable"""
        def operator(source):
            ref_count = [0]
            connection = [None]
            subject = None
            
            from ..core.subject import Subject
            
            def get_subject():
                nonlocal subject
                if subject is None:
                    subject = Subject()
                return subject
            
            def subscribe(observer):
                ref_count[0] += 1
                subj = get_subject()
                subj.subscribe(observer)
                
                if ref_count[0] == 1:
                    connection[0] = source.subscribe(subj)
                
                def unsubscribe():
                    nonlocal subject
                    ref_count[0] -= 1
                    if ref_count[0] == 0:
                        if connection[0]:
                            connection[0].unsubscribe()
                            connection[0] = None
                        subject = None
                
                from ..core.observable import Subscription
                return Subscription(unsubscribe)
            
            from ..core.observable import Observable
            return Observable(subscribe)
        
        return operator
    
    def publish():
        """转换为可连接 Observable"""
        def operator(source):
            subject = None
            
            from ..core.subject import Subject
            
            def subscribe(observer):
                nonlocal subject
                if subject is None:
                    subject = Subject()
                return subject.subscribe(observer)
            
            from ..core.observable import Observable
            return Observable(subscribe)
        
        return operator
    
    def share():
        """共享 Observable (publish + ref_count)"""
        return ref_count()(publish()(lambda x: x))


# ========== Backpressure 操作符 ==========

def backpressure_buffer(max_size: int = None) -> Callable:
    """缓冲背压项目
    
    Args:
        max_size: 最大缓冲区大小
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            buffer = []
            is_paused = [False]
            is_closed = [False]
            
            def drain():
                while buffer and not is_paused[0]:
                    if buffer:
                        observer.on_next(buffer.pop(0))
                if is_closed[0] and not buffer:
                    observer.on_completed()
            
            def on_next(value):
                if len(buffer) >= max_size if max_size else False:
                    is_paused[0] = True
                buffer.append(value)
                drain()
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                drain()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def backpressure_drop() -> Callable:
    """丢弃多余项目
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            is_busy = [False]
            
            def on_next(value):
                if not is_busy[0]:
                    is_busy[0] = True
                    observer.on_next(value)
                    is_busy[0] = False
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def backpressure_error() -> Callable:
    """产生错误（缓冲区满时）
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source, max_size: int = 1):
        def subscribe(observer):
            buffer = []
            
            def on_next(value):
                if len(buffer) >= max_size:
                    observer.on_error(BufferError("Backpressure buffer overflow"))
                else:
                    buffer.append(value)
                    observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def backpressure_latest() -> Callable:
    """只保留最新项目
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            latest = [None]
            is_emitting = [False]
            
            def on_next(value):
                latest[0] = value
                if not is_emitting[0]:
                    is_emitting[0] = True
                    observer.on_next(value)
                    is_emitting[0] = False
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== 创新功能 ==========

def retry_with_backoff(max_retries: int = None, initial_delay: float = 1.0, max_delay: float = 60.0, multiplier: float = 2.0) -> Callable:
    """带退避的重试操作符（创新）
    
    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        multiplier: 延迟倍增器
    
    Returns:
        操作符函数
    
    Example:
        >>> obs.pipe(retry_with_backoff(max_retries=5, initial_delay=1.0))
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            retry_count = [0]
            task = [None]
            is_closed = [False]
            
            def schedule_retry(delay):
                async def retry():
                    await asyncio.sleep(delay)
                    if is_closed[0]:
                        return
                    
                    retry_count[0] += 1
                    current_delay = min(initial_delay * (multiplier ** (retry_count[0] - 1)), max_delay)
                    
                    sub = source.subscribe(
                        on_next=observer.on_next,
                        on_error=lambda e: (
                            observer.on_error(e) if max_retries and retry_count[0] >= max_retries
                            else schedule_retry(current_delay)
                        ),
                        on_completed=observer.on_completed
                    )
                    task[0] = sub
                
                if max_retries is None or retry_count[0] < max_retries:
                    task[0] = _asyncio_create_task(retry())
                else:
                    observer.on_completed()
            
            def on_error(err):
                if max_retries is None or retry_count[0] < max_retries:
                    schedule_retry(initial_delay)
                else:
                    observer.on_error(err)
            
            source_sub = source.subscribe(
                on_next=observer.on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                if task[0] and asyncio.isfuture(task[0]):
                    task[0].cancel()
                source_sub.unsubscribe()
            
            return Observable.Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def circuit_breaker(threshold: int = 5, reset_timeout: float = 60.0) -> Callable:
    """断路器模式（创新）
    
    Args:
        threshold: 失败阈值，达到后断路
        reset_timeout: 重置超时（秒）
    
    Returns:
        操作符函数
    
    Example:
        >>> obs.pipe(circuit_breaker(threshold=5, reset_timeout=30))
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            failure_count = [0]
            is_open = [False]
            task = [None]
            
            def reset():
                nonlocal failure_count, is_open
                failure_count[0] = 0
                is_open[0] = False
            
            def on_next(value):
                failure_count[0] = 0
                observer.on_next(value)
            
            def on_error(err):
                failure_count[0] += 1
                if failure_count[0] >= threshold:
                    is_open[0] = True
                    task[0] = _asyncio_create_task(asyncio.sleep(reset_timeout))
                    task[0].add_done_callback(lambda _: reset())
                observer.on_error(err)
            
            return source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def debounce_evolution(due_time: float, estimator: Callable[[T], float] = None) -> Callable:
    """进化的防抖操作符（创新）
    
    允许动态调整防抖时间。
    
    Args:
        due_time: 默认防抖时间
        estimator: 动态估算函数，接收前一个值，返回新的防抖时间
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            task = [None]
            last_value = [None]
            current_due_time = [due_time]
            is_closed = [False]
            
            async def emit():
                await asyncio.sleep(current_due_time[0])
                if is_closed[0]:
                    return
                if last_value[0] is not None:
                    observer.on_next(last_value[0])
                    last_value[0] = None
            
            def on_next(value):
                nonlocal task, current_due_time
                if task[0]:
                    task[0].cancel()
                if estimator:
                    current_due_time[0] = estimator(value)
                last_value[0] = value
                task[0] = _asyncio_create_task(emit())
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                if last_value[0] is not None:
                    observer.on_next(last_value[0])
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def cache(duration: float = None, max_size: int = None) -> Callable:
    """缓存操作符（创新）
    
    缓存发射的值，支持过期时间和最大缓存数。
    
    Args:
        duration: 缓存过期时间（秒），None 表示永不过期
        max_size: 最大缓存数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        cached_values = []
        cache_time = []
        subscriptions = []
        has_completed = [False]
        
        def subscribe(observer):
            if cached_values:
                for i, (value, t) in enumerate(zip(cached_values, cache_time)):
                    if duration and (time.time() - t) > duration:
                        continue
                    observer.on_next(value)
                if has_completed[0]:
                    observer.on_completed()
                    return
            
            def on_next(value):
                if max_size and len(cached_values) >= max_size:
                    cached_values.pop(0)
                    cache_time.pop(0)
                cached_values.append(value)
                cache_time.append(time.time())
                observer.on_next(value)
            
            def on_completed():
                has_completed[0] = True
                observer.on_completed()
            
            sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscriptions.append(sub)
            
            def unsubscribe():
                sub.unsubscribe()
                if sub in subscriptions:
                    subscriptions.remove(sub)
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def parallel(max_concurrent: int = 4) -> Callable:
    """并行处理操作符（创新）
    
    限制同时处理的并发数。
    
    Args:
        max_concurrent: 最大并发数
    
    Returns:
        操作符函数
    """
    from ..core.observable import Observable
    
    def operator(source):
        def subscribe(observer):
            executor = ThreadPoolExecutor(max_workers=max_concurrent)
            active_tasks = []
            pending = []
            is_closed = [False]
            
            def process_next():
                while len(active_tasks) < max_concurrent and pending:
                    value, future = pending.pop(0)
                    active_tasks.append(future)
                    
                    def done(f):
                        active_tasks.remove(f)
                        try:
                            result = f.result()
                            observer.on_next(result)
                        except Exception as e:
                            observer.on_error(e)
                        process_next()
                        if is_closed[0] and not active_tasks and not pending:
                            observer.on_completed()
                    
                    future.add_done_callback(done)
            
            def on_next(value):
                if asyncio.iscoroutine(value):
                    future = _asyncio_create_task(value)
                else:
                    future = executor.submit(lambda: value)
                pending.append((value, future))
                process_next()
            
            def on_completed():
                nonlocal is_closed
                is_closed[0] = True
                if not active_tasks and not pending:
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                for task in active_tasks:
                    if asyncio.isfuture(task):
                        task.cancel()
                    elif hasattr(task, 'cancel'):
                        task.cancel()
                executor.shutdown(wait=False)
                source_sub.unsubscribe()
            
            from ..core.observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator