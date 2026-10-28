"""eventbus.py —— 进程内事件总线 (Phase G1)。

驱动事件: action.completed / action.failed / trigger.fired /
          workflow.node_done / workflow.completed

订阅者通过 subscribe() 注册回调；发布事件通过 publish()。

MCP 通知: 订阅者 'mcp_notifier' 负责将事件通过 MCP Notification
         推送给已订阅的 AI 客户端。

事件流落盘（本轮新增，增量能力）
--------------------------------
**内存总线仍是主设计**：订阅/发布、`get_history()` 的语义一点没变。
这里只是额外把每条事件**追加**到 `<meta_dir>/events.jsonl`，解决一个结构性
空洞：`actus events` 每次都是新进程，纯内存历史必然为空，于是它**永远**打印
「暂无事件」还 rc=0 —— 用户分不清「真的没有事件」和「历史根本不落盘」。

落盘规则（best-effort，**不影响 publish() 的既有行为**）：
  * 追加写（`open(..., 'a')` + flush），不重写整个文件；失败只记信号不抛出；
  * 文件超过 `PERSIST_MAX_BYTES`（5MB）时轮转为最近 `PERSIST_KEEP_LINES` 行
    （原子替换），不会无限增长；
  * `ACTUS_EVENTS_PERSIST=0` 可整体关闭（性能敏感/测试场景）；
  * 读侧 `read_persisted_events()` 是**纯读**：文件不存在就返回 exists=False，
    **绝不创建文件**（`actus events` 是只读命令）。
"""

import json
import os
import time
import threading
import logging
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ── 事件流落盘（跨进程可读；best-effort，见模块 docstring）──
EVENTS_FILENAME = "events.jsonl"
PERSIST_MAX_BYTES = 5 * 1024 * 1024     # 5MB 上限，超过就轮转
PERSIST_KEEP_LINES = 2000               # 轮转后保留最近多少行


def events_path() -> str:
    """事件流文件路径：`paths.meta_dir()/events.jsonl`。

    走 `paths.meta_dir()` 这个单一真源（`ACTUS_META_DIR` 优先），
    与 records / cost / probe.cache 的位置口径一致。**只算路径，不建目录、不建文件。**
    """
    from .paths import meta_dir
    return os.path.join(meta_dir(), EVENTS_FILENAME)


def _persist_enabled() -> bool:
    """落盘开关：默认开；`ACTUS_EVENTS_PERSIST=0`（或 false/no/off）关闭。"""
    value = os.environ.get('ACTUS_EVENTS_PERSIST')
    if value is None:
        return True
    return value.strip().lower() not in ('0', 'false', 'no', 'off')


def read_persisted_events(limit: int = 50, event_type: str = None) -> dict:
    """读取落盘的事件流（**纯读：文件不存在不创建**）。

    返回 dict：
        path      —— 事件流文件路径
        exists    —— 文件是否存在（False = 从未有事件落盘）
        empty     —— 文件存在但里面没有任何可解析事件
        total     —— 可解析事件总数（未过滤）
        skipped   —— 无法解析被跳过的行数（损坏/半截行）
        events    —— 按 `event_type` 过滤并取**最后 limit 条**（最新）
        error     —— 读取失败时的原因（可选键）
    """
    path = events_path()
    result = {
        "path": path,
        "exists": os.path.exists(path),
        "empty": True,
        "total": 0,
        "skipped": 0,
        "events": [],
    }
    if not result["exists"]:
        return result

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        return result

    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            result["skipped"] += 1
            continue
        if not isinstance(record, dict):
            result["skipped"] += 1
            continue
        records.append(record)

    result["total"] = len(records)
    result["empty"] = len(records) == 0
    if event_type:
        records = [r for r in records if r.get("type") == event_type]
    if isinstance(limit, int) and limit > 0:
        records = records[-limit:]
    result["events"] = records
    return result


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
        # 落盘状态（best-effort，见模块 docstring「事件流落盘」）
        self._persist_lock = threading.Lock()
        self._persisted_bytes = None      # 懒加载：首次落盘时用文件现有大小初始化
        self._persisted_count = 0
        self._persist_failures = 0

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

        # 同步通知订阅者：**在锁内取一份快照**再遍历。
        # 旧实现在锁外直接 `get(event_type, [])` 拿到列表对象本身，若发布循环期间
        # 另一线程 `unsubscribe`（`subs.remove(cb)`）改同一列表，遍历会抛
        # `RuntimeError: list changed size during iteration`（2026-10-16 巡检）。
        with self._lock:
            subs = list(self._subscribers.get(event_type, []))
        for cb in subs:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"事件处理器异常: {e}")

        # 落盘（best-effort）：订阅/内存历史这些既有语义先跑完，落盘失败不影响它们
        self._persist(event)

    # ── 事件流落盘（增量能力，best-effort）──

    def _persist(self, event: "Event") -> None:
        """把事件追加到 `<meta_dir>/events.jsonl`。失败**只留信号，绝不抛出**。"""
        if not _persist_enabled():
            return
        try:
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            payload = line.encode("utf-8")
            path = events_path()
            with self._persist_lock:
                directory = os.path.dirname(path)
                if directory:
                    os.makedirs(directory, exist_ok=True)   # 仅在真正落盘时建目录
                self._rotate_if_needed(path, len(payload))
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
                self._persisted_bytes = (self._persisted_bytes or 0) + len(payload)
                self._persisted_count += 1
        except Exception as exc:                 # noqa: BLE001 - 落盘绝不影响发布
            self._persist_failures += 1
            # 不静默：前 3 次逐次告警，之后每 100 次告警一次（避免刷爆日志）
            if self._persist_failures <= 3 or self._persist_failures % 100 == 0:
                logger.warning(
                    "事件落盘失败（第 %d 次；事件仍在内存历史中，不影响 publish）: %s",
                    self._persist_failures, exc)

    def _rotate_if_needed(self, path: str, incoming_bytes: int) -> None:
        """events.jsonl 超上限时截断为最近 PERSIST_KEEP_LINES 行（原子替换）。

        追加型文件平时不重写，只在**跨过上限那一刻**付一次读+写代价。
        调用方（`_persist`）已持有 `_persist_lock`。
        """
        if self._persisted_bytes is None:
            try:
                self._persisted_bytes = os.path.getsize(path)
            except OSError:
                self._persisted_bytes = 0
        if self._persisted_bytes + incoming_bytes <= PERSIST_MAX_BYTES:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            self._persisted_bytes = 0        # 读不到就当空，后面 append 重建
            return

        kept = lines[-PERSIST_KEEP_LINES:]
        # 再按**字节**裁一遍：只按行数保留是不够的 —— 事件 data 很大时，
        # 保留的 2000 行本身就可能超过 MAX_BYTES，于是轮转后的文件仍超限，
        # 之后**每次 publish 都会触发一次全文件重写**（热路径灾难）。
        # 这里保证「保留量 ≤ MAX_BYTES」，至少留 1 行（单行超限时没办法再裁）。
        kept_bytes = sum(len(line.encode("utf-8")) for line in kept)
        while len(kept) > 1 and kept_bytes > PERSIST_MAX_BYTES:
            kept_bytes -= len(kept[0].encode("utf-8"))
            kept = kept[1:]

        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                handle.writelines(kept)
            os.replace(tmp_path, path)
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            self._persisted_bytes = 0
            return

        self._persisted_bytes = kept_bytes
        logger.info("事件流已轮转: 保留最近 %d 行（%d 字节）",
                    len(kept), self._persisted_bytes)

    def persistence_stats(self) -> dict:
        """落盘诊断快照（计数 + 开关 + 路径），供排障/测试用。"""
        return {
            "enabled": _persist_enabled(),
            "path": events_path(),
            "written": self._persisted_count,
            "failures": self._persist_failures,
            "bytes": self._persisted_bytes,
            "max_bytes": PERSIST_MAX_BYTES,
            "keep_lines": PERSIST_KEEP_LINES,
        }

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
    'EVENTS_FILENAME',
    'Event',
    'EventBus',
    'EventType',
    'emit',
    'events_path',
    'get_event_bus',
    'logger',
    'on',
    'read_persisted_events',
]
