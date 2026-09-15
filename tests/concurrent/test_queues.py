"""tests/concurrent/test_queues.py — 队列测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.concurrent.queues import (
    VQueue, VPriorityQueue, VLifoQueue, VDeque, BoundedChannel,
    ChannelClosedError, merge_queues, queue_to_generator,
)


class TestVQueue:
    """VQueue 基础队列测试"""

    def test_put_and_get(self):
        q = VQueue()
        q.put('item')
        assert q.get() == 'item'

    def test_qsize(self):
        q = VQueue()
        q.put(1)
        q.put(2)
        assert q.qsize() == 2

    def test_is_empty(self):
        q = VQueue()
        assert q.is_empty() is True
        q.put(1)
        assert q.is_empty() is False

    def test_put_many(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        assert q.qsize() == 3

    def test_get_many(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        items = q.get_many(2)
        assert items == [1, 2]
        assert q.qsize() == 1

    def test_peek(self):
        q = VQueue()
        q.put('first')
        assert q.peek() == 'first'
        assert q.qsize() == 1

    def test_clear(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        q.clear()
        assert q.is_empty() is True

    def test_to_list(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        lst = q.to_list()
        assert lst == [1, 2, 3]

    def test_len(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        assert len(q) == 3

    def test_bool(self):
        q = VQueue()
        assert bool(q) is False
        q.put(1)
        assert bool(q) is True


class TestVPriorityQueue:
    """VPriorityQueue 优先队列测试"""

    def test_put_and_get(self):
        q = VPriorityQueue()
        q.put('low', priority=3)
        q.put('high', priority=1)
        q.put('mid', priority=2)
        # 应该按优先级顺序取出
        assert q.get() == 'high'
        assert q.get() == 'mid'
        assert q.get() == 'low'

    def test_qsize(self):
        q = VPriorityQueue()
        q.put(1, 'a')
        q.put(2, 'b')
        assert q.qsize() == 2

    def test_clear(self):
        q = VPriorityQueue()
        q.put(1, 'a')
        q.clear()
        assert q.is_empty() is True

    def test_to_list(self):
        q = VPriorityQueue()
        q.put(1, 'a')
        q.put(2, 'b')
        lst = q.to_list()
        assert len(lst) == 2


class TestVLifoQueue:
    """VLifoQueue 后进先出队列测试"""

    def test_put_and_get(self):
        q = VLifoQueue()
        q.put(1)
        q.put(2)
        q.put(3)
        # LIFO: 最后放入的最先取出
        assert q.get() == 3
        assert q.get() == 2
        assert q.get() == 1

    def test_push_pop(self):
        q = VLifoQueue()
        q.push('a')
        q.push('b')
        assert q.pop() == 'b'
        assert q.pop() == 'a'

    def test_peek(self):
        q = VLifoQueue()
        q.push('top')
        assert q.peek() == 'top'

    def test_clear(self):
        q = VLifoQueue()
        q.push(1)
        q.clear()
        assert q.is_empty() is True


class TestVDeque:
    """VDeque 双端队列测试"""

    def test_append_left(self):
        q = VDeque()
        q.append_left(1)
        q.append_left(2)
        assert q.pop_right() == 1
        assert q.pop_right() == 2

    def test_append_right(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        assert q.pop_left() == 1
        assert q.pop_left() == 2

    def test_peek_left(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        assert q.peek_left() == 1

    def test_peek_right(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        assert q.peek_right() == 2

    def test_len(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        q.append_left(0)
        assert len(q) == 3

    def test_clear(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        q.clear()
        assert q.is_empty() is True

    def test_rotate(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        q.append_right(3)
        q.rotate(1)
        assert q.pop_left() == 3

    def test_reverse(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        q.append_right(3)
        q.reverse()
        assert q.pop_left() == 3

    def test_count(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(1)
        q.append_right(2)
        assert q.count(1) == 2

    def test_contains(self):
        q = VDeque()
        q.append_right(1)
        assert 1 in q
        assert 2 not in q

    def test_remove(self):
        q = VDeque()
        q.append_right(1)
        q.append_right(2)
        q.remove(1)
        assert 1 not in q


class TestBoundedChannel:
    """BoundedChannel 有界通道测试"""

    def test_send_recv(self):
        ch = BoundedChannel(maxsize=5)
        ch.send('hello')
        assert ch.recv() == 'hello'

    def test_is_empty(self):
        ch = BoundedChannel(maxsize=5)
        assert ch.is_empty() is True
        ch.send(1)
        assert ch.is_empty() is False

    def test_is_closed(self):
        ch = BoundedChannel(maxsize=5)
        assert ch.is_closed is False
        ch.close()
        assert ch.is_closed is True

    def test_close_blocks_send(self):
        ch = BoundedChannel(maxsize=5)
        ch.close()
        with pytest.raises(ChannelClosedError):
            ch.send('data')

    def test_recv_closed_empty_returns_none(self):
        ch = BoundedChannel(maxsize=5)
        ch.close()
        # 关闭且空时返回 None
        assert ch.recv(timeout=0.1) is None

    def test_qsize(self):
        ch = BoundedChannel(maxsize=5)
        ch.send(1)
        ch.send(2)
        assert ch.qsize() == 2


class TestUtilityFunctions:
    """工具函数测试"""

    def test_merge_queues_nonblocking(self):
        q1 = VQueue()
        q2 = VQueue()
        q1.put(1)
        q1.put(2)
        q2.put(3)
        # 非阻塞模式：读取当前可用元素后立即返回
        merged = list(merge_queues([q1, q2], timeout=None))
        assert len(merged) >= 1

    def test_queue_to_generator_blocking(self):
        q = VQueue()
        q.put_many([1, 2, 3])
        gen = queue_to_generator(q, timeout=0.05)
        items = list(gen)
        assert 1 in items
        assert 2 in items
        assert 3 in items
