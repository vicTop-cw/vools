"""
vools-reactive Observable Core
"""

from typing import TypeVar, Callable, Optional, Any, Generic, Iterator, AsyncIterator, Union, Iterable
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
    """订阅管理类 - 性能优化版本"""
    
    __slots__ = ('_unsubscribe', '_is_closed', '_children')
    
    def __init__(self, unsubscribe):
        self._unsubscribe = unsubscribe
        self._is_closed = False
        self._children = None  # 使用None代替set()，减少内存开销
    
    def add_child(self, child):
        """添加子订阅"""
        if self._children is None:
            self._children = []
        self._children.append(child)
    
    def remove_child(self, child):
        """移除子订阅"""
        if self._children is not None and child in self._children:
            self._children.remove(child)
    
    def unsubscribe(self):
        if not self._is_closed:
            self._is_closed = True
            if self._children is not None:
                for child in self._children:
                    child.unsubscribe()
            self._unsubscribe()
    
    def dispose(self):
        """dispose 别名，与 RxPY/rx-rust 对齐"""
        self.unsubscribe()
    
    @property
    def is_closed(self) -> bool:
        """检查订阅是否已关闭"""
        return self._is_closed
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unsubscribe()
        return False


class Observer(Generic[T], ABC):
    """观察者抽象基类 - 性能优化版本，支持通过返回值控制流"""
    
    @abstractmethod
    def on_next(self, value: T) -> Optional[bool]:
        """收到下一个数据
        
        Returns:
            Optional[bool]: None继续正常处理，True停止后续迭代，False跳过本次
        """
        pass
    
    @abstractmethod
    def on_error(self, error: Exception) -> None:
        """收到错误"""
        pass
    
    @abstractmethod
    def on_completed(self) -> None:
        """流完成"""
        pass


class DefaultObserver(Observer[T]):
    """默认观察者实现 - 性能优化版本"""
    
    __slots__ = ('_on_next', '_on_error', '_on_completed', '_pool')
    
    def __init__(self, on_next=None, on_error=None, on_completed=None):
        self._on_next = on_next or (lambda _: None)
        self._on_error = on_error or (lambda e: None)
        self._on_completed = on_completed or (lambda: None)
        self._pool = None
    
    def on_next(self, value: T) -> Optional[bool]:
        """收到下一个数据
        
        Returns:
            Optional[bool]: None继续，True停止，False跳过
        """
        result = self._on_next(value)
        # 如果回调返回True，表示要停止迭代
        return result if result is not None else None
    
    def on_error(self, error: Exception) -> None:
        """收到错误"""
        self._on_error(error)
    
    def on_completed(self) -> None:
        """流完成"""
        self._on_completed()
    
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.
        
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
    
    def __get__(self, instance: "Observable", owner=None) -> "PipeBuilder":
        if instance is None:
            return self
        return PipeBuilder(instance, origin=instance)


class PipeBuilder(Generic[T]):
    """链式管道构建器"""
    
    __slots__ = ('_source', '_operators', '_origin', '_cached_result')
    
    def __init__(self, source: "Observable[T]", origin=None) -> None:
        self._source = source
        self._operators = []
        self._origin = origin if origin is not None else source
        self._cached_result = None
    
    def _add_operator(self, operator: Callable) -> "PipeBuilder[T]":
        """添加操作符到管道"""
        self._operators.append(operator)
        self._cached_result = None
        return self
    
    def _build(self) -> "Observable[Any]":
        """构建最终的 Observable"""
        if self._cached_result is not None:
            return self._cached_result
        source = self._source
        for op in self._operators:
            source = op(source)
        self._cached_result = source
        return source
    
    def subscribe(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        observer: Optional[Observer[T]] = None
    ) -> Subscription:
        """直接订阅"""
        if hasattr(self._origin, 'start') and callable(self._origin.start):
            self._origin.start()
        return self._build().subscribe(on_next, on_error, on_completed, observer)
    
    def connect(self) -> Subscription:
        """连接 ConnectableObservable"""
        result = self._build()
        if hasattr(result, 'connect'):
            return result.connect()
        raise AttributeError("'PipeBuilder' object has no attribute 'connect' - the result is not a ConnectableObservable")
    
    def __getattr__(self, name: str) -> Any:
        """代理其他属性到构建结果"""
        result = self._build()
        if hasattr(result, name):
            return getattr(result, name)
        raise AttributeError(f"'PipeBuilder' object has no attribute '{name}'")
    
    def __rshift__(self, other: Callable) -> "PipeBuilder[T]":
        """支持 >> 操作符"""
        if callable(other):
            self._operators.append(other)
        return self
    
    def __call__(self, *operators: Callable) -> Union["PipeBuilder[T]", Subscription]:
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
    
    def map(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.map"""
        from ..operators import map
        return self._add_operator(map(fn, **kwargs))
    
    def filter(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.filter"""
        from ..operators import filter
        return self._add_operator(filter(fn, **kwargs))
    
    def flat_map(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.flat_map"""
        from ..operators import flat_map
        return self._add_operator(flat_map(fn, **kwargs))
    
    def concat_map(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.concat_map"""
        from ..operators import concat_map
        return self._add_operator(concat_map(fn, **kwargs))
    
    def switch_map(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.switch_map"""
        from ..operators import switch_map
        return self._add_operator(switch_map(fn, **kwargs))
    
    def take(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.take"""
        from ..operators import take
        return self._add_operator(take(n))
    
    def skip(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.skip"""
        from ..operators import skip
        return self._add_operator(skip(n))
    
    def take_while(self, predicate=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.take_while"""
        from ..operators import take_while
        return self._add_operator(take_while(predicate, **kwargs))
    
    def skip_while(self, predicate=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.skip_while"""
        from ..operators import skip_while
        return self._add_operator(skip_while(predicate, **kwargs))
    
    def take_until(self, other) -> "PipeBuilder[T]":
        """代理到 ops.take_until"""
        from ..operators import take_until
        return self._add_operator(take_until(other))
    
    def distinct_until_changed(self, key_fn=None) -> "PipeBuilder[T]":
        """代理到 ops.distinct_until_changed"""
        from ..operators import distinct_until_changed
        return self._add_operator(distinct_until_changed(key_fn))
    
    def debounce(self, due_time) -> "PipeBuilder[T]":
        """代理到 ops.debounce"""
        from ..operators import debounce
        return self._add_operator(debounce(due_time))
    
    def throttle_first(self, duration) -> "PipeBuilder[T]":
        """代理到 ops.throttle_first"""
        from ..operators import throttle_first
        return self._add_operator(throttle_first(duration))
    
    def tap(self, fn=None, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.tap"""
        from ..operators import tap
        return self._add_operator(tap(fn, **kwargs))
    
    def delay(self, due_time) -> "PipeBuilder[T]":
        """代理到 ops.delay"""
        from ..operators import delay
        return self._add_operator(delay(due_time))
    
    def start_with(self, *values) -> "PipeBuilder[T]":
        """代理到 ops.start_with"""
        from ..operators import start_with
        return self._add_operator(start_with(*values))
    
    def end_with(self, *values) -> "PipeBuilder[T]":
        """代理到 ops.end_with"""
        from ..operators import end_with
        return self._add_operator(end_with(*values))
    
    def reduce(self, accumulator, seed=None) -> "PipeBuilder[T]":
        """代理到 ops.reduce"""
        from ..operators import reduce
        return self._add_operator(reduce(accumulator, seed))
    
    def scan(self, accumulator, seed=None) -> "PipeBuilder[T]":
        """代理到 ops.scan"""
        from ..operators import scan
        return self._add_operator(scan(accumulator, seed))
    
    def count(self) -> "PipeBuilder[T]":
        """代理到 ops.count"""
        from ..operators import count
        return self._add_operator(count())
    
    def sum(self, key_mapper=None) -> "PipeBuilder[T]":
        """代理到 ops.sum"""
        from ..operators import sum
        return self._add_operator(sum(key_mapper))
    
    def average(self, key_mapper=None) -> "PipeBuilder[T]":
        """代理到 ops.average"""
        from ..operators import average
        return self._add_operator(average(key_mapper))
    
    def minimum(self, key_mapper=None) -> "PipeBuilder[T]":
        """代理到 ops.minimum"""
        from ..operators import minimum
        return self._add_operator(minimum(key_mapper))
    
    def maximum(self, key_mapper=None) -> "PipeBuilder[T]":
        """代理到 ops.maximum"""
        from ..operators import maximum
        return self._add_operator(maximum(key_mapper))
    
    def all(self, predicate) -> "PipeBuilder[T]":
        """代理到 ops.all"""
        from ..operators import all
        return self._add_operator(all(predicate))
    
    def any(self, predicate=None) -> "PipeBuilder[T]":
        """代理到 ops.any"""
        from ..operators import any
        return self._add_operator(any(predicate))
    
    def contains(self, value) -> "PipeBuilder[T]":
        """代理到 ops.contains"""
        from ..operators import contains
        return self._add_operator(contains(value))
    
    def is_empty(self) -> "PipeBuilder[T]":
        """代理到 ops.is_empty"""
        from ..operators import is_empty
        return self._add_operator(is_empty())
    
    def to_list(self) -> "PipeBuilder[T]":
        """代理到 ops.to_list"""
        from ..operators import to_list
        return self._add_operator(to_list())
    
    def buffer(self, count) -> "PipeBuilder[T]":
        """代理到 ops.buffer"""
        from ..operators import buffer
        return self._add_operator(buffer(count))
    
    def group_by(self, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.group_by"""
        from ..operators import group_by
        return self._add_operator(group_by(key_fn))
    
    def merge(self, *others) -> "PipeBuilder[T]":
        """代理到 ops.merge"""
        from ..operators import merge
        return self._add_operator(merge(*others))
    
    def concat(self, *others) -> "PipeBuilder[T]":
        """代理到 ops.concat"""
        from ..operators import concat
        return self._add_operator(concat(*others))
    
    def catch(self, handler) -> "PipeBuilder[T]":
        """代理到 ops.catch"""
        from ..operators import catch
        return self._add_operator(catch(handler))
    
    def retry(self, times=None) -> "PipeBuilder[T]":
        """代理到 ops.retry"""
        from ..operators import retry
        return self._add_operator(retry(times))
    
    def on_error_return(self, value) -> "PipeBuilder[T]":
        """代理到 ops.on_error_return"""
        from ..operators import on_error_return
        return self._add_operator(on_error_return(value))
    
    def on_error_resume_next(self, fallback) -> "PipeBuilder[T]":
        """代理到 ops.on_error_resume_next"""
        from ..operators import on_error_resume_next
        return self._add_operator(on_error_resume_next(fallback))
    
    def retry_when(self, handler) -> "PipeBuilder[T]":
        """代理到 ops.retry_when"""
        from ..operators import retry_when
        return self._add_operator(retry_when(handler))
    
    # ========== 新增操作符 ==========
    
    def first(self, predicate=None) -> "PipeBuilder[T]":
        """代理到 ops.first"""
        from ..operators import first
        return self._add_operator(first(predicate))
    
    def last(self, predicate=None) -> "PipeBuilder[T]":
        """代理到 ops.last"""
        from ..operators import last
        return self._add_operator(last(predicate))
    
    def distinct(self, key_fn=None) -> "PipeBuilder[T]":
        """代理到 ops.distinct"""
        from ..operators import distinct
        return self._add_operator(distinct(key_fn))
    
    def element_at(self, index: int) -> "PipeBuilder[T]":
        """代理到 ops.element_at"""
        from ..operators import element_at
        return self._add_operator(element_at(index))
    
    def skip_until(self, other) -> "PipeBuilder[T]":
        """代理到 ops.skip_until"""
        from ..operators import skip_until
        return self._add_operator(skip_until(other))
    
    def default_if_empty(self, default_value) -> "PipeBuilder[T]":
        """代理到 ops.default_if_empty"""
        from ..operators import default_if_empty
        return self._add_operator(default_if_empty(default_value))
    
    def sequence_equal(self, other) -> "PipeBuilder[T]":
        """代理到 ops.sequence_equal"""
        from ..operators import sequence_equal
        return self._add_operator(sequence_equal(other))
    
    def timeout(self, timeout_duration) -> "PipeBuilder[T]":
        """代理到 ops.timeout"""
        from ..operators import timeout
        return self._add_operator(timeout(timeout_duration))
    
    def timestamp(self) -> "PipeBuilder[T]":
        """代理到 ops.timestamp"""
        from ..operators import timestamp
        return self._add_operator(timestamp())
    
    def iif(self, condition=None, true_body=None, false_body=None) -> "PipeBuilder[T]":
        """代理到 ops.iif"""
        from ..operators import iif
        return self._add_operator(iif(condition, true_body, false_body))
    
    # ========== 统计聚合扩展算子 ==========
    
    def median(self) -> "PipeBuilder[T]":
        """代理到 ops.median"""
        from ..operators.stats_operators import median
        return self._add_operator(median())
    
    def variance(self, ddof: int = 0) -> "PipeBuilder[T]":
        """代理到 ops.variance"""
        from ..operators.stats_operators import variance
        return self._add_operator(variance(ddof))
    
    def std(self, ddof: int = 0) -> "PipeBuilder[T]":
        """代理到 ops.std"""
        from ..operators.stats_operators import std
        return self._add_operator(std(ddof))
    
    def quantile(self, q: float) -> "PipeBuilder[T]":
        """代理到 ops.quantile"""
        from ..operators.stats_operators import quantile
        return self._add_operator(quantile(q))
    
    def arg_min(self) -> "PipeBuilder[T]":
        """代理到 ops.arg_min"""
        from ..operators.stats_operators import arg_min
        return self._add_operator(arg_min())
    
    def arg_max(self) -> "PipeBuilder[T]":
        """代理到 ops.arg_max"""
        from ..operators.stats_operators import arg_max
        return self._add_operator(arg_max())
    
    def n_unique(self) -> "PipeBuilder[T]":
        """代理到 ops.n_unique"""
        from ..operators.stats_operators import n_unique
        return self._add_operator(n_unique())
    
    # ========== 滚动窗口算子 ==========
    
    def rolling_sum(self, window_size: int) -> "PipeBuilder[T]":
        """代理到 ops.rolling_sum"""
        from ..operators.stats_operators import rolling_sum
        return self._add_operator(rolling_sum(window_size))
    
    def rolling_min(self, window_size: int) -> "PipeBuilder[T]":
        """代理到 ops.rolling_min"""
        from ..operators.stats_operators import rolling_min
        return self._add_operator(rolling_min(window_size))
    
    def rolling_max(self, window_size: int) -> "PipeBuilder[T]":
        """代理到 ops.rolling_max"""
        from ..operators.stats_operators import rolling_max
        return self._add_operator(rolling_max(window_size))
    
    def rolling_mean(self, window_size: int) -> "PipeBuilder[T]":
        """代理到 ops.rolling_mean"""
        from ..operators.stats_operators import rolling_mean
        return self._add_operator(rolling_mean(window_size))
    
    # ========== 累积变换算子 ==========
    
    def cum_sum(self) -> "PipeBuilder[T]":
        """代理到 ops.cum_sum"""
        from ..operators.stats_operators import cum_sum
        return self._add_operator(cum_sum())
    
    def cum_min(self) -> "PipeBuilder[T]":
        """代理到 ops.cum_min"""
        from ..operators.stats_operators import cum_min
        return self._add_operator(cum_min())
    
    def cum_max(self) -> "PipeBuilder[T]":
        """代理到 ops.cum_max"""
        from ..operators.stats_operators import cum_max
        return self._add_operator(cum_max())
    
    def cum_mean(self) -> "PipeBuilder[T]":
        """代理到 ops.cum_mean"""
        from ..operators.stats_operators import cum_mean
        return self._add_operator(cum_mean())
    
    def cum_prod(self) -> "PipeBuilder[T]":
        """代理到 ops.cum_prod"""
        from ..operators.stats_operators import cum_prod
        return self._add_operator(cum_prod())
    
    # ========== 排序 Top-N 算子 ==========
    
    def sort(self, key_fn=None, reverse: bool = False) -> "PipeBuilder[T]":
        """代理到 ops.sort"""
        from ..operators.stats_operators import sort
        return self._add_operator(sort(key_fn, reverse))
    
    def top_k(self, k: int, key_fn=None) -> "PipeBuilder[T]":
        """代理到 ops.top_k"""
        from ..operators.stats_operators import top_k
        return self._add_operator(top_k(k, key_fn))
    
    def bottom_k(self, k: int, key_fn=None) -> "PipeBuilder[T]":
        """代理到 ops.bottom_k"""
        from ..operators.stats_operators import bottom_k
        return self._add_operator(bottom_k(k, key_fn))
    
    # ========== None 值处理与数学工具 ==========
    
    def drop_none(self) -> "PipeBuilder[T]":
        """代理到 ops.drop_none"""
        from ..operators.stats_operators import drop_none
        return self._add_operator(drop_none())
    
    def fill_none(self, default_value) -> "PipeBuilder[T]":
        """代理到 ops.fill_none"""
        from ..operators.stats_operators import fill_none
        return self._add_operator(fill_none(default_value))
    
    def abs(self) -> "PipeBuilder[T]":
        """代理到 ops.abs_op"""
        from ..operators.stats_operators import abs_op
        return self._add_operator(abs_op())
    
    def clamp(self, min_val, max_val) -> "PipeBuilder[T]":
        """代理到 ops.clamp"""
        from ..operators.stats_operators import clamp
        return self._add_operator(clamp(min_val, max_val))
    
    # ========== 嵌套流展开算子 ==========
    
    def explode(self) -> "PipeBuilder[T]":
        """代理到 ops.explode"""
        from ..operators.stats_operators import explode
        return self._add_operator(explode())
    
    def flatten(self) -> "PipeBuilder[T]":
        """代理到 ops.flatten"""
        from ..operators.stats_operators import flatten
        return self._add_operator(flatten())

    # ========== worker 分发 ==========

    def dispatch_to_workers(
        self,
        fn=None,
        num_workers: int = 4,
        buffer_size: int = 0,
        on_drop=None,
        drop_strategy: str = "oldest",
        **kwargs
    ) -> "PipeBuilder[T]":
        """代理到 ops.dispatch_to_workers"""
        from ..operators import dispatch_to_workers
        return self._add_operator(dispatch_to_workers(
            fn=fn, num_workers=num_workers, buffer_size=buffer_size,
            on_drop=on_drop, drop_strategy=drop_strategy, **kwargs))

    def dispatch_workers(
        self,
        fn=None,
        num_workers: int = 4,
        buffer_size: int = 0,
        on_drop=None,
        drop_strategy: str = "oldest",
        **kwargs
    ) -> "PipeBuilder[T]":
        """代理到 ops.dispatch_workers"""
        return self.dispatch_to_workers(fn, num_workers, buffer_size,
                                        on_drop, drop_strategy, **kwargs)

    def amb(self, *sources) -> "PipeBuilder[T]":
        """代理到 ops.amb"""
        from ..operators import amb
        return self._add_operator(amb(*sources))
    
    def backpressure_buffer(self, max_size=None) -> "PipeBuilder[T]":
        """代理到 ops.backpressure_buffer"""
        from ..operators import backpressure_buffer
        return self._add_operator(backpressure_buffer(max_size))
    
    def backpressure_drop(self) -> "PipeBuilder[T]":
        """代理到 ops.backpressure_drop"""
        from ..operators import backpressure_drop
        return self._add_operator(backpressure_drop())
    
    def backpressure_error(self, max_size: int = 1) -> "PipeBuilder[T]":
        """代理到 ops.backpressure_error"""
        from ..operators import backpressure_error
        return self._add_operator(backpressure_error(max_size))
    
    def backpressure_latest(self) -> "PipeBuilder[T]":
        """代理到 ops.backpressure_latest"""
        from ..operators import backpressure_latest
        return self._add_operator(backpressure_latest())
    
    def buffer_until_idle(self, idle_seconds, max_size) -> "PipeBuilder[T]":
        """代理到 ops.buffer_until_idle"""
        from ..operators import buffer_until_idle
        return self._add_operator(buffer_until_idle(idle_seconds, max_size))
    
    def buffer_with_count(self, count: int) -> "PipeBuilder[T]":
        """代理到 ops.buffer_with_count"""
        from ..operators import buffer_with_count
        return self._add_operator(buffer_with_count(count))
    
    def cache(self, duration=None, max_size=None) -> "PipeBuilder[T]":
        """代理到 ops.cache"""
        from ..operators import cache
        return self._add_operator(cache(duration, max_size))
    
    def circuit_breaker(self, threshold: int = 5, reset_timeout: float = 60.0) -> "PipeBuilder[T]":
        """代理到 ops.circuit_breaker"""
        from ..operators import circuit_breaker
        return self._add_operator(circuit_breaker(threshold, reset_timeout))
    
    def collect_until(self, condition, on_collected, inclusive) -> "PipeBuilder[T]":
        """代理到 ops.collect_until"""
        from ..operators import collect_until
        return self._add_operator(collect_until(condition, on_collected, inclusive))
    
    def combine_latest(self, *sources) -> "PipeBuilder[T]":
        """代理到 ops.combine_latest"""
        from ..operators import combine_latest
        return self._add_operator(combine_latest(*sources))
    
    def zip(self, *sources) -> "PipeBuilder[T]":
        """代理到 ops.zip"""
        from ..operators import zip
        return self._add_operator(zip(*sources))
    
    def count_events(self) -> "PipeBuilder[T]":
        """代理到 ops.count_events"""
        from ..operators import count_events
        return self._add_operator(count_events())
    
    def curry_map(self, fn, *args) -> "PipeBuilder[T]":
        """代理到 ops.curry_map"""
        from ..operators import curry_map
        return self._add_operator(curry_map(fn, *args))
    
    def debounce_data(self, wait_seconds, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.debounce_data"""
        from ..operators import debounce_data
        return self._add_operator(debounce_data(wait_seconds, key_fn))
    
    def debounce_events(self, wait_seconds) -> "PipeBuilder[T]":
        """代理到 ops.debounce_events"""
        from ..operators import debounce_events
        return self._add_operator(debounce_events(wait_seconds))
    
    def debounce_evolution(self, due_time, estimator=None) -> "PipeBuilder[T]":
        """代理到 ops.debounce_evolution"""
        from ..operators import debounce_evolution
        return self._add_operator(debounce_evolution(due_time, estimator))
    
    def distinct_until_changed_by(self, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.distinct_until_changed_by"""
        from ..operators import distinct_until_changed_by
        return self._add_operator(distinct_until_changed_by(key_fn))
    
    def distinct_values(self, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.distinct_values"""
        from ..operators import distinct_values
        return self._add_operator(distinct_values(key_fn))
    
    def do_on_completed(self, fn) -> "PipeBuilder[T]":
        """代理到 ops.do_on_completed"""
        from ..operators import do_on_completed
        return self._add_operator(do_on_completed(fn))
    
    def do_on_error(self, fn) -> "PipeBuilder[T]":
        """代理到 ops.do_on_error"""
        from ..operators import do_on_error
        return self._add_operator(do_on_error(fn))
    
    def do_on_next(self, fn) -> "PipeBuilder[T]":
        """代理到 ops.do_on_next"""
        from ..operators import do_on_next
        return self._add_operator(do_on_next(fn))
    
    def finally_with_data(self, on_finally) -> "PipeBuilder[T]":
        """代理到 ops.finally_with_data"""
        from ..operators import finally_with_data
        return self._add_operator(finally_with_data(on_finally))
    
    def filter_by(self, predicate) -> "PipeBuilder[T]":
        """代理到 ops.filter_by"""
        from ..operators import filter_by
        return self._add_operator(filter_by(predicate))
    
    def filter_by_data(self, predicate, **data_matchers) -> "PipeBuilder[T]":
        """代理到 ops.filter_by_data"""
        from ..operators import filter_by_data
        return self._add_operator(filter_by_data(predicate, **data_matchers))
    
    def filter_by_event_type(self, *event_types) -> "PipeBuilder[T]":
        """代理到 ops.filter_by_event_type"""
        from ..operators import filter_by_event_type
        return self._add_operator(filter_by_event_type(*event_types))
    
    def flat_map_latest(self, fn) -> "PipeBuilder[T]":
        """代理到 ops.flat_map_latest"""
        from ..operators import flat_map_latest
        return self._add_operator(flat_map_latest(fn))
    
    def group_by_event_type(self, type_extractor) -> "PipeBuilder[T]":
        """代理到 ops.group_by_event_type"""
        from ..operators import group_by_event_type
        return self._add_operator(group_by_event_type(type_extractor))
    
    def ignore_elements(self) -> "PipeBuilder[T]":
        """代理到 ops.ignore_elements"""
        from ..operators import ignore_elements
        return self._add_operator(ignore_elements())
    
    def lazy_flat_map(self, lazy_fn, **kwargs) -> "PipeBuilder[T]":
        """代理到 ops.lazy_flat_map"""
        from ..operators import lazy_flat_map
        return self._add_operator(lazy_flat_map(lazy_fn, **kwargs))
    
    def observe_on(self, scheduler) -> "PipeBuilder[T]":
        """代理到 ops.observe_on"""
        from ..operators import observe_on
        return self._add_operator(observe_on(scheduler))
    
    def on_condition_met(self, condition, on_met, once) -> "PipeBuilder[T]":
        """代理到 ops.on_condition_met"""
        from ..operators import on_condition_met
        return self._add_operator(on_condition_met(condition, on_met, once))
    
    def on_data(self, predicate, on_match) -> "PipeBuilder[T]":
        """代理到 ops.on_data"""
        from ..operators import on_data
        return self._add_operator(on_data(predicate, on_match))
    
    def on_every_nth(self, n, on_nth) -> "PipeBuilder[T]":
        """代理到 ops.on_every_nth"""
        from ..operators import on_every_nth
        return self._add_operator(on_every_nth(n, on_nth))
    
    def on_next_data(self, on_next) -> "PipeBuilder[T]":
        """代理到 ops.on_next_data"""
        from ..operators import on_next_data
        return self._add_operator(on_next_data(on_next))
    
    def on_start(self, callback) -> "PipeBuilder[T]":
        """代理到 ops.on_start"""
        from ..operators import on_start
        return self._add_operator(on_start(callback))
    
    def on_stop(self, callback) -> "PipeBuilder[T]":
        """代理到 ops.on_stop"""
        from ..operators import on_stop
        return self._add_operator(on_stop(callback))
    
    def parallel(self, max_concurrent: int = 4) -> "PipeBuilder[T]":
        """代理到 ops.parallel"""
        from ..operators import parallel
        return self._add_operator(parallel(max_concurrent))
    
    def rate_limit(self, events_per_second, burst) -> "PipeBuilder[T]":
        """代理到 ops.rate_limit"""
        from ..operators import rate_limit
        return self._add_operator(rate_limit(events_per_second, burst))
    
    def retry_with_backoff(
        self,
        max_retries=None,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0
    ) -> "PipeBuilder[T]":
        """代理到 ops.retry_with_backoff"""
        from ..operators import retry_with_backoff
        return self._add_operator(retry_with_backoff(max_retries, initial_delay, max_delay, multiplier))
    
    def sample(self, period) -> "PipeBuilder[T]":
        """代理到 ops.sample"""
        from ..operators import sample
        return self._add_operator(sample(period))
    
    def sample_first(self, period_seconds) -> "PipeBuilder[T]":
        """代理到 ops.sample_first"""
        from ..operators import sample_first
        return self._add_operator(sample_first(period_seconds))
    
    def seq_bridge(self, seq_op) -> "PipeBuilder[T]":
        """代理到 ops.seq_bridge"""
        from ..operators import seq_bridge
        return self._add_operator(seq_bridge(seq_op))
    
    def skip_last(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.skip_last"""
        from ..operators import skip_last
        return self._add_operator(skip_last(n))
    
    def skip_n_events(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.skip_n_events"""
        from ..operators import skip_n_events
        return self._add_operator(skip_n_events(n))
    
    def skip_until_data(self, predicate, inclusive) -> "PipeBuilder[T]":
        """代理到 ops.skip_until_data"""
        from ..operators import skip_until_data
        return self._add_operator(skip_until_data(predicate, inclusive))
    
    def subscribe_on(self, scheduler) -> "PipeBuilder[T]":
        """代理到 ops.subscribe_on"""
        from ..operators import subscribe_on
        return self._add_operator(subscribe_on(scheduler))
    
    def switch(self) -> "PipeBuilder[T]":
        """代理到 ops.switch"""
        from ..operators import switch
        return self._add_operator(switch())
    
    def take_last(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.take_last"""
        from ..operators import take_last
        return self._add_operator(take_last(n))
    
    def take_n_events(self, n: int) -> "PipeBuilder[T]":
        """代理到 ops.take_n_events"""
        from ..operators import take_n_events
        return self._add_operator(take_n_events(n))
    
    def take_until_data(self, predicate, inclusive) -> "PipeBuilder[T]":
        """代理到 ops.take_until_data"""
        from ..operators import take_until_data
        return self._add_operator(take_until_data(predicate, inclusive))
    
    def throttle_events(self, period_seconds, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.throttle_events"""
        from ..operators import throttle_events
        return self._add_operator(throttle_events(period_seconds, key_fn))
    
    def throttle_latest(self, period) -> "PipeBuilder[T]":
        """代理到 ops.throttle_latest"""
        from ..operators import throttle_latest
        return self._add_operator(throttle_latest(period))
    
    def throttle_with_trailing(self, duration, trailing) -> "PipeBuilder[T]":
        """代理到 ops.throttle_with_trailing"""
        from ..operators import throttle_with_trailing
        return self._add_operator(throttle_with_trailing(duration, trailing))
    
    def time_interval(self) -> "PipeBuilder[T]":
        """代理到 ops.time_interval"""
        from ..operators import time_interval
        return self._add_operator(time_interval())
    
    def to_map(self, key_fn) -> "PipeBuilder[T]":
        """代理到 ops.to_map"""
        from ..operators import to_map
        return self._add_operator(to_map(key_fn))
    
    def to_set(self) -> "PipeBuilder[T]":
        """代理到 ops.to_set"""
        from ..operators import to_set
        return self._add_operator(to_set())
    
    def when(self, predicate, handler) -> "PipeBuilder[T]":
        """代理到 ops.when"""
        from ..operators import when
        return self._add_operator(when(predicate, handler))
    
    def when_error(self, on_error) -> "PipeBuilder[T]":
        """代理到 ops.when_error"""
        from ..operators import when_error
        return self._add_operator(when_error(on_error))
    
    def when_start(self, predicate) -> "PipeBuilder[T]":
        """代理到 ops.when_start"""
        from ..operators import when_start
        return self._add_operator(when_start(predicate))
    
    def when_stop(self, predicate, inclusive: bool = True) -> "PipeBuilder[T]":
        """代理到 ops.when_stop"""
        from ..operators import when_stop
        return self._add_operator(when_stop(predicate, inclusive))
    
    def window(self, window_size) -> "PipeBuilder[T]":
        """代理到 ops.window"""
        from ..operators import window
        return self._add_operator(window(window_size))
    
    def with_latest_from(self, other) -> "PipeBuilder[T]":
        """代理到 ops.with_latest_from"""
        from ..operators import with_latest_from
        return self._add_operator(with_latest_from(other))
    
    def with_state(self, initial_state, reducer, on_state_change) -> "PipeBuilder[T]":
        """代理到 ops.with_state"""
        from ..operators import with_state
        return self._add_operator(with_state(initial_state, reducer, on_state_change))


class Observable(Generic[T]):
    """Observable 核心类
    
    Observable 是 vools 响应式编程的核心类，表示一个可观察的序列，
    可以发射数据项、错误和完成通知。
    """
    
    __slots__ = ('_subscribe_fn', '_source', '_subject', '_connection', '_subscriptions', '_has_subscribed', 'connect')
    
    def __init__(self, subscribe_fn: Callable[[Observer[T]], Subscription]) -> None:
        """初始化 Observable
        
        Args:
            subscribe_fn: 订阅函数，接受一个 Observer 并返回 Subscription
        """
        self._subscribe_fn = subscribe_fn

    def __getstate__(self) -> dict:
        """返回序列化状态"""
        d = {}
        for s in ('_subscribe_fn', '_source', '_subject', '_connection', '_has_subscribed'):
            try:
                d[s] = getattr(self, s)
            except AttributeError:
                d[s] = None
        d['connect'] = getattr(self, 'connect', None)
        return d
    
    def __setstate__(self, state: dict) -> None:
        """从序列化状态恢复"""
        for s in ('_subscribe_fn', '_source', '_subject', '_connection', '_has_subscribed'):
            object.__setattr__(self, s, state.get(s))
        self._subscriptions = set()
        object.__setattr__(self, 'connect', state.get('connect'))

    def subscribe(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        observer: Optional[Observer[T]] = None
    ) -> Subscription:
        """订阅此 Observable - 性能优化版本
        
        Args:
            on_next: 数据到达回调
            on_error: 错误发生回调
            on_completed: 完成回调
            observer: 可选的 Observer 对象，如果提供则忽略前三个参数
            
        Returns:
            Subscription 对象，可调用 dispose() 取消订阅
        """
        # 性能优化：直接创建observer而不使用object_pool
        if observer is None:
            observer = DefaultObserver(
                on_next or (lambda _: None),
                on_error or (lambda e: None),
                on_completed or (lambda: None)
            )
        
        subscription = self._subscribe_fn(observer)
        
        # 高性能优化：对于简单subscription，不包装unsubscribe
        # 只有当observer来自object_pool时才需要包装释放逻辑
        if hasattr(observer, '_pool') and observer._pool is not None:
            original_unsubscribe = subscription._unsubscribe
            def wrapped_unsubscribe():
                original_unsubscribe()
                observer.release()
            subscription._unsubscribe = wrapped_unsubscribe
        
        return subscription
    
    def subscribe_(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_completed: Optional[Callable[[], None]] = None
    ) -> Subscription:
        """直接传递回调函数订阅，避免创建 DefaultObserver
        
        Args:
            on_next: 数据到达回调
            on_error: 错误发生回调
            on_completed: 完成回调
            
        Returns:
            Subscription 对象
        """
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
    
    pipe: PipeDescriptor[T] = PipeDescriptor[T]()
    
    def p(self) -> "PipeBuilder[T]":
        """返回链式管道构建器"""
        return PipeBuilder(self)
    
    def __rshift__(self, other: Callable) -> "Observable":
        """支持 >> 操作符"""
        return self.pipe(other)
    
    @classmethod
    def from_iterable(cls, iterable: Iterable[T]) -> "Observable[T]":
        """从可迭代对象创建 Observable - 极高性能版本
        
        Args:
            iterable: 可迭代数据源
            
        Returns:
            "Observable[T]": 发射可迭代对象中所有元素的序列
        """
        def subscribe(observer: Observer[T]) -> Subscription:
            # 检查iterable是否为空列表/元组，直接完成无需迭代
            if isinstance(iterable, (list, tuple)) and len(iterable) == 0:
                observer.on_completed()
                return Subscription(lambda: None)
            
            iterator = iter(iterable)
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            subscription = Subscription(unsubscribe)
            
            try:
                # 极高性能优化：使用observer返回值直接控制迭代
                while not is_closed:
                    result = observer.on_next(next(iterator))
                    # 如果observer返回True，立即停止迭代（真正的提前终止）
                    if result is True:
                        is_closed = True
                        break
            except StopIteration:
                pass
            
            # 只有在未关闭且未发生错误时才调用on_completed
            if not is_closed:
                observer.on_completed()
            
            return subscription
        return cls(subscribe)
    
    @classmethod
    def just(cls, *values: T) -> "Observable[T]":
        """创建发射指定值的 Observable
        
        Args:
            *values: 要发射的值
            
        Returns:
            "Observable[T]": 依次发射所有值的序列
        """
        return cls.from_iterable(values)
    
    @classmethod
    def of(cls, *values: T) -> "Observable[T]":
        """创建发射指定值的 Observable（just 的别名）
        
        Args:
            *values: 要发射的值
            
        Returns:
            "Observable[T]": 依次发射所有值的序列
        """
        return cls.just(*values)
    
    @classmethod
    def from_range(cls, n: int) -> "Observable[int]":
        """创建发出范围序列整数的 Observable
        
        Args:
            n: 结束值（不包含）
            
        Returns:
            "Observable[int]": 发射 0 到 n-1 的整数序列
        """
        return cls.from_iterable(range(n))
    
    @classmethod
    def empty(cls) -> "Observable[Any]":
        """创建空序列 Observable
        
        Returns:
            "Observable[Any]": 立即完成的空序列
        """
        def subscribe(observer: Observer) -> Subscription:
            observer.on_completed()
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def never(cls) -> "Observable[Any]":
        """创建永不完成的 Observable
        
        Returns:
            "Observable[Any]": 永不发射也不完成的序列
        """
        def subscribe(observer: Observer) -> Subscription:
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def error(cls, error: Exception) -> "Observable[Any]":
        """创建立即发出错误的 Observable
        
        Args:
            error: 要发射的异常
            
        Returns:
            "Observable[Any]": 立即发射错误并完成的序列
        """
        def subscribe(observer: Observer) -> Subscription:
            observer.on_error(error)
            return Subscription(lambda: None)
        return cls(subscribe)
    
    @classmethod
    def throw(cls, error: Exception) -> "Observable[Any]":
        """创建立即发出错误的 Observable（error 的别名）
        
        Args:
            error: 要发射的异常
            
        Returns:
            "Observable[Any]": 立即发射错误并完成的序列
        """
        return cls.error(error)
    
    @classmethod
    def interval(cls, period: float) -> "Observable[int]":
        """创建一个每隔指定时间发射递增整数的 Observable
        
        Args:
            period: 发射间隔（秒）
            
        Returns:
            "Observable[int]": 发射 0, 1, 2, 3, ... 的序列
        """
        def subscribe(observer: Observer[int]) -> Subscription:
            counter = 0
            stopped = threading.Event()

            def emit_loop() -> None:
                nonlocal counter
                while not stopped.is_set():
                    observer.on_next(counter)
                    counter += 1
                    stopped.wait(timeout=period)

            def unsubscribe() -> None:
                stopped.set()

            t = threading.Thread(target=emit_loop, daemon=True)
            t.start()

            return Subscription(unsubscribe)

        return cls(subscribe)
    
    @classmethod
    def timer(cls, due_time: float, period: Optional[float] = None) -> "Observable[int]":
        """创建一个在指定延迟后发射单个值或周期性发射值的 Observable
        
        Args:
            due_time: 首次发射前的延迟（秒）
            period: 后续发射的间隔（秒），如果为 None 则只发射一次
            
        Returns:
            "Observable[int]": 发射 0, 1, 2, 3, ... 的序列
        """
        def subscribe(observer: Observer[int]) -> Subscription:
            counter = 0
            stopped = threading.Event()

            def emit_once() -> None:
                nonlocal counter
                if stopped.wait(timeout=due_time):
                    return
                observer.on_next(counter)
                counter += 1

                if period is None:
                    observer.on_completed()
                    return

                while not stopped.is_set():
                    observer.on_next(counter)
                    counter += 1
                    stopped.wait(timeout=period)

            def unsubscribe() -> None:
                stopped.set()

            t = threading.Thread(target=emit_once, daemon=True)
            t.start()

            return Subscription(unsubscribe)

        return cls(subscribe)
    
    @classmethod
    def defer(cls, factory: Callable[[], "Observable[T]"]) -> "Observable[T]":
        """延迟创建 Observable，直到订阅时才调用工厂函数
        
        Args:
            factory: 返回 Observable 的工厂函数
            
        Returns:
            "Observable[T]": 由工厂函数创建的 Observable
        """
        def subscribe(observer: Observer[T]) -> Subscription:
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
    def repeat(cls, value: T, times: Optional[int] = None) -> "Observable[T]":
        """创建一个重复发射指定值的 Observable
        
        Args:
            value: 要重复发射的值
            times: 重复次数，如果为 None 则无限重复（注意：无限重复会阻塞）
            
        Returns:
            "Observable[T]": 重复发射指定值的序列
        """
        def subscribe(observer: Observer[T]) -> Subscription:
            if times is None:
                def unsubscribe() -> None:
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
    def from_range(
        cls,
        start_or_stop: int,
        stop: Optional[int] = None,
        step: int = 1
    ) -> "Observable[int]":
        """创建发出范围序列整数的 Observable
        
        Args:
            start_or_stop: 起始值（包含）或结束值（不包含）
            stop: 结束值（不包含）
            step: 步长
            
        Returns:
            "Observable[int]": 发出整数序列
            
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
        
        def subscribe(observer: Observer[int]) -> Subscription:
            try:
                for i in range(start_val, stop_val, step):
                    observer.on_next(i)
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
            
            return Subscription(lambda: None)
        
        return cls(subscribe)
    
    @classmethod
    def from_callable(cls, func: Callable[[], T]) -> "Observable[T]":
        """从 Callable 创建 Observable
        
        Args:
            func: 返回值的 Callable
            
        Returns:
            "Observable[T]": 发出 Callable 返回的值
        """
        def subscribe(observer: Observer[T]) -> Subscription:
            try:
                result = func()
                observer.on_next(result)
                observer.on_completed()
            except Exception as e:
                observer.on_error(e)
            
            return Subscription(lambda: None)
        
        return cls(subscribe)
    
    @classmethod
    def from_future(cls, future) -> "Observable[T]":
        """从 Future 创建 Observable
        
        Args:
            future: concurrent.futures.Future 对象
            
        Returns:
            "Observable[T]": 发出 Future 结果
        """
        def subscribe(observer: Observer[T]) -> Subscription:
            def done_callback(f) -> None:
                try:
                    observer.on_next(f.result())
                    observer.on_completed()
                except Exception as e:
                    observer.on_error(e)
            
            future.add_done_callback(done_callback)
            
            return Subscription(lambda: future.cancel() if hasattr(future, 'cancel') else None)
        
        return cls(subscribe)