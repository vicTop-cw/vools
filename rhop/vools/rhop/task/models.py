"""vools.rhop.task.models - 任务队列通用模型（状态机 + 任务记录）

对齐 vools.pyk.look_upon 的表结构与状态流转，但去掉 P0..P3 跳板角色：
队列只认「方向（A 提交 / B 执行 / C 中转）+ 配置」，任务身份用 ``task_name``，
依赖用 ``task_name`` 列表表达（而不是自增 ``task_id``）。这样三种拓扑
（单一共享库 / 双方各自持库后同步收敛 / 后续 PostgreSQL 后端）能用同一份依赖语义。

本模块只用标准库，Py3.6 兼容（不用 dataclasses、不用 datetime.fromisoformat）。
"""

from __future__ import absolute_import

import datetime
import json
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 时间辅助：统一 UTC ISO（秒精度，字符串可直接按字典序比较）
# ---------------------------------------------------------------------------

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime.datetime:
    """当前 UTC 时间（tz-aware，避开 datetime.utcnow() 的弃用告警）。"""
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO 文本（形如 2026-10-21T11:02:50Z）。"""
    return utcnow().strftime(ISO_FORMAT)


def iso_add_seconds(base_iso: str, seconds: float) -> str:
    """在 ISO 文本上加若干秒，返回同格式 ISO 文本。

    Args:
        base_iso: ``utcnow_iso()`` 形态的 UTC 文本；空值以当前时间兜底。
        seconds:  偏移秒数（可为负）。

    Returns:
        str: 同格式 UTC ISO 文本。
    """
    base = parse_iso(base_iso) or utcnow()
    return (base + datetime.timedelta(seconds=float(seconds))).strftime(ISO_FORMAT)


def parse_iso(value: Any) -> Optional[datetime.datetime]:
    """把多种时间写法解析为 tz-aware UTC datetime，解析失败返回 None。

    兼容：``2026-10-21T11:02:50Z`` / 带微秒 / 空格分隔 / epoch 秒。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
    text = str(value).strip()
    candidates = (
        ISO_FORMAT,
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in candidates:
        try:
            return datetime.datetime.strptime(text, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.datetime.fromtimestamp(float(text), datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def to_iso(value: Any) -> Optional[str]:
    """把任意可识别时间写法归一为 ISO 文本；无法识别返回 None。"""
    dt = parse_iso(value)
    return dt.strftime(ISO_FORMAT) if dt is not None else None


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------

class TaskState(object):
    """任务状态常量（字符串，Py3.6 兼容；不用 Enum，便于直接落库与进 JSON）。

    流转（参考 look_upon §2，去掉跳板角色相关语义）::

        PENDING ──claim──▶ LOCKED ──start──▶ RUNNING ──ok──▶ COMPLETED
           ▲                  │                 │
           │               释放/超时            ├─retry(未超限)─▶ RETRY_PENDING ─▶ LOCKED
           └──────────────────┘                 └─retry 超限──▶ FAILED
        PENDING / LOCKED / RUNNING ──cancel──▶ CANCELLED
    """

    PENDING = "PENDING"
    LOCKED = "LOCKED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    CANCELLED = "CANCELLED"

    #: 全部合法状态
    ALL = (PENDING, LOCKED, RUNNING, COMPLETED, FAILED, RETRY_PENDING, CANCELLED)
    #: 非终态（"还有事没做完"，驱动 is_all_done 判断）
    ACTIVE = (PENDING, LOCKED, RUNNING, RETRY_PENDING)
    #: 可被 worker 领取的状态
    CLAIMABLE = (PENDING, RETRY_PENDING)
    #: 终态
    TERMINAL = (COMPLETED, FAILED, CANCELLED)

    @classmethod
    def normalize(cls, value: Any) -> str:
        """大小写不敏感地归一状态值；非法值抛 ValueError。"""
        if value is None:
            raise ValueError("状态不能为空")
        text = str(value).strip().upper()
        if text not in cls.ALL:
            raise ValueError(
                "未知任务状态 %r（可用: %s）" % (value, ", ".join(cls.ALL))
            )
        return text

    @classmethod
    def is_valid(cls, value: Any) -> bool:
        """是否是合法状态值。"""
        try:
            cls.normalize(value)
            return True
        except ValueError:
            return False

    @classmethod
    def is_terminal(cls, value: Any) -> bool:
        """是否终态（COMPLETED / FAILED / CANCELLED）。"""
        return value in cls.TERMINAL

    @classmethod
    def can_transition(cls, old: Any, new: Any) -> bool:
        """判断状态流转是否合法。"""
        try:
            old_s = cls.normalize(old)
            new_s = cls.normalize(new)
        except ValueError:
            return False
        return new_s in _TRANSITIONS.get(old_s, set())


#: 模块级流转表（类体里放可变 dict 易被误读，放模块级更清晰）
_TRANSITIONS = {
    TaskState.PENDING: {TaskState.LOCKED, TaskState.CANCELLED},
    TaskState.LOCKED: {TaskState.RUNNING, TaskState.PENDING, TaskState.CANCELLED},
    TaskState.RUNNING: {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.RETRY_PENDING,
        TaskState.CANCELLED,
    },
    TaskState.RETRY_PENDING: {TaskState.LOCKED, TaskState.CANCELLED},
    # 终态默认不可流转；运维侧重跑走 force=True（见 SqliteTaskStore.set_state）
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


# ---------------------------------------------------------------------------
# 任务记录
# ---------------------------------------------------------------------------

#: 任务表列顺序（store 层与 TaskRecord 共用，保证 INSERT/SELECT 一致）
TASK_COLUMNS = (
    "task_id",
    "task_name",
    "task_type",
    "value",
    "deps",
    "state",
    "priority",
    "timeout_min",
    "retry_delay_min",
    "retry_count",
    "max_retries",
    "scheduled_at",
    "worker_id",
    "lock_time",
    "expire_time",
    "start_time",
    "end_time",
    "cancel_requested",
    "version",
    "payload_enc",
    "payload_sha",
    "back_info",
    "last_err",
    "tags",
    "queue",
    "owner",
    "team",
    "group_name",
    "extra_desc",
    "created_at",
    "updated_at",
)

#: 由 add_tasks/submit 写入的定义型字段（不含运行时状态字段）
DEFINITION_FIELDS = (
    "task_type",
    "value",
    "deps",
    "priority",
    "timeout_min",
    "retry_delay_min",
    "max_retries",
    "scheduled_at",
    "payload_enc",
    "payload_sha",
    "tags",
    "queue",
    "owner",
    "team",
    "group_name",
    "extra_desc",
)


def _as_json_list(value: Any) -> List[Any]:
    """把 deps/tags 统一成 list（兼容 None / JSON 文本 / 已解析 list）。"""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = [value]
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
        return [parsed]
    return [value]


class TaskRecord(object):
    """一条任务记录（与任务表列一一对应）。

    Attributes:
        task_name:     任务身份（唯一键，幂等与依赖引用都用它）
        value:         任务原始参数。**存储为 TEXT**（对齐 look_upon 的 VARCHAR(200)），
                       因此数字/布尔写进去再读出来是文本形态；结构化参数请放 payload。
        deps:          依赖的 **task_name 列表**
        state:         TaskState 之一
        payload_enc:   加密后的 JSON 指令载荷（"A 给 B 传的加密 JSON"）
        payload_sha:   明文载荷的 sha256（解密后校验完整性/幂等）
        back_info:     执行结果（JSON 文本；encrypt_result=true 时是密文）
        version:       乐观锁版本（同步收敛时判新旧）
    """

    def __init__(self, **kwargs):
        self.task_id = kwargs.get("task_id")
        self.task_name = str(kwargs.get("task_name") or "").strip()
        self.task_type = str(kwargs.get("task_type") or "CLI")
        self.value = kwargs.get("value")
        self.deps = [str(x) for x in _as_json_list(kwargs.get("deps"))]
        self.state = kwargs.get("state") or TaskState.PENDING
        self.priority = int(kwargs.get("priority") or 0)
        self.timeout_min = float(kwargs.get("timeout_min") if kwargs.get("timeout_min") is not None else 60)
        self.retry_delay_min = float(kwargs.get("retry_delay_min") if kwargs.get("retry_delay_min") is not None else 5)
        self.retry_count = int(kwargs.get("retry_count") or 0)
        self.max_retries = int(kwargs.get("max_retries") if kwargs.get("max_retries") is not None else 3)
        self.scheduled_at = kwargs.get("scheduled_at")
        self.worker_id = kwargs.get("worker_id")
        self.lock_time = kwargs.get("lock_time")
        self.expire_time = kwargs.get("expire_time")
        self.start_time = kwargs.get("start_time")
        self.end_time = kwargs.get("end_time")
        self.cancel_requested = bool(kwargs.get("cancel_requested"))
        self.version = int(kwargs.get("version") or 1)
        self.payload_enc = kwargs.get("payload_enc")
        self.payload_sha = kwargs.get("payload_sha")
        self.back_info = kwargs.get("back_info")
        self.last_err = kwargs.get("last_err")
        self.tags = _as_json_list(kwargs.get("tags"))
        self.queue = str(kwargs.get("queue") or "")
        self.owner = str(kwargs.get("owner") or "")
        self.team = str(kwargs.get("team") or "")
        self.group_name = str(kwargs.get("group_name") or "")
        self.extra_desc = kwargs.get("extra_desc")
        self.created_at = kwargs.get("created_at")
        self.updated_at = kwargs.get("updated_at")

    # ---- 协议 ----

    def __repr__(self):
        return "<TaskRecord {0} {1} deps={2}>".format(
            self.task_name, self.state, self.deps
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为 dict（deps/tags 为 list，cancel_requested 为 bool）。"""
        return {name: getattr(self, name) for name in TASK_COLUMNS}

    def to_row(self) -> Dict[str, Any]:
        """导出为「可直接写库」的 dict（deps/tags 转 JSON 文本，bool 转 int）。"""
        row = self.to_dict()
        row["deps"] = json.dumps(self.deps, ensure_ascii=False)
        row["tags"] = json.dumps(self.tags, ensure_ascii=False)
        row["cancel_requested"] = 1 if self.cancel_requested else 0
        return row

    @classmethod
    def from_row(cls, row: Any) -> "TaskRecord":
        """从 sqlite3.Row / dict 构造（deps/tags 自动解析 JSON）。"""
        try:
            data = dict(row)
        except (TypeError, ValueError):
            data = row
        return cls(**{k: v for k, v in data.items() if k in TASK_COLUMNS})

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        """从 dict 构造（容忍额外字段）。"""
        return cls(**{k: v for k, v in (data or {}).items() if k in TASK_COLUMNS})

    def is_terminal(self) -> bool:
        """是否终态。"""
        return TaskState.is_terminal(self.state)


__all__ = [
    "ISO_FORMAT",
    "TASK_COLUMNS",
    "DEFINITION_FIELDS",
    "TaskState",
    "TaskRecord",
    "utcnow",
    "utcnow_iso",
    "iso_add_seconds",
    "parse_iso",
    "to_iso",
]