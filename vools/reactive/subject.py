"""
vools-reactive Subject

Subject 是一种特殊的 Observable，既可以作为 Observable 也可以作为 Observer。
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Set, Generic

from .observable import Subscription, DefaultObserver, Observable

T = TypeVar('T')


class Subject(Generic[T]):
    """基础 Subject - 多播数据流"""
    
    def __init__(self):
        self._observers: Set = set()
        self._is_closed = False
        self._is_completed = False
    
    def subscribe(
        self,
        on_next: Optional[Callable[[T], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        observer: Optional = None
    ) -> Subscription:
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        
        if self._is_completed:
            observer.on_completed()
            return Subscription(lambda: None)
        
        self._observers.add(observer)
        
        def unsubscribe():
            self._observers.discard(observer)
        
        return Subscription(unsubscribe)
    
    def pipe(self, *operators: Callable[..., Observable[Any]]) -> Observable[Any]:
        source: Observable[Any] = Observable(self._subscribe_generator)
        for op in operators:
            if callable(op):
                source = op(source)
        return source
    
    def _subscribe_generator(self, observer) -> Subscription:
        return self.subscribe(observer=observer)
    
    def on_next(self, value: T) -> None:
        if not self._is_closed:
            for observer in list(self._observers):
                observer.on_next(value)
    
    def on_error(self, error: Exception) -> None:
        if not self._is_closed:
            self._is_closed = True
            for observer in list(self._observers):
                observer.on_error(error)
            self._observers.clear()
    
    def on_completed(self) -> None:
        if not self._is_closed and not self._is_completed:
            self._is_completed = True
            self._is_closed = True
            for observer in list(self._observers):
                observer.on_completed()
            self._observers.clear()
    
    def as_observable(self) -> Observable[T]:
        return Observable(self._subscribe_generator)
    
    def __rshift__(self, other: Callable[..., Observable[Any]]) -> Observable[Any]:
        return self.pipe(other)


class BehaviorSubject(Subject[T], Generic[T]):
    """BehaviorSubject - 重放最后一个值给新订阅者"""
    
    def __init__(self, initial_value: T):
        super().__init__()
        self._value = initial_value
    
    def subscribe(
        self,
        on_next: Optional[Callable[[T], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        observer: Optional = None
    ) -> Subscription:
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        
        observer.on_next(self._value)
        
        if self._is_completed:
            observer.on_completed()
            return Subscription(lambda: None)
        
        self._observers.add(observer)
        
        def unsubscribe():
            self._observers.discard(observer)
        
        return Subscription(unsubscribe)
    
    def on_next(self, value: T) -> None:
        self._value = value
        super().on_next(value)
    
    @property
    def value(self) -> T:
        return self._value


class ReplaySubject(Subject[T], Generic[T]):
    """ReplaySubject - 重放历史值给新订阅者"""
    
    def __init__(self, buffer_size: int = None):
        super().__init__()
        self._buffer_size = buffer_size
        self._buffer = []
    
    def subscribe(
        self,
        on_next: Optional[Callable[[T], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        observer: Optional = None
    ) -> Subscription:
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        
        for value in self._buffer:
            observer.on_next(value)
        
        if self._is_completed:
            observer.on_completed()
            return Subscription(lambda: None)
        
        self._observers.add(observer)
        
        def unsubscribe():
            self._observers.discard(observer)
        
        return Subscription(unsubscribe)
    
    def on_next(self, value: T) -> None:
        self._buffer.append(value)
        if self._buffer_size is not None and len(self._buffer) > self._buffer_size:
            self._buffer.pop(0)
        super().on_next(value)


class AsyncSubject(Subject[T], Generic[T]):
    """AsyncSubject - 仅在完成时发射最后一个值"""
    
    def __init__(self):
        super().__init__()
        self._has_value = False
        self._value: T = None
    
    def subscribe(
        self,
        on_next: Optional[Callable[[T], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
        on_completed: Optional[Callable[[], Any]] = None,
        observer: Optional = None
    ) -> Subscription:
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        
        if self._is_completed:
            if self._has_value:
                observer.on_next(self._value)
            observer.on_completed()
            return Subscription(lambda: None)
        
        self._observers.add(observer)
        
        def unsubscribe():
            self._observers.discard(observer)
        
        return Subscription(unsubscribe)
    
    def on_next(self, value: T) -> None:
        self._value = value
        self._has_value = True
    
    def on_completed(self) -> None:
        if not self._is_closed and not self._is_completed:
            self._is_completed = True
            self._is_closed = True
            if self._has_value:
                for observer in list(self._observers):
                    observer.on_next(self._value)
            for observer in list(self._observers):
                observer.on_completed()
            self._observers.clear()


# ========== 工厂函数 ==========

def subject() -> Subject[Any]:
    """创建基础 Subject"""
    return Subject()


def behavior_subject(initial_value: T) -> BehaviorSubject[T]:
    """创建 BehaviorSubject"""
    return BehaviorSubject(initial_value)


def replay_subject(buffer_size: int = None) -> ReplaySubject[Any]:
    """创建 ReplaySubject"""
    return ReplaySubject(buffer_size)


def async_subject() -> AsyncSubject[Any]:
    """创建 AsyncSubject"""
    return AsyncSubject()


def publish_subject() -> Subject[Any]:
    """创建 PublishSubject (同 Subject)"""
    return Subject()