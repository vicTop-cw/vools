# -*- coding: utf-8 -*-
"""回归测试：QueueBridge 转发异常可见 + bridge_queues 方向校验（BUG-402）。

`QueueBridge._worker` 原先对 filter/transform/put 的异常一律
``except Exception: pass``：

    bridge = QueueBridge(src, dst, filter_fn=lambda x: 1/0)
    bridge.start()
    src.put(1)
    # 消息被**静默丢弃**，is_running 仍为 True，last_error 不存在——
    # 用户只能看到"没消息过来"，完全没有线索

`bridge_queues(direction='bogus')` 同样静默返回 ``(None, None)``，调用方以为
桥接已建立。

修复：
- `_worker` 记录 `last_error` / `error_count`，首次出错发 RuntimeWarning，
  仍保持"单条坏消息不停桥"的原有韧性；
- `bridge_queues` 校验 direction ∈ {forward, backward, both}，否则 ValueError。

正常 filter/transform 转发、三种方向、start/stop/restart 行为不变。
"""

import queue
import time
import warnings

import pytest

from vools.vconcurrent.bridges import QueueBridge, bridge_queues


class TestBridgeQueuesDirection:
    @pytest.mark.parametrize('bad', ['bogus', '', 'oneway', None, 'Both'])
    def test_invalid_direction(self, bad):
        with pytest.raises(ValueError) as ei:
            bridge_queues(queue.Queue(), queue.Queue(), direction=bad)
        assert 'direction' in str(ei.value)

    @pytest.mark.parametrize('direction,expected', [
        ('forward', (True, False)),
        ('backward', (False, True)),
        ('both', (True, True)),
    ])
    def test_valid_directions(self, direction, expected):
        q1, q2 = queue.Queue(), queue.Queue()
        bridges = bridge_queues(q1, q2, direction=direction)
        try:
            assert tuple(b is not None for b in bridges) == expected
        finally:
            for b in bridges:
                if b is not None:
                    b.stop()


class TestFilterErrorVisibility:
    def test_filter_exception_recorded(self):
        src, dst = queue.Queue(), queue.Queue()
        src.put(1)
        bridge = QueueBridge(src, dst,
                             filter_fn=lambda x: (_ for _ in ()).throw(
                                 RuntimeError('boom')))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            bridge.start()
            time.sleep(0.25)
            bridge.stop()
        # 修复前：静默丢弃，无 warning、无 last_error
        assert caught
        assert isinstance(bridge.last_error, RuntimeError)
        assert bridge.error_count == 1
        assert dst.qsize() == 0

    def test_transform_exception_recorded(self):
        src, dst = queue.Queue(), queue.Queue()
        src.put('x')
        bridge = QueueBridge(src, dst,
                             transform_fn=lambda x: (_ for _ in ()).throw(
                                 ValueError('bad transform')))
        with warnings.catch_warnings(record=True):
            warnings.simplefilter('always')
            bridge.start()
            time.sleep(0.25)
            bridge.stop()
        assert isinstance(bridge.last_error, ValueError)
        assert bridge.error_count == 1

    def test_bridge_keeps_running_after_bad_item(self):
        src, dst = queue.Queue(), queue.Queue()
        calls = []

        def flaky(x):
            calls.append(x)
            if x == 'bad':
                raise RuntimeError('boom')
            return x

        bridge = QueueBridge(src, dst, filter_fn=flaky)
        try:
            bridge.start()
            with warnings.catch_warnings(record=True):
                warnings.simplefilter('always')
                src.put('bad')
                time.sleep(0.15)
                src.put('good')
                time.sleep(0.2)
        finally:
            bridge.stop()
        # 坏消息被丢弃，后续好消息仍转发
        assert calls == ['bad', 'good']
        assert dst.get_nowait() == 'good'
        assert bridge.error_count == 1


class TestNormalPathsUnchanged:
    def test_filter_and_transform(self):
        src, dst = queue.Queue(), queue.Queue()
        for i in (1, 2, 3, 4):
            src.put(i)
        bridge = QueueBridge(src, dst,
                             filter_fn=lambda x: x % 2 == 0,
                             transform_fn=lambda x: x * 10)
        bridge.start()
        time.sleep(0.25)
        bridge.stop()
        got = []
        while not dst.empty():
            got.append(dst.get())
        assert got == [20, 40]
        assert bridge.error_count == 0
        assert bridge.last_error is None

    def test_start_stop_restart(self):
        bridge = QueueBridge(queue.Queue(), queue.Queue())
        assert bridge.is_running is False
        bridge.start()
        assert bridge.is_running is True
        bridge.stop()
        assert bridge.is_running is False
        bridge.stop()          # 重复 stop 幂等
        bridge.start()
        time.sleep(0.05)
        bridge.stop()
        assert bridge.is_running is False

    def test_context_manager(self):
        src, dst = queue.Queue(), queue.Queue()
        with QueueBridge(src, dst) as bridge:
            src.put('a')
            time.sleep(0.2)
            assert dst.get_nowait() == 'a'
        assert bridge.is_running is False