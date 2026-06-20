"""
vools-reactive Observable Core
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Generic, Iterator, AsyncIterator
from abc import ABC, abstractmethod
import asyncio
import sys
import threading
import time

from ...decorators import curry, lazy
from .object_pool import get_pool, pooled_acquire, pooled_release
__all__ = ['T', 'R', 'Subscription', 'Observer', 'DefaultObserver', 'PipeDescriptor', 'PipeBuilder', 'Observable']

T = TypeVar('T')
R = TypeVar('R')


class Subscription:
    """订阅管理类"""
    
    __slots__ = ('_unsubscribe', '_is_closed', '_children')
    
    def __init__(self, unsubscribe):
        self._unsubscribe = unsubscribe
        self._is_closed = False
        self._children = set()
    
    def add_child(self, child):
        """添加子订阅"""
        self._children.add(child)
    
    def remove_child(self, child):
        """移除子订阅"""
        self._children.discard(child)
    
    def unsubscribe(self):
        if not self._is_closed:
            self._is_closed = True
            for child in self._children:
                child.unsubscribe()
            self._unsubscribe()
    
    def dispose(self):
        """dispose 别名，与 RxPY/rx-rust 对齐"""
        self.unsubscribe()
    
    @property
    def is_closed(self):
        return self._is_closed
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unsubscribe()
        return False


class Observer(Generic[T], ABC):
    """观察者抽象基类"""
    
    @abstractmethod
    def on_next(self, value):
        pass
    
    @abstractmethod
    def on_error(self, error):
        pass
    
    @abstractmethod

    def on_completed(self):
        pass


class DefaultObserver(Observer[T]):
    """默认观察者实现"""
    
    __slots__ = ('_on_next', '_on_error', '_on_completed', '_pool')
    
    def __init__(self, on_next=None, on_error=None, on_completed=None):
        self._on_next = on_next or (lambda _: None)
        self._on_error = on_error or (lambda e: None)
        self._on_completed = on_completed or (lambda: None)
        self._pool = None
    
    def on_next(self, value):
        self._on_next(value)
    
    def on_error(self, error):
        self._on_error(error)
    
    def on_completed(self):
        self._on_completed()
    
    def reset(self):
        """重置观察者状态"""
        self._on_next = lambda _: None
        self._on_error = lambda e: None
        self._on_completed = lambda: None
    
    def set_pool(self, pool):
        """设置所属对象池"""
        self._pool = pool
    
    def release(self):
        """释放回对象池"""
        if self._pool is not None:
            self.reset()
            self._pool.release(self)


class PipeDescriptor(Generic[T]):
    """pipe 描述符 - 同时支持可调用和链式调用"""
    

    def __get__(self, instance: Observable[T], owner=None) -> 'PipeBuilder[T]':
        if instance is None:
            return self
        return PipeBuilder(instance, origin=instance)


class PipeBuilder(Generic[T]):
    """链式管道构建器"""
    
    __slots__ = ('_source', '_operators', '_origin', '_cached_result')
    
    def __init__(self, source: Observable[T], origin=None):
        self._source = source
        self._operators = []
        self._origin = origin if origin is not None else source
        self._cached_result = None
    
    def _add_operator(self, operator):
        self._operators.append(operator)
        self._cached_result = None
        return self
    
    def _build(self) -> Observable:
        """构建最终的 Observable"""
        if self._cached_result is not None:
            return self._cached_result
        source = self._source
        for op in self._operators:
            source = op(source)
        self._cached_result = source
        return source
    
    def subscribe(self, on_next=None, on_error=None, on_completed=None, observer=None):
        """直接订阅"""
        if hasattr(self._origin, 'start') and callable(self._origin.start):
            self._origin.start()
        return self._build().subscribe(on_next, on_error, on_completed, observer)
    
    def connect(self):
        """连接 ConnectableObservable"""
        result = self._build()
        if hasattr(result, 'connect'):
            return result.connect()
        raise AttributeError("'PipeBuilder' object has no attribute 'connect' - the result is not a ConnectableObservable")
    
    def __getattr__(self, name):
        """代理其他属性到构建结果"""
        result = self._build()
        if hasattr(result, name):
            return getattr(result, name)
        raise AttributeError(f"'PipeBuilder' object has no attribute '{name}'")
    
    def __rshift__(self, other):
        """支持 >> 操作符"""
        if callable(other):
            self._operators.append(other)
        return self
    
    def __call__(self, *operators):
        """支持 pipe(f1, f2, f3) 调用方式"""
        for op in operators:
            if callable(op):
                self._operators.append(op)
        
        if len(self._operators) == 1:
            result = self._operators[0](self._source)
            if isinstance(result, Subscription):
                return result
        
        return self
    
    # ========== 操作符方法 ==========
    
    def map(self, fn=None, **kwargs):
        from ..operators import map
        return self._add_operator(map(fn, **kwargs))
    
    def filter(self, fn=None, **kwargs):
        from ..operators import filter
        return self._add_operator(filter(fn, **kwargs))
    
    def flat_map(self, fn=None, **kwargs):
        from ..operators import flat_map
        return self._add_operator(flat_map(fn, **kwargs))
    
    def concat_map(self, fn=None, **kwargs):
        from ..operators import concat_map
        return self._add_operator(concat_map(fn, **kwargs))
    
    def switch_map(self, fn=None, **kwargs):
        from ..operators import switch_map
        return self._add_operator(switch_map(fn, **kwargs))
    
    def take(self, n):
        from ..operators import take
        return self._add_operator(take(n))
    
    def skip(self, n):
        from ..operators import skip
        return self._add_operator(skip(n))
    
    def take_while(self, predicate=None, **kwargs):
        from ..operators import take_while
        return self._add_operator(take_while(predicate, **kwargs))
    
    def skip_while(self, predicate=None, **kwargs):
        from ..operators import skip_while
        return self._add_operator(skip_while(predicate, **kwargs))
    
    def take_until(self, other):
        from ..operators import take_until
        return self._add_operator(take_until(other))
    
    def distinct_until_changed(self, key_fn=None):
        from ..operators import distinct_until_changed
        return self._add_operator(distinct_until_changed(key_fn))
    
    def debounce(self, due_time):
        from ..operators import debounce
        return self._add_operator(debounce(due_time))
    
    def throttle_first(self, duration):
        from ..operators import throttle_first
        return self._add_operator(throttle_first(duration))
    
    def tap(self, fn=None, **kwargs):
        from ..operators import tap
        return self._add_operator(tap(fn, **kwargs))
    
    def delay(self, due_time):
        from ..operators import delay
        return self._add_operator(delay(due_time))
    
    def start_with(self, *values):
        from ..operators import start_with
        return self._add_operator(start_with(*values))
    
    def end_with(self, *values):
        from ..operators import end_with
        return self._add_operator(end_with(*values))
    
    def reduce(self, accumulator, seed=None):
        from ..operators import reduce
        return self._add_operator(reduce(accumulator, seed))
    
    def scan(self, accumulator, seed=None):
        from ..operators import scan
        return self._add_operator(scan(accumulator, seed))
    
    def count(self):
        from ..operators import count
        return self._add_operator(count())
    
    def sum(self, key_mapper=None):
        from ..operators import sum
        return self._add_operator(sum(key_mapper))
    
    def average(self, key_mapper=None):
        from ..operators import average
        return self._add_operator(average(key_mapper))
    
    def minimum(self, key_mapper=None):
        from ..operators import minimum
        return self._add_operator(minimum(key_mapper))
    
    def maximum(self, key_mapper=None):
        from ..operators import maximum
        return self._add_operator(maximum(key_mapper))
    
    def all(self, predicate):
        from ..operators import all
        return self._add_operator(all(predicate))
    
    def any(self, predicate=None):
        from ..operators import any
        return self._add_operator(any(predicate))
    
    def contains(self, value):
        from ..operators import contains
        return self._add_operator(contains(value))
    
    def is_empty(self):
        from ..operators import is_empty
        return self._add_operator(is_empty())
    
    def to_list(self):
        from ..operators import to_list
        return self._add_operator(to_list())
    
    def buffer(self, count):
        from ..operators import buffer
        return self._add_operator(buffer(count))
    
    def group_by(self, key_fn):
        from ..operators import group_by
        return self._add_operator(group_by(key_fn))
    
    def merge(self, *others):
        from ..operators import merge
        return self._add_operator(merge(*others))
    
    def concat(self, *others):
        from ..operators import concat
        return self._add_operator(concat(*others))
    
    def catch(self, handler):
        from ..operators import catch
        return self._add_operator(catch(handler))
    
    def retry(self, times=None):
        from ..operators import retry
        return self._add_operator(retry(times))
    
    def on_error_return(self, value):
        from ..operators import on_error_return
        return self._add_operator(on_error_return(value))
    
    def on_error_resume_next(self, fallback):
        from ..operators import on_error_resume_next
        return self._add_operator(on_error_resume_next(fallback))
    
    def retry_when(self, handler):
        from ..operators import retry_when
        return self._add_operator(retry_when(handler))
    
    # ========== 新增操作符 ==========
    
    def first(self, predicate=None):
        from ..operators import first
        return self._add_operator(first(predicate))
    
    def last(self, predicate=None):
        from ..operators import last
        return self._add_operator(last(predicate))
    
    def distinct(self, key_fn=None):
        from ..operators import distinct
        return self._add_operator(distinct(key_fn))
    
    def element_at(self, index):
        from ..operators import element_at
        return self._add_operator(element_at(index))
    
    def skip_until(self, other):
        from ..operators import skip_until
        return self._add_operator(skip_until(other))
    
    def default_if_empty(self, default_value):
        from ..operators import default_if_empty
        return self._add_operator(default_if_empty(default_value))
    
    def sequence_equal(self, other):
        from ..operators import sequence_equal
        return self._add_operator(sequence_equal(other))
    
    def timeout(self, timeout_duration):
        from ..operators import timeout
        return self._add_operator(timeout(timeout_duration))
    
    def timestamp(self):
        from ..operators import timestamp
        return self._add_operator(timestamp())
    
    def iif(self, condition=None, true_body=None, false_body=None):
        from ..operators import iif
        return self._add_operator(iif(condition, true_body, false_body))
    
    # ========== 统计聚合扩展算子 ==========
    
    def median(self):
        from ..operators.stats_operators import median
        return self._add_operator(median())
    
    def variance(self, ddof: int = 0):
        from ..operators.stats_operators import variance
        return self._add_operator(variance(ddof))
    
    def std(self, ddof: int = 0):
        from ..operators.stats_operators import std
        return self._add_operator(std(ddof))
    
    def quantile(self, q: float):
        from ..operators.stats_operators import quantile
        return self._add_operator(quantile(q))
    
    def arg_min(self):
        from ..operators.stats_operators import arg_min
        return self._add_operator(arg_min())
    
    def arg_max(self):
        from ..operators.stats_operators import arg_max
        return self._add_operator(arg_max())
    
    def n_unique(self):
        from ..operators.stats_operators import n_unique
        return self._add_operator(n_unique())
    
    # ========== 滚动窗口算子 ==========
    
    def rolling_sum(self, window_size: int):
        from ..operators.stats_operators import rolling_sum
        return self._add_operator(rolling_sum(window_size))
    
    def rolling_min(self, window_size: int):
        from ..operators.stats_operators import rolling_min
        return self._add_operator(rolling_min(window_size))
    
    def rolling_max(self, window_size: int):
        from ..operators.stats_operators import rolling_max
        return self._add_operator(rolling_max(window_size))
    
    def rolling_mean(self, window_size: int):
        from ..operators.stats_operators import rolling_mean
        return self._add_operator(rolling_mean(window_size))
    
    # ========== 累积变换算子 ==========
    
    def cum_sum(self):
        from ..operators.stats_operators import cum_sum
        return self._add_operator(cum_sum())
    
    def cum_min(self):
        from ..operators.stats_operators import cum_min
        return self._add_operator(cum_min())
    
    def cum_max(self):
        from ..operators.stats_operators import cum_max
        return self._add_operator(cum_max())
    
    def cum_mean(self):
        from ..operators.stats_operators import cum_mean
        return self._add_operator(cum_mean())
    
    def cum_prod(self):
        from ..operators.stats_operators import cum_prod
        return self._add_operator(cum_prod())
    
    # ========== 排序 Top-N 算子 ==========
    
    def sort(self, key_fn=None, reverse=False):
        from ..operators.stats_operators import sort
        return self._add_operator(sort(key_fn, reverse))
    
    def top_k(self, k: int, key_fn=None):
        from ..operators.stats_operators import top_k
        return self._add_operator(top_k(k, key_fn))
    
    def bottom_k(self, k: int, key_fn=None):
        from ..operators.stats_operators import bottom_k
        return self._add_operator(bottom_k(k, key_fn))
    
    # ========== None 值处理与数学工具 ==========
    
    def drop_none(self):
        from ..operators.stats_operators import drop_none
        return self._add_operator(drop_none())
    
    def fill_none(self, default_value):
        from ..operators.stats_operators import fill_none
        return self._add_operator(fill_none(default_value))
    
    def abs(self):
        from ..operators.stats_operators import abs_op
        return self._add_operator(abs_op())
    
    def clamp(self, min_val, max_val):
        from ..operators.stats_operators import clamp
        return self._add_operator(clamp(min_val, max_val))
    
    # ========== 嵌套流展开算子 ==========
    
    def explode(self):
        from ..operators.stats_operators import explode
        return self._add_operator(explode())
    
    def flatten(self):
        from ..operators.stats_operators import flatten
        return self._add_operator(flatten())

    # ========== worker 分发 ==========

    def dispatch_to_workers(self, fn=None, num_workers=4, buffer_size=0,
                             on_drop=None, drop_strategy="oldest", **kwargs):
        from ..operators import dispatch_to_workers
        return self._add_operator(dispatch_to_workers(
            fn=fn, num_workers=num_workers, buffer_size=buffer_size,
            on_drop=on_drop, drop_strategy=drop_strategy, **kwargs))

    def dispatch_workers(self, fn=None, num_workers=4, buffer_size=0,
                         on_drop=None, drop_strategy="oldest", **kwargs):
        return self.dispatch_to_workers(fn, num_workers, buffer_size,
                                        on_drop, drop_strategy, **kwargs)

    def amb(self, *sources):
        from ..operators import amb
        return self._add_operator(amb(*sources))
    def backpressure_buffer(self, max_size=None):
        from ..operators import backpressure_buffer
        return self._add_operator(backpressure_buffer(max_size))
    def backpressure_drop(self):
        from ..operators import backpressure_drop
        return self._add_operator(backpressure_drop())
    def backpressure_error(self, max_size=1):
        from ..operators import backpressure_error
        return self._add_operator(backpressure_error(max_size))
    def backpressure_latest(self):
        from ..operators import backpressure_latest
        return self._add_operator(backpressure_latest())
    def buffer_until_idle(self, idle_seconds, max_size):
        from ..operators import buffer_until_idle
        return self._add_operator(buffer_until_idle(idle_seconds, max_size))
    def buffer_with_count(self, count):
        from ..operators import buffer_with_count
        return self._add_operator(buffer_with_count(count))
    def cache(self, duration=None, max_size=None):
        from ..operators import cache
        return self._add_operator(cache(duration, max_size))
    def circuit_breaker(self, threshold=5, reset_timeout=60.0):
        from ..operators import circuit_breaker
        return self._add_operator(circuit_breaker(threshold, reset_timeout))
    def collect_until(self, condition, on_collected, inclusive):
        from ..operators import collect_until
        return self._add_operator(collect_until(condition, on_collected, inclusive))
    def combine_latest(self, *sources):
        from ..operators import combine_latest
        return self._add_operator(combine_latest(*sources))
    
    def zip(self, *sources):
        from ..operators import zip
        return self._add_operator(zip(*sources))
    def count_events(self, ):
        from ..operators import count_events
        return self._add_operator(count_events())
    def curry_map(self, fn, *args):
        from ..operators import curry_map
        return self._add_operator(curry_map(fn, *args))
    def debounce_data(self, wait_seconds, key_fn):
        from ..operators import debounce_data
        return self._add_operator(debounce_data(wait_seconds, key_fn))
    def debounce_events(self, wait_seconds):
        from ..operators import debounce_events
        return self._add_operator(debounce_events(wait_seconds))
    def debounce_evolution(self, due_time, estimator=None):
        from ..operators import debounce_evolution
        return self._add_operator(debounce_evolution(due_time, estimator))
    def distinct_until_changed_by(self, key_fn):
        from ..operators import distinct_until_changed_by
        return self._add_operator(distinct_until_changed_by(key_fn))
    def distinct_values(self, key_fn):
        from ..operators import distinct_values
        return self._add_operator(distinct_values(key_fn))
    def do_on_completed(self, fn):
        from ..operators import do_on_completed
        return self._add_operator(do_on_completed(fn))
    def do_on_error(self, fn):
        from ..operators import do_on_error
        return self._add_operator(do_on_error(fn))
    def do_on_next(self, fn):
        from ..operators import do_on_next
        return self._add_operator(do_on_next(fn))
    def finally_with_data(self, on_finally):
        from ..operators import finally_with_data
        return self._add_operator(finally_with_data(on_finally))
    def filter_by(self, predicate):
        from ..operators import filter_by
        return self._add_operator(filter_by(predicate))
    def filter_by_data(self, predicate, **data_matchers):
        from ..operators import filter_by_data
        return self._add_operator(filter_by_data(predicate, **data_matchers))
    def filter_by_event_type(self, *event_types):
        from ..operators import filter_by_event_type
        return self._add_operator(filter_by_event_type(*event_types))
    def flat_map_latest(self, fn):
        from ..operators import flat_map_latest
        return self._add_operator(flat_map_latest(fn))
    def group_by_event_type(self, type_extractor):
        from ..operators import group_by_event_type
        return self._add_operator(group_by_event_type(type_extractor))
    def ignore_elements(self, ):
        from ..operators import ignore_elements
        return self._add_operator(ignore_elements())
    def lazy_flat_map(self, lazy_fn, **kwargs):
        from ..operators import lazy_flat_map
        return self._add_operator(lazy_flat_map(lazy_fn, **kwargs))
    def observe_on(self, scheduler):
        from ..operators import observe_on
        return self._add_operator(observe_on(scheduler))
    def on_condition_met(self, condition, on_met, once):
        from ..operators import on_condition_met
        return self._add_operator(on_condition_met(condition, on_met, once))
    def on_data(self, predicate, on_match):
        from ..operators import on_data
        return self._add_operator(on_data(predicate, on_match))
    def on_every_nth(self, n, on_nth):
        from ..operators import on_every_nth
        return self._add_operator(on_every_nth(n, on_nth))
    def on_next_data(self, on_next):
        from ..operators import on_next_data
        return self._add_operator(on_next_data(on_next))
    def on_start(self, callback):
        from ..operators import on_start
        return self._add_operator(on_start(callback))
    def on_stop(self, callback):
        from ..operators import on_stop
        return self._add_operator(on_stop(callback))
    def parallel(self, max_concurrent=4):
        from ..operators import parallel
        return self._add_operator(parallel(max_concurrent))
    def rate_limit(self, events_per_second, burst):
        from ..operators import rate_limit
        return self._add_operator(rate_limit(events_per_second, burst))
    def retry_with_backoff(self, max_retries=None, initial_delay=1.0, max_delay=60.0, multiplier=2.0):
        from ..operators import retry_with_backoff
        return self._add_operator(retry_with_backoff(max_retries, initial_delay, max_delay, multiplier))
    def sample(self, period):
        from ..operators import sample
        return self._add_operator(sample(period))
    def sample_first(self, period_seconds):
        from ..operators import sample_first
        return self._add_operator(sample_first(period_seconds))
    def seq_bridge(self, seq_op):
        from ..operators import seq_bridge
        return self._add_operator(seq_bridge(seq_op))
    def skip_last(self, n):
        from ..operators import skip_last
        return self._add_operator(skip_last(n))
    def skip_n_events(self, n):
        from ..operators import skip_n_events
        return self._add_operator(skip_n_events(n))
    def skip_until_data(self, predicate, inclusive):
        from ..operators import skip_until_data
        return self._add_operator(skip_until_data(predicate, inclusive))
    def subscribe_on(self, scheduler):
        from ..operators import subscribe_on
        return self._add_operator(subscribe_on(scheduler))
    def switch(self, ):
        from ..operators import switch
        return self._add_operator(switch())
    def take_last(self, n):
        from ..operators import take_last
        return self._add_operator(take_last(n))
    def take_n_events(self, n):
        from ..operators import take_n_events
        return self._add_operator(take_n_events(n))
    def take_until_data(self, predicate, inclusive):
        from ..operators import take_until_data
        return self._add_operator(take_until_data(predicate, inclusive))
    def throttle_events(self, period_seconds, key_fn):
        from ..operators import throttle_events
        return self._add_operator(throttle_events(period_seconds, key_fn))
    def throttle_latest(self, period):
        from ..operators import throttle_latest
        return self._add_operator(throttle_latest(period))
    def throttle_with_trailing(self, duration, trailing):
        from ..operators import throttle_with_trailing
        return self._add_operator(throttle_with_trailing(duration, trailing))
    def time_interval(self, ):
        from ..operators import time_interval
        return self._add_operator(time_interval())
    def to_map(self, key_fn):
        from ..operators import to_map
        return self._add_operator(to_map(key_fn))
    def to_set(self, ):
        from ..operators import to_set
        return self._add_operator(to_set())
    def when(self, predicate, handler):
        from ..operators import when
        return self._add_operator(when(predicate, handler))
    def when_error(self, on_error):
        from ..operators import when_error
        return self._add_operator(when_error(on_error))
    def when_start(self, predicate):
        from ..operators import when_start
        return self._add_operator(when_start(predicate))
    def when_stop(self, predicate, inclusive: bool = True):
        from ..operators import when_stop
        return self._add_operator(when_stop(predicate, inclusive))
    def window(self, window_size):
        from ..operators import window
        return self._add_operator(window(window_size))
    def with_latest_from(self, other):
        from ..operators import with_latest_from
        return self._add_operator(with_latest_from(other))
    def with_state(self, initial_state, reducer, on_state_change):
        from ..operators import with_state
        return self._add_operator(with_state(initial_state, reducer, on_state_change))


class Observable(Generic[T]):
    """Observable 核心类"""
    
    __slots__ = ('_subscribe_fn', '_source', '_subject', '_connection', '_subscriptions', '_has_subscribed', 'connect')
    
    def __init__(self, subscribe_fn):
        self._subscribe_fn = subscribe_fn

    def __getstate__(self):
        """Return serialization state"""
        d = {}
        for s in ('_subscribe_fn', '_source', '_subject', '_connection', '_has_subscribed'):
            try:
                d[s] = getattr(self, s)
            except AttributeError:
                d[s] = None
        d['connect'] = getattr(self, 'connect', None)
        return d
    def __setstate__(self, state):
        """Restore from serialization state"""
        for s in ('_subscribe_fn', '_source', '_subject', '_connection', '_has_subscribed'):
            object.__setattr__(self, s, state.get(s))
        self._subscriptions = set()
        object.__setattr__(self, 'connect', state.get('connect'))

    def subscribe(self, on_next=None, on_error=None, on_completed=None, observer=None):
        if observer is None:
            observer_pool = get_pool(DefaultObserver, max_size=200, min_size=20)
            observer = observer_pool.acquire()
            observer._on_next = on_next or (lambda _: None)
            observer._on_error = on_error or (lambda e: None)
            observer._on_completed = on_completed or (lambda: None)
            observer._pool = observer_pool
        
        subscription = self._subscribe_fn(observer)
        
        original_unsubscribe = subscription._unsubscribe
        def wrapped_unsubscribe():
            original_unsubscribe()
            if hasattr(observer, 'release') and callable(observer.release):
                observer.release()
        
        subscription._unsubscribe = wrapped_unsubscribe
        return subscription
    
    def subscribe_(self, on_next=None, on_error=None, on_completed=None):
        """直接传递回调函数，避免创建 DefaultObserver"""
        observer_pool = get_pool(DefaultObserver, max_size=200, min_size=20)
        observer = observer_pool.acquire()
        observer._on_next = on_next or (lambda _: None)
        observer._on_error = on_error or (lambda e: None)
        observer._on_completed = on_completed or (lambda: None)
        observer._pool = observer_pool
        
        subscription = self._subscribe_fn(observer)
        
        if subscription is None:
            return Subscription(lambda: observer.release())
        
        original_unsubscribe = subscription._unsubscribe
        def wrapped_unsubscribe():
            original_unsubscribe()
            observer.release()
        
        subscription._unsubscribe = wrapped_unsubscribe
        return subscription
    
    pipe = PipeDescriptor[T]()
    
    def p(self) -> PipeBuilder[T]:
        """返回链式管道构建器"""
        return PipeBuilder(self)
    
    def __rshift__(self, other):
        return self.pipe(other)
    
    @classmethod
    def from_iterable(cls, iterable):
        def subscribe(observer):
            iterator = iter(iterable)
            subscription = None
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            subscription = Subscription(unsubscribe)
            
            try:
                while not is_closed:
                    observer.on_next(next(iterator))
                    if is_closed:
                        break
            except StopIteration:
                pass
            
            if not is_closed:
                observer.on_completed()
            
            return subscription
        return cls(subscribe)
    
    @classmethod
    def just(cls, *values):
        return cls.from_iterable(values)
    
    @classmethod
    def of(cls, *values):
        return cls.just(*values)
    
    @classmethod
    def from_range(cls, n):
        return cls.from_iterable(range(n))
    
    @classmethod
    def empty(cls):
        def subscribe(observer):
            observer.on_completed()
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def never(cls):
        def subscribe(observer):
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def error(cls, error):
        def subscribe(observer):
            observer.on_error(error)
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def throw(cls, error):
        return cls.error(error)
    
    @classmethod
    def interval(cls, period: float):
        """创建一个每隔指定时间发射递增整数的 Observable

        Args:
            period: 发射间隔（秒）

        Returns:
            Observable[int]: 发射 0, 1, 2, 3, ... 的序列
        """
        def subscribe(observer):
            counter = 0
            stopped = threading.Event()

            def emit_loop():
                nonlocal counter
                while not stopped.is_set():
                    observer.on_next(counter)
                    counter += 1
                    stopped.wait(timeout=period)
                    # 如果 period 期间触发了停止，wait 提前返回 True，循环退出

            def unsubscribe():
                stopped.set()

            t = threading.Thread(target=emit_loop, daemon=True)
            t.start()

            return Subscription(unsubscribe)

        return cls(subscribe)
    
    @classmethod
    def timer(cls, due_time: float, period: float = None):
        """创建一个在指定延迟后发射单个值或周期性发射值的 Observable

        Args:
            due_time: 首次发射前的延迟（秒）
            period: 后续发射的间隔（秒），如果为 None 则只发射一次

        Returns:
            Observable[int]: 发射 0, 1, 2, 3, ... 的序列
        """
        def subscribe(observer):
            counter = 0
            stopped = threading.Event()

            def emit_once():
                nonlocal counter
                # 等待首次延迟
                if stopped.wait(timeout=due_time):
                    return  # 被取消
                observer.on_next(counter)
                counter += 1

                if period is None:
                    observer.on_completed()
                    return

                # 周期性发射
                while not stopped.is_set():
                    observer.on_next(counter)
                    counter += 1
                    stopped.wait(timeout=period)

            def unsubscribe():
                stopped.set()

            t = threading.Thread(target=emit_once, daemon=True)
            t.start()

            return Subscription(unsubscribe)

        return cls(subscribe)
    
    @classmethod
    def defer(cls, factory: Callable[[], 'Observable[T]']):
        """延迟创建 Observable，直到订阅时才调用工厂函数
        
        Args:
            factory: 返回 Observable 的工厂函数
        
        Returns:
            Observable[T]: 由工厂函数创建的 Observable
        """
        def subscribe(observer):
            observable = factory()
            if isinstance(observer, DefaultObserver):
                return observable.subscribe(
                    on_next=observer._on_next,
                    on_error=observer._on_error,
                    on_completed=observer._on_completed
                )
            return observable.subscribe(observer)
        
        return cls(subscribe)
    
    @classmethod
    def repeat(cls, value, times: int = None):
        """创建一个重复发射指定值的 Observable
        
        Args:
            value: 要重复发射的值
            times: 重复次数，如果为 None 则无限重复
        
        Returns:
            Observable[T]: 重复发射指定值的序列
        """
        def subscribe(observer):
            if times is None:
                def unsubscribe():
                    pass
                
                while True:
                    observer.on_next(value)
                
                return Subscription(unsubscribe)
            else:
                for _ in range(times):
                    observer.on_next(value)
                observer.on_completed()
                return Subscription(lambda: None)
        
        return cls(subscribe)
    
    @classmethod
    def from_range(cls, start_or_stop: int, stop: int = None, step: int = 1):
        """创建发出范围序列整数的 Observable
        
        Args:
            start_or_stop: 起始值（包含）或结束值（不包含）
            stop: 结束值（不包含）
            step: 步长
        
        Returns:
            Observable[int]: 发出整数序列
        
        Example:
            >>> Observable.from_range(5)  # 0, 1, 2, 3, 4
            >>> Observable.from_range(2, 6)  # 2, 3, 4, 5
            >>> Observable.from_range(0, 10, 2)  # 0, 2, 4, 6, 8
        """
        if stop is None:
            start_val = 0
            stop_val = start_or_stop
        else:
            start_val = start_or_stop
            stop_val = stop
        
        def subscribe(observer):
            try:
                for i in range(start_val, stop_val, step):
                    observer.on_next(i)
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
            
            return Subscription(lambda: None)
        
        return cls(subscribe)
    
    @classmethod
    def from_callable(cls, func: Callable[[], T]):
        """从 Callable 创建 Observable
        
        Args:
            func: 返回值的 Callable
        
        Returns:
            Observable[T]: 发出 Callable 返回的值
        """
        def subscribe(observer):
            try:
                result = func()
                observer.on_next(result)
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
            
            return Subscription(lambda: None)
        
        return cls(subscribe)
    
    @classmethod
    def from_future(cls, future):
        """从 Future 创建 Observable
        
        Args:
            future: concurrent.futures.Future 对象
        
        Returns:
            Observable[T]: 发出 Future 结果
        """
        def subscribe(observer):
            def done_callback(f):
                try:
                    observer.on_next(f.result())
                    observer.on_completed()
                except Exception as e:
                    observer.on_error(e)
            
            future.add_done_callback(done_callback)
            
            return Subscription(lambda: future.cancel() if hasattr(future, 'cancel') else None)
        
        return cls(subscribe)