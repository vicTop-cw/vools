"""tests/concurrent/test_bridges.py — 桥接工具测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.bridges import (
    PipePair, ThreadProcessBridge, ChannelBridge, QueueBridge,
    SharedBridge, EventBridge, StreamBridge, bridge_queues,
)


class TestPipePair:
    """PipePair 管道对测试"""

    def test_creation(self):
        pp = PipePair()
        assert pp is not None

    def test_a_and_b(self):
        pp = PipePair()
        assert pp.a is not None
        assert pp.b is not None

    def test_close(self):
        pp = PipePair()
        pp.close()
        assert True  # 无异常即通过

    def test_context_manager(self):
        with PipePair() as pp:
            assert pp.a is not None
        assert True  # 无异常即通过


class TestThreadProcessBridge:
    """ThreadProcessBridge 线程-进程桥接测试"""

    def test_creation(self):
        b = ThreadProcessBridge()
        assert b is not None

    def test_send_recv_thread_side(self):
        b = ThreadProcessBridge()
        b.send_thread_side('hello')
        assert b.recv_thread_side() == 'hello'

    def test_close(self):
        b = ThreadProcessBridge()
        b.close()
        assert True  # 无异常即通过


class TestChannelBridge:
    """ChannelBridge 通道桥接测试"""

    def test_creation(self):
        b = ChannelBridge()
        assert b is not None

    def test_connection(self):
        b = ChannelBridge()
        assert b.connection is not None

    def test_send_recv(self):
        b = ChannelBridge()
        b.send('test')
        assert b.recv() == 'test'

    def test_send_json_recv_json(self):
        b = ChannelBridge()
        b.send_json({'key': 'value'})
        assert b.recv_json() == {'key': 'value'}

    def test_poll(self):
        b = ChannelBridge()
        assert b.poll(0.1) is False

    def test_closed(self):
        b = ChannelBridge()
        assert b.closed is False
        b.close()
        assert b.closed is True


class TestQueueBridge:
    """QueueBridge 队列桥接测试"""

    def test_creation(self):
        b = QueueBridge()
        assert b is not None

    def test_start_stop(self):
        b = QueueBridge()
        b.start()
        assert b.is_running() is True
        b.stop()
        assert b.is_running() is False


class TestSharedBridge:
    """SharedBridge 共享内存桥接测试"""

    def test_creation(self):
        b = SharedBridge('test_bridge', size=1024)
        assert b is not None

    def test_name(self):
        b = SharedBridge('my_bridge', size=1024)
        assert b.name == 'my_bridge'

    def test_size(self):
        b = SharedBridge('test', size=2048)
        assert b.size == 2048

    def test_write_read(self):
        b = SharedBridge('test', size=1024)
        b.write(b'hello')
        assert b.read(5) == b'hello'

    def test_write_object_read_object(self):
        b = SharedBridge('test', size=4096)
        b.write_object({'key': 'value'})
        assert b.read_object() == {'key': 'value'}

    def test_close(self):
        b = SharedBridge('test', size=1024)
        b.close()
        assert True  # 无异常即通过

    def test_unlink(self):
        b = SharedBridge('test', size=1024)
        b.unlink()
        assert True  # 无异常即通过


class TestEventBridge:
    """EventBridge 事件桥接测试"""

    def test_creation(self):
        b = EventBridge()
        assert b is not None

    def test_set_clear(self):
        b = EventBridge()
        b.set()
        assert b.is_set() is True
        b.clear()
        assert b.is_set() is False

    def test_wait(self):
        b = EventBridge()
        b.set()
        assert b.wait(1.0) is True

    def test_event(self):
        b = EventBridge()
        assert b.event is not None


class TestStreamBridge:
    """StreamBridge 流桥接测试"""

    def test_creation(self):
        b = StreamBridge()
        assert b is not None

    def test_buffer_size(self):
        b = StreamBridge(buffer_size=1024)
        assert b.buffer_size == 1024

    def test_send_recv(self):
        b = StreamBridge()
        b.send('data')
        assert b.recv() == 'data'

    def test_qsize(self):
        b = StreamBridge()
        assert b.qsize() == 0

    def test_close(self):
        b = StreamBridge()
        b.close()
        assert True  # 无异常即通过


class TestBridgeQueues:
    """bridge_queues 工具函数测试"""

    def test_bridge_queues(self):
        from vools.concurrent.queues import VQueue
        q1 = VQueue()
        q2 = VQueue()
        bridge = bridge_queues(q1, q2)
        assert bridge is not None
