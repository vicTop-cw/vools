# -*- coding: utf-8 -*-
"""回归测试：事件/回调注册入口的参数校验（BUG-401）。

`vconcurrent.delegates` 各注册入口原先把任意对象直接塞进容器，零校验：

    EventBus().subscribe('e', 'nope')             # 接受
    EventBus().publish('e', 1)                    # → TypeError，且中断后续订阅者
    Delegate().add('nope')                        # 接受 → invoke 时才炸
    CallbackChain().add('nope')                   # 接受 → execute 静默返回 False
    MessageDispatcher().register('T', 'nope')     # 接受 → dispatch 抛
                                                  # issubclass() arg 2 must be a class...

其中 `MessageDispatcher` 的错误尤其跑偏（把注册键当类做 issubclass）。
修复：handler 必须可调用；`MessageDispatcher.register` 的消息类型必须是类；
`EventBus` 事件名必须非空字符串。正常订阅/发布/分发/链式执行行为不变。
"""

import pytest

from vools.vconcurrent.delegates import (
    CallbackChain,
    Delegate,
    EventBus,
    MessageDispatcher,
)


class TestCallableValidation:
    def test_event_bus_handler(self):
        with pytest.raises(TypeError) as ei:
            EventBus().subscribe('e', 'nope')
        assert '可调用' in str(ei.value)

    def test_delegate_handler(self):
        with pytest.raises(TypeError):
            Delegate().add('nope')

    def test_dispatcher_handler(self):
        with pytest.raises(TypeError) as ei:
            MessageDispatcher().register(str, 'nope')
        assert '消息处理器' in str(ei.value)

    def test_callback_chain_callback(self):
        with pytest.raises(TypeError):
            CallbackChain().add('nope')


class TestEventNameValidation:
    @pytest.mark.parametrize('bad', [123, '', '   ', None])
    def test_bad_event_name(self, bad):
        with pytest.raises(ValueError):
            EventBus().subscribe(bad, print)


class TestDispatcherMessageType:
    @pytest.mark.parametrize('bad', ['T', 123, None, object()])
    def test_non_class_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            MessageDispatcher().register(bad, print)
        assert '类' in str(ei.value)

    def test_valid_dispatch(self):
        class Msg:
            pass

        hits = []
        m = MessageDispatcher()
        m.register(Msg, lambda msg: hits.append(msg))
        m.dispatch(Msg())
        assert len(hits) == 1

    def test_subclass_matching(self):
        class Base:
            pass

        class Child(Base):
            pass

        hits = []
        m = MessageDispatcher()
        m.register(Base, lambda msg: hits.append('base'))
        m.dispatch(Child())
        assert hits == ['base']


class TestNormalPathsUnchanged:
    def test_event_bus_publish_and_unsubscribe(self):
        bus = EventBus()
        hits = []
        bus.subscribe('evt', lambda x: hits.append(x))
        bus.publish('evt', 1)
        assert hits == [1]
        bus.unsubscribe('evt', lambda x: None)  # 未注册的 handler：无副作用
        bus.publish('evt', 2)
        assert hits == [1, 2]

    def test_wildcard(self):
        bus = EventBus()
        hits = []
        bus.subscribe('*', lambda evt, *args: hits.append((evt, args)))
        bus.publish('other', 9)
        assert hits == [('other', (9,))]

    def test_delegate(self):
        d = Delegate()
        hits = []
        d.add(lambda x: hits.append(x))
        d.invoke(5)
        assert hits == [5]

    def test_callback_chain_order(self):
        chain = CallbackChain()
        log = []
        chain.add(lambda: log.append('main'))
        chain.add_pre(lambda: log.append('pre'))
        chain.execute()
        assert log == ['pre', 'main']