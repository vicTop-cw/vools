"""tests/concurrent/test_delegates.py — 委托/事件总线测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.delegates import (
    Delegate, AsyncDelegate, EventBus, MessageDispatcher, CallbackChain,
    delegate, thread_safe,
)


class TestDelegate:
    """Delegate 委托测试"""

    def test_add_and_invoke(self):
        d = Delegate()
        results = []
        d.add(lambda x: results.append(x))
        d.invoke(42)
        assert results == [42]

    def test_remove(self):
        d = Delegate()
        handler = lambda x: None
        d.add(handler)
        assert d.count == 1
        d.remove(handler)
        assert d.count == 0

    def test_clear(self):
        d = Delegate()
        d.add(lambda x: None)
        d.add(lambda x: None)
        d.clear()
        assert d.count == 0

    def test_handlers(self):
        d = Delegate()
        h = lambda x: None
        d.add(h)
        assert h in d.handlers

    def test_invoke_safe(self):
        d = Delegate()
        results = []
        d.add(lambda x: results.append(x))
        d.invoke_safe(10)
        assert results == [10]

    def test_iadd(self):
        d = Delegate()
        h = lambda x: None
        d += h
        assert d.count == 1

    def test_isub(self):
        d = Delegate()
        h = lambda x: None
        d += h
        d -= h
        assert d.count == 0

    def test_len(self):
        d = Delegate()
        d.add(lambda x: None)
        assert len(d) == 1

    def test_bool(self):
        d = Delegate()
        assert bool(d) is False
        d.add(lambda x: None)
        assert bool(d) is True

    def test_call(self):
        d = Delegate()
        results = []
        d.add(lambda x: results.append(x))
        d(5)
        assert results == [5]


class TestAsyncDelegate:
    """AsyncDelegate 异步委托测试"""

    def test_add_and_invoke(self):
        d = AsyncDelegate()
        results = []
        d.add(lambda x: results.append(x))
        d.invoke(42)
        assert results == [42]

    def test_invoke_and_wait(self):
        d = AsyncDelegate()
        results = []
        d.add(lambda x: results.append(x * 2))
        d.invoke_and_wait(10)
        assert results == [20]


class TestEventBus:
    """EventBus 事件总线测试"""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        results = []
        # handler 接收 (event, *args, **kwargs)
        bus.subscribe('test.event', lambda event, data: results.append(data))
        bus.publish('test.event', {'msg': 'hello'})
        assert len(results) >= 1

    def test_unsubscribe(self):
        bus = EventBus()
        results = []
        handler = lambda event, data: results.append(data)
        bus.subscribe('test.event', handler)
        bus.unsubscribe('test.event', handler)
        bus.publish('test.event', {})
        assert len(results) == 0

    def test_has_subscribers(self):
        bus = EventBus()
        assert bus.has_subscribers('test') is False
        bus.subscribe('test', lambda event, data: None)
        assert bus.has_subscribers('test') is True

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe('evt', lambda event, data: None)
        bus.subscribe('evt', lambda event, data: None)
        assert bus.subscriber_count('evt') == 2

    def test_publish_safe(self):
        bus = EventBus()
        bus.publish_safe('evt', {})  # 无订阅者时不应报错
        assert True

    def test_events(self):
        bus = EventBus()
        # events() 是方法不是属性
        assert bus.events() == []
        bus.subscribe('evt', lambda event, data: None)
        assert 'evt' in bus.events()


class TestMessageDispatcher:
    """MessageDispatcher 消息分发器测试"""

    def test_register_and_dispatch(self):
        d = MessageDispatcher()
        results = []
        d.register(str, lambda msg: results.append(msg))
        d.dispatch('hello')
        assert results == ['hello']

    def test_unregister(self):
        d = MessageDispatcher()
        handler = lambda msg: None
        d.register(str, handler)
        d.unregister(str, handler)
        assert d.handler_count(str) == 0

    def test_has_handlers(self):
        d = MessageDispatcher()
        assert d.has_handlers(str) is False
        d.register(str, lambda msg: None)
        assert d.has_handlers(str) is True

    def test_dispatch_safe(self):
        d = MessageDispatcher()
        d.dispatch_safe('test')  # 无处理器时不应报错
        assert True

    def test_registered_types(self):
        d = MessageDispatcher()
        d.register(int, lambda msg: None)
        # registered_types() 是方法
        assert int in d.registered_types()


class TestCallbackChain:
    """CallbackChain 回调链测试"""

    def test_add_and_execute(self):
        chain = CallbackChain()
        results = []
        # 回调返回 True 表示继续传递
        chain.add(lambda: (results.append('a'), True))
        chain.add(lambda: (results.append('b'), True))
        chain.execute()
        assert results == ['a', 'b']

    def test_add_pre(self):
        chain = CallbackChain()
        results = []
        chain.add(lambda: (results.append('main'), True))
        chain.add_pre(lambda: results.append('pre'))
        chain.execute()
        assert 'pre' in results
        assert 'main' in results

    def test_add_post(self):
        chain = CallbackChain()
        results = []
        chain.add(lambda: (results.append('main'), True))
        chain.add_post(lambda: results.append('post'))
        chain.execute()
        assert 'main' in results
        assert 'post' in results

    def test_clear(self):
        chain = CallbackChain()
        chain.add(lambda: True)
        chain.clear()
        # __len__ 包含 main + pre + post
        assert len(chain) == 0

    def test_execute_with_args(self):
        chain = CallbackChain()
        results = []
        chain.add(lambda x: (results.append(x), True))
        chain.execute(42)
        assert results == [42]


class TestDecorators:
    """装饰器测试"""

    def test_delegate_decorator(self):
        @delegate
        def my_event(x):
            return x

        assert my_event.count == 1  # 装饰器添加了原函数
        my_event.add(lambda x: None)
        assert my_event.count == 2

    def test_thread_safe_decorator(self):
        @thread_safe
        def critical_func():
            return 42

        assert critical_func() == 42
