"""
内存后端 — 轻量场景 / 测试用。

不持久化，进程退出即丢失。
状态机与 PG/SQLite 后端一致：
    PENDING（依赖未满足）→ READY → RUNNING → SUCCESS / FAILED
    失败可重试 → RETRY_PENDING（可被再次领取）；上游终态失败 → 下游级联 SKIPPED。
"""

__all__ = ['MemoryTaskBackend']

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from . import _dag



def _validate_backend_options(max_retries: Any, retry_delay_min: Any, what: str) -> None:
    """校验后端共有选项（BUG-429）。

    原实现零校验：``max_retries='x'`` 会让 ``fail()`` 里的
    ``retry_count >= max_retries`` 在运行期抛 TypeError；``max_retries=-1``
    被静默接受，使首次失败即终态（与 ``max_retries=0`` 语义重复且含义不明）；
    ``retry_delay_min=1.5`` 被接受但调度里按整数使用。
    """
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError(
            f"{what} 的 max_retries 需要整数，收到 "
            f"{type(max_retries).__name__}: {max_retries!r}")
    if max_retries < 0:
        raise ValueError(f"{what} 的 max_retries 不能为负，收到 {max_retries}")
    if isinstance(retry_delay_min, bool) or not isinstance(retry_delay_min, int):
        raise TypeError(
            f"{what} 的 retry_delay_min 需要整数，收到 "
            f"{type(retry_delay_min).__name__}: {retry_delay_min!r}")
    if retry_delay_min < 0:
        raise ValueError(f"{what} 的 retry_delay_min 不能为负，收到 {retry_delay_min}")


class MemoryTaskBackend:
    """内存任务队列后端（线程内使用，无锁）。

    Args:
        max_retries: 单任务最大重试次数（``fail`` 路径按此上限转 FAILED）。
        retry_delay_min: **当前仅为 API 兼容占位，不影响重试时序**——失败任务
            转 RETRY_PENDING 后立即可被再次领取，无退避等待（BUG-231，真实
            退避留作后续独立任务）。
    """

    def __init__(self, max_retries: int = 3, retry_delay_min: int = 5):
        # BUG-429: 入口校验（见 _validate_backend_options）
        _validate_backend_options(max_retries, retry_delay_min, "MemoryTaskBackend")

        self.max_retries = max_retries
        self.retry_delay_min = retry_delay_min
        self._tasks: Dict[int, Dict[str, Any]] = {}
        self._children: Dict[int, Set[int]] = {}
        self._seq = 0

    # ---------- 内部 ----------
    def _status_of(self, tid: int) -> str:
        t = self._tasks.get(tid)
        return t["status"] if t else "SUCCEEDED_MISSING"

    def _deps_of(self, tid: int) -> List[int]:
        t = self._tasks.get(tid)
        return list(t["dependencies"]) if t else []

    def _children_of(self, dep: int) -> List[int]:
        return list(self._children.get(dep, ()))

    def _set(self, tid: int, **fields):
        t = self._tasks.get(tid)
        if t is not None:
            t.update(fields)
            t["updated_at"] = datetime.utcnow()

    def _promote_and_skip(self, success_ids=(), failed_id=None):
        """成功点亮下游 READY；终态失败级联 SKIPPED。"""
        for cid in success_ids:
            for child in _dag.ready_after_success(
                    cid, self._deps_of, self._children_of, self._status_of):
                self._set(child, status="READY")
        if failed_id is not None:
            for child in _dag.skip_after_failure(
                    failed_id, self._children_of, self._status_of):
                self._set(child, status="SKIPPED", completed_at=datetime.utcnow())

    # ---------- 表 ----------
    def init_table(self, drop_if_exists: bool = False):
        if drop_if_exists:
            self._tasks.clear()
            self._children.clear()
            self._seq = 0

    # ---------- 提交 ----------
    def submit(self, task_name: str, payload: Optional[Dict[str, Any]] = None,
               task_type: Optional[str] = None, task_value: Optional[str] = None,
               priority: int = 0, max_retries: Optional[int] = None,
               dependencies: Optional[List[int]] = None) -> int:
        deps = [d for d in (dependencies or []) if d in self._tasks]
        self._seq += 1
        tid = self._seq
        now = datetime.utcnow()
        status = _dag.initial_status(deps, self._status_of)
        self._tasks[tid] = {
            "id": tid,
            "task_name": task_name,
            "task_type": task_type or "PYTHON",
            "task_value": task_value,
            "payload": payload,
            "status": status,
            "priority": priority,
            "retry_count": 0,
            "max_retries": max_retries if max_retries is not None else self.max_retries,
            "error_message": None,
            "back_info": None,
            "dependencies": deps,
            "worker_id": None,
            "locked_by": None,
            "lease_timeout": None,
            "ts": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
        }
        for d in deps:
            self._children.setdefault(d, set()).add(tid)
        return tid

    # ---------- 领取 ----------
    def acquire(self, worker_id: str, timeout_min: int = 5,
                states: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        # 依赖满足的任务在提交时即 READY；RETRY_PENDING 可被再次领取
        # BUG-255: 原 `states or [...]` 是假值陷阱——显式空列表（不领取任何
        # 状态）被替换为默认状态，会领走调用方明确排除的任务。
        if states is None:
            states = ["READY", "RETRY_PENDING"]
        now = datetime.utcnow()
        rank = {"READY": 0, "RETRY_PENDING": 1, "PENDING": 2}
        cands = sorted(
            (t for t in self._tasks.values()
             if t["status"] in states
             and (t["lease_timeout"] is None or t["lease_timeout"] < now)),
            key=lambda t: (rank.get(t["status"], 9), -t["priority"], t["id"]),
        )
        if not cands:
            return None
        t = cands[0]
        lease = now + timedelta(minutes=timeout_min)
        t.update(status="RUNNING", worker_id=worker_id, locked_by=worker_id,
                 lease_timeout=lease, ts=now, started_at=t.get("started_at") or now,
                 updated_at=now)
        return dict(t)

    def heartbeat(self, task_id: int, worker_id: str, timeout_min: int = 5):
        t = self._tasks.get(task_id)
        if t and t["worker_id"] == worker_id and t["status"] == "RUNNING":
            t["lease_timeout"] = datetime.utcnow() + timedelta(minutes=timeout_min)

    # ---------- 完成 / 失败 ----------
    def complete(self, task_id: int, worker_id: str, back_info: Optional[Dict[str, Any]] = None):
        t = self._tasks.get(task_id)
        if not t or t["worker_id"] != worker_id or t["status"] != "RUNNING":
            return
        now = datetime.utcnow()
        t.update(status="SUCCESS", back_info=back_info, completed_at=now,
                 lease_timeout=None, updated_at=now)
        self._promote_and_skip(success_ids=[task_id])

    def fail(self, task_id: int, worker_id: str, error: str):
        t = self._tasks.get(task_id)
        if not t or t["worker_id"] != worker_id or t["status"] != "RUNNING":
            return
        t["retry_count"] += 1
        t["error_message"] = error
        t["lease_timeout"] = None
        t["updated_at"] = datetime.utcnow()
        if t["retry_count"] >= t["max_retries"]:
            t["status"] = "FAILED"
            t["completed_at"] = datetime.utcnow()
            self._promote_and_skip(failed_id=task_id)
        else:
            t["status"] = "RETRY_PENDING"

    def retry(self, task_id: int):
        t = self._tasks.get(task_id)
        if t and t["status"] == "RETRY_PENDING":
            t["status"] = "READY"
            t["updated_at"] = datetime.utcnow()

    # ---------- 心跳 / 清理 ----------
    def clean_stale_locks(self, timeout_min: int = 10) -> int:
        """回收过期锁（worker 挂掉后把 RUNNING 任务重置为 RETRY_PENDING）。

        BUG-406: 原实现完全**忽略 timeout_min** 参数——只比较 lease_timeout
        是否过期。现按文档语义使用它：除「lease 已过期」外，还回收
        「RUNNING 但 lease_timeout 为空、且 updated_at 早于 timeout_min 分钟」
        的僵尸任务（worker 在 acquire 后、写 lease 前崩溃的情况，否则会永久
        卡在 RUNNING）。
        """
        if isinstance(timeout_min, bool) or not isinstance(timeout_min, (int, float)):
            raise TypeError(
                f"clean_stale_locks 的 timeout_min 需要数字（分钟），收到 "
                f"{type(timeout_min).__name__}: {timeout_min!r}")
        if timeout_min < 0:
            raise ValueError(f"clean_stale_locks 的 timeout_min 不能为负，收到 {timeout_min}")
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=timeout_min)
        n = 0
        for t in self._tasks.values():
            if t["status"] != "RUNNING":
                continue
            lease = t.get("lease_timeout")
            if (lease is not None and lease < now) or (
                    lease is None and t.get("updated_at") and t["updated_at"] < cutoff):
                t.update(status="RETRY_PENDING", worker_id=None, locked_by=None,
                         lease_timeout=None, updated_at=now)
                n += 1
        return n

    # ---------- 查询 ----------
    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        t = self._tasks.get(task_id)
        return dict(t) if t else None

    def query(self, sql: str = "", params: Optional[List[Any]] = None) -> List[tuple]:
        # 内存后端不支持 SQL；返回全部任务对象
        return list(self._tasks.values())

    def count_by_status(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for t in self._tasks.values():
            out[t["status"]] = out.get(t["status"], 0) + 1
        return out

    def is_all_done(self) -> bool:
        if not self._tasks:
            return True
        return all(t["status"] in _dag.TERMINAL_STATES for t in self._tasks.values())

    def close(self):
        pass
