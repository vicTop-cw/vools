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

import pickle
import base64
import io
from enum import Enum
from typing import Optional, Any, Dict, Set
from datetime import datetime
import json

from ...core.dataclass_compat import dataclass, field
from ...core.datetime_compat import datetime_fromisoformat

# BUG-149: Task 的 args/kwargs/result 可能含不可 JSON 序列化对象
#（函数、自定义类实例等），无条件 json.dumps 会抛 TypeError，任务无法持久化。
# 这里统一用 pickle+base64 标记恢复，实在不行回退 repr 保证不崩溃。
_PICKLE_MARKER = "__vools_pickle__:"


class _SafeUnpickler(pickle.Unpickler):
    """BUG-207: 受限反序列化器，find_class 走白名单，杜绝 __reduce__ gadget RCE。

    仅允许恢复函数对象与常见标准库类型；os/subprocess/sys/__main__ 及一切
    未在白名单的全局一律拒绝，抛 UnpicklingError（_restore_pickle 捕获后按纯
    字符串回退，不执行任何 payload）。
    """

    _ALLOWED = {
        'builtins': {
            'function', 'globals', 'staticmethod', 'classmethod', 'object',
            'slice', 'complex', 'frozenset', 'set',
            # 异常层级（创建异常对象本身无害，构造参数为普通对象）
            'BaseException', 'Exception', 'ArithmeticError', 'LookupError',
            'ValueError', 'TypeError', 'KeyError', 'RuntimeError', 'AttributeError',
            'NotImplementedError', 'IndexError', 'NameError', 'OSError',
            'FileNotFoundError', 'PermissionError', 'StopIteration', 'ImportError',
            'ModuleNotFoundError', 'OverflowError', 'ZeroDivisionError',
            'UnicodeError', 'RecursionError', 'MemoryError', 'EOFError',
            'ConnectionError', 'BrokenPipeError', 'ReferenceError',
        },
        'datetime': {'datetime', 'date', 'time', 'timedelta', 'timezone'},
        'decimal': {'Decimal'},
        'uuid': {'UUID'},
        'collections': {'OrderedDict', 'defaultdict', 'deque', 'Counter'},
    }

    def find_class(self, module, name):
        allowed = self._ALLOWED.get(module)
        if allowed and name in allowed:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"forbidden global {module}.{name} in vools task payload (BUG-207)"
        )


def _safe_pickle_loads(data: bytes):
    """受限 pickle.loads，仅允许白名单全局（BUG-207）。"""
    return _SafeUnpickler(io.BytesIO(data)).load()


def _json_default(obj):
    """json.dumps 的 default 回调：不可 JSON 序列化 → pickle 编码为标记字符串"""
    try:
        payload = pickle.dumps(obj)
        return _PICKLE_MARKER + base64.b64encode(payload).decode("ascii")
    except Exception:
        try:
            return repr(obj)
        except Exception:
            return "<unserializable>"


def _restore_pickle(obj):
    """递归恢复 __vools_pickle__ 标记字符串为原始对象（BUG-207：受限反序列化）"""
    if isinstance(obj, str) and obj.startswith(_PICKLE_MARKER):
        try:
            return _safe_pickle_loads(
                base64.b64decode(obj[len(_PICKLE_MARKER):].encode("ascii"))
            )
        except Exception:
            return obj
    if isinstance(obj, list):
        return [_restore_pickle(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_restore_pickle(x) for x in obj)
    if isinstance(obj, dict):
        return {k: _restore_pickle(v) for k, v in obj.items()}
    return obj


def _dump_json(value):
    """JSON 序列化（带 pickle fallback），None 保留为 None"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _load_json(value):
    """JSON 反序列化（带 pickle 恢复）"""
    if not value:
        return None
    return _restore_pickle(json.loads(value))


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
            "payload": _dump_json(self.payload),
            "args": _dump_json(self.args),
            "kwargs": _dump_json(self.kwargs),
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result": _dump_json(self.result),
            "back_info": _dump_json(self.back_info),
            "ts": self.ts.isoformat() if self.ts else None,
            "dependencies": _dump_json(list(self.dependencies)),
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
            payload=_load_json(data.get("payload")),
            args=_load_json(data.get("args", "[]")),
            kwargs=_load_json(data.get("kwargs", "{}")),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            result=_load_json(data.get("result")),
            back_info=_load_json(data.get("back_info")),
            ts=datetime_fromisoformat(data["ts"]) if data.get("ts") else None,
            dependencies=set(_load_json(data.get("dependencies", "[]")) or []),
            created_at=datetime_fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime_fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            started_at=datetime_fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime_fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            worker_id=data.get("worker_id"),
            lease_timeout=datetime_fromisoformat(data["lease_timeout"]) if data.get("lease_timeout") else None,
            locked_by=data.get("locked_by"),
        )