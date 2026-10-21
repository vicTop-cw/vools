"""
SQLite 后端 — 与 PG/Memory 后端同构的持久化队列（单机多 Worker）。

自带与 pg.DEFAULT_PG_SCHEMA 对齐的表（含 task_type / payload / back_info /
dependencies），用线程锁 + BEGIN IMMEDIATE 保证领取原子性，不依赖旧版
TaskStorage（那套是 task_func/args/kwargs schema，服务于 TaskQueue/WorkerPool）。
"""

__all__ = ['SqliteTaskBackend']

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import _dag


class SqliteTaskBackend:
    """SQLite 任务队列后端。

    Args:
        db_path: SQLite 数据库文件路径。
        table: 主表名（边表为 ``<table>_edges``）。
        max_retries: 单任务最大重试次数。
        retry_delay_min: **当前仅为 API 兼容占位，不影响重试时序**——失败任务
            立即进入可领取状态，无退避等待（BUG-231）。
    """

    def __init__(self, db_path: str = "tasks_queue.db", table: str = "vic_tasks_task",
                 max_retries: int = 3, retry_delay_min: int = 5):
        self.db_path = db_path
        self.table = table
        self.edges = table + "_edges"
        self.max_retries = max_retries
        self.retry_delay_min = retry_delay_min
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_table()

    # ---------- 建表 ----------
    def _init_table(self):
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS "{t}" (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name     TEXT NOT NULL,
                    task_type     TEXT NOT NULL DEFAULT 'PYTHON',
                    task_value    TEXT,
                    payload       TEXT,
                    status        TEXT NOT NULL DEFAULT 'PENDING',
                    priority      INTEGER NOT NULL DEFAULT 0,
                    retry_count   INTEGER NOT NULL DEFAULT 0,
                    max_retries   INTEGER NOT NULL DEFAULT 3,
                    error_message TEXT,
                    back_info     TEXT,
                    dependencies  TEXT NOT NULL DEFAULT '[]',
                    worker_id     TEXT,
                    locked_by     TEXT,
                    lease_timeout TEXT,
                    ts            TEXT,
                    created_at    TEXT,
                    updated_at    TEXT,
                    started_at    TEXT,
                    completed_at  TEXT
                )
                """.format(t=self.table))
            self._conn.execute(
                'CREATE INDEX IF NOT EXISTS "idx_{t}_status" ON "{t}"(status)'
                .format(t=self.table))
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS "{e}" (
                    task_id       INTEGER NOT NULL,
                    depends_on_id INTEGER NOT NULL,
                    PRIMARY KEY (task_id, depends_on_id)
                )
                """.format(e=self.edges))
            self._conn.execute(
                'CREATE INDEX IF NOT EXISTS "idx_{e}_dep" ON "{e}"(depends_on_id)'
                .format(e=self.edges))

    def init_table(self, drop_if_exists: bool = False):
        with self._lock, self._conn:
            if drop_if_exists:
                self._conn.execute('DROP TABLE IF EXISTS "{e}"'.format(e=self.edges))
                self._conn.execute('DROP TABLE IF EXISTS "{t}"'.format(t=self.table))
        if drop_if_exists:
            self._init_table()

    # ---------- 工具 ----------
    @staticmethod
    def _now():
        return datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["payload"] = _loads(d.get("payload"))
        d["back_info"] = _loads(d.get("back_info"))
        d["dependencies"] = _loads(d.get("dependencies"), [])
        return d

    def _status_of(self, tid: int) -> str:
        cur = self._conn.execute(
            'SELECT status FROM "{t}" WHERE id=?'.format(t=self.table), (tid,))
        r = cur.fetchone()
        return r[0] if r else "SUCCESS"

    def _deps_of(self, tid: int) -> List[int]:
        cur = self._conn.execute(
            'SELECT depends_on_id FROM "{e}" WHERE task_id=? ORDER BY depends_on_id'
            .format(e=self.edges), (tid,))
        return [r[0] for r in cur.fetchall()]

    def _children_of(self, dep: int) -> List[int]:
        cur = self._conn.execute(
            'SELECT task_id FROM "{e}" WHERE depends_on_id=? ORDER BY task_id'
            .format(e=self.edges), (dep,))
        return [r[0] for r in cur.fetchall()]

    # ---------- 提交 ----------
    def submit(self, task_name: str, payload: Optional[Dict[str, Any]] = None,
               task_type: Optional[str] = None, task_value: Optional[str] = None,
               priority: int = 0, max_retries: Optional[int] = None,
               dependencies: Optional[List[int]] = None) -> int:
        deps = list(dict.fromkeys(dependencies or []))
        with self._lock, self._conn:
            # 只登记真实存在的依赖；初始状态依依赖是否全成功
            valid = []
            for d in deps:
                r = self._conn.execute(
                    'SELECT 1 FROM "{t}" WHERE id=?'.format(t=self.table), (d,)).fetchone()
                if r:
                    valid.append(d)
            status = _dag.initial_status(valid, self._status_of)
            now = self._now()
            cur = self._conn.execute(
                """
                INSERT INTO "{t}" (task_name, task_type, task_value, payload, status,
                    priority, max_retries, dependencies, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """.format(t=self.table),
                (task_name, task_type or "PYTHON", task_value,
                 json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                 status, priority,
                 max_retries if max_retries is not None else self.max_retries,
                 json.dumps(valid), now, now))
            tid = cur.lastrowid
            self._conn.executemany(
                'INSERT OR IGNORE INTO "{e}" (task_id, depends_on_id) VALUES (?,?)'
                .format(e=self.edges),
                [(tid, d) for d in valid])
        return tid

    # ---------- 领取 ----------
    def acquire(self, worker_id: str, timeout_min: int = 5,
                states: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        states = states or ["READY", "RETRY_PENDING"]
        order = ("CASE status WHEN 'READY' THEN 0 WHEN 'RETRY_PENDING' THEN 1 ELSE 2 END,"
                 " priority DESC, id")
        now = self._now()
        lease = (datetime.utcnow() + timedelta(minutes=timeout_min)
                 ).isoformat(sep=" ", timespec="seconds")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                qmarks = ",".join("?" for _ in states)
                row = self._conn.execute(
                    """
                    SELECT * FROM "{t}"
                    WHERE status IN ({s})
                      AND (lease_timeout IS NULL OR lease_timeout < ?)
                    ORDER BY {o} LIMIT 1
                    """.format(t=self.table, s=qmarks, o=order),
                    list(states) + [now]).fetchone()
                if not row:
                    self._conn.commit()
                    return None
                tid = row["id"]
                self._conn.execute(
                    """
                    UPDATE "{t}" SET status='RUNNING', worker_id=?, locked_by=?,
                        lease_timeout=?, ts=?, started_at=COALESCE(started_at, ?),
                        updated_at=? WHERE id=?
                    """.format(t=self.table),
                    (worker_id, worker_id, lease, now, now, now, tid))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.get(tid)

    def heartbeat(self, task_id: int, worker_id: str, timeout_min: int = 5):
        lease = (datetime.utcnow() + timedelta(minutes=timeout_min)
                 ).isoformat(sep=" ", timespec="seconds")
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE "{t}" SET lease_timeout=?, updated_at=?
                WHERE id=? AND worker_id=? AND status='RUNNING'
                """.format(t=self.table), (lease, self._now(), task_id, worker_id))

    # ---------- 完成 / 失败 ----------
    def complete(self, task_id: int, worker_id: str, back_info: Optional[Dict[str, Any]] = None):
        now = self._now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                UPDATE "{t}" SET status='SUCCESS', back_info=?, completed_at=?,
                    lease_timeout=NULL, updated_at=?
                WHERE id=? AND worker_id=? AND status='RUNNING'
                """.format(t=self.table),
                (json.dumps(back_info, ensure_ascii=False) if back_info is not None else None,
                 now, now, task_id, worker_id))
            if cur.rowcount:
                self._promote_successes([task_id])

    def fail(self, task_id: int, worker_id: str, error: str):
        now = self._now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                UPDATE "{t}" SET retry_count=retry_count+1, error_message=?,
                    lease_timeout=NULL, updated_at=?
                WHERE id=? AND worker_id=? AND status='RUNNING'
                """.format(t=self.table), (error, now, task_id, worker_id))
            if not cur.rowcount:
                return
            r = self._conn.execute(
                'SELECT retry_count, max_retries FROM "{t}" WHERE id=?'
                .format(t=self.table), (task_id,)).fetchone()
            retry_count, max_retries = r[0], r[1]
            if retry_count >= max_retries:
                self._conn.execute(
                    """
                    UPDATE "{t}" SET status='FAILED', completed_at=?, updated_at=?
                    WHERE id=?
                    """.format(t=self.table), (now, now, task_id))
                skipped = _dag.skip_after_failure(task_id, self._children_of, self._status_of)
                for cid in skipped:
                    self._conn.execute(
                        """
                        UPDATE "{t}" SET status='SKIPPED', completed_at=?, updated_at=?
                        WHERE id=?
                        """.format(t=self.table), (now, now, cid))
            else:
                self._conn.execute(
                    "UPDATE \"{t}\" SET status='RETRY_PENDING', updated_at=? WHERE id=?"
                    .format(t=self.table), (now, task_id))

    def retry(self, task_id: int):
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE "{t}" SET status='READY', updated_at=?
                WHERE id=? AND status='RETRY_PENDING'
                """.format(t=self.table), (self._now(), task_id))

    def _promote_successes(self, success_ids):
        for sid in success_ids:
            ready = _dag.ready_after_success(
                sid, self._deps_of, self._children_of, self._status_of)
            for cid in ready:
                self._conn.execute(
                    "UPDATE \"{t}\" SET status='READY', updated_at=? WHERE id=? AND status='PENDING'"
                    .format(t=self.table), (self._now(), cid))

    # ---------- 清理 ----------
    def clean_stale_locks(self, timeout_min: int = 10) -> int:
        now = self._now()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                UPDATE "{t}" SET status='RETRY_PENDING', worker_id=NULL, locked_by=NULL,
                    lease_timeout=NULL, updated_at=?
                WHERE status='RUNNING' AND lease_timeout IS NOT NULL AND lease_timeout < ?
                """.format(t=self.table), (now, now))
            return cur.rowcount

    # ---------- 查询 ----------
    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._conn:
            row = self._conn.execute(
                'SELECT * FROM "{t}" WHERE id=?'.format(t=self.table), (task_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def query(self, sql: str = "", params: Optional[List[Any]] = None) -> List[tuple]:
        with self._lock, self._conn:
            cur = self._conn.execute(
                sql or 'SELECT * FROM "{t}" ORDER BY id'.format(t=self.table),
                params or [])
            return cur.fetchall()

    def count_by_status(self) -> Dict[str, int]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                'SELECT status, COUNT(*) FROM "{t}" GROUP BY status'.format(t=self.table)
            ).fetchall()
            return {r[0]: r[1] for r in rows}

    def is_all_done(self) -> bool:
        qmarks = ",".join("?" for _ in _dag.TERMINAL_STATES)
        with self._lock, self._conn:
            n = self._conn.execute(
                'SELECT COUNT(*) FROM "{t}" WHERE status NOT IN ({s})'
                .format(t=self.table, s=qmarks),
                list(_dag.TERMINAL_STATES)).fetchone()[0]
            return n == 0

    def close(self):
        with self._lock:
            self._conn.close()


def _loads(v, default=None):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v
