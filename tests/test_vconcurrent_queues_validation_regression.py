# -*- coding: utf-8 -*-
"""回归测试：vconcurrent.queues 的 maxsize / timeout 参数校验（BUG-347）。

修复前：

    VQueue("x")            # 构造成功（repr 里 maxsize=x），直到第一次
    VQueue("x").is_full()  # TypeError: '<' not supported between instances of 'int' and 'str'
    VQueue("x").put(1)     # TypeError: '>' not supported between instances of 'str' and 'int'
    VLifoQueue("x")        # 同上
    BoundedChannel("x")    # 同上（send 时才炸）

    q.get_timeout("x")     # TypeError: '<' not supported between instances of 'str' and 'int'
    q.put_timeout(1, "x")  # 同类裸错（视队列状态才暴露）

修复：三个构造函数的 maxsize 必须整数（bool 拒绝；0/负数按 stdlib 语义=无界）；
VQueue/VLifoQueue/VPriorityQueue 的 get_timeout、VQueue 的 get/put/put_timeout
统一校验 timeout 为 None 或非负数值。

本文件的阻塞类断言都带超时参数，避免测试挂死。
"""

import pytest

from vools.vconcurrent.queues import BoundedChannel, VLifoQueue, VPriorityQueue, VQueue


class TestMaxsizeValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, True, [1]])
    def test_vqueue(self, bad):
        with pytest.raises(TypeError) as ei:
            VQueue(bad)
        assert "maxsize" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None, True])
    def test_lifo(self, bad):
        with pytest.raises(TypeError) as ei:
            VLifoQueue(bad)
        assert "maxsize" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None, True])
    def test_bounded_channel(self, bad):
        with pytest.raises(TypeError) as ei:
            BoundedChannel(bad)
        assert "maxsize" in str(ei.value)


class TestTimeoutValidation:
    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_get_timeout(self, bad):
        q = VQueue()
        with pytest.raises(TypeError) as ei:
            q.get_timeout(bad)
        assert "timeout" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_put_timeout(self, bad):
        q = VQueue()
        with pytest.raises(TypeError) as ei:
            q.put_timeout(1, bad)
        assert "timeout" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_get_with_timeout(self, bad):
        q = VQueue()
        with pytest.raises(TypeError):
            q.get(timeout=bad)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_put_with_timeout(self, bad):
        q = VQueue()
        with pytest.raises(TypeError):
            q.put(1, timeout=bad)

    def test_negative_timeout_rejected(self):
        q = VQueue()
        with pytest.raises(ValueError):
            q.get_timeout(-1)
        with pytest.raises(ValueError):
            q.put_timeout(1, -1)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_lifo_and_priority_get_timeout(self, bad):
        with pytest.raises(TypeError):
            VLifoQueue().get_timeout(bad)
        with pytest.raises(TypeError):
            VPriorityQueue().get_timeout(bad)


class TestBehaviourUnchanged:
    def test_vqueue_roundtrip(self):
        q = VQueue(2)
        assert q.put(1) is None
        assert q.get_timeout(0.5) == 1

    def test_negative_maxsize_means_unbounded(self):
        q = VQueue(-1)
        assert q.is_full() is False
        q.put(1)
        assert q.qsize() == 1

    def test_zero_maxsize_means_unbounded(self):
        assert VQueue(0).is_full() is False

    def test_bounded_channel_roundtrip(self):
        ch = BoundedChannel(1)
        ch.send(1)
        assert ch.recv() == 1
        ch.close()

    def test_lifo_order(self):
        q = VLifoQueue()
        q.put(1)
        q.put(2)
        assert q.get_timeout(0.5) == 2

    def test_priority_order(self):
        q = VPriorityQueue()
        q.put("low", priority=9)
        q.put("high", priority=0)
        assert q.get_timeout(0.5) == "high"

    def test_put_timeout_when_full(self):
        q = VQueue(1)
        q.put(1)
        assert q.put_timeout(2, 0.01) is False

    def test_get_timeout_when_empty(self):
        assert VQueue().get_timeout(0.01) is None
