# -*- coding: utf-8 -*-
"""回归测试：queue_to_generator 默认哨兵为 None 导致 None 负载被丢（BUG-494）。

修复前 ``sentinel: Any = None``：

    q.put(None)        # 合法负载
    q.put("after")
    list(queue_to_generator(q, timeout=0.05))
    # -> []   （生成器在 None 处 return）'after' 被静默丢弃，队列里还留着它

修复后默认使用**私有哨兵对象**：队列里的 ``None`` 作为普通负载正常产出；
显式传 ``sentinel=None`` 时仍按旧语义在 None 处停止（向后兼容），
``sentinel=0``/``'STOP'`` 等显式值行为不变。
"""

import queue

import pytest

from vools.vconcurrent.queues import queue_to_generator


class TestNonePayloadNotLost:
    def test_none_payload_passes_through(self):
        q = queue.Queue()
        q.put(None)
        q.put("after")
        assert list(queue_to_generator(q, timeout=0.05)) == [None, "after"]
        assert q.qsize() == 0        # 修复前会剩 1

    def test_multiple_none_payloads(self):
        q = queue.Queue()
        for item in (None, 1, None, 2):
            q.put(item)
        assert list(queue_to_generator(q, timeout=0.05)) == [None, 1, None, 2]

    def test_defensive_copy_of_old_failure(self):
        """修复前的准确症状：返回 [] 且队列残留。"""
        q = queue.Queue()
        q.put(None)
        q.put("after")
        result = list(queue_to_generator(q, timeout=0.05))
        assert result, "修复前这里恒为空列表（数据被静默丢弃）"
        assert "after" in result


class TestExplicitSentinelUnchanged:
    def test_explicit_none_sentinel_stops(self):
        q = queue.Queue()
        q.put(None)
        q.put("after")
        assert list(queue_to_generator(q, timeout=0.05, sentinel=None)) == []

    def test_numeric_sentinel(self):
        q = queue.Queue()
        for item in (1, 0, 2):
            q.put(item)
        assert list(queue_to_generator(q, timeout=0.05, sentinel=0)) == [1]

    def test_string_sentinel(self):
        q = queue.Queue()
        q.put("STOP")
        q.put("x")
        assert list(queue_to_generator(q, timeout=0.05, sentinel="STOP")) == []


class TestNormalPathUnchanged:
    def test_plain_items(self):
        q = queue.Queue()
        for item in (1, 2, 3):
            q.put(item)
        assert list(queue_to_generator(q, timeout=0.05)) == [1, 2, 3]

    def test_empty_queue_terminates(self):
        assert list(queue_to_generator(queue.Queue(), timeout=0.05)) == []

    def test_vqueue_compat(self):
        from vools.vconcurrent.queues import VQueue

        qv = VQueue()
        qv.put_many([1, 2, 3])
        assert list(queue_to_generator(qv, timeout=0.05)) == [1, 2, 3]
