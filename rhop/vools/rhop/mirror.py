"""vools.rhop.mirror - 镜像数据库（SQLite，双方共享 schema）

双方各持一份本地 SQLite，schema 完全一致；daemon 负责同步——本类只提供本地读写，不做网络操作。

Schema:
    tasks       — 任务主表（task_id 主键，乐观锁 version）
    events      — 状态变更事件流水
    sync_log    — 同步审计日志（push/pull 结果、字节数）

Q4 默认决策：信封 payload 大小不设硬上限，由传输层/外部通道限制兜底；
         大文件建议走独立通道（如 shared path 直接投文件，信封仅携带引用）。
Q5 默认决策：当前只支持一对一边；多工作地/多仓库通过多配置/多实例扩展。
"""

import json
import os
import sqlite3
import time
from typing import Dict, List, Optional

from .core import Side, TaskStatus
from .envelope import Envelope


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    side        TEXT NOT NULL,
    payload     TEXT,
    result      TEXT,
    error       TEXT,
    signature   TEXT,
    version     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    checksum    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    old_status   TEXT,
    new_status   TEXT,
    detail       TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    direction    TEXT NOT NULL,
    transport    TEXT NOT NULL,
    task_id      TEXT,
    success      INTEGER NOT NULL,
    error        TEXT,
    bytes_xfer   INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_sync_task  ON sync_log(task_id);
"""


class StaleVersionError(Exception):
    """乐观锁冲突：本地 version 高于或等于写入方。"""
    pass


class MirrorDB:
    """镜像数据库：双方各持一份，schema 完全一致。

    daemon 负责同步——本类只提供本地读写，不做网络操作。
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """初始化 schema（幂等）。"""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── 任务 CRUD ──

    def upsert_task(self, env: Envelope):
        """写入/更新任务（乐观锁：version 必须递增）。

        如果 task_id 已存在且本地 version >= 传入 version，抛 StaleVersionError。
        事件流水记录 'updated'。
        """
        now = _now_iso()
        cur = self._conn.execute(
            "SELECT version FROM tasks WHERE task_id = ?", (env.task_id,)
        )
        row = cur.fetchone()
        if row:
            if env.version <= row["version"]:
                raise StaleVersionError(
                    "task %s: local version %d, incoming %d" % (
                        env.task_id, row["version"], env.version))
        self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, status, side, payload, result, error, signature,
                version, created_at, updated_at, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (env.task_id, env.status.value, env.side.value,
             json.dumps(env.payload), json.dumps(env.result), env.error,
             env.signature, env.version, env.created_at, now, env.checksum)
        )
        self._conn.execute(
            "INSERT INTO events (task_id, event_type, old_status, new_status, created_at) "
            "VALUES (?, 'updated', NULL, ?, ?)",
            (env.task_id, env.status.value, now)
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> Optional[Envelope]:
        """读取单个任务（返回 Envelope 或 None）。"""
        cur = self._conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_envelope(row)

    def list_tasks(self, status=None, limit=50) -> List[Envelope]:
        """列出任务，可按状态过滤。"""
        if status is not None:
            if isinstance(status, TaskStatus):
                status = status.value
            cur = self._conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [_row_to_envelope(row) for row in cur.fetchall()]

    def update_status(self, task_id: str, new_status: TaskStatus,
                      result=None, error=None, signature=None):
        """更新任务状态（version + 1）。

        校验合法流转；不合法则抛 ValueError。
        事件流水记录 'status_changed'。
        """
        now = _now_iso()
        cur = self._conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("task not found: %s" % task_id)
        old_status = TaskStatus(row["status"])
        if not old_status.can_transition(new_status):
            raise ValueError(
                "illegal transition: %s -> %s for task %s" % (
                    old_status.value, new_status.value, task_id))
        new_version = row["version"] + 1
        self._conn.execute(
            "UPDATE tasks SET status=?, version=?, updated_at=?, result=?, error=?, signature=? "
            "WHERE task_id=?",
            (new_status.value, new_version, now,
             json.dumps(result) if result is not None else row["result"],
             error, signature, task_id)
        )
        self._conn.execute(
            "INSERT INTO events (task_id, event_type, old_status, new_status, created_at) "
            "VALUES (?, 'status_changed', ?, ?, ?)",
            (task_id, old_status.value, new_status.value, now)
        )
        self._conn.commit()

    def claim_task(self, worker_id: str, lock_timeout_sec=300) -> Optional[Envelope]:
        """任务端领任务：PENDING → CLAIMED。

        原子地领取一个 PENDING 任务并标记为 CLAIMED。
        返回 Envelope（含新状态）或 None（无 PENDING 任务）。
        """
        now = _now_iso()
        cur = self._conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC LIMIT 1",
            (TaskStatus.PENDING.value,)
        )
        row = cur.fetchone()
        if not row:
            return None
        task_id = row["task_id"]
        new_version = row["version"] + 1
        self._conn.execute(
            "UPDATE tasks SET status=?, version=?, updated_at=? WHERE task_id=?",
            (TaskStatus.CLAIMED.value, new_version, now, task_id)
        )
        self._conn.execute(
            "INSERT INTO events (task_id, event_type, old_status, new_status, detail, created_at) "
            "VALUES (?, 'status_changed', ?, ?, ?, ?)",
            (task_id, TaskStatus.PENDING.value, TaskStatus.CLAIMED.value,
             "worker=%s" % worker_id, now)
        )
        self._conn.commit()
        return self.get_task(task_id)

    def count_by_status(self) -> Dict[str, int]:
        """按状态统计任务数。"""
        cur = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        )
        return {row["status"]: row["n"] for row in cur.fetchall()}

    # ── 同步日志 ──

    def log_sync(self, direction: str, transport: str, task_id: str,
                 success: bool, error: str = None, bytes_xfer: int = 0):
        """记录同步日志。"""
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO sync_log (direction, transport, task_id, success, error, bytes_xfer, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (direction, transport, task_id, 1 if success else 0, error, bytes_xfer, now)
        )
        self._conn.commit()

    def pending_sync(self, since=None) -> List[dict]:
        """列出待同步的事件（用于 push 到对端）。

        since: ISO 时间戳，只返回此时间之后的事件。
        """
        if since:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE created_at > ? ORDER BY id ASC", (since,)
            )
        else:
            cur = self._conn.execute("SELECT * FROM events ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]

    def close(self):
        self._conn.close()


def _row_to_envelope(row) -> Envelope:
    """从 sqlite3.Row 构造 Envelope。"""
    return Envelope(
        task_id=row["task_id"],
        status=TaskStatus(row["status"]),
        payload=json.loads(row["payload"]) if row["payload"] else {},
        result=json.loads(row["result"]) if row["result"] else None,
        error=row["error"],
        side=Side(row["side"]),
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        checksum=row["checksum"],
    )


def _now_iso() -> str:
    """当前 UTC ISO 时间戳（Py3.6 兼容）。"""
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
