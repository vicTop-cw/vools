"""
vools-reactive Operators

核心操作符实现，与 vools 生态深度集成:
- 支持 curry 部分应用
- 支持 placeholder 表达式
- 支持管道操作
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Generic, List, Dict, Set, Tuple
import asyncio
import time

from ..decorators import curry, lazy
from ..functional.placeholder import _
from ..functional.pipe_ops import P
from ..functional.iif import iif as iif_func
from .observable import Observable, Observer, Subscription
from .subject import Subject

T = TypeVar('T')
R = TypeVar('R')


def _parse_expr(expr: str, **env):
    """解析字符串表达式为可调用函数"""
    from ..functional.placeholder import _expr
    return _expr(expr, **env)


# ========== 基础操作符 ==========

def map(fn: Callable[[T], R] = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """映射操作符 - 支持普通函数、字符串表达式和预绑定参数"""
    
    # 支持字符串表达式: ops.map("x * 2", y=10)
    if isinstance(fn, str):
        fn = _parse_expr(fn, **kwargs)
    
    # 支持预绑定参数: ops.map(fn, x=1)
    elif kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            def on_next(value: T) -> None:
                try:
                    result = fn(value)
                    observer.on_next(result)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def filter(predicate: Callable[[T], bool] = None, **kwargs) -> Callable[[Observable[T]], Observable[T]]:
    """过滤操作符 - 支持普通函数、字符串表达式和预绑定参数"""
    
    # 支持字符串表达式
    if isinstance(predicate, str):
        predicate = _parse_expr(predicate, **kwargs)
    
    # 支持预绑定参数
    elif kwargs and predicate is not None:
        @curry
        def curried_fn(*args, **kw):
            return predicate(*args, **kw)
        predicate = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T) -> None:
                try:
                    if predicate(value):
                        observer.on_next(value)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def flat_map(fn: Callable[[T], Observable[R]] = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """扁平映射操作符"""
    
    if kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            subscription = Subscription(lambda: None)
            active_subscriptions = set()
            is_closed = False
            
            def on_next(value: T) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                
                try:
                    inner_fn = fn(value) if callable(fn) else fn
                    if isinstance(inner_fn, Observable):
                        inner_sub = inner_fn.subscribe(
                            on_next=observer.on_next,
                            on_error=observer.on_error,
                            on_completed=lambda: None
                        )
                        active_subscriptions.add(inner_sub)
                        subscription.add_child(inner_sub)
                    else:
                        observer.on_next(inner_fn)
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed = True
                while active_subscriptions:
                    sub = active_subscriptions.pop()
                    sub.unsubscribe()
                observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def concat_map(fn: Callable[[T], Observable[R]] = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """顺序连接映射操作符 - 按顺序订阅内部 Observable"""
    
    if kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            subscription = Subscription(lambda: None)
            is_closed = False
            is_emitting = False
            queue = []
            current_sub = None
            
            def subscribe_next():
                nonlocal is_emitting, current_sub
                if is_closed or is_emitting or not queue:
                    return
                
                is_emitting = True
                inner_obs = queue.pop(0)
                
                def on_inner_completed():
                    nonlocal is_emitting, current_sub
                    is_emitting = False
                    current_sub = None
                    subscribe_next()
                
                current_sub = inner_obs.subscribe(
                    on_next=observer.on_next,
                    on_error=observer.on_error,
                    on_completed=on_inner_completed
                )
                subscription.add_child(current_sub)
            
            def on_next(value: T) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                
                try:
                    inner_obs = fn(value) if callable(fn) else fn
                    queue.append(inner_obs)
                    subscribe_next()
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed = True
                if not is_emitting and not queue:
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def switch_map(fn: Callable[[T], Observable[R]] = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """切换映射操作符 - 切换到最新的内部 Observable"""
    
    if kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            subscription = Subscription(lambda: None)
            is_closed = False
            inner_sub = None
            
            def on_next(value: T) -> None:
                nonlocal is_closed, inner_sub
                if is_closed:
                    return
                
                try:
                    inner_obs = fn(value) if callable(fn) else fn
                    
                    if inner_sub:
                        inner_sub.unsubscribe()
                        subscription.remove_child(inner_sub)
                    
                    inner_sub = inner_obs.subscribe(
                        on_next=observer.on_next,
                        on_error=observer.on_error,
                        on_completed=lambda: None
                    )
                    subscription.add_child(inner_sub)
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed = True
                observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def concat(*sources: Observable[T]) -> Observable[T]:
    """连接多个 Observable"""
    def subscribe(observer: Observer[T]) -> Subscription:
        subscription = Subscription(lambda: None)
        source_iter = iter(sources)
        current_subscription = None
        is_closed = False
        
        def subscribe_next():
            nonlocal current_subscription, is_closed
            try:
                source = next(source_iter)
                current_sub = source.subscribe(
                    on_next=observer.on_next,
                    on_error=observer.on_error,
                    on_completed=subscribe_next
                )
                current_subscription = current_sub
                subscription.add_child(current_sub)
            except StopIteration:
                if not is_closed:
                    observer.on_completed()
            except Exception as e:
                if not is_closed:
                    observer.on_error(e)
        
        def unsubscribe():
            nonlocal is_closed
            is_closed = True
        
        subscription._unsubscribe = unsubscribe
        subscribe_next()
        
        return subscription
    
    return Observable(subscribe)


def merge(*sources: Observable[T]) -> Observable[T]:
    """合并多个 Observable"""
    def subscribe(observer: Observer[T]) -> Subscription:
        subscription = Subscription(lambda: None)
        completed_count = 0
        total_sources = len(sources)
        is_closed = False
        
        def on_completed():
            nonlocal completed_count, is_closed
            completed_count += 1
            if completed_count == total_sources and not is_closed:
                observer.on_completed()
        
        for source in sources:
            sub = source.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(sub)
        
        return subscription
    
    return Observable(subscribe)


def zip(*sources: Observable[Any]) -> Observable[Tuple]:
    """将多个 Observable 压缩成元组"""
    def subscribe(observer: Observer[Tuple]) -> Subscription:
        if not sources:
            observer.on_completed()
            return Subscription(lambda: None)
        
        subscription = Subscription(lambda: None)
        buffers = [[] for _ in sources]
        completed_count = 0
        total_sources = len(sources)
        is_closed = False
        
        def check_and_emit():
            nonlocal is_closed
            if is_closed:
                return
            
            min_len = min(len(buf) for buf in buffers)
            while min_len > 0:
                result = tuple(buf.pop(0) for buf in buffers)
                observer.on_next(result)
                min_len = min(len(buf) for buf in buffers)
        
        def make_on_next(index):
            def on_next(value):
                nonlocal is_closed
                if is_closed:
                    return
                buffers[index].append(value)
                check_and_emit()
            return on_next
        
        def on_completed():
            nonlocal completed_count, is_closed
            completed_count += 1
            if completed_count == total_sources and not is_closed:
                is_closed = True
                observer.on_completed()
        
        for i, source in enumerate(sources):
            sub = source.subscribe(
                on_next=make_on_next(i),
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(sub)
        
        return subscription
    
    return Observable(subscribe)


def combine_latest(*sources: Observable[Any]) -> Observable[Tuple]:
    """组合多个 Observable 的最新值
    
    当所有源都至少发出过一个值后，每当任一源发出新值时，
    发射所有源的最新值组成的元组。
    """
    def subscribe(observer: Observer[Tuple]) -> Subscription:
        if not sources:
            observer.on_completed()
            return Subscription(lambda: None)
        
        subscription = Subscription(lambda: None)
        latest_values = [None] * len(sources)
        has_emitted = [False] * len(sources)
        completed_count = 0
        total_sources = len(sources)
        is_closed = False
        is_initializing = True
        
        def try_emit():
            nonlocal is_closed, is_initializing
            if is_closed or is_initializing:
                return
            if all(has_emitted):
                observer.on_next(tuple(latest_values))
        
        def make_on_next(index):
            def on_next(value):
                nonlocal is_closed
                if is_closed:
                    return
                latest_values[index] = value
                has_emitted[index] = True
                try_emit()
            return on_next
        
        def on_completed():
            nonlocal completed_count, is_closed
            completed_count += 1
            if completed_count == total_sources and not is_closed:
                is_closed = True
                observer.on_completed()
        
        for i, source in enumerate(sources):
            sub = source.subscribe(
                on_next=make_on_next(i),
                on_error=observer.on_error,
                on_completed=on_completed
            )
            subscription.add_child(sub)
        
        is_initializing = False
        
        if all(has_emitted):
            observer.on_next(tuple(latest_values))
        
        return subscription
    
    return Observable(subscribe)


def with_latest_from(other: Observable[R]) -> Callable[[Observable[T]], Observable[Tuple[T, R]]]:
    """与另一个 Observable 的最新值组合"""
    def operator(source: Observable[T]) -> Observable[Tuple[T, R]]:
        def subscribe(observer: Observer[Tuple[T, R]]) -> Subscription:
            subscription = Subscription(lambda: None)
            latest_other = None
            has_other_value = False
            is_closed = False
            
            other_buffer = []
            
            other.subscribe(
                on_next=lambda x: other_buffer.append(x),
                on_error=lambda e: None,
                on_completed=lambda: None
            )
            
            if other_buffer:
                latest_other = other_buffer[-1]
                has_other_value = True
            
            def on_source_next(value):
                nonlocal is_closed
                if is_closed:
                    return
                if has_other_value:
                    observer.on_next((value, latest_other))
            
            def on_other_next(value):
                nonlocal latest_other, has_other_value, is_closed
                if is_closed:
                    return
                latest_other = value
                has_other_value = True
            
            source_sub = source.subscribe(
                on_next=on_source_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def take(n: int) -> Callable[[Observable[T]], Observable[T]]:
    """取前 n 个元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            counter = 0
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            def on_next(value: T) -> None:
                nonlocal counter, is_closed
                if is_closed:
                    return
                if counter < n:
                    observer.on_next(value)
                    counter += 1
                    if counter == n:
                        is_closed = True
                        observer.on_completed()
            
            def on_completed():
                nonlocal is_closed
                if not is_closed:
                    is_closed = True
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def skip(n: int) -> Callable[[Observable[T]], Observable[T]]:
    """跳过前 n 个元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            counter = 0
            
            def on_next(value: T) -> None:
                nonlocal counter
                if counter >= n:
                    observer.on_next(value)
                else:
                    counter += 1
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def first(predicate: Optional[Callable[[T], bool]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """取第一个元素，或第一个满足条件的元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            def on_next(value: T) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                
                try:
                    if predicate is None or predicate(value):
                        is_closed = True
                        observer.on_next(value)
                        observer.on_completed()
                except Exception as e:
                    is_closed = True
                    observer.on_error(e)
            
            def on_completed():
                nonlocal is_closed
                if not is_closed:
                    is_closed = True
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            def cleanup():
                unsubscribe()
                source_sub.unsubscribe()
            
            return Subscription(cleanup)
        
        return Observable(subscribe)
    
    return operator


def last(predicate: Optional[Callable[[T], bool]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """取最后一个元素，或最后一个满足条件的元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_value = None
            has_value = False
            
            def on_next(value: T) -> None:
                nonlocal last_value, has_value
                try:
                    if predicate is None or predicate(value):
                        last_value = value
                        has_value = True
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                if has_value:
                    observer.on_next(last_value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def distinct(key_fn: Optional[Callable[[T], Any]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """过滤重复元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            seen = set()
            
            def on_next(value: T) -> None:
                nonlocal seen
                try:
                    key = key_fn(value) if key_fn else value
                    if key not in seen:
                        seen.add(key)
                        observer.on_next(value)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def element_at(index: int) -> Callable[[Observable[T]], Observable[T]]:
    """取指定索引位置的元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            counter = 0
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            def on_next(value: T) -> None:
                nonlocal counter, is_closed
                if is_closed:
                    return
                if counter == index:
                    is_closed = True
                    observer.on_next(value)
                    observer.on_completed()
                else:
                    counter += 1
            
            def on_completed():
                nonlocal is_closed
                if not is_closed:
                    is_closed = True
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            def cleanup():
                unsubscribe()
                source_sub.unsubscribe()
            
            return Subscription(cleanup)
        
        return Observable(subscribe)
    
    return operator


def take_until(other: Observable[Any]) -> Callable[[Observable[T]], Observable[T]]:
    """取元素直到另一个 Observable 发出值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            is_stopped = False
            
            def on_other_next(value):
                nonlocal is_stopped
                is_stopped = True
                observer.on_completed()
            
            def on_source_next(value: T) -> None:
                if not is_stopped:
                    observer.on_next(value)
            
            other_sub = other.subscribe(
                on_next=on_other_next,
                on_error=observer.on_error,
                on_completed=lambda: None
            )
            subscription.add_child(other_sub)
            
            source_sub = source.subscribe(
                on_next=on_source_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def take_while(predicate: Callable[[T], bool] = None, **kwargs) -> Callable[[Observable[T]], Observable[T]]:
    """取元素直到条件不满足"""
    if isinstance(predicate, str):
        predicate = _parse_expr(predicate, **kwargs)
    elif kwargs and predicate is not None:
        @curry
        def curried_fn(*args, **kw):
            return predicate(*args, **kw)
        predicate = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            is_stopped = False
            
            def on_next(value: T) -> None:
                nonlocal is_stopped
                if is_stopped:
                    return
                try:
                    if predicate(value):
                        observer.on_next(value)
                    else:
                        is_stopped = True
                        observer.on_completed()
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                nonlocal is_stopped
                if not is_stopped:
                    is_stopped = True
                    observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            return source_sub
        
        return Observable(subscribe)
    
    return operator


def skip_while(predicate: Callable[[T], bool] = None, **kwargs) -> Callable[[Observable[T]], Observable[T]]:
    """跳过元素直到条件不满足"""
    if isinstance(predicate, str):
        predicate = _parse_expr(predicate, **kwargs)
    elif kwargs and predicate is not None:
        @curry
        def curried_fn(*args, **kw):
            return predicate(*args, **kw)
        predicate = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            is_skipping = True
            
            def on_next(value: T) -> None:
                nonlocal is_skipping
                if is_skipping:
                    try:
                        if not predicate(value):
                            is_skipping = False
                            observer.on_next(value)
                    except Exception as e:
                        observer.on_error(e)
                else:
                    observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def distinct_until_changed(key_fn: Optional[Callable[[T], Any]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """去除连续重复元素"""
    key_fn = key_fn or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_key = None
            is_first = True
            
            def on_next(value: T) -> None:
                nonlocal last_key, is_first
                try:
                    current_key = key_fn(value)
                    if is_first or current_key != last_key:
                        last_key = current_key
                        is_first = False
                        observer.on_next(value)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def group_by(key_fn: Callable[[T], Any]) -> Callable[[Observable[T]], Observable[Observable[T]]]:
    """按键分组操作符"""
    def operator(source: Observable[T]) -> Observable[Observable[T]]:
        def subscribe(observer: Observer[Observable[T]]) -> Subscription:
            groups: Dict[Any, Observable[T]] = {}
            
            def get_or_create_group(key: Any) -> Observable[T]:
                if key not in groups:
                    inner_observer = _GroupedObserver()
                    groups[key] = Observable(inner_observer.subscribe)
                    observer.on_next(groups[key])
                return groups[key]
            
            def on_next(value: T) -> None:
                try:
                    key = key_fn(value)
                    group = get_or_create_group(key)
                    group._subscribe_fn(inner_observer)
                except Exception as e:
                    observer.on_error(e)
            
            inner_observer = _GroupedObserver()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            
            return source_sub
        
        return Observable(subscribe)
    
    return operator


class _GroupedObserver(Observer[T]):
    """分组观察者"""
    def __init__(self):
        self._values: List[T] = []
        self._observers: List[Observer[T]] = []
    
    def subscribe(self, observer: Observer[T]) -> Subscription:
        for value in self._values:
            observer.on_next(value)
        self._observers.append(observer)
        
        def unsubscribe():
            if observer in self._observers:
                self._observers.remove(observer)
        
        return Subscription(unsubscribe)


def debounce(delay: float) -> Callable[[Observable[T]], Observable[T]]:
    """防抖操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            timer = None
            last_value = None
            
            def fire():
                nonlocal timer, last_value
                timer = None
                if last_value is not None:
                    observer.on_next(last_value)
                    last_value = None
            
            def on_next(value: T) -> None:
                nonlocal timer, last_value
                last_value = value
                if timer:
                    timer.cancel()
                timer = asyncio.get_event_loop().call_later(delay, fire)
            
            def on_completed():
                nonlocal timer
                if timer:
                    timer.cancel()
                    timer = None
                if last_value is not None:
                    observer.on_next(last_value)
                observer.on_completed()
            
            def unsubscribe():
                nonlocal timer
                if timer:
                    timer.cancel()
                    timer = None
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            subscription = Subscription(unsubscribe)
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def throttle_first(delay: float) -> Callable[[Observable[T]], Observable[T]]:
    """节流操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_emit_time = -float('inf')
            
            def on_next(value: T) -> None:
                nonlocal last_emit_time
                now = asyncio.get_event_loop().time()
                if now - last_emit_time >= delay:
                    last_emit_time = now
                    observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def catch(handler: Callable[[Exception], Observable[T]] = None, fallback: Observable[T] = None) -> Callable[[Observable[T]], Observable[T]]:
    """错误恢复操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            using_fallback = False
            fallback_source = fallback
            handler_fn = handler
            
            def on_error(error: Exception) -> None:
                nonlocal using_fallback
                if using_fallback:
                    observer.on_error(error)
                    return
                
                try:
                    if fallback_source is not None:
                        using_fallback = True
                        fallback_sub = fallback_source.subscribe(
                            on_next=observer.on_next,
                            on_error=observer.on_error,
                            on_completed=observer.on_completed
                        )
                        subscription.add_child(fallback_sub)
                    elif handler_fn is not None:
                        using_fallback = True
                        fallback_obs = handler_fn(error)
                        if isinstance(fallback_obs, Observable):
                            fallback_sub = fallback_obs.subscribe(
                                on_next=observer.on_next,
                                on_error=observer.on_error,
                                on_completed=observer.on_completed
                            )
                            subscription.add_child(fallback_sub)
                    else:
                        observer.on_error(error)
                except Exception as e:
                    observer.on_error(e)
            
            source_sub = source.subscribe(
                on_next=observer.on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def retry(times: int = -1) -> Callable[[Observable[T]], Observable[T]]:
    """重试操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            attempt = 0
            
            def do_subscribe():
                nonlocal attempt
                attempt += 1
                
                def on_error(error: Exception) -> None:
                    nonlocal attempt
                    if times == -1 or attempt < times:
                        do_subscribe()
                    else:
                        observer.on_error(error)
                
                sub = source.subscribe(
                    on_next=observer.on_next,
                    on_error=on_error,
                    on_completed=observer.on_completed
                )
                subscription.add_child(sub)
            
            do_subscribe()
            return subscription
        
        return Observable(subscribe)
    
    return operator


def on_error_return(value: T) -> Callable[[Observable[T]], Observable[T]]:
    """错误时返回指定值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_error(error: Exception) -> None:
                observer.on_next(value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=observer.on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def on_error_resume_next(next_source: Observable[T]) -> Callable[[Observable[T]], Observable[T]]:
    """错误时切换到下一个 Observable"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            using_fallback = False
            
            def on_error(error: Exception) -> None:
                nonlocal using_fallback
                if using_fallback:
                    observer.on_error(error)
                    return
                
                using_fallback = True
                fallback_sub = next_source.subscribe(
                    on_next=observer.on_next,
                    on_error=observer.on_error,
                    on_completed=observer.on_completed
                )
                subscription.add_child(fallback_sub)
            
            source_sub = source.subscribe(
                on_next=observer.on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def retry_when(notifier: Callable[[Observable[Exception]], Observable[Any]]) -> Callable[[Observable[T]], Observable[T]]:
    """根据错误通知决定是否重试"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            error_subject = Subject()
            
            def handle_error(error: Exception) -> None:
                error_subject.on_next(error)
            
            def on_notifier_next(value: Any) -> None:
                do_subscribe()
            
            def on_notifier_error(error: Exception) -> None:
                observer.on_error(error)
            
            notifier_sub = notifier(error_subject).subscribe(
                on_next=on_notifier_next,
                on_error=on_notifier_error
            )
            subscription.add_child(notifier_sub)
            
            def do_subscribe():
                sub = source.subscribe(
                    on_next=observer.on_next,
                    on_error=handle_error,
                    on_completed=observer.on_completed
                )
                subscription.add_child(sub)
            
            do_subscribe()
            return subscription
        
        return Observable(subscribe)
    
    return operator


def sum(key_mapper: Optional[Callable[[T], float]] = None) -> Callable[[Observable[T]], Observable[float]]:
    """求和操作符"""
    key_mapper = key_mapper or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            total = 0.0
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal total, is_empty
                try:
                    total += key_mapper(value)
                    is_empty = False
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                if not is_empty:
                    observer.on_next(total)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def average(key_mapper: Optional[Callable[[T], float]] = None) -> Callable[[Observable[T]], Observable[float]]:
    """求平均操作符"""
    key_mapper = key_mapper or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[float]:
        def subscribe(observer: Observer[float]) -> Subscription:
            total = 0.0
            count = 0
            
            def on_next(value: T) -> None:
                nonlocal total, count
                try:
                    total += key_mapper(value)
                    count += 1
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                if count > 0:
                    observer.on_next(total / count)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def minimum(key_mapper: Optional[Callable[[T], float]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """求最小值操作符"""
    key_mapper = key_mapper or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            min_value = None
            min_key = None
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal min_value, min_key, is_empty
                try:
                    key = key_mapper(value)
                    if is_empty or key < min_key:
                        min_value = value
                        min_key = key
                    is_empty = False
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                if not is_empty:
                    observer.on_next(min_value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def maximum(key_mapper: Optional[Callable[[T], float]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """求最大值操作符"""
    key_mapper = key_mapper or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            max_value = None
            max_key = None
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal max_value, max_key, is_empty
                try:
                    key = key_mapper(value)
                    if is_empty or key > max_key:
                        max_value = value
                        max_key = key
                    is_empty = False
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                if not is_empty:
                    observer.on_next(max_value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def reduce(accumulator: Callable[[R, T], R] = None, initial: R = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """归约操作符"""
    if kwargs and accumulator is not None:
        @curry
        def curried_fn(*args, **kw):
            return accumulator(*args, **kw)
        accumulator = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            accum = initial
            is_first = initial is None
            
            def on_next(value: T) -> None:
                nonlocal accum, is_first
                try:
                    if is_first:
                        accum = value
                        is_first = False
                    else:
                        accum = accumulator(accum, value)
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                if not is_first:
                    observer.on_next(accum)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def scan(accumulator: Callable[[R, T], R], initial: R) -> Callable[[Observable[T]], Observable[R]]:
    """扫描操作符"""
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            accum = initial
            observer.on_next(accum)
            
            def on_next(value: T) -> None:
                nonlocal accum
                try:
                    accum = accumulator(accum, value)
                    observer.on_next(accum)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def count() -> Callable[[Observable[T]], Observable[int]]:
    """计数操作符"""
    def operator(source: Observable[T]) -> Observable[int]:
        def subscribe(observer: Observer[int]) -> Subscription:
            counter = 0
            
            def on_next(value: T) -> None:
                nonlocal counter
                counter += 1
            
            def on_completed() -> None:
                observer.on_next(counter)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def all(predicate: Callable[[T], bool]) -> Callable[[Observable[T]], Observable[bool]]:
    """判断所有元素是否满足条件"""
    def operator(source: Observable[T]) -> Observable[bool]:
        def subscribe(observer: Observer[bool]) -> Subscription:
            all_match = True
            is_empty = True
            
            def on_next(value: T) -> None:
                nonlocal all_match, is_empty
                is_empty = False
                try:
                    if not predicate(value):
                        all_match = False
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                observer.on_next(all_match and not is_empty)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def any(predicate: Callable[[T], bool] = None) -> Callable[[Observable[T]], Observable[bool]]:
    """判断是否有元素满足条件"""
    predicate = predicate or (lambda x: x)
    
    def operator(source: Observable[T]) -> Observable[bool]:
        def subscribe(observer: Observer[bool]) -> Subscription:
            any_match = False
            
            def on_next(value: T) -> None:
                nonlocal any_match
                try:
                    if predicate(value):
                        any_match = True
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed() -> None:
                observer.on_next(any_match)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def contains(value: T) -> Callable[[Observable[T]], Observable[bool]]:
    """判断是否包含指定元素"""
    def operator(source: Observable[T]) -> Observable[bool]:
        def subscribe(observer: Observer[bool]) -> Subscription:
            found = False
            
            def on_next(item: T) -> None:
                nonlocal found
                if item == value:
                    found = True
            
            def on_completed() -> None:
                observer.on_next(found)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def is_empty() -> Callable[[Observable[T]], Observable[bool]]:
    """判断 Observable 是否为空"""
    def operator(source: Observable[T]) -> Observable[bool]:
        def subscribe(observer: Observer[bool]) -> Subscription:
            is_empty_val = True
            
            def on_next(value: T) -> None:
                nonlocal is_empty_val
                is_empty_val = False
            
            def on_completed() -> None:
                observer.on_next(is_empty_val)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def to_list() -> Callable[[Observable[T]], Observable[List[T]]]:
    """转换为列表"""
    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            items = []
            
            def on_next(value: T) -> None:
                items.append(value)
            
            def on_completed() -> None:
                observer.on_next(items)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def buffer(buffer_size: int) -> Callable[[Observable[T]], Observable[List[T]]]:
    """缓冲操作符"""
    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            buf = []
            
            def on_next(value: T) -> None:
                buf.append(value)
                if len(buf) >= buffer_size:
                    observer.on_next(buf.copy())
                    buf.clear()
            
            def on_completed() -> None:
                if buf:
                    observer.on_next(buf)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def tap(fn: Callable[[T], Any] = None, **kwargs) -> Callable[[Observable[T]], Observable[T]]:
    """轻触操作符 - 用于调试"""
    if isinstance(fn, str):
        fn = _parse_expr(fn, **kwargs)
    elif kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T) -> None:
                if fn is not None:
                    fn(value)
                observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def timeout(timeout_duration: float) -> Callable[[Observable[T]], Observable[T]]:
    """超时操作符 - 如果指定时间内没有发射则发出错误"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            timeout_task = None
            is_timed_out = False
            
            def on_timeout():
                nonlocal is_timed_out
                is_timed_out = True
                observer.on_error(TimeoutError("Observable timeout"))
            
            def reset_timeout():
                nonlocal timeout_task
                if timeout_task:
                    timeout_task.cancel()
                timeout_task = asyncio.create_task(asyncio.sleep(timeout_duration))
                timeout_task.add_done_callback(lambda _: on_timeout())
            
            def on_next(value: T) -> None:
                if not is_timed_out:
                    reset_timeout()
                    observer.on_next(value)
            
            def on_completed():
                nonlocal is_timed_out
                if not is_timed_out:
                    is_timed_out = True
                    if timeout_task:
                        timeout_task.cancel()
                    observer.on_completed()
            
            def on_error(error):
                nonlocal is_timed_out
                if not is_timed_out:
                    is_timed_out = True
                    if timeout_task:
                        timeout_task.cancel()
                    observer.on_error(error)
            
            reset_timeout()
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed
            )
            subscription.add_child(source_sub)
            
            def cleanup():
                nonlocal is_timed_out
                is_timed_out = True
                if timeout_task:
                    timeout_task.cancel()
            
            subscription._unsubscribe = cleanup
            return subscription
        
        return Observable(subscribe)
    
    return operator


def timestamp() -> Callable[[Observable[T]], Observable[Tuple[T, float]]]:
    """为每个元素添加时间戳"""
    def operator(source: Observable[T]) -> Observable[Tuple[T, float]]:
        def subscribe(observer: Observer[Tuple[T, float]]) -> Subscription:
            def on_next(value: T) -> None:
                observer.on_next((value, time.time()))
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def skip_until(other: Observable[Any]) -> Callable[[Observable[T]], Observable[T]]:
    """跳过元素直到另一个 Observable 发出值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            has_triggered = False
            
            def on_other_next(value):
                nonlocal has_triggered
                has_triggered = True
            
            def on_source_next(value: T) -> None:
                if has_triggered:
                    observer.on_next(value)
            
            other_sub = other.subscribe(
                on_next=on_other_next,
                on_error=observer.on_error,
                on_completed=lambda: None
            )
            subscription.add_child(other_sub)
            
            source_sub = source.subscribe(
                on_next=on_source_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            subscription.add_child(source_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def default_if_empty(default_value: T) -> Callable[[Observable[T]], Observable[T]]:
    """如果 Observable 为空则发出默认值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            has_value = False
            
            def on_next(value: T) -> None:
                nonlocal has_value
                has_value = True
                observer.on_next(value)
            
            def on_completed():
                if not has_value:
                    observer.on_next(default_value)
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def sequence_equal(other: Observable[T]) -> Callable[[Observable[T]], Observable[bool]]:
    """判断两个 Observable 是否发出相同的序列"""
    def operator(source: Observable[T]) -> Observable[bool]:
        def subscribe(observer: Observer[bool]) -> Subscription:
            source_buffer = []
            other_buffer = []
            source_completed = False
            other_completed = False
            
            def check_equal():
                nonlocal source_completed, other_completed
                if source_completed and other_completed:
                    observer.on_next(source_buffer == other_buffer)
                    observer.on_completed()
            
            def on_source_next(value: T) -> None:
                source_buffer.append(value)
            
            def on_source_completed():
                nonlocal source_completed
                source_completed = True
                check_equal()
            
            def on_other_next(value: T) -> None:
                other_buffer.append(value)
            
            def on_other_completed():
                nonlocal other_completed
                other_completed = True
                check_equal()
            
            source_sub = source.subscribe(
                on_next=on_source_next,
                on_error=observer.on_error,
                on_completed=on_source_completed
            )
            
            other_sub = other.subscribe(
                on_next=on_other_next,
                on_error=observer.on_error,
                on_completed=on_other_completed
            )
            
            subscription = Subscription(lambda: None)
            subscription.add_child(source_sub)
            subscription.add_child(other_sub)
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def delay(delay_time: float) -> Callable[[Observable[T]], Observable[T]]:
    """延迟发射操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            subscription = Subscription(lambda: None)
            pending_items = []
            is_closed = False
            
            def on_next(value: T) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                scheduled_time = asyncio.get_event_loop().time() + delay_time
                pending_items.append((scheduled_time, value, 'next'))
                schedule_next()
            
            def on_error(error: Exception) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                scheduled_time = asyncio.get_event_loop().time() + delay_time
                pending_items.append((scheduled_time, error, 'error'))
                schedule_next()
            
            def on_completed() -> None:
                nonlocal is_closed
                if is_closed:
                    return
                scheduled_time = asyncio.get_event_loop().time() + delay_time
                pending_items.append((scheduled_time, None, 'completed'))
                schedule_next()
            
            timer = None
            
            def schedule_next():
                nonlocal timer
                if timer:
                    timer.cancel()
                    timer = None
                
                if not pending_items or is_closed:
                    return
                
                pending_items.sort()
                scheduled_time, item, kind = pending_items.pop(0)
                now = asyncio.get_event_loop().time()
                wait_time = max(0, scheduled_time - now)
                
                def fire():
                    nonlocal timer
                    timer = None
                    if is_closed:
                        return
                    if kind == 'next':
                        observer.on_next(item)
                    elif kind == 'error':
                        observer.on_error(item)
                    elif kind == 'completed':
                        observer.on_completed()
                    schedule_next()
                
                timer = asyncio.get_event_loop().call_later(wait_time, fire)
            
            def unsubscribe():
                nonlocal is_closed, timer
                is_closed = True
                if timer:
                    timer.cancel()
                    timer = None
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed
            )
            subscription.add_child(source_sub)
            subscription._unsubscribe = unsubscribe
            
            return subscription
        
        return Observable(subscribe)
    
    return operator


def start_with(*initial_values: T) -> Callable[[Observable[T]], Observable[T]]:
    """在序列开头添加初始值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            for value in initial_values:
                observer.on_next(value)
            return source.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        return Observable(subscribe)
    return operator


def end_with(*final_values: T) -> Callable[[Observable[T]], Observable[T]]:
    """在序列结尾添加最终值"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_completed():
                for value in final_values:
                    observer.on_next(value)
                observer.on_completed()
            return source.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        return Observable(subscribe)
    return operator


# ========== vools 集成操作符 ==========

def curry_map(fn: Callable[..., Any], *args, **kwargs) -> Callable[[Observable[T]], Observable[Any]]:
    """使用 curry 的 map 操作符"""
    @curry
    def curried_fn(*c_args, **c_kwargs):
        return fn(*c_args, *args, **c_kwargs, **kwargs)
    
    return map(curried_fn)


def lazy_flat_map(lazy_fn: Callable[[T], Any] = None, **kwargs) -> Callable[[Observable[T]], Observable[Any]]:
    """使用 lazy 的 flat_map 操作符"""
    def operator(source: Observable[T]) -> Observable[Any]:
        def subscribe(observer: Observer[Any]) -> Subscription:
            def on_next(value: T) -> None:
                try:
                    fn = lazy_fn(value) if callable(lazy_fn) else lazy_fn
                    result = lazy(fn)()
                    if isinstance(result, Observable):
                        result.subscribe(
                            on_next=observer.on_next,
                            on_error=observer.on_error,
                            on_completed=lambda: None
                        )
                    else:
                        observer.on_next(result)
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def seq_bridge(seq_op: Callable) -> Callable[[Observable[T]], Observable[Any]]:
    """Seq 操作桥接器"""
    def operator(source: Observable[T]) -> Observable[Any]:
        from ..data import Seq
        
        def subscribe(observer: Observer[Any]) -> Subscription:
            buf = []
            
            def on_next(value: T) -> None:
                buf.append(value)
            
            def on_completed() -> None:
                try:
                    result = seq_op(Seq(buf))
                    if hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
                        for item in result:
                            observer.on_next(item)
                    else:
                        observer.on_next(result)
                    observer.on_completed()
                except Exception as e:
                    observer.on_error(e)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def iif(condition=None, true_body=None, false_body=None) -> Callable[[Observable[T]], Observable[T]]:
    """响应式条件操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T) -> None:
                result = iif_func(condition, true_body, false_body, data=value)
                observer.on_next(result)
            
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


# ========== Additional Filtering Operators ==========

def throttle_latest(period: float) -> Callable[[Observable[T]], Observable[T]]:
    """在时间窗口内取最新值
    
    Args:
        period: 时间窗口（秒）
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
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
            
            def on_next(value: T) -> None:
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err) -> None:
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_error(err)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            task[0] = asyncio.create_task(emit_latest())
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                source_sub.unsubscribe()
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def skip_last(n: int) -> Callable[[Observable[T]], Observable[T]]:
    """跳过最后 n 个项目
    
    Args:
        n: 要跳过的项目数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            buffer = []
            
            def on_next(value: T) -> None:
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


def take_last(n: int) -> Callable[[Observable[T]], Observable[T]]:
    """只取最后 n 个项目
    
    Args:
        n: 要取的项目数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            buffer = []
            
            def on_next(value: T) -> None:
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


def ignore_elements() -> Callable[[Observable[T]], Observable[T]]:
    """不发出任何项目，只传递终止通知
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            return source.subscribe(
                on_next=lambda _: None,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def sample(period: float) -> Callable[[Observable[T]], Observable[T]]:
    """在周期时间间隔内发出最近一次发出的项目
    
    Args:
        period: 采样周期（秒）
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
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
            
            def on_next(value: T) -> None:
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err) -> None:
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_error(err)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            task[0] = asyncio.create_task(emit_sample())
            
            def unsubscribe():
                nonlocal is_closed
                is_closed[0] = True
                if task[0]:
                    task[0].cancel()
                source_sub.unsubscribe()
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


# ========== Additional Mathematical Operators ==========

def to_map(key_fn: Optional[Callable[[T], K]] = None) -> Callable[[Observable[T]], Observable[Dict[K, T]]]:
    """转换为 Map
    
    Args:
        key_fn: 键提取函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[Dict[K, T]]:
        def subscribe(observer: Observer[Dict[K, T]]) -> Subscription:
            result = {}
            
            def on_next(value: T) -> None:
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


def to_set() -> Callable[[Observable[T]], Observable[Set[T]]]:
    """转换为 Set
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[Set[T]]:
        def subscribe(observer: Observer[Set[T]]) -> Subscription:
            result = set()
            
            def on_next(value: T) -> None:
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


# ========== Do Operators ==========

def do_on_next(fn: Callable[[T], None]) -> Callable[[Observable[T]], Observable[T]]:
    """在每个 next 事件时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T) -> None:
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


def do_on_error(fn: Callable[[Exception], None]) -> Callable[[Observable[T]], Observable[T]]:
    """在错误发生时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_error(err: Exception) -> None:
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


def do_on_completed(fn: Callable[[], None]) -> Callable[[Observable[T]], Observable[T]]:
    """在完成时执行
    
    Args:
        fn: 要执行的函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_completed() -> None:
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


# ========== Additional Utility Operators ==========

def observe_on(scheduler) -> Callable[[Observable[T]], Observable[T]]:
    """指定观察者使用的调度器
    
    Args:
        scheduler: 调度器实例
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(value: T) -> None:
                scheduler.schedule(lambda v=value: observer.on_next(v))
            
            def on_error(err) -> None:
                scheduler.schedule(lambda e=err: observer.on_error(e))
            
            def on_completed() -> None:
                scheduler.schedule(observer.on_completed)
            
            return source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def subscribe_on(scheduler) -> Callable[[Observable[T]], Observable[T]]:
    """指定订阅使用的调度器
    
    Args:
        scheduler: 调度器实例
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def subscribe_inner():
                return source.subscribe(observer)
            
            scheduler.schedule(subscribe_inner)
            
            return Subscription(lambda: None)
        
        return Observable(subscribe)
    
    return operator


def time_interval() -> Callable[[Observable[T]], Observable[Tuple[T, float]]]:
    """转换为发出排放之间的时间
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[Tuple[T, float]]:
        def subscribe(observer: Observer[Tuple[T, float]]) -> Subscription:
            last_time = [time.time()]
            
            def on_next(value: T) -> None:
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


# ========== Additional Transforming Operators ==========

def flat_map_latest(fn: Callable[[T], Observable[U]]) -> Callable[[Observable[T]], Observable[U]]:
    """只处理最新的内部 Observable
    
    Args:
        fn: 映射函数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[U]:
        def subscribe(observer: Observer[U]) -> Subscription:
            inner_sub = [None]
            is_closed = [False]
            
            def on_next(value: T) -> None:
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
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def window(window_size: int) -> Callable[[Observable[T]], Observable[Observable[T]]]:
    """定期将项目细分为 Observable 窗口
    
    Args:
        window_size: 窗口大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[Observable[T]]:
        def subscribe(observer: Observer[Observable[T]]) -> Subscription:
            buffer = []
            is_closed = [False]
            
            def emit_window():
                if buffer:
                    window_obs = Observable.from_iterable(buffer[:])
                    observer.on_next(window_obs)
                    buffer.clear()
            
            def on_next(value: T) -> None:
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


# ========== Additional Combining Operators ==========

def amb(*sources: Observable[T]) -> Observable[T]:
    """选择第一个发出项目的 Observable
    
    Returns:
        操作符函数
    """
    def subscribe(observer: Observer[T]) -> Subscription:
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
        
        return Subscription(unsubscribe)
    
    return Observable(subscribe)


def switch() -> Callable[[Observable[Observable[T]]], Observable[T]]:
    """将发出 Observables 的 Observable 转换为单个
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[Observable[T]]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            inner_sub = [None]
            is_closed = [False]
            
            def on_next(value: Observable[T]) -> None:
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
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


# ========== Backpressure Operators ==========

def backpressure_buffer(max_size: int = None) -> Callable[[Observable[T]], Observable[T]]:
    """缓冲背压项目
    
    Args:
        max_size: 最大缓冲区大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            buffer = []
            is_paused = [False]
            is_closed = [False]
            
            def drain():
                while buffer and not is_paused[0]:
                    if buffer:
                        observer.on_next(buffer.pop(0))
                if is_closed[0] and not buffer:
                    observer.on_completed()
            
            def on_next(value: T) -> None:
                if max_size and len(buffer) >= max_size:
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


def backpressure_drop() -> Callable[[Observable[T]], Observable[T]]:
    """丢弃多余项目
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            is_busy = [False]
            
            def on_next(value: T) -> None:
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


def backpressure_error(max_size: int = 1) -> Callable[[Observable[T]], Observable[T]]:
    """产生错误（缓冲区满时）
    
    Args:
        max_size: 最大缓冲区大小
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            buffer = []
            
            def on_next(value: T) -> None:
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


def backpressure_latest() -> Callable[[Observable[T]], Observable[T]]:
    """只保留最新项目
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            latest = [None]
            is_emitting = [False]
            
            def on_next(value: T) -> None:
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


# ========== Innovation Features ==========

def retry_with_backoff(max_retries: int = None, initial_delay: float = 1.0, max_delay: float = 60.0, multiplier: float = 2.0) -> Callable[[Observable[T]], Observable[T]]:
    """带退避的重试操作符（创新）
    
    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        multiplier: 延迟倍增器
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
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
                    task[0] = asyncio.create_task(retry())
                else:
                    observer.on_completed()
            
            def on_error(err) -> None:
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
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def circuit_breaker(threshold: int = 5, reset_timeout: float = 60.0) -> Callable[[Observable[T]], Observable[T]]:
    """断路器模式（创新）
    
    Args:
        threshold: 失败阈值，达到后断路
        reset_timeout: 重置超时（秒）
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            failure_count = [0]
            is_open = [False]
            task = [None]
            
            def reset():
                failure_count[0] = 0
                is_open[0] = False
            
            def on_next(value: T) -> None:
                failure_count[0] = 0
                observer.on_next(value)
            
            def on_error(err: Exception) -> None:
                failure_count[0] += 1
                if failure_count[0] >= threshold:
                    is_open[0] = True
                    task[0] = asyncio.create_task(asyncio.sleep(reset_timeout))
                    task[0].add_done_callback(lambda _: reset())
                observer.on_error(err)
            
            return source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def debounce_evolution(due_time: float, estimator: Callable[[T], float] = None) -> Callable[[Observable[T]], Observable[T]]:
    """进化的防抖操作符（创新）
    
    允许动态调整防抖时间。
    
    Args:
        due_time: 默认防抖时间
        estimator: 动态估算函数，接收前一个值，返回新的防抖时间
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
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
            
            def on_next(value: T) -> None:
                nonlocal task, current_due_time
                if task[0]:
                    task[0].cancel()
                if estimator:
                    current_due_time[0] = estimator(value)
                last_value[0] = value
                task[0] = asyncio.create_task(emit())
            
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


def cache(duration: float = None, max_size: int = None) -> Callable[[Observable[T]], Observable[T]]:
    """缓存操作符（创新）
    
    缓存发射的值，支持过期时间和最大缓存数。
    
    Args:
        duration: 缓存过期时间（秒），None 表示永不过期
        max_size: 最大缓存数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        cached_values = []
        cache_time = []
        has_completed = [False]
        
        def subscribe(observer: Observer[T]) -> Subscription:
            if cached_values:
                for i, (value, t) in enumerate(zip(cached_values, cache_time)):
                    if duration and (time.time() - t) > duration:
                        continue
                    observer.on_next(value)
                if has_completed[0]:
                    observer.on_completed()
                    return
            
            def on_next(value: T) -> None:
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
            
            def unsubscribe():
                sub.unsubscribe()
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def parallel(max_concurrent: int = 4) -> Callable[[Observable[T]], Observable[T]]:
    """并行处理操作符（创新）
    
    限制同时处理的并发数。
    
    Args:
        max_concurrent: 最大并发数
    
    Returns:
        操作符函数
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            from concurrent.futures import ThreadPoolExecutor
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
                    future = asyncio.create_task(value)
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
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator
