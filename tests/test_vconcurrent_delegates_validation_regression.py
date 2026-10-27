# -*- coding: utf-8 -*-
"""回归测试：delegates 族参数校验（BUG-358）。

修复前：

    AsyncDelegate().add(None)              # 静默登记（Delegate.add 有校验，Async 没有）
    AsyncDelegate().invoke_and_wait(timeout="x")
        # TypeError: '>' not supported between instances of 'int' and 'str'
    AsyncDelegate().invoke_and_wait(timeout=-1)   # 静默"不等待"
    EventBus().subscribe("e", fn, priority="x")   # 接受；随后**任何** subscribe 在
                                                 # 排序时抛 "'<' not supported between
                                                 # instances of 'int' and 'str'"（一次坏入参
                                                 # 把整个 bus 打成不可用）
    EventBus().unsubscribe(None, fn)              # 静默接受（subscribe 却校验事件名）
    EventBus().has_subscribers(None)              # 静默返回 False
    MessageDispatcher().has_handlers(None)        # TypeError: issubclass() arg 1 must be a class

修复：AsyncDelegate.add 复用 _require_callable；invoke_and_wait 校验 timeout；
EventBus.subscribe 校验 priority 为 int；EventBus 的 unsubscribe/has_subscribers/
subscriber_count 校验事件名；MessageDispatcher 的 has_handlers/handler_count 校验消息类型。
"""

import pytest

from vools.vconcurrent.delegates import AsyncDelegate, EventBus, MessageDispatcher


class _Msg:
    pass


class TestAsyncDelegateValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x"])
    def test_add_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            AsyncDelegate().add(bad)
        assert "回调" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", [1]])
    def test_timeout_type(self, bad):
        with pytest.raises(TypeError) as ei:
            AsyncDelegate().invoke_and_wait(timeout=bad)
        assert "timeout" in str(ei.value)

    def test_timeout_negative(self):
        with pytest.raises(ValueError):
            AsyncDelegate().invoke_and_wait(timeout=-1)

    def test_behaviour_unchanged(self):
        a = AsyncDelegate()
        a.add(lambda: 7)
        assert a.invoke_and_wait(timeout=0.5) == [7]


class TestEventBusSubscribeValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, None, True])
    def test_priority_must_be_int(self, bad):
        with pytest.raises(TypeError) as ei:
            EventBus().subscribe("e", lambda: 1, priority=bad)
        assert "priority" in str(ei.value)

    def test_bad_priority_does_not_poison_bus(self):
        bus = EventBus()
        with pytest.raises(TypeError):
            bus.subscribe("e", lambda: 1, priority="x")
        # 关键：bus 仍可用
        bus.subscribe("e", lambda: 42, priority=1)
        assert bus.publish("e") == [42]

    def test_priority_ordering_unchanged(self):
        bus = EventBus()
        bus.subscribe("p", lambda: "low", priority=5)
        bus.subscribe("p", lambda: "high", priority=1)
        assert bus.publish("p") == ["high", "low"]


class TestEventBusEventNameValidation:
    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_unsubscribe(self, bad):
        with pytest.raises(ValueError) as ei:
            EventBus().unsubscribe(bad, lambda: 1)
        assert "event" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_has_subscribers(self, bad):
        with pytest.raises(ValueError):
            EventBus().has_subscribers(bad)

    @pytest.mark.parametrize("bad", [None, 123, ""])
    def test_subscriber_count(self, bad):
        with pytest.raises(ValueError):
            EventBus().subscriber_count(bad)

    def test_behaviour_unchanged(self):
        bus = EventBus()
        handler = lambda *a: "hit"  # noqa: E731
        bus.subscribe("ev", handler)
        assert bus.has_subscribers("ev") is True
        assert bus.subscriber_count("ev") == 1
        assert bus.publish("ev") == ["hit"]
        bus.unsubscribe("ev", handler)
        assert bus.has_subscribers("ev") is False


class TestMessageDispatcherValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x"])
    def test_has_handlers(self, bad):
        with pytest.raises(TypeError) as ei:
            MessageDispatcher().has_handlers(bad)
        assert "msg_type" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_handler_count(self, bad):
        with pytest.raises(TypeError):
            MessageDispatcher().handler_count(bad)

    def test_behaviour_unchanged(self):
        md = MessageDispatcher()
        md.register(_Msg, lambda m: "ok")
        assert md.has_handlers(_Msg) is True
        assert md.handler_count(_Msg) == 1
        assert md.dispatch(_Msg()) == ["ok"]
        # 未注册类型仍返回空列表（既有契约）
        assert md.dispatch(123) == []
