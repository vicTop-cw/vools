"""
vools-reactive Connectable Observable

Connectable Observable 是一种特殊的 Observable，只有在调用 connect() 方法后才会开始发射数据。
支持多播、共享和重播功能。
"""

from __future__ import annotations
from typing import TypeVar, Callable, Optional, Any, Generic, List, Dict, Set, Tuple, TYPE_CHECKING
import time

if TYPE_CHECKING:
    from .observable import Observable

# 延迟导入 Observable
from .observable import Observable

T = TypeVar('T')
K = TypeVar('K')


class ConnectableObservable(Observable[T]):
    """可连接的 Observable
    
    只有在调用 connect() 方法后才会开始发射数据。
    支持多个订阅者共享同一个数据流。
    
    Example:
        >>> from vools.reactive import Observable
        >>> source = Observable.interval(1.0)
        >>> connectable = source.pipe(publish())
        >>> # 此时还没有开始发射
        >>> sub1 = connectable.subscribe(print)
        >>> sub2 = connectable.subscribe(print)
        >>> # 手动触发连接
        >>> connection = connectable.connect()
        >>> # 两个订阅者都会收到相同的数据
    """
    
    __slots__ = ('_source', '_subject', '_connection')
    
    def __init__(self, subscribe_fn, source, subject):
        super().__init__(subscribe_fn)
        self._source = source
        self._subject = subject
        self._connection = None
    
    def subscribe(self, on_next=None, on_error=None, on_completed=None, observer=None):
        """订阅"""
        from .observable import DefaultObserver
        
        if observer is None:
            observer = DefaultObserver(on_next, on_error, on_completed)
        return self._subscribe_fn(observer)
    
    def connect(self):
        """连接并开始发射数据
        
        Returns:
            Subscription: 可用于取消连接的订阅
        """
        if self._connection is None:
            self._connection = self._source.subscribe(observer=self._subject)
        return self._connection


def _make_connectable(source, subject):
    """创建一个可连接 Observable"""
    subject_local = subject  # 闭包捕获
    
    def subscribe_fn(observer):
        # 正确传递 observer 参数
        return subject_local.subscribe(observer=observer)
    
    return ConnectableObservable(subscribe_fn, source, subject)


def ref_count() -> Callable:
    """使可连接 Observable 像普通 Observable
    
    当有订阅者时自动连接，当所有订阅者取消时自动断开。
    
    Returns:
        操作符函数
    """
    from .observable import Observable
    
    def operator(source):
        ref_count_val = [0]
        connection = [None]
        subject = [None]
        
        def get_subject():
            if subject[0] is None:
                from .subject import ReplaySubject
                subject[0] = ReplaySubject()  # 使用 ReplaySubject 以支持历史重放
            return subject[0]
        
        def subscribe_fn(observer):
            nonlocal connection
            ref_count_val[0] += 1
            
            subj = get_subject()
            # 使用正确的回调方式订阅 Subject
            sub = subj.subscribe(
                on_next=observer.on_next if hasattr(observer, 'on_next') else observer,
                on_error=observer.on_error if hasattr(observer, 'on_error') else None,
                on_completed=observer.on_completed if hasattr(observer, 'on_completed') else None
            )
            
            if ref_count_val[0] == 1:
                # 如果 source 有 connect 方法（ConnectableObservable），使用它
                if hasattr(source, 'connect'):
                    connection[0] = source.connect()
                else:
                    # 否则直接订阅，使用 Subject 的多播接口
                    connection[0] = source.subscribe(
                        on_next=subj.on_next,
                        on_error=subj.on_error,
                        on_completed=subj.on_completed
                    )
            
            def unsubscribe():
                nonlocal connection
                ref_count_val[0] -= 1
                sub.unsubscribe()
                if ref_count_val[0] == 0:
                    if connection[0]:
                        connection[0].unsubscribe()
                        connection[0] = None
            
            from .observable import Subscription
            return Subscription(unsubscribe)
        
        return Observable(subscribe_fn)
    
    return operator


def publish() -> Callable:
    """转换为可连接 Observable
    
    使用 Subject 来多播数据。
    
    Returns:
        操作符函数
    """
    from .subject import Subject
    
    def operator(source):
        subject = Subject()
        return _make_connectable(source, subject)
    
    return operator


def share() -> Callable:
    """共享 Observable (publish + ref_count)
    
    自动管理连接/断开连接。
    
    Returns:
        操作符函数
    """
    return ref_count()(publish())


def replay(buffer_size: int = None, window: float = None) -> Callable:
    """确保所有观察者看到相同序列
    
    新订阅者可以收到历史发射的值。
    
    Args:
        buffer_size: 缓冲区大小，None 表示无限
        window: 时间窗口（秒），暂不支持，保留参数接口
    
    Returns:
        操作符函数
    """
    from .subject import ReplaySubject
    
    def operator(source):
        subject = ReplaySubject(buffer_size=buffer_size)
        return _make_connectable(source, subject)
    
    return operator


def publish_replay(buffer_size: int = None, window: float = None) -> Callable:
    """Publish + Replay 组合
    
    Args:
        buffer_size: 缓冲区大小
        window: 时间窗口
    
    Returns:
        操作符函数
    """
    return replay(buffer_size=buffer_size, window=window)


def auto_connect(num_subscriptions: int = 1) -> Callable:
    """自动连接，当达到指定订阅数时开始发射
    
    Args:
        num_subscriptions: 自动连接的订阅数
    
    Returns:
        操作符函数
    """
    from .observable import Observable
    
    def operator(source):
        connection = [None]
        subscription_count = [0]
        is_connected = [False]
        
        def subscribe_fn(observer):
            nonlocal is_connected
            
            # 先订阅数据流（添加观察者到 Subject）
            sub = source.subscribe(observer=observer)
            
            subscription_count[0] += 1
            
            # 当达到指定订阅数时，自动连接
            if subscription_count[0] >= num_subscriptions and not is_connected[0]:
                is_connected[0] = True
                connection[0] = source.connect()
            
            return sub
        
        return Observable(subscribe_fn)
    
    return operator
