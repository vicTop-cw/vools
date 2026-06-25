"""
vools-reactive Operators

核心操作符实现，与 vools 生态深度集成:
- 支持 curry 部分应用
- 支持 placeholder 表达式
- 支持管道操作
"""

from typing import TypeVar, Callable, Optional, Any, Generic, List, Dict, Set, Tuple, Union, Iterable
import asyncio
import time as _time
import inspect
import threading as _threading
import builtins

from ...core.asyncio_compat import create_task as _asyncio_create_task
from ...decorators import curry, lazy
from ...functional.placeholder import _
from ...functional.pipe_ops import P
from ...functional.iif import iif as iif_func
from ..core.observable import Observable, Observer, Subscription
from ..core.subject import Subject

T = TypeVar('T')
R = TypeVar('R')
K = TypeVar('K')
V = TypeVar('V')
U = TypeVar('U')
S = TypeVar('S')


def _parse_expr(expr: str, **env):
    """解析字符串表达式为可调用函数"""
    from ...functional.arrow_func import g
    import re
    pattern1 = r'(?<!\w)_(?!\w)'
    pattern2 = r'(?<!\w)_(0*[1-9]\d*)(?!\w)'
    if not re.search(pattern1, expr) and not re.search(pattern2, expr) and not '=>' in expr and not expr.strip().startswith('lambda'):
        if re.search(r'\b[a-zA-Z_]\w*\b', expr):
            return g(f"x => {expr}", env)
    return g(expr, env=env)


# ========== 基础操作符 ==========

def map(fn: Callable[[T], R] = None, **kwargs) -> Callable[[Observable[T]], Observable[R]]:
    """映射操作符 - 支持普通函数、字符串表达式和预绑定参数"""
    
    if isinstance(fn, str):
        fn = _parse_expr(fn, **kwargs)
    
    elif kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            observer_on_next = observer.on_next
            observer_on_error = observer.on_error
            
            def on_next(value: T) -> None:
                try:
                    result = fn(value)
                except Exception as e:
                    observer_on_error(e)
                else:
                    observer_on_next(result)
            
            return source.subscribe_(
                on_next=on_next,
                on_error=observer_on_error,
                on_completed=observer.on_completed
            )
        
        return Observable(subscribe)
    
    return operator


def filter(predicate: Callable[[T], bool] = None, **kwargs) -> Callable[[Observable[T]], Observable[T]]:
    """过滤操作符 - 支持普通函数、字符串表达式和预绑定参数"""
    
    if isinstance(predicate, str):
        predicate = _parse_expr(predicate, **kwargs)
    
    elif kwargs and predicate is not None:
        @curry
        def curried_fn(*args, **kw):
            return predicate(*args, **kw)
        predicate = curried_fn(**kwargs)
    
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            observer_on_next = observer.on_next
            observer_on_error = observer.on_error
            
            def on_next(value: T) -> None:
                try:
                    if predicate(value):
                        observer_on_next(value)
                except Exception as e:
                    observer_on_error(e)
            
            return source.subscribe_(
                on_next=on_next,
                on_error=observer_on_error,
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
            if builtins.all(has_emitted):
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
        
        if builtins.all(has_emitted):
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
            source_sub = None
            
            def unsubscribe():
                nonlocal is_closed, source_sub
                is_closed = True
                if source_sub is not None:
                    source_sub.unsubscribe()
            
            def on_next(value: T) -> None:
                nonlocal counter, is_closed, source_sub
                if is_closed:
                    return
                if counter < n:
                    observer.on_next(value)
                    counter += 1
                    if counter == n:
                        is_closed = True
                        if source_sub is not None:
                            source_sub.unsubscribe()
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
            
            result = Subscription(unsubscribe)
            result.add_child(source_sub)
            return result
        
        return Observable(subscribe)
    
    return operator


def skip(n: int) -> Callable[[Observable[T]], Observable[T]]:
    """跳过前 n 个元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            counter = 0
            source_sub = None
            
            def unsubscribe():
                nonlocal source_sub
                if source_sub is not None:
                    source_sub.unsubscribe()
            
            def on_next(value: T) -> None:
                nonlocal counter
                if counter >= n:
                    observer.on_next(value)
                else:
                    counter += 1
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            
            result = Subscription(unsubscribe)
            result.add_child(source_sub)
            return result
        
        return Observable(subscribe)
    
    return operator


def first(predicate: Optional[Callable[[T], bool]] = None) -> Callable[[Observable[T]], Observable[T]]:
    """取第一个元素，或第一个满足条件的元素"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            is_closed = False
            source_sub = None
            
            def unsubscribe():
                nonlocal is_closed, source_sub
                is_closed = True
                if source_sub is not None:
                    source_sub.unsubscribe()
            
            def on_next(value: T) -> None:
                nonlocal is_closed, source_sub
                if is_closed:
                    return
                
                try:
                    if predicate is None or predicate(value):
                        is_closed = True
                        if source_sub is not None:
                            source_sub.unsubscribe()
                        observer.on_next(value)
                        observer.on_completed()
                except Exception as e:
                    is_closed = True
                    if source_sub is not None:
                        source_sub.unsubscribe()
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
            
            result = Subscription(unsubscribe)
            result.add_child(source_sub)
            return result
        
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
            seen = {}
            source_sub = None
            
            def unsubscribe():
                nonlocal source_sub, seen
                seen.clear()
                if source_sub is not None:
                    source_sub.unsubscribe()
            
            def on_next(value: T) -> None:
                nonlocal seen
                try:
                    key = key_fn(value) if key_fn else value
                    if key not in seen:
                        seen[key] = True
                        observer.on_next(value)
                except Exception as e:
                    observer.on_error(e)
            
            def on_completed():
                seen.clear()
                observer.on_completed()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed
            )
            
            result = Subscription(unsubscribe)
            result.add_child(source_sub)
            return result
        
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

    def on_next(self, value: T) -> None:
        self._values.append(value)
        for obs in self._observers:
            obs.on_next(value)

    def on_error(self, error: Exception) -> None:
        for obs in self._observers:
            obs.on_error(error)

    def on_completed(self) -> None:
        for obs in self._observers:
            obs.on_completed()

    def subscribe(self, observer: Observer[T]) -> Subscription:
        for value in self._values:
            observer.on_next(value)
        self._observers.append(observer)
        
        def unsubscribe():
            if observer in self._observers:
                self._observers.remove(observer)
        
        return Subscription(unsubscribe)
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



def debounce(delay: float) -> Callable[[Observable[T]], Observable[T]]:
    """防抖操作符"""
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            timer = None
            last_value = None
            source_sub = None
            
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
                timer = _threading.Timer(delay, fire)
                timer.daemon = True
                timer.start()
            
            def on_completed():
                nonlocal timer, last_value
                if timer:
                    timer.cancel()
                    timer = None
                if last_value is not None:
                    observer.on_next(last_value)
                    last_value = None
                observer.on_completed()
            
            def unsubscribe():
                nonlocal timer, last_value, source_sub
                if timer:
                    timer.cancel()
                    timer = None
                last_value = None
                if source_sub is not None:
                    source_sub.unsubscribe()
            
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
            source_sub = None
            
            def on_next(value: T) -> None:
                nonlocal last_emit_time
                now = _time.time()
                if now - last_emit_time >= delay:
                    last_emit_time = now
                    observer.on_next(value)
            
            def unsubscribe():
                nonlocal source_sub, last_emit_time
                last_emit_time = -float('inf')
                if source_sub is not None:
                    source_sub.unsubscribe()
            
            source_sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed
            )
            
            result = Subscription(unsubscribe)
            result.add_child(source_sub)
            return result
        
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
            timeout_timer = None
            is_timed_out = False
            
            def on_timeout():
                nonlocal is_timed_out
                is_timed_out = True
                observer.on_error(TimeoutError("Observable timeout"))
            
            def reset_timeout():
                nonlocal timeout_timer
                if timeout_timer:
                    timeout_timer.cancel()
                timeout_timer = _threading.Timer(timeout_duration, on_timeout)
                timeout_timer.daemon = True
                timeout_timer.start()
            
            def on_next(value: T) -> None:
                if not is_timed_out:
                    reset_timeout()
                    observer.on_next(value)
            
            def on_completed():
                nonlocal is_timed_out
                if not is_timed_out:
                    is_timed_out = True
                    if timeout_timer:
                        timeout_timer.cancel()
                    observer.on_completed()
            
            def on_error(error):
                nonlocal is_timed_out
                if not is_timed_out:
                    is_timed_out = True
                    if timeout_timer:
                        timeout_timer.cancel()
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
                if timeout_timer:
                    timeout_timer.cancel()
            
            subscription._unsubscribe = cleanup
            return subscription
        
        return Observable(subscribe)
    
    return operator


def timestamp() -> Callable[[Observable[T]], Observable[Tuple[T, float]]]:
    """为每个元素添加时间戳"""
    def operator(source: Observable[T]) -> Observable[Tuple[T, float]]:
        def subscribe(observer: Observer[Tuple[T, float]]) -> Subscription:
            def on_next(value: T) -> None:
                observer.on_next((value, _time.time()))
            
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
                scheduled_time = _time.time() + delay_time
                pending_items.append((scheduled_time, value, 'next'))
                schedule_next()
            
            def on_error(error: Exception) -> None:
                nonlocal is_closed
                if is_closed:
                    return
                scheduled_time = _time.time() + delay_time
                pending_items.append((scheduled_time, error, 'error'))
                schedule_next()
            
            def on_completed() -> None:
                nonlocal is_closed
                if is_closed:
                    return
                scheduled_time = _time.time() + delay_time
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
                now = _time.time()
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
                
                timer = _threading.Timer(wait_time, fire)
                timer.daemon = True
                timer.start()
            
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
            is_closed = [False]
            timer = [None]
            
            def emit_latest():
                while not is_closed[0]:
                    if is_closed[0]:
                        break
                    if has_value[0]:
                        observer.on_next(latest_value[0])
                        has_value[0] = False
                    # Wait using Event
                    ev = _threading.Event()
                    timer[0] = ev
                    ev.wait(timeout=period)
            
            def on_next(value: T) -> None:
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err) -> None:
                nonlocal is_closed
                is_closed[0] = True
                observer.on_error(err)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed[0] = True
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            t = _threading.Thread(target=emit_latest, daemon=True)
            t.start()
            
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
            is_closed = [False]
            
            def emit_sample():
                while not is_closed[0]:
                    if is_closed[0]:
                        break
                    if has_value[0]:
                        observer.on_next(latest_value[0])
                    # Wait
                    _threading.Event().wait(timeout=period)
            
            def on_next(value: T) -> None:
                latest_value[0] = value
                has_value[0] = True
            
            def on_error(err) -> None:
                nonlocal is_closed
                is_closed[0] = True
                observer.on_error(err)
            
            def on_completed() -> None:
                nonlocal is_closed
                is_closed[0] = True
                observer.on_completed()
            
            source_sub = source.subscribe(on_next=on_next, on_error=on_error, on_completed=on_completed)
            t = _threading.Thread(target=emit_sample, daemon=True)
            t.start()
            
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
            last_time = [_time.time()]
            
            def on_next(value: T) -> None:
                current_time = _time.time()
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
                def retry():
                    nonlocal task
                    _time.sleep(delay)
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
                    t = _threading.Thread(target=retry, daemon=True)
                    t.start()
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
            
            def emit():
                _time.sleep(current_due_time[0])
                if is_closed[0]:
                    return
                if last_value[0] is not None:
                    observer.on_next(last_value[0])
                    last_value[0] = None
            
            def on_next(value: T) -> None:
                nonlocal task, current_due_time
                if task[0] and task[0].is_alive():
                    pass  # don't cancel, just replace
                if estimator:
                    current_due_time[0] = estimator(value)
                last_value[0] = value
                t = _threading.Thread(target=emit, daemon=True)
                t.start()
                task[0] = t
            
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
                    if duration and (_time.time() - t) > duration:
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
                cache_time.append(_time.time())
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
            
            return Subscription(unsubscribe)
        
        return Observable(subscribe)
    
    return operator


def dispatch_to_workers(
    fn: Callable[[T], R] = None,
    num_workers: int = 4,
    buffer_size: int = 0,
    on_drop: Optional[Callable[[T], None]] = None,
    drop_strategy: str = "oldest",
    **kwargs,
) -> Callable[[Observable[T]], Observable[R]]:
    """按闲/忙状态分发到 worker 池

    核心语义:
      - 上游每个值 -> 找一个"空闲"的 worker -> 调用 ``fn(value)`` -> 结果发给下游
      - worker "忙"期间不会再分配新值
      - 所有 worker 都忙时: 新值进入缓冲队列
      - 缓冲队列满时: 按 ``drop_strategy`` 丢弃（并调用 ``on_drop``）

    结果按"先完成先发出"的顺序输出（类似带并发上限的 flat_map）。

    Args:
        fn: 每个值的处理函数，支持同步函数和异步函数（返回 coroutine）
        num_workers: 最大并发 worker 数，必须 >= 1
        buffer_size: 缓冲队列大小，0 表示不限（可能导致内存无限增长）
        on_drop: 值被丢弃时的回调，接收被丢弃的值作为唯一参数
        drop_strategy: ``"oldest"`` 缓冲满时丢弃最旧的；
                       ``"newest"`` 缓冲满时丢弃新来的
        **kwargs: 预留的 curry 参数

    Returns:
        操作符函数
    """
    if num_workers < 1:
        raise ValueError("num_workers must be >= 1, got %d" % num_workers)

    if drop_strategy not in ("oldest", "newest"):
        raise ValueError(
            "drop_strategy must be 'oldest' or 'newest', got %r" % drop_strategy
        )

    if isinstance(fn, str):
        fn = _parse_expr(fn, **kwargs)
    elif kwargs and fn is not None:
        @curry
        def curried_fn(*args, **kw):
            return fn(*args, **kw)
        fn = curried_fn(**kwargs)

    if fn is None:
        fn = lambda x: x  # noqa: E731

    def operator(source: Observable[T]) -> Observable[R]:
        def subscribe(observer: Observer[R]) -> Subscription:
            from collections import deque
            from concurrent.futures import ThreadPoolExecutor
            import threading as _threading

            executor = ThreadPoolExecutor(max_workers=num_workers)

            state_lock = _threading.Lock()
            state = {
                "buffer": deque(),
                "active": 0,
                "closed": False,
                "errored": False,
                "completed_called": False,
            }

            def try_process_next():
                if state["errored"] or state["completed_called"]:
                    return
                while state["active"] < num_workers and len(state["buffer"]) > 0:
                    value = state["buffer"].popleft()
                    state["active"] += 1

                    def worker_task(v=value):
                        try:
                            result = fn(v)
                            if asyncio.iscoroutine(result):
                                loop = asyncio.new_event_loop()
                                try:
                                    result = loop.run_until_complete(result)
                                finally:
                                    loop.close()
                        except Exception as e:
                            with state_lock:
                                state["active"] -= 1
                                if not state["errored"] and not state["completed_called"]:
                                    observer.on_error(e)
                            return

                        observer.on_next(result)

                        with state_lock:
                            state["active"] -= 1
                            should_complete = (
                                state["closed"]
                                and not state["errored"]
                                and not state["completed_called"]
                                and state["active"] == 0
                                and len(state["buffer"]) == 0
                            )
                            if should_complete:
                                state["completed_called"] = True
                                observer.on_completed()
                            elif not state["errored"] and not state["completed_called"]:
                                try_process_next()

                    executor.submit(worker_task)

            def on_next(value: T) -> None:
                with state_lock:
                    if state["errored"] or state["completed_called"]:
                        return
                    if state["closed"]:
                        return
                    # 满了吗？所有 worker 都忙且缓冲已满
                    full = (
                        buffer_size > 0
                        and state["active"] >= num_workers
                        and len(state["buffer"]) >= buffer_size
                    )
                    if full:
                        if drop_strategy == "oldest":
                            dropped = state["buffer"].popleft()
                        else:
                            dropped = value
                        if on_drop is not None:
                            try:
                                on_drop(dropped)
                            except Exception:
                                pass
                        if drop_strategy == "newest":
                            return
                    state["buffer"].append(value)
                    try_process_next()

            def on_error(error: Exception) -> None:
                with state_lock:
                    if state["errored"] or state["completed_called"]:
                        return
                    state["errored"] = True
                    state["buffer"].clear()
                observer.on_error(error)

            def on_completed() -> None:
                with state_lock:
                    if state["closed"] or state["errored"] or state["completed_called"]:
                        return
                    state["closed"] = True
                    if state["active"] == 0 and len(state["buffer"]) == 0:
                        state["completed_called"] = True
                        observer.on_completed()

            source_sub = source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed,
            )

            def unsubscribe() -> None:
                with state_lock:
                    state["closed"] = True
                    state["errored"] = True
                    state["buffer"].clear()
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
                source_sub.unsubscribe()

            return Subscription(unsubscribe)

        return Observable(subscribe)

    return operator


def dispatch_workers(
    fn: Callable[[T], R] = None,
    num_workers: int = 4,
    buffer_size: int = 0,
    on_drop: Optional[Callable[[T], None]] = None,
    drop_strategy: str = "oldest",
    **kwargs,
) -> Callable[[Observable[T]], Observable[R]]:
    """``dispatch_to_workers`` 的短别名。"""
    return dispatch_to_workers(
        fn=fn,
        num_workers=num_workers,
        buffer_size=buffer_size,
        on_drop=on_drop,
        drop_strategy=drop_strategy,
        **kwargs,
    )


# ========================================================================
# 专用操作符: 生命周期 / 事件过滤 / 节流防抖 / 缓冲分组 / 速率限制
# ========================================================================


def on_start(
    callback: Callable[..., Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    订阅时执行回调。支持两种回调签名：
      - ``callback() -> Any``                订阅时立即调用
      - ``callback(first_value: T) -> Any``   首值到达时调用

    >>> stream.pipe(on_start(lambda: print("started"))).subscribe()
    >>> stream.pipe(on_start(lambda v: print("first:", v))).subscribe()
    """
    try:
        _sig = inspect.signature(callback)
        _takes_arg = len(_sig.parameters) > 0
    except (TypeError, ValueError):
        _takes_arg = False

    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            fired = [False]

            def on_next_wrapped(value: T) -> None:
                if not fired[0] and _takes_arg:
                    fired[0] = True
                    try:
                        callback(value)
                    except Exception as e:
                        observer.on_error(e)
                        return
                observer.on_next(value)

            if not _takes_arg:
                try:
                    callback()
                except Exception as e:
                    observer.on_error(e)

            return source.subscribe(
                on_next=on_next_wrapped if _takes_arg else observer.on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def on_stop(
    callback: Callable[..., Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    流结束时（完成/错误/取消订阅）执行回调。支持两种签名：
      - ``callback() -> Any``
      - ``callback(last_value: Optional[T]) -> Any``

    >>> stream.pipe(on_stop(lambda: print("stopped"))).subscribe()
    >>> stream.pipe(on_stop(lambda v: print("last:", v))).subscribe()
    """
    try:
        _sig = inspect.signature(callback)
        _takes_arg = len(_sig.parameters) > 0
    except (TypeError, ValueError):
        _takes_arg = False

    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_value: "List[Optional[T]]" = [None]

            def on_next_wrapped(value: T) -> None:
                if _takes_arg:
                    last_value[0] = value
                observer.on_next(value)

            def _fire_stop() -> None:
                try:
                    if _takes_arg:
                        callback(last_value[0])
                    else:
                        callback()
                except Exception:
                    pass

            sub = source.subscribe(
                on_next=on_next_wrapped if _takes_arg else observer.on_next,
                on_error=lambda e: (_fire_stop(), observer.on_error(e)),
                on_completed=lambda: (_fire_stop(), observer.on_completed()),
            )
            sub.add_child(Subscription(_fire_stop))
            return sub
        return Observable(subscribe)
    return operator


def when_start(
    predicate: Callable[[T], bool],
) -> Callable[[Observable[T]], Observable[T]]:
    """
    当条件满足时开始转发事件。在 predicate 返回 True 之前，所有事件都会被丢弃。
    
    Args:
        predicate: 判断函数，接收数据并返回布尔值，返回 True 时开始转发

    >>> stream.pipe(when_start(lambda data: data.is_press)).subscribe()
    >>> clipboard.pipe(when_start(lambda data: data.change_type == ClipChangeType.TEXT)).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            started = [False]

            def on_next_wrapped(value: T) -> None:
                if not started[0]:
                    if predicate(value):
                        started[0] = True
                        observer.on_next(value)
                else:
                    observer.on_next(value)

            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def when_stop(
    predicate: Callable[[T], bool],
    inclusive: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    """
    当条件满足时停止转发事件。在 predicate 返回 True 之后，所有事件都会被丢弃。
    
    Args:
        predicate: 判断函数，接收数据并返回布尔值，返回 True 时停止转发
        inclusive: 是否包含触发停止的事件（默认 True）

    >>> stream.pipe(when_stop(lambda data: data.key == 'Escape')).subscribe()
    >>> clipboard.pipe(when_stop(lambda data: data.size > 1024 * 1024)).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            stopped = [False]

            def on_next_wrapped(value: T) -> None:
                if not stopped[0]:
                    if predicate(value):
                        stopped[0] = True
                        if inclusive:
                            observer.on_next(value)
                        observer.on_completed()
                    else:
                        observer.on_next(value)

            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def filter_by(
    predicate: Callable[[T], bool],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""按谓词过滤事件（filter 的语义别名）。"""
    return filter(predicate)


def filter_by_event_type(
    *event_types: Any,
    type_extractor: Optional[Callable[[T], Any]] = None,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    按事件类型枚举值过滤。

    >>> keyboard.pipe(filter_by_event_type(KeyEventType.KEY_DOWN)).subscribe()
    """
    allowed: Set[Any] = set(event_types)
    if type_extractor is None:
        def _default_extractor(v: Any) -> Any:
            return getattr(v, "event_type", v)
        _extract = _default_extractor
    else:
        _extract = type_extractor

    def predicate(v: T) -> bool:
        return _extract(v) in allowed
    return filter(predicate)


def when(
    predicate: Callable[[T], bool],
    handler: Callable[[T], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    条件副作用：当 ``predicate(value)`` 为真时调用 ``handler(value)``，主流通路不变。

    >>> keyboard.pipe(when(lambda kd: kd.key_name == "enter",
    ...                    lambda kd: print("ENTER"))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(v: T) -> None:
                try:
                    if predicate(v):
                        handler(v)
                except Exception:
                    pass
                observer.on_next(v)
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def throttle_events(
    period_seconds: float,
    key_fn: Optional[Callable[[T], Any]] = None,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    事件节流 -- 每个 key 每 period_seconds 只发射一次事件。

    >>> mouse.pipe(throttle_events(0.05, key_fn=lambda md: "move")).subscribe()
    """
    period = max(0.0, float(period_seconds))

    def operator(source: Observable[T]) -> Observable[T]:
        last_emitted: Dict[Any, float] = {}
        lock = _threading.Lock()

        def on_next_wrapper(value: T, emit: Callable[[T], None]) -> None:
            key = key_fn(value) if key_fn is not None else "__all__"
            now = _time.monotonic()
            should_emit = False
            with lock:
                last = last_emitted.get(key, -float("inf"))
                if now - last >= period:
                    last_emitted[key] = now
                    should_emit = True
            if should_emit:
                emit(value)

        def subscribe(observer: Observer[T]) -> Subscription:
            return source.subscribe(
                on_next=lambda v: on_next_wrapper(v, observer.on_next),
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def debounce_events(
    wait_seconds: float,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    事件防抖 -- 静止 wait_seconds 后才发射最后一个事件。

    >>> clipboard.pipe(debounce_events(0.2)).subscribe()
    """
    wait = max(0.0, float(wait_seconds))

    def operator(source: Observable[T]) -> Observable[T]:
        timer_state: Dict[str, Any] = {"t": None, "last": None}

        def schedule(observer: Observer[T]) -> None:
            if timer_state["t"] is not None:
                try:
                    timer_state["t"].cancel()
                except Exception:
                    pass
            timer_state["t"] = _threading.Timer(
                wait, lambda: _emit_last(observer)
            )
            timer_state["t"].daemon = True
            timer_state["t"].start()

        def _emit_last(observer: Observer[T]) -> None:
            last = timer_state["last"]
            if last is not None:
                timer_state["last"] = None
                try:
                    observer.on_next(last)
                except Exception:
                    pass

        def _cancel_timer() -> None:
            if timer_state["t"] is not None:
                try:
                    timer_state["t"].cancel()
                except Exception:
                    pass

        def subscribe(observer: Observer[T]) -> Subscription:
            def on_next(v: T) -> None:
                timer_state["last"] = v
                schedule(observer)
            sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
            sub.add_child(Subscription(_cancel_timer))
            return sub
        return Observable(subscribe)
    return operator


def distinct_until_changed_by(
    key_fn: Callable[[T], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    按键去重 -- 连续相同的 key 只发射一次。

    >>> clipboard.pipe(distinct_until_changed_by(lambda cd: cd.content)).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        sentinel = object()
        last: List[Any] = [sentinel]

        def on_next_wrapper(v: T, emit: Callable[[T], None]) -> None:
            try:
                key = key_fn(v)
            except Exception:
                emit(v)
                return
            if last[0] is sentinel or last[0] != key:
                last[0] = key
                emit(v)

        def subscribe(observer: Observer[T]) -> Subscription:
            return source.subscribe(
                on_next=lambda v: on_next_wrapper(v, observer.on_next),
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def buffer_with_count(
    count: int,
) -> Callable[[Observable[T]], Observable[List[T]]]:
    r"""
    按数量缓冲事件 -- 每 count 个事件发射一次列表。

    >>> keyboard.pipe(buffer_with_count(5)).subscribe()
    """
    n = max(1, int(count))

    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            buf: List[T] = []

            def on_next(v: T) -> None:
                buf.append(v)
                if len(buf) >= n:
                    snapshot = list(buf)
                    buf.clear()
                    observer.on_next(snapshot)

            def on_completed() -> None:
                if buf:
                    observer.on_next(list(buf))
                observer.on_completed()

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=on_completed,
            )
        return Observable(subscribe)
    return operator


def count_events() -> Callable[[Observable[T]], Observable[int]]:
    r"""计数 -- 每发射一个事件，输出当前累计计数。"""
    def operator(source: Observable[T]) -> Observable[int]:
        def subscribe(observer: Observer[int]) -> Subscription:
            counter = [0]
            def on_next(v: T) -> None:
                counter[0] += 1
                observer.on_next(counter[0])
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def group_by_event_type(
    type_extractor: Optional[Callable[[T], Any]] = None,
) -> Callable[[Observable[T]], Observable[Tuple[Any, T]]]:
    r"""
    按事件类型分组 -- 输出 (event_type, value) 元组。

    >>> keyboard.pipe(group_by_event_type()).subscribe()
    """
    if type_extractor is None:
        def _default(v: Any) -> Any:
            return getattr(v, "event_type", v)
        _extract = _default
    else:
        _extract = type_extractor

    def operator(source: Observable[T]) -> Observable[Tuple[Any, T]]:
        def subscribe(observer: Observer[Tuple[Any, T]]) -> Subscription:
            def on_next(v: T) -> None:
                et = _extract(v)
                observer.on_next((et, v))
            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def sample_first(
    period_seconds: float,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    时间窗口采样 -- 每个窗口只发射第一个事件。

    >>> keyboard.pipe(sample_first(1.0)).subscribe()
    """
    period = max(0.0, float(period_seconds))

    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_time = [-float("inf")]

            def on_next(v: T) -> None:
                now = _time.monotonic()
                if now - last_time[0] >= period:
                    last_time[0] = now
                    observer.on_next(v)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def on_next_data(
    on_next: Callable[[T], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    语义别名 tap -- 在每个事件上触发副作用，原始值不变。

    >>> stream.pipe(on_next_data(lambda v: print("got", v))).subscribe()
    """
    return tap(on_next)


def filter_by_data(
    predicate: Optional[Callable[[T], bool]] = None,
    **data_matchers: Any,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    按字段值或谓词过滤事件。

    支持两种方式：
      - keyword arguments: ``filter_by_data(is_press=True)`` 按字段值过滤
      - predicate: ``filter_by_data(lambda v: v.size > 1024)``
      - 两者可组合（AND 语义）

    >>> clipboard.pipe(filter_by_data(change_type=ClipChangeType.TEXT)).subscribe()
    >>> keyboard.pipe(filter_by_data(is_press=True)).subscribe()
    """
    def _field_matcher(v: Any) -> bool:
        return builtins.all(getattr(v, k, None) == val for k, val in data_matchers.items())

    def operator(source: Observable[T]) -> Observable[T]:
        def predicate_combined(v: T) -> bool:
            ok = True
            if data_matchers:
                ok = ok and _field_matcher(v)
            if predicate is not None:
                try:
                    ok = ok and bool(predicate(v))
                except Exception:
                    ok = False
            return ok

        def subscribe(observer: Observer[T]) -> Subscription:
            return source.subscribe(
                on_next=lambda v: observer.on_next(v) if predicate_combined(v) else None,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def take_until_data(
    predicate: Callable[[T], bool],
    inclusive: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    发射事件直到 ``predicate(value)`` 为真，然后完成。

    Args:
        predicate: 停止条件
        inclusive: 为真时也发射触发停止的那个事件（默认 True）

    >>> keyboard.pipe(take_until_data(lambda kd: kd.key_name == "escape")).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            state = {"done": False}
            sub_holder: "List[Optional[Subscription]]" = [None]

            def on_next(v: T) -> None:
                if state["done"]:
                    return
                try:
                    should_stop = bool(predicate(v))
                except Exception:
                    should_stop = False
                if should_stop:
                    state["done"] = True
                    if inclusive:
                        observer.on_next(v)
                    observer.on_completed()
                    if sub_holder[0] is not None:
                        try:
                            sub_holder[0].unsubscribe()
                        except Exception:
                            pass
                else:
                    observer.on_next(v)

            sub_holder[0] = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
            return sub_holder[0] if sub_holder[0] is not None else Subscription()
        return Observable(subscribe)
    return operator


def skip_until_data(
    predicate: Callable[[T], bool],
    inclusive: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    跳过事件直到 ``predicate(value)`` 为真，然后发射后续所有事件。

    >>> keyboard.pipe(skip_until_data(lambda kd: kd.key_name == "ctrl")).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            state = {"started": False}

            def on_next(v: T) -> None:
                if not state["started"]:
                    try:
                        triggered = bool(predicate(v))
                    except Exception:
                        triggered = False
                    if triggered:
                        state["started"] = True
                        if inclusive:
                            observer.on_next(v)
                        return
                observer.on_next(v)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def finally_with_data(
    on_finally: Callable[[Optional[T]], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    流结束时（完成/错误/取消订阅）用最后发射的值调用回调。

    >>> clipboard.pipe(finally_with_data(lambda last: print("last:", last))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_value: "List[Optional[T]]" = [None]

            def _fire() -> None:
                try:
                    on_finally(last_value[0])
                except Exception:
                    pass

            def on_next_tracked(v: T) -> None:
                last_value[0] = v
                observer.on_next(v)

            sub = source.subscribe(
                on_next=on_next_tracked,
                on_error=lambda e: (_fire(), observer.on_error(e)),
                on_completed=lambda: (_fire(), observer.on_completed()),
            )
            sub.add_child(Subscription(_fire))
            return sub
        return Observable(subscribe)
    return operator


def on_data(
    predicate: Callable[[T], bool],
    on_match: Callable[[T], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    条件副作用（when 的语义别名）。

    >>> keyboard.pipe(on_data(lambda kd: kd.key_name == "enter",
    ...                       lambda kd: print("ENTER"))).subscribe()
    """
    return when(predicate, on_match)


def buffer_until_idle(
    idle_seconds: float,
    max_size: Optional[int] = None,
) -> Callable[[Observable[T]], Observable[List[T]]]:
    r"""
    空闲缓冲 -- 当静止 idle_seconds 或达到 max_size 时发射缓冲列表。

    >>> file_watcher.pipe(buffer_until_idle(0.3, max_size=50)).subscribe()
    """
    idle = max(0.0, float(idle_seconds))
    _max = int(max_size) if max_size is not None else None

    def operator(source: Observable[T]) -> Observable[List[T]]:
        def subscribe(observer: Observer[List[T]]) -> Subscription:
            buf: "List[T]" = []
            timer_state: Dict[str, Any] = {"t": None}
            lock = _threading.Lock()

            def _emit_locked() -> None:
                if timer_state["t"] is not None:
                    try:
                        timer_state["t"].cancel()
                    except Exception:
                        pass
                    timer_state["t"] = None
                if buf:
                    snapshot = list(buf)
                    buf.clear()
                    observer.on_next(snapshot)

            def _schedule() -> None:
                if timer_state["t"] is not None:
                    try:
                        timer_state["t"].cancel()
                    except Exception:
                        pass
                t = _threading.Timer(
                    idle,
                    lambda: (lock.acquire(timeout=1.0) and (_emit_locked(), lock.release())),
                )
                t.daemon = True
                timer_state["t"] = t
                t.start()

            def on_next(v: T) -> None:
                with lock:
                    buf.append(v)
                    if _max is not None and len(buf) >= _max:
                        _emit_locked()
                    else:
                        _schedule()

            def _cleanup() -> None:
                with lock:
                    _emit_locked()

            sub = source.subscribe(
                on_next=on_next,
                on_error=lambda e: (_cleanup(), observer.on_error(e)),
                on_completed=lambda: (_cleanup(), observer.on_completed()),
            )
            sub.add_child(Subscription(_cleanup))
            return sub
        return Observable(subscribe)
    return operator


def take_n_events(n: int) -> Callable[[Observable[T]], Observable[T]]:
    r"""take 的语义别名：取前 n 个事件后完成。"""
    return take(n)


def skip_n_events(n: int) -> Callable[[Observable[T]], Observable[T]]:
    r"""skip 的语义别名：跳过前 n 个事件。"""
    return skip(n)


def distinct_values(
    key_fn: Optional[Callable[[T], Any]] = None,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    去重（全流生命期）-- 基于 key_fn(value) 去重，任何重复值都被丢弃。

    >>> clipboard.pipe(distinct_values(lambda cd: cd.content)).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            seen: Set[Any] = set()
            lock = _threading.Lock()

            def on_next(v: T) -> None:
                try:
                    key = key_fn(v) if key_fn is not None else v
                except Exception:
                    key = v
                with lock:
                    if key not in seen:
                        seen.add(key)
                        observer.on_next(v)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def rate_limit(
    events_per_second: float,
    burst: int = 1,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    令牌桶速率限制 -- 每秒最多 events_per_second 个事件，可突发 burst 个。

    >>> mouse.pipe(rate_limit(30, 5)).subscribe()
    """
    eps = max(0.0, float(events_per_second))
    burst_n = max(1, int(burst))

    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            tokens: float = float(burst_n)
            last_t: float = _time.monotonic()
            lock = _threading.Lock()

            def on_next(v: T) -> None:
                nonlocal tokens, last_t
                now = _time.monotonic()
                with lock:
                    elapsed = now - last_t
                    tokens = min(float(burst_n), tokens + elapsed * eps)
                    last_t = now
                    if tokens >= 1.0:
                        tokens -= 1.0
                        observer.on_next(v)

            return source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def debounce_data(
    wait_seconds: float,
    key_fn: Optional[Callable[[T], Any]] = None,
) -> Callable[[Observable[T]], Observable[T]]:
    r"""
    按 key 防抖 -- 每个 distinct key_fn(value) 独立防抖。

    >>> clipboard.pipe(debounce_data(0.3, lambda cd: cd.change_type)).subscribe()
    """
    wait = max(0.0, float(wait_seconds))

    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            timers: Dict[Any, Any] = {}
            last_values: Dict[Any, T] = {}
            lock = _threading.Lock()

            def _emit_key(key: Any) -> None:
                with lock:
                    v = last_values.pop(key, None)
                    t = timers.pop(key, None)
                if t is not None:
                    try:
                        t.cancel()
                    except Exception:
                        pass
                if v is not None:
                    observer.on_next(v)

            def on_next(v: T) -> None:
                key = key_fn(v) if key_fn is not None else "__all__"
                with lock:
                    old_t = timers.get(key)
                    if old_t is not None:
                        try:
                            old_t.cancel()
                        except Exception:
                            pass
                    last_values[key] = v
                    t = _threading.Timer(wait, lambda k=key: _emit_key(k))
                    t.daemon = True
                    timers[key] = t
                    t.start()

            def _cleanup() -> None:
                with lock:
                    for t in timers.values():
                        try:
                            t.cancel()
                        except Exception:
                            pass
                    timers.clear()
                    last_values.clear()

            sub = source.subscribe(
                on_next=on_next,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
            sub.add_child(Subscription(_cleanup))
            return sub
        return Observable(subscribe)
    return operator


# ========================================================================
# 监控场景专用操作符扩展
# ========================================================================


def when_error(
    on_error: Callable[[Exception], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    """
    错误发生时执行回调。
    
    >>> stream.pipe(when_error(lambda e: print(f'Error: {e}'))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            def on_error_wrapped(error: Exception) -> None:
                try:
                    on_error(error)
                except Exception:
                    pass
                observer.on_error(error)
            
            return source.subscribe(
                on_next=observer.on_next,
                on_error=on_error_wrapped,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def on_every_nth(
    n: int,
    on_nth: Callable[[T], Any],
) -> Callable[[Observable[T]], Observable[T]]:
    """
    每第N个事件执行回调。
    
    >>> stream.pipe(on_every_nth(5, lambda v: print(f'5th: {v}'))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            counter = [0]
            
            def on_next_wrapped(value: T) -> None:
                counter[0] += 1
                if counter[0] % n == 0:
                    try:
                        on_nth(value)
                    except Exception:
                        pass
                observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def on_condition_met(
    condition: Callable[[T], bool],
    on_met: Callable[[T], Any],
    once: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    """
    当条件满足时执行回调。
    
    Args:
        condition: 判断条件函数
        on_met: 条件满足时的回调
        once: 是否只触发一次（默认 True）
    
    >>> stream.pipe(on_condition_met(lambda v: v > 100, lambda v: print(f'Over 100: {v}'))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            triggered = [False]
            
            def on_next_wrapped(value: T) -> None:
                if not triggered[0] and condition(value):
                    triggered[0] = once
                    try:
                        on_met(value)
                    except Exception:
                        pass
                observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def collect_until(
    condition: Callable[[T], bool],
    on_collected: Callable[[List[T]], Any],
    inclusive: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    """
    收集事件直到条件满足，然后执行回调。
    
    Args:
        condition: 停止收集的条件
        on_collected: 收集完成后的回调
        inclusive: 是否包含触发条件的事件（默认 True）
    
    >>> stream.pipe(collect_until(lambda v: v == 'stop', lambda lst: print(f'Collected: {lst}'))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            collected: List[T] = []
            collecting = [True]
            
            def on_next_wrapped(value: T) -> None:
                if collecting[0]:
                    if inclusive:
                        collected.append(value)
                    if condition(value):
                        collecting[0] = False
                        try:
                            on_collected(collected)
                        except Exception:
                            pass
                    elif not inclusive:
                        collected.append(value)
                observer.on_next(value)
            
            def on_completed_wrapped() -> None:
                if collecting[0] and collected:
                    try:
                        on_collected(collected)
                    except Exception:
                        pass
                observer.on_completed()
            
            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=on_completed_wrapped,
            )
        return Observable(subscribe)
    return operator


def with_state(
    initial_state: S,
    reducer: Callable[[S, T], S],
    on_state_change: Optional[Callable[[S], Any]] = None,
) -> Callable[[Observable[T]], Observable[T]]:
    """
    带状态的操作符，类似 Redux 的 reducer 模式。
    
    Args:
        initial_state: 初始状态
        reducer: 状态更新函数，接收当前状态和新值，返回新状态
        on_state_change: 状态变化时的回调（可选）
    
    >>> stream.pipe(with_state(0, lambda state, v: state + v, lambda s: print(f'Sum: {s}'))).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            state = [initial_state]
            
            def on_next_wrapped(value: T) -> None:
                try:
                    state[0] = reducer(state[0], value)
                    if on_state_change:
                        on_state_change(state[0])
                except Exception:
                    pass
                observer.on_next(value)
            
            return source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
        return Observable(subscribe)
    return operator


def throttle_with_trailing(
    duration: float,
    trailing: bool = True,
) -> Callable[[Observable[T]], Observable[T]]:
    """
    节流操作符，可选是否发送最后一个事件。
    
    Args:
        duration: 节流时间（秒）
        trailing: 是否在节流结束后发送最后一个事件（默认 True）
    
    >>> stream.pipe(throttle_with_trailing(0.5)).subscribe()
    """
    def operator(source: Observable[T]) -> Observable[T]:
        def subscribe(observer: Observer[T]) -> Subscription:
            last_value: "List[Optional[T]]" = [None]
            last_time = [0.0]
            timer = [None]
            
            def _emit() -> None:
                timer[0] = None
                if last_value[0] is not None:
                    observer.on_next(last_value[0])
                    last_value[0] = None
            
            def on_next_wrapped(value: T) -> None:
                now = _time.time()
                if now - last_time[0] >= duration:
                    last_time[0] = now
                    observer.on_next(value)
                elif trailing:
                    last_value[0] = value
                    if timer[0] is None:
                        timer[0] = _threading.Timer(duration, _emit)
                        timer[0].daemon = True
                        timer[0].start()
            
            def _cleanup() -> None:
                if timer[0] is not None:
                    timer[0].cancel()
                    timer[0] = None
            
            sub = source.subscribe(
                on_next=on_next_wrapped,
                on_error=observer.on_error,
                on_completed=observer.on_completed,
            )
            sub.add_child(Subscription(_cleanup))
            return sub
        return Observable(subscribe)
    return operator
