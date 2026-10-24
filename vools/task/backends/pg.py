"""
PG 后端 — 对标 look_upon 的多 Worker 竞争队列。

用 PostgreSQL 表作为持久化队列，支持：
    - 多 Worker 竞争（SELECT ... FOR UPDATE SKIP LOCKED）
    - 状态机（PENDING → READY → RUNNING → SUCCESS / FAILED / RETRY_PENDING）
    - 心跳 / 租约续期（clean_stale_locks）
    - 结构化 payload（JSONB）
    - DAG 依赖（dependencies JSONB）
    - 结果回写（back_info JSONB）

依赖：psycopg2（生产 p2/p3 已打包 whl）。
"""

__all__ = ['PgTaskBackend', 'DEFAULT_PG_SCHEMA']

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import _dag

logger = logging.getLogger(__name__)

# ============================================================
# 默认建表 SQL（对标 look_upon 的 32 列能力面）
# ============================================================
DEFAULT_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id            BIGSERIAL PRIMARY KEY,
    task_name     VARCHAR(255) NOT NULL,
    task_type     VARCHAR(32) NOT NULL DEFAULT 'PYTHON',
    task_value    VARCHAR(255),
    payload       JSONB,
    status        VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    priority      INTEGER NOT NULL DEFAULT 0,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    max_retries   INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    back_info     JSONB,
    dependencies  JSONB NOT NULL DEFAULT '[]',
    worker_id     VARCHAR(128),
    locked_by     VARCHAR(128),
    lease_timeout TIMESTAMP,
    ts            TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at    TIMESTAMP,
    completed_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_{table}_status ON {table}(status);
CREATE INDEX IF NOT EXISTS idx_{table}_priority ON {table}(priority DESC);
"""


class PgTaskBackend:
    """PG 任务队列后端。

    用法：
        backend = PgTaskBackend(dsn, table="vic_tasks_task")
        backend.init_table()
        tid = backend.submit("my_task", {"cli": {"cmd": "echo hello"}})
        task = backend.acquire(worker_id="w1", timeout_min=5)
        ...
        backend.complete(tid, worker_id="w1", back_info={"stdout": "hello"})

    Args:
        dsn: PostgreSQL 连接串。
        table: 主表名。
        max_retries: 单任务最大重试次数。
        retry_delay_min: **当前仅为 API 兼容占位，不影响重试时序**——失败任务
            立即进入可领取状态，无退避等待（BUG-231）。
        autocommit: 是否自动提交事务。
    """

    def __init__(self, dsn: str, table: str = "vic_tasks_task",
                 max_retries: int = 3, retry_delay_min: int = 5,
                 autocommit: bool = True):
        # BUG-428: 原实现零校验——dsn=123 / table=123 / max_retries=-1 /
        # retry_delay_min='x' 全部被接受，错误直到真正连库/发 SQL 才暴露
        # （天书），且 max_retries 为负会让 fail() 的重试判断出现反向语义。
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError(
                f"PgTaskBackend 的 dsn 需要非空字符串，收到 "
                f"{type(dsn).__name__}: {dsn!r}")
        if not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"PgTaskBackend 的 table 需要非空字符串，收到 "
                f"{type(table).__name__}: {table!r}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError(
                f"PgTaskBackend 的 max_retries 需要整数，收到 "
                f"{type(max_retries).__name__}: {max_retries!r}")
        if max_retries < 0:
            raise ValueError(f"PgTaskBackend 的 max_retries 不能为负，收到 {max_retries}")
        if isinstance(retry_delay_min, bool) or not isinstance(retry_delay_min, int):
            raise TypeError(
                f"PgTaskBackend 的 retry_delay_min 需要整数，收到 "
                f"{type(retry_delay_min).__name__}: {retry_delay_min!r}")
        if retry_delay_min < 0:
            raise ValueError(
                f"PgTaskBackend 的 retry_delay_min 不能为负，收到 {retry_delay_min}")
        if not isinstance(autocommit, bool):
            raise TypeError(
                f"PgTaskBackend 的 autocommit 需要 bool，收到 "
                f"{type(autocommit).__name__}: {autocommit!r}")

        self.dsn = dsn
        self.table = table
        self.max_retries = max_retries
        self.retry_delay_min = retry_delay_min
        self.autocommit = autocommit
        self._conn = None

    # ---------- 连接 ----------
    def _connect(self):
        import psycopg2
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = self.autocommit
        return self._conn

    def _cursor(self):
        return self._connect().cursor()

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
        self._conn = None

    # ---------- 表 ----------
    def init_table(self, drop_if_exists: bool = False):
        """创建表（可先 DROP）。"""
        conn = self._connect()
        cur = conn.cursor()
        if drop_if_exists:
            cur.execute('DROP TABLE IF EXISTS "%s"' % self.table)
        cur.execute(DEFAULT_PG_SCHEMA.format(table=self.table))
        conn.commit()
        cur.close()

    def _verify_table_exists(self):
        cur = self._cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name=%s", (self.table,))
        ok = cur.fetchone() is not None
        cur.close()
        return ok

    # ---------- 提交 ----------
    def _status_of(self, tid: int) -> str:
        cur = self._cursor()
        cur.execute('SELECT status FROM "{t}" WHERE id=%s'.format(t=self.table), (tid,))
        r = cur.fetchone()
        cur.close()
        return r[0] if r else "SUCCESS"

    def _deps_of(self, tid: int) -> List[int]:
        cur = self._cursor()
        cur.execute('SELECT dependencies FROM "{t}" WHERE id=%s'.format(t=self.table), (tid,))
        r = cur.fetchone()
        cur.close()
        return list(_loads(r[0], []) if r else [])

    def _children_of(self, dep: int) -> List[int]:
        # dependencies 是 JSONB 数组，用 contains 操作符 @> 反查依赖了 dep 的任务
        cur = self._cursor()
        cur.execute(
            'SELECT id FROM "{t}" WHERE dependencies @> %s::jsonb ORDER BY id'
            .format(t=self.table),
            (json.dumps([dep]),),
        )
        ids = [r[0] for r in cur.fetchall()]
        cur.close()
        return ids

    def submit(self, task_name: str, payload: Optional[Dict[str, Any]] = None,
               task_type: Optional[str] = None, task_value: Optional[str] = None,
               priority: int = 0, max_retries: Optional[int] = None,
               dependencies: Optional[List[int]] = None) -> int:
        """提交任务，返回 id。依赖全部已成功则 READY，否则 PENDING（等待点亮）。"""
        max_retries = max_retries if max_retries is not None else self.max_retries
        deps = list(dict.fromkeys(dependencies or []))
        # 只保留真实存在的依赖
        valid = [d for d in deps if self._task_exists(d)]
        status = _dag.initial_status(valid, self._status_of)
        cur = self._cursor()
        cur.execute(
            'INSERT INTO "{t}" (task_name, task_type, task_value, payload, status,'
            ' priority, max_retries, dependencies)'
            ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id'.format(t=self.table),
            (task_name, task_type or "PYTHON", task_value,
             json.dumps(payload, ensure_ascii=False) if payload is not None else None,
             status, priority, max_retries, json.dumps(valid)),
        )
        row = cur.fetchone()
        self._connect().commit()
        cur.close()
        return row[0]

    def _task_exists(self, tid: int) -> bool:
        cur = self._cursor()
        cur.execute('SELECT 1 FROM "{t}" WHERE id=%s'.format(t=self.table), (tid,))
        ok = cur.fetchone() is not None
        cur.close()
        return ok

    # ---------- Worker 竞争（对标 look_upon._acquire_task） ----------
    def acquire(self, worker_id: str, timeout_min: int = 5,
                states: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """原子领取一个可执行任务（FOR UPDATE SKIP LOCKED）。

        states 指定可领取状态；默认 ['PENDING', 'READY', 'RETRY_PENDING']。
        返回任务 dict（含 id/payload/...），无任务返回 None。
        """
        # BUG-255: 原 `states or [...]` 是假值陷阱——显式空列表（不领取任何
        # 状态）被替换为默认状态，会领走调用方明确排除的任务。
        if states is None:
            states = ["READY", "RETRY_PENDING"]
        cur = self._cursor()
        # 只领 READY / RETRY_PENDING；PENDING 表示依赖未满足，不能抢跑
        order = ("CASE WHEN status='READY' THEN 0 WHEN status='RETRY_PENDING' THEN 1"
                 " ELSE 2 END, priority DESC, id")
        try:
            cur.execute(
                'SELECT id, task_name, task_type, task_value, payload, status, priority,'
                ' retry_count, max_retries, error_message, back_info, dependencies, ts'
                ' FROM "{t}" WHERE status = ANY(%s) AND (lease_timeout IS NULL'
                ' OR lease_timeout < CURRENT_TIMESTAMP)'
                ' ORDER BY {o} LIMIT 1 FOR UPDATE SKIP LOCKED'.format(t=self.table, o=order),
                (states,),
            )
            row = cur.fetchone()
        except Exception as e:
            logger.warning("acquire 查询失败: %s", e)
            self._conn.rollback()
            return None

        if not row:
            cur.close()
            return None

        tid = row[0]
        lease = datetime.utcnow() + timedelta(minutes=timeout_min)
        cur.execute(
            'UPDATE "{t}" SET status=%s, worker_id=%s, locked_by=%s,'
            ' lease_timeout=%s, ts=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP'
            ' WHERE id=%s RETURNING status'.format(t=self.table),
            ("RUNNING", worker_id, worker_id, lease, tid),
        )
        self._connect().commit()
        cur.close()

        return {
            "id": tid,
            "task_name": row[1],
            "task_type": row[2],
            "task_value": row[3],
            "payload": _loads(row[4]),
            "status": row[5],
            "priority": row[6],
            "retry_count": row[7],
            "max_retries": row[8],
            "error_message": row[9],
            "back_info": _loads(row[10]),
            "dependencies": _loads(row[11], []),
            "ts": row[12],
            "lease_timeout": lease,
        }

    def _heartbeat(self, task_id: int, worker_id: str, timeout_min: int):
        """续期租约（心跳）。"""
        lease = datetime.utcnow() + timedelta(minutes=timeout_min)
        cur = self._cursor()
        cur.execute(
            'UPDATE "{t}" SET lease_timeout=%s, updated_at=CURRENT_TIMESTAMP'
            ' WHERE id=%s AND worker_id=%s'.format(t=self.table),
            (lease, task_id, worker_id),
        )
        self._connect().commit()
        cur.close()

    # ---------- 完成 / 失败 / 重试 ----------
    def complete(self, task_id: int, worker_id: str, back_info: Optional[Dict[str, Any]] = None):
        """任务成功：置 SUCCESS，并把依赖已全满足的下游 PENDING 点亮为 READY。"""
        cur = self._cursor()
        cur.execute(
            'UPDATE "{t}" SET status=%s, back_info=%s, completed_at=CURRENT_TIMESTAMP,'
            ' updated_at=CURRENT_TIMESTAMP, lease_timeout=NULL'
            ' WHERE id=%s AND worker_id=%s AND status=%s'.format(t=self.table),
            ("SUCCESS", json.dumps(back_info, ensure_ascii=False) if back_info is not None else None,
             task_id, worker_id, "RUNNING"),
        )
        affected = cur.rowcount
        if affected:
            self._promote_successes(cur, [task_id])
        self._connect().commit()
        cur.close()

    def _promote_successes(self, cur, success_ids):
        for sid in success_ids:
            for child in _dag.ready_after_success(
                    sid, self._deps_of, self._children_of, self._status_of):
                cur.execute(
                    'UPDATE "{t}" SET status=%s, updated_at=CURRENT_TIMESTAMP'
                    ' WHERE id=%s AND status=%s'.format(t=self.table),
                    ("READY", child, "PENDING"),
                )

    def fail(self, task_id: int, worker_id: str, error: str):
        """任务失败：达到重试上限则 FAILED（下游未启动任务级联 SKIPPED），否则 RETRY_PENDING。"""
        cur = self._cursor()
        cur.execute(
            'UPDATE "{t}" SET retry_count=retry_count+1, error_message=%s,'
            ' updated_at=CURRENT_TIMESTAMP WHERE id=%s AND worker_id=%s AND status=%s'
            ' RETURNING retry_count, max_retries'.format(t=self.table),
            (error, task_id, worker_id, "RUNNING"),
        )
        row = cur.fetchone()
        if row is None:
            self._connect().rollback()
            cur.close()
            return
        retry_count, max_retries = row[0], row[1]
        if retry_count >= max_retries:
            cur.execute(
                'UPDATE "{t}" SET status=%s, completed_at=CURRENT_TIMESTAMP,'
                ' lease_timeout=NULL WHERE id=%s'.format(t=self.table),
                ("FAILED", task_id),
            )
            for child in _dag.skip_after_failure(task_id, self._children_of, self._status_of):
                cur.execute(
                    'UPDATE "{t}" SET status=%s, completed_at=CURRENT_TIMESTAMP,'
                    ' lease_timeout=NULL WHERE id=%s'.format(t=self.table),
                    ("SKIPPED", child),
                )
        else:
            cur.execute(
                'UPDATE "{t}" SET status=%s, lease_timeout=NULL WHERE id=%s'.format(t=self.table),
                ("RETRY_PENDING", task_id),
            )
        self._connect().commit()
        cur.close()

    def retry(self, task_id: int):
        """手动重试（RETRY_PENDING → READY）。"""
        cur = self._cursor()
        cur.execute(
            'UPDATE "{t}" SET status=%s, updated_at=CURRENT_TIMESTAMP'
            ' WHERE id=%s AND status=%s'.format(t=self.table),
            ("READY", task_id, "RETRY_PENDING"),
        )
        self._connect().commit()
        cur.close()

    # ---------- 心跳 / 清理 ----------
    def clean_stale_locks(self, timeout_min: int = 10) -> int:
        """清理过期锁（worker 挂掉后把 RUNNING 状态回收）。

        BUG-406: 与原 memory/sqlite 实现一致——真正使用 timeout_min：
        除「lease 已过期」外，也回收「lease 为空且 updated_at 早于
        timeout_min 分钟」的僵尸 RUNNING 任务。
        """
        if isinstance(timeout_min, bool) or not isinstance(timeout_min, (int, float)):
            raise TypeError(
                f"clean_stale_locks 的 timeout_min 需要数字（分钟），收到 "
                f"{type(timeout_min).__name__}: {timeout_min!r}")
        if timeout_min < 0:
            raise ValueError(
                f"clean_stale_locks 的 timeout_min 不能为负，收到 {timeout_min}")
        cur = self._cursor()
        cur.execute(
            'UPDATE "{t}" SET status=%s, worker_id=NULL, locked_by=NULL,'
            ' lease_timeout=NULL, error_message=COALESCE(error_message, %s)'
            ' WHERE status=%s AND (lease_timeout < CURRENT_TIMESTAMP'
            '   OR (lease_timeout IS NULL'
            "       AND updated_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')))"
            .format(t=self.table),
            ("RETRY_PENDING", "锁过期回收", "RUNNING", timeout_min),
        )
        affected = cur.rowcount
        self._connect().commit()
        cur.close()
        return affected

    # ---------- 查询 ----------
    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        cur = self._cursor()
        cur.execute(
            'SELECT id, task_name, task_type, task_value, payload, status, priority,'
            ' retry_count, max_retries, error_message, back_info, dependencies, ts,'
            ' worker_id, locked_by, created_at, updated_at, started_at, completed_at'
            ' FROM "{t}" WHERE id=%s'.format(t=self.table), (task_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        cols = ["id", "task_name", "task_type", "task_value", "payload", "status", "priority",
                "retry_count", "max_retries", "error_message", "back_info", "dependencies", "ts",
                "worker_id", "locked_by", "created_at", "updated_at", "started_at", "completed_at"]
        out = dict(zip(cols, row))
        out["payload"] = _loads(out["payload"])
        out["back_info"] = _loads(out["back_info"])
        out["dependencies"] = _loads(out["dependencies"], [])
        return out

    def query(self, sql: str = "", params: Optional[List[Any]] = None) -> List[tuple]:
        """通用查询。"""
        cur = self._cursor()
        cur.execute(sql or 'SELECT * FROM "{t}" ORDER BY id'.format(t=self.table), params or [])
        rows = cur.fetchall()
        cur.close()
        return rows

    def count_by_status(self) -> Dict[str, int]:
        cur = self._cursor()
        cur.execute(
            'SELECT status, COUNT(*) FROM "{t}" GROUP BY status'.format(t=self.table))
        rows = cur.fetchall()
        cur.close()
        return {r[0]: r[1] for r in rows}

    def is_all_done(self) -> bool:
        cur = self._cursor()
        cur.execute(
            'SELECT COUNT(*) FROM "{t}" WHERE status NOT IN'
            " (%s,%s,%s,%s,%s)".format(t=self.table),
            ("SUCCESS", "COMPLETED", "FAILED", "SKIPPED", "CANCEL"))
        n = cur.fetchone()[0]
        cur.close()
        return n == 0


def _loads(v, default=None):
    """安全 JSON 解析。"""
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v