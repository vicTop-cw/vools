# -*- coding: utf-8 -*-
"""回归测试：bridge_queues 接受非队列对象 → 完全空转桥（BUG-491）。

修复前：

    bridge_queues(123, q)     # 静默返回两个 QueueBridge：
                              # is_running=True / error_count=0 / last_error=None
                              # ——线程活着、零错误、但**永远不转发**，调用方无从发现
    bridge_queues(q, q2, filter_fn=123)      # 非可调用 filter 静默接受
    bridge_queues(q, q2, transform_fn="x")   # 同上
    bridge_queues(q, q2, daemon="yes")       # daemon 非 bool 静默当成真值

修复后按鸭子类型校验队列（需 get()/put()）、filter_fn/transform_fn 可调用、
daemon 为 bool。正常转发/过滤/转换行为不变。
"""

import queue
import time

import pytest

from vools.vconcurrent.bridges import QueueBridge, bridge_queues


def _drain(q, timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return q.get_nowait()
        except queue.Empty:
            time.sleep(0.01)
    raise queue.Empty


class TestQueueValidation:
    @pytest.mark.parametrize("bad", [123, "x", None, []])
    def test_q1_not_a_queue(self, bad):
        with pytest.raises(TypeError) as ei:
            bridge_queues(bad, queue.Queue())
        assert "q1" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x"])
    def test_q2_not_a_queue(self, bad):
        with pytest.raises(TypeError) as ei:
            bridge_queues(queue.Queue(), bad)
        assert "q2" in str(ei.value)

    def test_object_without_put_rejected(self):
        class Fake:
            def get(self):
                return None

        with pytest.raises(TypeError):
            bridge_queues(Fake(), queue.Queue())

    @pytest.mark.parametrize("kw", ["filter_fn", "transform_fn"])
    def test_non_callable_hooks(self, kw):
        with pytest.raises(TypeError) as ei:
            bridge_queues(queue.Queue(), queue.Queue(), **{kw: 123})
        assert kw in str(ei.value)

    @pytest.mark.parametrize("bad", ["yes", 1, None])
    def test_daemon_must_be_bool(self, bad):
        with pytest.raises(TypeError) as ei:
            bridge_queues(queue.Queue(), queue.Queue(), daemon=bad)
        assert "daemon" in str(ei.value)

    def test_bad_direction(self):
        with pytest.raises(ValueError):
            bridge_queues(queue.Queue(), queue.Queue(), direction="nope")


class TestBridgingBehaviourUnchanged:
    def test_forward(self):
        q1, q2 = queue.Queue(), queue.Queue()
        fwd, bwd = bridge_queues(q1, q2, direction="forward")
        try:
            assert isinstance(fwd, QueueBridge)
            assert bwd is None
            q1.put({"m": 1})
            assert _drain(q2) == {"m": 1}
        finally:
            fwd.stop()

    def test_bidirectional(self):
        q1, q2 = queue.Queue(), queue.Queue()
        b1, b2 = bridge_queues(q1, q2)
        try:
            assert b1 is not None and b2 is not None
            q1.put("from-q1")
            assert _drain(q2) == "from-q1"
            q2.put("from-q2")
            assert _drain(q1) == "from-q2"
        finally:
            b1.stop()
            b2.stop()

    def test_filter_and_transform(self):
        q1, q2 = queue.Queue(), queue.Queue()
        fwd, _ = bridge_queues(
            q1, q2, direction="forward",
            filter_fn=lambda x: x > 0,
            transform_fn=lambda x: x * 10,
        )
        try:
            q1.put(1)
            q1.put(-1)          # 被过滤
            assert _drain(q2) == 10
            time.sleep(0.1)
            assert q2.empty()
        finally:
            fwd.stop()

    def test_bridge_status_properties(self):
        q1, q2 = queue.Queue(), queue.Queue()
        fwd, _ = bridge_queues(q1, q2, direction="forward")
        try:
            assert fwd.is_running is True
            assert fwd.error_count == 0
            assert fwd.last_error is None
        finally:
            fwd.stop()
