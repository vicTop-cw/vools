# -*- coding: utf-8 -*-
"""回归测试：EventBus.publish 传播异常、publish_safe 隔离（BUG-229）。

原 `publish` 与 `publish_safe` **双双静默吞订阅者异常**（安全/非安全区分
失效）——同族 `Delegate.invoke`/`invoke_safe` 与 `MessageDispatcher.dispatch`/
`dispatch_safe` 都是严格区分（非安全版传播），且 `publish_safe` docstring
反证 publish 应传播。

另：原实现用 `except TypeError` 探测订阅者签名——业务 TypeError 被误判为
签名不匹配而重试，`*args` 形态订阅者被**双执行**且真实错误被吞。现改为
签名一次性判定（sigcache.get_signature + sig.bind），调用不再捕获业务异常。
"""

import pytest

from vools.vconcurrent.delegates import EventBus


class TestPublishPropagates:
    """BUG-229 核心：非安全版传播订阅者异常。"""

    def test_publish_propagates_business_error(self):
        bus = EventBus()
        bus.subscribe("e", lambda event, data: 1 / 0)
        with pytest.raises(ZeroDivisionError):
            bus.publish("e", 1)

    def test_publish_propagates_runtime_error(self):
        bus = EventBus()

        def bad(event, data):
            raise RuntimeError("业务错误必须可见")

        bus.subscribe("e", bad)
        with pytest.raises(RuntimeError, match="业务错误必须可见"):
            bus.publish("e", 1)

    def test_publish_safe_isolates(self):
        bus = EventBus()
        bus.subscribe("e", lambda event, data: 1 / 0)
        assert bus.publish_safe("e", 1) == [None]


class TestNoDoubleExecution:
    """BUG-229 第二面：业务 TypeError 不得触发重试双执行。"""

    def test_star_args_handler_runs_once(self):
        runs = []

        def generic(*args):
            runs.append(args)
            raise TypeError("业务 TypeError 不该被当签名不匹配")

        bus = EventBus()
        bus.subscribe("t", generic)
        with pytest.raises(TypeError):
            bus.publish("t", 42)
        assert len(runs) == 1

    def test_degraded_form_still_dispatched(self):
        # 不接收 event 首参的订阅者仍能正确分发（签名一次性判定）
        got = {}
        bus = EventBus()
        bus.subscribe("x", lambda data: got.__setitem__("val", data))
        bus.publish("x", 7)
        assert got["val"] == 7


class TestCallingConventions:
    """两种订阅者惯例签名均正确分发。"""

    def test_with_event_form(self):
        got = {}
        bus = EventBus()
        bus.subscribe("x", lambda event, data: got.update(ev=event, data=data))
        bus.publish("x", 7)
        assert got == {"ev": "x", "data": 7}

    def test_no_event_form(self):
        got = {}
        bus = EventBus()
        bus.subscribe("x", lambda data: got.__setitem__("data", data))
        bus.publish("x", 7)
        assert got["data"] == 7


class TestNormalPathsUnchanged:
    """正常返回路径保持（防修复过度）。"""

    def test_multiple_subscribers_results(self):
        bus = EventBus()
        bus.subscribe("m", lambda event, d: "a")
        bus.subscribe("m", lambda event, d: "b")
        assert bus.publish("m", 1) == ["a", "b"]
        assert bus.publish_safe("m", 1) == ["a", "b"]

    def test_no_subscribers(self):
        bus = EventBus()
        assert bus.publish("none", 1) == []
        assert bus.publish_safe("none", 1) == []