"""
vools-reactive Observable Core
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Generic, Iterator, AsyncIterator
from abc import ABC, abstractmethod
import asyncio
import sys

from ..decorators import curry, lazy

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
    
    __slots__ = ('_on_next', '_on_error', '_on_completed')
    
    def __init__(self, on_next=None, on_error=None, on_completed=None):
        self._on_next = on_next or (lambda _: None)
        self._on_error = on_error or (lambda e: None)
        self._on_completed = on_completed or (lambda: None)
    
    def on_next(self, value):
        self._on_next(value)
    
    def on_error(self, error):
        self._on_error(error)
    
    def on_completed(self):
        self._on_completed()


class PipeBuilder(Generic[T]):
    """链式管道构建器"""
    
    __slots__ = ('_source', '_operators')
    
    def __init__(self, source: Observable[T]):
        self._source = source
        self._operators = []
    
    def _add_operator(self, operator):
        self._operators.append(operator)
        return self
    
    def _build(self) -> Observable:
        """构建最终的 Observable"""
        source = self._source
        for op in self._operators:
            source = op(source)
        return source
    
    def subscribe(self, on_next=None, on_error=None, on_completed=None, observer=None):
        """直接订阅"""
        return self._build().subscribe(on_next, on_error, on_completed, observer)
    
    def __rshift__(self, other):
        """支持 >> 操作符"""
        if callable(other):
            self._operators.append(other)
        return self
    
    # ========== 操作符方法 ==========
    
    def map(self, fn=None, **kwargs):
        from .operators import map
        return self._add_operator(map(fn, **kwargs))
    
    def filter(self, fn=None, **kwargs):
        from .operators import filter
        return self._add_operator(filter(fn, **kwargs))
    
    def flat_map(self, fn=None, **kwargs):
        from .operators import flat_map
        return self._add_operator(flat_map(fn, **kwargs))
    
    def concat_map(self, fn=None, **kwargs):
        from .operators import concat_map
        return self._add_operator(concat_map(fn, **kwargs))
    
    def switch_map(self, fn=None, **kwargs):
        from .operators import switch_map
        return self._add_operator(switch_map(fn, **kwargs))
    
    def take(self, n):
        from .operators import take
        return self._add_operator(take(n))
    
    def skip(self, n):
        from .operators import skip
        return self._add_operator(skip(n))
    
    def take_while(self, predicate):
        from .operators import take_while
        return self._add_operator(take_while(predicate))
    
    def skip_while(self, predicate):
        from .operators import skip_while
        return self._add_operator(skip_while(predicate))
    
    def take_until(self, other):
        from .operators import take_until
        return self._add_operator(take_until(other))
    
    def distinct_until_changed(self, key_fn=None):
        from .operators import distinct_until_changed
        return self._add_operator(distinct_until_changed(key_fn))
    
    def debounce(self, due_time):
        from .operators import debounce
        return self._add_operator(debounce(due_time))
    
    def throttle_first(self, duration):
        from .operators import throttle_first
        return self._add_operator(throttle_first(duration))
    
    def tap(self, fn=None, **kwargs):
        from .operators import tap
        return self._add_operator(tap(fn, **kwargs))
    
    def delay(self, due_time):
        from .operators import delay
        return self._add_operator(delay(due_time))
    
    def start_with(self, *values):
        from .operators import start_with
        return self._add_operator(start_with(*values))
    
    def end_with(self, *values):
        from .operators import end_with
        return self._add_operator(end_with(*values))
    
    def reduce(self, accumulator, seed=None):
        from .operators import reduce
        return self._add_operator(reduce(accumulator, seed))
    
    def scan(self, accumulator, seed=None):
        from .operators import scan
        return self._add_operator(scan(accumulator, seed))
    
    def count(self):
        from .operators import count
        return self._add_operator(count())
    
    def sum(self):
        from .operators import sum
        return self._add_operator(sum())
    
    def average(self):
        from .operators import average
        return self._add_operator(average())
    
    def minimum(self):
        from .operators import minimum
        return self._add_operator(minimum())
    
    def maximum(self):
        from .operators import maximum
        return self._add_operator(maximum())
    
    def all(self, predicate):
        from .operators import all
        return self._add_operator(all(predicate))
    
    def any(self, predicate):
        from .operators import any
        return self._add_operator(any(predicate))
    
    def contains(self, value):
        from .operators import contains
        return self._add_operator(contains(value))
    
    def is_empty(self):
        from .operators import is_empty
        return self._add_operator(is_empty())
    
    def to_list(self):
        from .operators import to_list
        return self._add_operator(to_list())
    
    def buffer(self, count):
        from .operators import buffer
        return self._add_operator(buffer(count))
    
    def group_by(self, key_fn):
        from .operators import group_by
        return self._add_operator(group_by(key_fn))
    
    def merge(self, *others):
        from .operators import merge
        return self._add_operator(merge(*others))
    
    def concat(self, *others):
        from .operators import concat
        return self._add_operator(concat(*others))
    
    def catch(self, handler):
        from .operators import catch
        return self._add_operator(catch(handler))
    
    def retry(self, times=None):
        from .operators import retry
        return self._add_operator(retry(times))
    
    def on_error_return(self, value):
        from .operators import on_error_return
        return self._add_operator(on_error_return(value))
    
    def on_error_resume_next(self, fallback):
        from .operators import on_error_resume_next
        return self._add_operator(on_error_resume_next(fallback))
    
    def retry_when(self, handler):
        from .operators import retry_when
        return self._add_operator(retry_when(handler))
    
    # ========== 新增操作符 ==========
    
    def first(self, predicate=None):
        from .operators import first
        return self._add_operator(first(predicate))
    
    def last(self, predicate=None):
        from .operators import last
        return self._add_operator(last(predicate))
    
    def distinct(self, key_fn=None):
        from .operators import distinct
        return self._add_operator(distinct(key_fn))
    
    def element_at(self, index):
        from .operators import element_at
        return self._add_operator(element_at(index))
    
    def skip_until(self, other):
        from .operators import skip_until
        return self._add_operator(skip_until(other))
    
    def default_if_empty(self, default_value):
        from .operators import default_if_empty
        return self._add_operator(default_if_empty(default_value))
    
    def sequence_equal(self, other):
        from .operators import sequence_equal
        return self._add_operator(sequence_equal(other))
    
    def timeout(self, timeout_duration):
        from .operators import timeout
        return self._add_operator(timeout(timeout_duration))
    
    def timestamp(self):
        from .operators import timestamp
        return self._add_operator(timestamp())
    
    def iif(self, condition=None, true_body=None, false_body=None):
        from .operators import iif
        return self._add_operator(iif(condition, true_body, false_body))
    
    # ========== 统计聚合扩展算子 ==========
    
    def median(self):
        from .stats_operators import median
        return self._add_operator(median())
    
    def variance(self, ddof: int = 0):
        from .stats_operators import variance
        return self._add_operator(variance(ddof))
    
    def std(self, ddof: int = 0):
        from .stats_operators import std
        return self._add_operator(std(ddof))
    
    def quantile(self, q: float):
        from .stats_operators import quantile
        return self._add_operator(quantile(q))
    
    def arg_min(self):
        from .stats_operators import arg_min
        return self._add_operator(arg_min())
    
    def arg_max(self):
        from .stats_operators import arg_max
        return self._add_operator(arg_max())
    
    def n_unique(self):
        from .stats_operators import n_unique
        return self._add_operator(n_unique())
    
    # ========== 滚动窗口算子 ==========
    
    def rolling_sum(self, window_size: int):
        from .stats_operators import rolling_sum
        return self._add_operator(rolling_sum(window_size))
    
    def rolling_min(self, window_size: int):
        from .stats_operators import rolling_min
        return self._add_operator(rolling_min(window_size))
    
    def rolling_max(self, window_size: int):
        from .stats_operators import rolling_max
        return self._add_operator(rolling_max(window_size))
    
    def rolling_mean(self, window_size: int):
        from .stats_operators import rolling_mean
        return self._add_operator(rolling_mean(window_size))
    
    # ========== 累积变换算子 ==========
    
    def cum_sum(self):
        from .stats_operators import cum_sum
        return self._add_operator(cum_sum())
    
    def cum_min(self):
        from .stats_operators import cum_min
        return self._add_operator(cum_min())
    
    def cum_max(self):
        from .stats_operators import cum_max
        return self._add_operator(cum_max())
    
    def cum_mean(self):
        from .stats_operators import cum_mean
        return self._add_operator(cum_mean())
    
    def cum_prod(self):
        from .stats_operators import cum_prod
        return self._add_operator(cum_prod())
    
    # ========== 排序 Top-N 算子 ==========
    
    def sort(self, key_fn=None, reverse=False):
        from .stats_operators import sort
        return self._add_operator(sort(key_fn, reverse))
    
    def top_k(self, k: int, key_fn=None):
        from .stats_operators import top_k
        return self._add_operator(top_k(k, key_fn))
    
    def bottom_k(self, k: int, key_fn=None):
        from .stats_operators import bottom_k
        return self._add_operator(bottom_k(k, key_fn))
    
    # ========== None 值处理与数学工具 ==========
    
    def drop_none(self):
        from .stats_operators import drop_none
        return self._add_operator(drop_none())
    
    def fill_none(self, default_value):
        from .stats_operators import fill_none
        return self._add_operator(fill_none(default_value))
    
    def abs(self):
        from .stats_operators import abs_op
        return self._add_operator(abs_op())
    
    def clamp(self, min_val, max_val):
        from .stats_operators import clamp
        return self._add_operator(clamp(min_val, max_val))
    
    # ========== 嵌套流展开算子 ==========
    
    def explode(self):
        from .stats_operators import explode
        return self._add_operator(explode())
    
    def flatten(self):
        from .stats_operators import flatten
        return self._add_operator(flatten())


class Observable(Generic[T]):
    """Observable 核心类"""
    
    __slots__ = ('_subscribe_fn', '_source', '_subject', '_connection', '_subscriptions', '_has_subscribed', 'connect')
    
    def __init__(self, subscribe_fn):
        self._subscribe_fn = subscribe_fn
    
    def subscribe(self, on_next=None, on_error=None, on_completed=None, observer=None):
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        return self._subscribe_fn(observer)
    
    def subscribe_(self, on_next=None, on_error=None, on_completed=None):
        """直接传递回调函数，避免创建 DefaultObserver"""
        observer = DefaultObserver(on_next, on_error, on_completed)
        return self._subscribe_fn(observer)
    
    def pipe(self, *operators):
        source = self
        for op in operators:
            if callable(op):
                source = op(source)
        return source
    
    def p(self) -> PipeBuilder[T]:
        """返回链式管道构建器"""
        return PipeBuilder(self)
    
    def __rshift__(self, other):
        return self.pipe(other)
    
    @classmethod
    def from_iterable(cls, iterable):
        def subscribe(observer):
            iterator = iter(iterable)
            is_closed = False
            
            def unsubscribe():
                nonlocal is_closed
                is_closed = True
            
            try:
                while not is_closed:
                    observer.on_next(next(iterator))
            except StopIteration:
                pass
            
            if not is_closed:
                observer.on_completed()
            
            return Subscription(unsubscribe)
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
            task = None
            
            async def emit():
                nonlocal counter, task
                while True:
                    observer.on_next(counter)
                    counter += 1
                    await asyncio.sleep(period)
            
            def unsubscribe():
                nonlocal task
                if task:
                    task.cancel()
            
            task = asyncio.create_task(emit())
            
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
            task = None
            
            async def emit():
                nonlocal counter, task
                await asyncio.sleep(due_time)
                
                if period is None:
                    observer.on_next(counter)
                    observer.on_completed()
                    return
                
                while True:
                    observer.on_next(counter)
                    counter += 1
                    await asyncio.sleep(period)
            
            def unsubscribe():
                nonlocal task
                if task:
                    task.cancel()
            
            task = asyncio.create_task(emit())
            
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
