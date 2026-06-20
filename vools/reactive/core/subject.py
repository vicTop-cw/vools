"""
vools-reactive Subject

Subject 是一种特殊的 Observable，既可以作为 Observable 也可以作为 Observer。
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Set, Generic

from .observable import Subscription, DefaultObserver, Observable, PipeDescriptor

T = TypeVar('T')


class Subject(Generic[T]):
    """基础 Subject - 多播数据流"""
    
    __slots__ = ('_observers', '_is_closed', '_is_completed', '_cached_callbacks')
    
    def __init__(self):
        self._observers: Set = set()
        self._is_closed = False
        self._is_completed = False
        self._cached_callbacks = None

    def __getstate__(self):
        return {'_is_closed': self._is_closed, '_is_completed': self._is_completed}
    def __setstate__(self, state):
        self._observers = set()
        self._is_closed = state['_is_closed']
        self._is_completed = state['_is_completed']
        self._cached_callbacks = None

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
        self._cached_callbacks = None
        
        def unsubscribe():
            self._observers.discard(observer)
            self._cached_callbacks = None
        
        return Subscription(unsubscribe)
    
    def subscribe_(self, on_next=None, on_error=None, on_completed=None):
        """直接传递回调函数"""
        return self.subscribe(on_next, on_error, on_completed)
    
    pipe = PipeDescriptor[T]()
    
    def p(self):
        from .observable import PipeBuilder
        return PipeBuilder(Observable(self._subscribe_generator), origin=self)
    
    def _subscribe_generator(self, observer) -> Subscription:
        return self.subscribe(observer=observer)
    
    def on_next(self, value: T) -> None:
        if not self._is_closed:
            if self._cached_callbacks is None:
                self._cached_callbacks = [obs.on_next for obs in self._observers]
            for callback in self._cached_callbacks:
                callback(value)
    
    def on_error(self, error: Exception) -> None:
        if not self._is_closed:
            self._is_closed = True
            for observer in list(self._observers):
                observer.on_error(error)
            self._observers.clear()
            self._cached_callbacks = None
    
    def on_completed(self) -> None:
        if not self._is_closed and not self._is_completed:
            self._is_completed = True
            self._is_closed = True
            for observer in list(self._observers):
                observer.on_completed()
            self._observers.clear()
            self._cached_callbacks = None
    
    def as_observable(self) -> Observable[T]:
        return Observable(self._subscribe_generator)
    
    def __rshift__(self, other: Callable[..., Observable[Any]]) -> Observable[Any]:
        return self.pipe(other)


class BehaviorSubject(Subject[T], Generic[T]):
    """BehaviorSubject - 重放最后一个值给新订阅者"""
    
    def __init__(self, initial_value: T):
        super().__init__()
        self._value = initial_value

    def __getstate__(self):
        d = Subject.__getstate__(self)
        d['_value'] = self._value
        return d
    def __setstate__(self, state):
        Subject.__setstate__(self, state)
        self._value = state['_value']

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

    def __getstate__(self):
        d = Subject.__getstate__(self)
        d['_buffer'] = list(self._buffer)
        d['_buffer_size'] = self._buffer_size
        return d
    def __setstate__(self, state):
        Subject.__setstate__(self, state)
        self._buffer_size = state['_buffer_size']
        self._buffer = list(state.get('_buffer', []))

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

    def __getstate__(self):
        d = Subject.__getstate__(self)
        d['_value'] = self._value
        d['_has_value'] = self._has_value
        return d
    def __setstate__(self, state):
        Subject.__setstate__(self, state)
        self._value = state['_value']
        self._has_value = state['_has_value']

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


PublishSubject = Subject
"""PublishSubject 别名，与 RxPY/rx-rust 对齐"""
__all__ = ['T', 'Subject', 'BehaviorSubject', 'ReplaySubject', 'AsyncSubject', 'PublishSubject', 'subject', 'behavior_subject', 'replay_subject', 'async_subject', 'publish_subject']


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