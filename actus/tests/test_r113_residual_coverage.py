# -*- coding: utf-8 -*-
"""R113 收口：4 个「在用但零测试引用」公开函数的直接契约测试。

背景：R105 公开覆盖重审计发现 9 个零测试引用公开函数（R105 残差清单漏算）。
分治方案（用户拍板）：
  - 5 个死函数（prod 引用=0）降级为 `_` 前缀（见 R113-A）；
  - 本文件锁定 4 个在用公开函数（prod 引用>0，无外部消费者）的直接行为，
    使其按名进入测试面，闭合契约覆盖指标。

覆盖对象：
  - vools.actus.eventbus.emit
  - vools.actus.intent.get_default_router
  - vools.actus.webhook.start_webhook
  - vools.actus.viz.visualize_action_workflow
"""
import os

import pytest

from vools.actus import eventbus, intent, webhook, viz


# 工作流样例（取自 test_viz.py 的 GOOD）
GOOD_WF = {
    "nodes": [
        {"id": "a", "action": "x"},
        {"id": "b", "action": "y", "depends": ["a"]},
    ]
}


# --------------------------------------------------------------------------
# eventbus.emit —— 快捷发布事件应送达订阅者
# --------------------------------------------------------------------------
def test_eventbus_emit_publishes_to_subscriber():
    old = os.environ.get("ACTUS_EVENTS_PERSIST")
    os.environ["ACTUS_EVENTS_PERSIST"] = "0"          # 测试不落盘
    et = "r113.unit.emit.test"
    bus = eventbus.get_event_bus()
    received = []
    cb = lambda e: received.append(e)                  # noqa: E731 - 测试桩
    bus.subscribe(et, cb)
    try:
        eventbus.emit(et, {"k": "v"}, "r113-test")
        assert len(received) == 1
        assert received[0].type == et
        assert received[0].data == {"k": "v"}
        assert received[0].source == "r113-test"
    finally:
        bus.unsubscribe(et, cb)
        if old is None:
            os.environ.pop("ACTUS_EVENTS_PERSIST", None)
        else:
            os.environ["ACTUS_EVENTS_PERSIST"] = old


# --------------------------------------------------------------------------
# intent.get_default_router —— 返回带默认 keyword_map 的路由器
# --------------------------------------------------------------------------
def test_intent_get_default_router_returns_wired_router():
    router = intent.get_default_router()
    assert isinstance(router, intent.IntentRouter)
    assert router._keyword_map == intent.DEFAULT_KEYWORD_MAP
    assert intent.DEFAULT_KEYWORD_MAP, "默认 keyword_map 不应为空"


# --------------------------------------------------------------------------
# webhook.start_webhook —— 便捷函数应接线 create_receiver + start + 返回接收器
# （mock start 避免真实绑定端口/阻塞；锁接线行为）
# --------------------------------------------------------------------------
def test_webhook_start_webhook_wires_receiver(monkeypatch):
    calls = []
    def fake_start(self):
        calls.append(1)
    monkeypatch.setattr(webhook.WebhookReceiver, "start", fake_start)

    receiver = webhook.start_webhook(host="127.0.0.1", port=9999, secret="s3cr3t")
    assert isinstance(receiver, webhook.WebhookReceiver)
    assert receiver._config.host == "127.0.0.1"
    assert receiver._config.port == 9999
    assert receiver._config.secret == "s3cr3t"
    assert calls == [1], "start_webhook 必须调用 receiver.start()"


# --------------------------------------------------------------------------
# viz.visualize_action_workflow —— 从 action_meta.workflow 渲染；无 workflow 回退
# --------------------------------------------------------------------------
def test_viz_visualize_action_workflow_renders():
    out = viz.visualize_action_workflow({"workflow": GOOD_WF}, format_="ascii")
    assert "a" in out and "b" in out


def test_viz_visualize_action_workflow_no_workflow():
    assert viz.visualize_action_workflow({}) == "(无工作流定义)"
    assert viz.visualize_action_workflow({"workflow": {}}) == "(无工作流定义)"


def test_viz_visualize_action_workflow_bad_format_raises():
    with pytest.raises(ValueError):
        viz.visualize_action_workflow({"workflow": GOOD_WF}, format_="zzz")
