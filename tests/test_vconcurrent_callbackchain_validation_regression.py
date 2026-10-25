# -*- coding: utf-8 -*-
"""回归测试：CallbackChain 的 pre/post 回调缺校验（BUG-489）。

``Delegate`` / ``EventBus`` / ``MessageDispatcher`` / ``CallbackChain.add`` 都会
校验回调可调用，唯独 ``add_pre`` / ``add_post`` 漏了：

    cc.add_pre(123)     # 修复前 → 静默收下（pre=1）
    cc.execute()        # → 内部 except Exception: pass 把 TypeError 吞掉，
                        #   钩子"注册成功但从不生效"，且无任何提示

修复后两个入口与 ``add`` 同口径拒绝非可调用对象。
"""

import pytest

from vools.vconcurrent.delegates import (
    CallbackChain,
    Delegate,
    EventBus,
    MessageDispatcher,
)


class TestCallbackChainValidation:
    @pytest.mark.parametrize("bad", [123, "x", None, [1]])
    def test_add_pre(self, bad):
        with pytest.raises(TypeError) as ei:
            CallbackChain().add_pre(bad)
        assert "前置回调" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x", None])
    def test_add_post(self, bad):
        with pytest.raises(TypeError) as ei:
            CallbackChain().add_post(bad)
        assert "后置回调" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, None])
    def test_add(self, bad):
        with pytest.raises(TypeError) as ei:
            CallbackChain().add(bad)
        assert "链回调" in str(ei.value)


class TestCallbackChainSemanticsUnchanged:
    def test_execute_order_and_result(self):
        trace = []
        cc = CallbackChain()
        cc.add_pre(lambda: trace.append("pre"))
        cc.add(lambda: trace.append("main") or True)
        cc.add_post(lambda: trace.append("post"))
        assert cc.execute() is True
        assert trace == ["pre", "main", "post"]

    def test_false_stops_chain(self):
        trace = []
        cc = CallbackChain()
        cc.add(lambda: trace.append(1) or False)
        cc.add(lambda: trace.append(2) or True)
        cc.add_post(lambda: trace.append("post"))
        assert cc.execute() is False
        assert trace == [1, "post"]      # 停止后仍执行 post

    def test_empty_chain_completes(self):
        assert CallbackChain().execute() is True


class TestOtherDelegatesUnchanged:
    def test_delegate_invoke(self):
        d = Delegate()
        d.add(lambda x: x * 2)
        d.add(lambda x: x + 1)
        assert d.invoke(3) == [6, 4]
        assert d.count == 2

    def test_delegate_rejects_non_callable(self):
        with pytest.raises(TypeError):
            Delegate().add(123)

    def test_event_bus(self):
        bus = EventBus()
        bus.subscribe("e", lambda p: p * 2)
        assert bus.publish("e", 3) == [6]
        assert bus.subscriber_count("e") == 1
        with pytest.raises(TypeError):
            bus.subscribe("e", 123)
        with pytest.raises(ValueError):
            bus.subscribe("", lambda p: p)

    def test_message_dispatcher(self):
        md = MessageDispatcher()
        md.register(int, lambda m: "int")
        assert md.dispatch(1) == ["int"]
        assert md.dispatch("x") == []
        with pytest.raises(TypeError):
            md.register(123, lambda m: "x")
        with pytest.raises(TypeError):
            md.register(int, 123)

    def test_delegate_decorator(self):
        from vools.vconcurrent.delegates import delegate

        @delegate
        def handler(x):
            return x * 2

        assert handler(3) == [6]
        handler.add(lambda v: v + 1)
        assert handler.invoke(3) == [6, 4]
