"""
任务数据模型和状态定义

状态机（补齐后对齐 look_upon 能力面）：
    PENDING → READY → RUNNING → SUCCESS
       ↑        ↑        │  │
       │        └────────┤  ├→ RETRY_PENDING → READY
       │                 │  └→ FAILED
       └─────────────────┴──→ SKIPPED (上游失败)
                           └→ CANCEL

LOCKED 是 Worker 竞争中间态（领取瞬间），心跳续期防重复领取。
"""

__all__ = ['TaskStatus', 'Task', 'DagValidationError']

from enum import Enum
from typing import Optional, Any, Dict, Set
from datetime import datetime
import json

from ...core.dataclass_compat import dataclass, field
from ...core.datetime_compat import datetime_fromisoformat


class DagValidationError(Exception):
    """DAG 验证异常（循环依赖等）"""
    pass


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "PENDING"          # 等待处理
    READY = "READY"              # 依赖已满足，可调度
    LOCKED = "LOCKED"            # Worker 领取中（瞬间态）
    RUNNING = "RUNNING"          # 正在处理
    RETRYING = "RETRYING"        # 重试中（保留兼容）
    RETRY_PENDING = "RETRY_PENDING"  # 失败等待重试（look_upon 兼容）
    FAILED = "FAILED"            # 失败
    SUCCESS = "SUCCESS"          # 成功
    COMPLETED = "COMPLETED"      # 已完成（look_upon 兼容）
    SKIPPED = "SKIPPED"          # 因上游失败被跳过
    CANCEL = "CANCEL"            # 已取消


@dataclass
class Task:
    """任务数据模型"""
    id: Optional[int] = None
    task_name: str = ""
    task_func: str = ""            # pickled 函数（函数任务）
    task_type: str = "PYTHON"      # PYTHON | CLI | SQL | SCALA | SHELL ...（look_upon 兼容，无枚举限制）
    payload: Optional[Dict[str, Any]] = None  # 结构化 payload（含 cli / sql / fn 等子 dict）
    args: list = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Any = None
    back_info: Optional[Dict[str, Any]] = None  # 执行结果回写（look_upon 兼容）
    ts: Optional[datetime] = None  # 领任务时间（look_upon 兼容）

    def __getstate__(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
    def __setstate__(self, state):
        for k, v in state.items():
            setattr(self, k, v)

    dependencies: Set[int] = field(default_factory=set)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    lease_timeout: Optional[datetime] = None
    locked_by: Optional[str] = None  # 抢占 Worker ID（look_upon 兼容）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "task_name": self.task_name,
            "task_func": self.task_func,
            "task_type": self.task_type,
            "payload": json.dumps(self.payload, ensure_ascii=False) if self.payload is not None else None,
            "args": json.dumps(self.args),
            "kwargs": json.dumps(self.kwargs),
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result": json.dumps(self.result, ensure_ascii=False) if self.result is not None else None,
            "back_info": json.dumps(self.back_info, ensure_ascii=False) if self.back_info is not None else None,
            "ts": self.ts.isoformat() if self.ts else None,
            "dependencies": json.dumps(list(self.dependencies)),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "worker_id": self.worker_id,
            "lease_timeout": self.lease_timeout.isoformat() if self.lease_timeout else None,
            "locked_by": self.locked_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """从字典创建任务"""
        return cls(
            id=data.get("id"),
            task_name=data.get("task_name", ""),
            task_func=data.get("task_func", ""),
            task_type=data.get("task_type", "PYTHON"),
            payload=json.loads(data["payload"]) if data.get("payload") else None,
            args=json.loads(data.get("args", "[]")),
            kwargs=json.loads(data.get("kwargs", "{}")),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            result=json.loads(data.get("result")) if data.get("result") else None,
            back_info=json.loads(data.get("back_info")) if data.get("back_info") else None,
            ts=datetime_fromisoformat(data["ts"]) if data.get("ts") else None,
            dependencies=set(json.loads(data.get("dependencies", "[]"))),
            created_at=datetime_fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime_fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            started_at=datetime_fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime_fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            worker_id=data.get("worker_id"),
            lease_timeout=datetime_fromisoformat(data["lease_timeout"]) if data.get("lease_timeout") else None,
            locked_by=data.get("locked_by"),
        )