# -*- coding: utf-8 -*-
"""回归测试：BoundedChannel.recv() 在已关闭空通道上永久阻塞（BUG-493）。

修复前：

    ch = BoundedChannel(2)
    ch.close()
    ch.recv()          # 永久阻塞！实现是 self._queue.get(timeout=None)，
                       # queue.Empty 永不抛出 → 消费者线程静默挂死
                       # 而 docstring 承诺"通道关闭且已空时返回 None"

修复后：默认无超时时按 0.1s 分片等待并检查关闭状态——已关闭且空立即返回 None，
未关闭时仍保持阻塞等待语义（有数据照常返回）。
"""

import threading
import time

import pytest

from vools.vconcurrent.queues import BoundedChannel, ChannelClosedError


class TestClosedChannelRecv:
    def test_closed_empty_returns_none_quickly(self):
        ch = BoundedChannel(2)
        ch.close()
        t0 = time.time()
        assert ch.recv() is None
        assert time.time() - t0 < 1.0      # 修复前会一直挂着

    def test_drains_data_before_none(self):
        ch = BoundedChannel(2)
        ch.send(1)
        ch.send(2)
        ch.close()
        assert ch.recv() == 1
        assert ch.recv() == 2
        assert ch.recv() is None

    def test_second_recv_also_returns_none(self):
        ch = BoundedChannel(1)
        ch.close()
        assert ch.recv() is None
        assert ch.recv() is None

    def test_iteration_after_close_drains(self):
        ch = BoundedChannel(2)
        ch.send("a")
        ch.close()
        assert list(ch) == ["a"]


class TestBlockingSemanticsPreserved:
    def test_open_empty_blocks_until_data(self):
        """未关闭时必须保持"阻塞等待数据"的既有语义。"""
        ch = BoundedChannel(1)

        def later():
            time.sleep(0.2)
            ch.send("late")

        threading.Thread(target=later, daemon=True).start()
        t0 = time.time()
        assert ch.recv() == "late"
        assert time.time() - t0 >= 0.1

    def test_recv_timeout_unchanged(self):
        ch = BoundedChannel(1)
        assert ch.recv_timeout(0.05) is None

    def test_close_then_send_raises(self):
        ch = BoundedChannel(1)
        ch.close()
        with pytest.raises(ChannelClosedError):
            ch.send(1)

    def test_send_recv_roundtrip(self):
        ch = BoundedChannel(1)
        ch.send("x")
        assert ch.recv() == "x"


class TestOtherQueueTypesUnchanged:
    def test_priority_queue_order(self):
        from vools.vconcurrent.queues import VPriorityQueue

        # 优先级是独立的 priority= 关键字参数（item 本身不参与排序）
        pq = VPriorityQueue()
        pq.put("low", priority=10)
        pq.put("high", priority=1)
        assert pq.get() == "high"
        assert pq.get() == "low"

    def test_lifo_queue_order(self):
        from vools.vconcurrent.queues import VLifoQueue

        lifo = VLifoQueue()
        lifo.push("a")
        lifo.push("b")
        assert lifo.pop() == "b"

    def test_vqueue_fifo(self):
        from vools.vconcurrent.queues import VQueue

        q = VQueue(3)
        q.put(1)
        q.put(2)
        assert q.get() == 1
        assert q.qsize() == 1
