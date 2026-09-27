"""WebhookServer — 触发器引擎的 HTTP 端点 executor。

包装已有的 WebhookReceiver（webhook.py）为 TriggerEngine 标准接口
（add/remove/start/stop/status），与 CronScheduler / FileWatcher /
HotkeyListener 对齐。

设计：
- 多个 webhook trigger 共享一个 HTTP 端口（默认 8765），
  按 trigger.key（event_type）路由到对应 action；
- trigger.method 默认 POST，trigger.args 作为事件 payload；
- HMAC 签名 / IP 白名单 / 速率限制由 WebhookReceiver 已有能力处理；
- 零新增第三方依赖（stdlib http.server）。
"""

__all__ = ['WebhookServer']

import threading
from typing import Callable, Dict, List, Optional

from .triggers import Trigger
from .webhook import WebhookConfig, WebhookReceiver


class WebhookServer:
    """Webhook 触发器执行器（TriggerEngine 标准接口）。

    多个 trigger 共享一个 WebhookReceiver 实例，按 event_type 路由。
    """

    def __init__(self, port: int = 8765, host: str = '0.0.0.0',
                 secret: str = ''):
        self._port = port
        self._host = host
        self._secret = secret
        self._receiver: Optional[WebhookReceiver] = None
        self._routes: Dict[str, Trigger] = {}  # event_type -> trigger
        self._callbacks: Dict[str, Callable] = {}
        self._running = False
        self._lock = threading.Lock()

    def add(self, trigger: Trigger, callback: Callable):
        """注册 webhook 触发器。event_type = trigger.key。"""
        event_type = trigger.key or trigger.action_id
        with self._lock:
            self._routes[event_type] = trigger
            self._callbacks[event_type] = callback
            if self._receiver is not None:
                self._receiver.register_route(event_type, event_type)

    def remove(self, action_id: str):
        """移除指定 action 的所有 webhook 触发器。"""
        with self._lock:
            to_remove = [et for et, t in self._routes.items()
                        if t.action_id == action_id]
            for et in to_remove:
                del self._routes[et]
                del self._callbacks[et]
                if self._receiver is not None:
                    self._receiver.unregister_route(et)

    def start(self):
        """启动 HTTP 服务器（幂等）。"""
        if self._running:
            return
        config = WebhookConfig(
            host=self._host, port=self._port,
            secret=self._secret, require_signature=bool(self._secret),
        )
        self._receiver = WebhookReceiver(config)
        # 注册所有路由
        with self._lock:
            for et in self._routes:
                self._receiver.register_route(et, et)
        # 包装回调：WebhookReceiver 的路由解析后调用我们注册的 callback
        self._receiver._fallback_action_id = None
        # 覆盖 _dispatch_action：用我们的 callbacks 代替 execute_action
        receiver = self._receiver

        def _patched_dispatch(action_id, event_type, payload):
            with self._lock:
                # action_id 来自 resolve_action，是 event_type 或 payload.event
                # 我们的路由按 trigger.key 注册，需要找到对应的 callback
                cb = self._callbacks.get(action_id)
                trigger = self._routes.get(action_id)
                if not cb:
                    # 降级：遍历 routes 找匹配的 callback
                    for et, t in self._routes.items():
                        if t.action_id == action_id:
                            cb = self._callbacks.get(et)
                            trigger = t
                            break
            if cb and trigger:
                threading.Thread(
                    target=_safe_call, args=(cb, trigger, payload),
                    daemon=True).start()

        receiver._dispatch_action = _patched_dispatch
        self._receiver.start_background()
        self._running = True

    def stop(self):
        """停止 HTTP 服务器。"""
        if self._receiver is not None:
            self._receiver.stop()
        self._running = False
        with self._lock:
            self._routes.clear()
            self._callbacks.clear()

    def status(self) -> dict:
        """返回状态摘要。"""
        with self._lock:
            routes = dict(self._routes)
        stats = {}
        if self._receiver is not None:
            # stats 是 @property（webhook.py:170），原先写成 self._receiver.stats() ——
            # 必然 TypeError，又被下面的 except-pass 吞掉，于是运行统计在 status() 里
            # 恒缺且无人报错。这里不再兜异常：读不到就让它响，别再静默降级。
            stats = self._receiver.stats.to_dict()
        return {
            'webhooks': len(routes),
            'port': self._port,
            'running': self._running,
            'routes': {et: t.action_id for et, t in routes.items()},
            **stats,
        }


def _safe_call(callback: Callable, trigger: Trigger, payload: dict = None):
    """安全执行回调（与 cron/watch/hotkey 一致：异常不传播）。"""
    try:
        callback(trigger)
    except Exception:
        pass
