"""eventbus.py —— 进程内事件总线 (Phase G1)。

驱动事件: action.completed / action.failed / trigger.fired /
          workflow.node_done / workflow.completed

订阅者通过 subscribe() 注册回调；发布事件通过 publish()。

MCP 通知: 订阅者 'mcp_notifier' 负责将事件通过 MCP Notification
         推送给已订阅的 AI 客户端。
"""

import time
import threading
import logging
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class Event:
    """事件对象。"""

    def __init__(self, type: str, data: dict, source: str = ""):
        self.type = type
        self.data = data
        self.source = source
        self.timestamp = time.time()
        self.id = f"{type}-{int(self.timestamp * 1000)}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class EventBus:
    """进程内事件总线。

    支持订阅/发布模式，线程安全。
    """

    def __init__(self, history_limit: int = 1000):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[Event] = []
        self._history_limit = history_limit
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件类型。

        Args:
            event_type: 事件类型, 如 'action.completed'
            callback: 回调函数, 接收 Event 对象
        """
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)
        logger.debug(f"订阅事件: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable):
        """取消订阅。"""
        with self._lock:
            subs = self._subscribers.get(event_type, [])
            if callback in subs:
                subs.remove(callback)

    def publish(self, event_type: str, data: dict, source: str = ""):
        """发布事件到所有订阅者。

        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源标识
        """
        event = Event(type=event_type, data=data, source=source)

        with self._lock:
            self._history.append(event)
            # 裁剪历史
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]

        # 异步通知订阅者
        subs = self._subscribers.get(event_type, [])
        for cb in subs:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"事件处理器异常: {e}")

    def get_history(self, event_type: str = None, limit: int = 100) -> List[dict]:
        """获取事件历史。"""
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e.type == event_type]
            return [e.to_dict() for e in events[-limit:]]

    def clear_history(self):
        """清空历史。"""
        with self._lock:
            self._history.clear()

    def subscriber_count(self, event_type: str = None) -> int:
        """获取订阅者数量。"""
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(s) for s in self._subscribers.values())


# 单例
_bus = EventBus()


def get_event_bus() -> EventBus:
    """获取全局事件总线。"""
    return _bus


# ── 事件类型常量 ──

class EventType:
    """事件类型常量。"""

    # 动作生命周期
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    ACTION_FAILED = "action.failed"
    ACTION_CANCELLED = "action.cancelled"

    # 触发器
    TRIGGER_FIRED = "trigger.fired"
    TRIGGER_REGISTERED = "trigger.registered"
    TRIGGER_UNREGISTERED = "trigger.unregistered"

    # 工作流
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_NODE_STARTED = "workflow.node_started"
    WORKFLOW_NODE_DONE = "workflow.node_done"
    WORKFLOW_NODE_FAILED = "workflow.node_failed"
    WORKFLOW_NODE_SKIPPED = "workflow.node_skipped"

    # 依赖
    DEPENDENCY_RESOLVED = "dependency.resolved"
    DEPENDENCY_FAILED = "dependency.failed"

    # Vault
    SECRET_SET = "secret.set"
    SECRET_REVOKED = "secret.revoked"

    # 市场
    ACTION_INSTALLED = "action.installed"
    ACTION_UPDATED = "action.updated"


def emit(event_type: str, data: dict, source: str = ""):
    """快捷发布事件。"""
    get_event_bus().publish(event_type, data, source)


def on(event_type: str, callback: Callable):
    """快捷订阅事件。"""
    get_event_bus().subscribe(event_type, callback)


__all__ = [
    'Event',
    'EventBus',
    'EventType',
    'emit',
    'get_event_bus',
    'logger',
    'on'
]
