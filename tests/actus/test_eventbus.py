"""tests/actus/test_eventbus.py — 事件总线测试"""
import pytest
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.eventbus import EventBus, Event, EventType, get_event_bus


class TestEvent:
    """Event 数据类测试"""

    def test_event_creation(self):
        e = Event(type='test.event', data={'key': 'value'}, source='test')
        assert e.type == 'test.event'
        assert e.data == {'key': 'value'}
        assert e.source == 'test'

    def test_event_to_dict(self):
        e = Event(type='test', data={'a': 1}, source='src')
        d = e.to_dict()
        assert d['type'] == 'test'
        assert d['data']['a'] == 1


class TestEventBus:
    """EventBus 核心功能测试"""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe('test.event', lambda e: received.append(e))
        bus.publish('test.event', {'msg': 'hello'}, source='test')
        time.sleep(0.1)  # 等待异步处理
        assert len(received) == 1
        assert received[0].data['msg'] == 'hello'

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        callback = lambda e: received.append(e)
        bus.subscribe('test.event', callback)
        bus.unsubscribe('test.event', callback)
        bus.publish('test.event', {'msg': 'hello'})
        time.sleep(0.1)
        assert len(received) == 0

    def test_multiple_subscribers(self):
        bus = EventBus()
        results = []
        bus.subscribe('multi', lambda e: results.append('a'))
        bus.subscribe('multi', lambda e: results.append('b'))
        bus.publish('multi', {})
        time.sleep(0.1)
        assert 'a' in results
        assert 'b' in results

    def test_get_history(self):
        bus = EventBus()
        bus.publish('evt1', {'n': 1})
        bus.publish('evt2', {'n': 2})
        time.sleep(0.1)
        history = bus.get_history()
        assert len(history) >= 2

    def test_history_filter_by_type(self):
        bus = EventBus()
        bus.publish('type_a', {'x': 1})
        bus.publish('type_b', {'x': 2})
        time.sleep(0.1)
        filtered = bus.get_history(event_type='type_a')
        assert all(e['type'] == 'type_a' for e in filtered)

    def test_clear_history(self):
        bus = EventBus()
        bus.publish('evt', {})
        time.sleep(0.1)
        bus.clear_history()
        assert len(bus.get_history()) == 0

    def test_subscriber_count(self):
        bus = EventBus()
        bus.subscribe('evt', lambda e: None)
        bus.subscribe('evt', lambda e: None)
        assert bus.subscriber_count('evt') == 2

    def test_history_limit(self):
        bus = EventBus(history_limit=5)
        for i in range(10):
            bus.publish('evt', {'n': i})
        time.sleep(0.2)
        history = bus.get_history()
        assert len(history) <= 5

    def test_publish_without_subscribers(self):
        bus = EventBus()
        # 无订阅者时发布不应报错
        bus.publish('no_subs', {'data': 1})
        time.sleep(0.05)
        assert True  # 无异常即通过


class TestEventType:
    """EventType 常量测试"""

    def test_event_type_values(self):
        assert hasattr(EventType, 'ACTION_COMPLETED')
        assert hasattr(EventType, 'ACTION_FAILED')

    def test_emit_and_on(self):
        from vools.actus.eventbus import on, emit
        bus = get_event_bus()
        results = []
        on('test.custom', lambda e: results.append(e))
        emit('test.custom', {'val': 42})
        time.sleep(0.1)
        assert len(results) >= 1
