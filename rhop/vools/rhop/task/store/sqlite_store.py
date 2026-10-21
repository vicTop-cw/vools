"""vools.rhop.task.store.sqlite_store - SQLite 任务存储（共享 / 各自持库共用同一个实现）

同一个 ``SqliteTaskStore`` 通过不同 ``path`` 与 PRAGMA 策略承载两种拓扑：

| 拓扑 | kind | path | journal_mode | synchronous | 语义 |
|---|---|---|---|---|---|
| 单一共享库 | ``sqlite-shared`` | 共享介质上同一文件 | ``DELETE`` | ``FULL`` | A/B 直接读写同一份数据，状态天然一致 |
| 双方各自持库 | ``sqlite-local`` | 各自本地文件 | ``WAL`` | ``NORMAL`` | 靠 TaskSync 加密包收敛成"同样的库" |

为什么共享库禁用 WAL：WAL 依赖共享内存映射与可靠的文件锁，在网络盘（SMB/NFS）
上不可靠，官方也明确不建议；共享场景用回滚日志模式 + 全同步 + busy_timeout + 写重试。

并发正确性：写路径一律 ``BEGIN IMMEDIATE`` 显式事务（isolated_level=None 手动管事务），
``claim_next`` 在事务内选行 + 带状态守卫的 UPDATE（rowcount 校验），因此多个 worker
（甚至跨机）不会领到同一条任务。
"""

from __future__ import absolute_import

import contextlib
import json
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ..errors import StoreError, StoreUnavailable, TaskNotFound
from ..models import (
    DEFINITION_FIELDS,
    TASK_COLUMNS,
    TaskRecord,
    TaskState,
    iso_add_seconds,
    utcnow_iso,
)
from .base import TaskStore, require_shared_root, resolve_path_template

#: 表名/列名安全校验（动态表名必须挡住注入）
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: set_state/update_fields 允许写的附加列白名单（防止把 task_name 等身份列改掉）
_MUTABLE_FIELDS = (
    "task_type",
    "value",
    "deps",
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
)

#: 允许被"列表"排序的列（避免任意 SQL）
_ORDER_COLUMNS = {
    "priority": "priority DESC, task_id ASC",
    "created": "created_at ASC, task_id ASC",
    "created_desc": "created_at DESC, task_id DESC",
    "name": "task_name ASC",
    "updated": "updated_at DESC",
}


def _validate_identifier(name: str, what: str) -> str:
    """校验动态 SQL 标识符合法（表名/列名）。"""
    text = str(name or "").strip()
    if not _IDENT_RE.match(text):
        raise StoreUnavailable("%s 不合法: %r（只允许字母/数字/下划线，且不以数字开头）" % (what, name))
    return text


def _to_db_value(column: str, value: Any) -> Any:
    """把 Python 值转成 SQLite 可写值（list/dict→JSON，bool→int）。"""
    if column in ("deps", "tags"):
        if value is None or value == "":
            return "[]"
        if isinstance(value, str):
            return value
        return json.dumps(list(value), ensure_ascii=False)
    if column == "cancel_requested":
        return 1 if value else 0
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 1 if value else 0
    return value


class SqliteTaskStore(TaskStore):
    """SQLite 后端（共享库 / 各自持库共用）。"""

    kind = "sqlite"

    def __init__(self, spec: Optional[dict] = None, ctx: Optional[dict] = None):
        TaskStore.__init__(self, spec, ctx)
        self.table = _validate_identifier(self.spec.get("table") or "tasks", "表名")
        self.busy_timeout_sec = float(self.spec.get("busy_timeout_sec") or 15)
        self.write_retries = int(self.spec.get("write_retries") or 6)
        self.retry_backoff_sec = float(self.spec.get("write_retry_backoff_sec") or 0.25)
        self.lock_ttl_sec = float(self.spec.get("lock_ttl_sec") or 900)
        self.claim_scan_limit = int(self.spec.get("claim_scan_limit") or 500)
        self.journal_mode = str(self.spec.get("journal_mode") or "DELETE").upper()
        self.synchronous = str(self.spec.get("synchronous") or "FULL").upper()

        self.path = self._resolve_path(self.spec.get("path"))
        self._ensure_parent_dir()
        self._conn = self._connect()
        self.init_schema()

    # ------------------------------------------------------------------
    # 路径与连接
    # ------------------------------------------------------------------

    def _resolve_path(self, raw_path: Any) -> str:
        """解析数据库文件路径（支持 {shared}/{name}/{role}/{base_dir} 模板）。"""
        template = resolve_path_template(str(raw_path or ""), self.ctx)
        if not template:
            raise StoreUnavailable(
                "存储缺少 path：请在 queue.store.path 指定数据库文件位置"
                "（sqlite-shared 可用 {shared}/tasks.db，sqlite-local 可用 {base_dir}/rhop-{role}.db）"
            )
        path = os.path.abspath(os.path.expanduser(template))
        parent = os.path.dirname(path)
        if not parent:
            raise StoreUnavailable("存储 path 不是有效文件路径: %r" % raw_path)
        return path

    def _ensure_parent_dir(self) -> None:
        """确保父目录存在（网络盘创建失败要明确报错，不要等到 sqlite 抛异常）。"""
        parent = os.path.dirname(self.path)
        if os.path.isdir(parent):
            return
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            raise StoreUnavailable(
                "无法创建数据库目录 %s（%s）。请确认该路径存在且可写；"
                "若介质是 SFTP/Git 等非文件系统形态，请改用 queue.store.kind=sqlite-local。" % (parent, exc)
            )

    def _connect(self) -> sqlite3.Connection:
        """建立连接并设置并发/持久化 PRAGMA。"""
        try:
            conn = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_sec,
                isolation_level=None,  # 手动管理事务（显式 BEGIN IMMEDIATE）
            )
        except sqlite3.Error as exc:
            raise StoreUnavailable("打开数据库失败 %s: %s" % (self.path, exc))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = %d" % int(self.busy_timeout_sec * 1000))
            conn.execute("PRAGMA journal_mode = %s" % self.journal_mode)
            conn.execute("PRAGMA synchronous = %s" % self.synchronous)
        except sqlite3.Error as exc:
            raise StoreUnavailable("设置数据库 PRAGMA 失败: %s" % exc)
        return conn

    @property
    def schema_version(self) -> int:
        """当前 schema 版本（PRAGMA user_version，供将来迁移）。"""
        try:
            return int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        except (sqlite3.Error, TypeError):
            return 0

    @property
    def effective_journal_mode(self) -> str:
        """实际生效的 journal_mode（可能被同库其他进程改写，诊断用）。"""
        try:
            return str(self._conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
        except (sqlite3.Error, TypeError):
            return self.journal_mode

    # ------------------------------------------------------------------
    # schema
    # ------------------------------------------------------------------

    def schema_sql(self) -> str:
        """建表 + 建索引 SQL（表名动态，标识符已校验）。"""
        table = self.table
        index_prefix = "idx_%s" % table
        return """
CREATE TABLE IF NOT EXISTS {table} (
    task_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name         TEXT NOT NULL UNIQUE,
    task_type         TEXT NOT NULL DEFAULT 'CLI',
    value             TEXT,
    deps              TEXT NOT NULL DEFAULT '[]',
    state             TEXT NOT NULL DEFAULT 'PENDING'
                      CHECK (state IN ('PENDING','LOCKED','RUNNING','COMPLETED',
                                       'FAILED','RETRY_PENDING','CANCELLED')),
    priority          INTEGER NOT NULL DEFAULT 0,
    timeout_min       REAL NOT NULL DEFAULT 60,
    retry_delay_min   REAL NOT NULL DEFAULT 5,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    max_retries       INTEGER NOT NULL DEFAULT 3,
    scheduled_at      TEXT,
    worker_id         TEXT,
    lock_time         TEXT,
    expire_time       TEXT,
    start_time        TEXT,
    end_time          TEXT,
    cancel_requested  INTEGER NOT NULL DEFAULT 0,
    version           INTEGER NOT NULL DEFAULT 1,
    payload_enc       TEXT,
    payload_sha       TEXT,
    back_info         TEXT,
    last_err          TEXT,
    tags              TEXT NOT NULL DEFAULT '[]',
    queue             TEXT NOT NULL DEFAULT '',
    owner             TEXT NOT NULL DEFAULT '',
    team              TEXT NOT NULL DEFAULT '',
    group_name        TEXT NOT NULL DEFAULT '',
    extra_desc        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS {ip}_state       ON {table}(state);
CREATE INDEX IF NOT EXISTS {ip}_priority    ON {table}(priority);
CREATE INDEX IF NOT EXISTS {ip}_lock_time   ON {table}(lock_time);
CREATE INDEX IF NOT EXISTS {ip}_scheduled   ON {table}(scheduled_at);
CREATE INDEX IF NOT EXISTS {ip}_worker      ON {table}(worker_id);
CREATE INDEX IF NOT EXISTS {ip}_type        ON {table}(task_type);
CREATE INDEX IF NOT EXISTS {ip}_queue       ON {table}(queue);
""".format(table=table, ip=index_prefix)

    def init_schema(self) -> None:
        """建表（幂等）并把 PRAGMA user_version 置为 1。"""
        try:
            self._conn.executescript(self.schema_sql())
        except sqlite3.Error as exc:
            raise StoreError("初始化表 %s 失败: %s" % (self.table, exc))
        if self.schema_version < 1:
            try:
                self._conn.execute("PRAGMA user_version = 1")
            except sqlite3.Error:
                pass  # user_version 只是迁移标记，写不进去不影响使用

    def describe(self) -> Dict[str, Any]:
        """后端自描述（含实际生效的 journal_mode，便于诊断共享盘问题）。"""
        return {
            "kind": "sqlite",
            "path": self.path,
            "table": self.table,
            "journal_mode": self.effective_journal_mode,
            "journal_mode_configured": self.journal_mode,
            "synchronous": self.synchronous,
            "busy_timeout_sec": self.busy_timeout_sec,
            "schema_version": self.schema_version,
        }

    # ------------------------------------------------------------------
    # 事务 + 重试
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def _write_tx(self):
        """显式写事务：BEGIN IMMEDIATE → yield → COMMIT / ROLLBACK。"""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        else:
            self._conn.execute("COMMIT")

    def _retry(self, fn, what: str):
        """对「数据库被占用」做退避重试；其他 sqlite 错误直接转 StoreError。"""
        last = None
        for attempt in range(1, self.write_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if "locked" in msg or "busy" in msg:
                    last = exc
                    time.sleep(self.retry_backoff_sec * attempt)
                    continue
                raise StoreError("%s 失败: %s" % (what, exc))
            except sqlite3.Error as exc:
                raise StoreError("%s 失败: %s" % (what, exc))
        raise StoreError(
            "%s 失败：数据库持续被占用（%s）。共享盘上多写者竞争或锁文件不可靠时，"
            "请降低写并发、调大 busy_timeout_sec，或改用 queue.store.kind=sqlite-local。" % (what, last)
        )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def insert_tasks(self, records: List[TaskRecord]) -> int:
        """批量幂等写入（INSERT OR IGNORE，按 task_name 去重）。"""
        items = list(records or [])
        if not items:
            return 0

        def _do():
            inserted = 0
            with self._write_tx() as conn:
                for item in items:
                    rec = item if isinstance(item, TaskRecord) else TaskRecord.from_dict(item)
                    if not rec.task_name:
                        raise StoreError("任务缺少 task_name，无法写入")
                    row = rec.to_row()
                    now = row.get("updated_at") or utcnow_iso()
                    row["created_at"] = row.get("created_at") or now
                    row["updated_at"] = now
                    cols = [c for c in TASK_COLUMNS if c != "task_id"]
                    sql = "INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % (
                        self.table,
                        ",".join(cols),
                        ",".join("?" for _ in cols),
                    )
                    cur = conn.execute(sql, [_to_db_value(c, row.get(c)) for c in cols])
                    inserted += cur.rowcount
            return inserted

        return self._retry(_do, "写入任务")

    def set_state(self, task_name: str, state: str, expect_version: Optional[int] = None,
                  force: bool = False, now: Optional[str] = None, **fields) -> bool:
        """更新状态 + 附加字段（含流转合法性校验与乐观锁）。"""
        target = TaskState.normalize(state)
        now_iso = now or utcnow_iso()

        def _do():
            with self._write_tx() as conn:
                row = conn.execute(
                    "SELECT * FROM %s WHERE task_name = ?" % self.table, (task_name,)
                ).fetchone()
                if row is None:
                    raise TaskNotFound("任务不存在: %s" % task_name)
                current = TaskRecord.from_row(row)
                if expect_version is not None and current.version > int(expect_version):
                    return False
                if not force and current.state != target \
                        and not TaskState.can_transition(current.state, target):
                    raise StoreError("非法状态流转: %s -> %s (task %s)" % (
                        current.state, target, task_name))
                sets = ["state = ?", "version = version + 1", "updated_at = ?"]
                params = [target, fields.pop("updated_at", None) or now_iso]
                for key in _MUTABLE_FIELDS:
                    if key in fields:
                        sets.append("%s = ?" % key)
                        params.append(_to_db_value(key, fields.pop(key)))
                params.append(task_name)
                cur = conn.execute(
                    "UPDATE %s SET %s WHERE task_name = ?" % (self.table, ", ".join(sets)),
                    params,
                )
                return cur.rowcount == 1

        return self._retry(_do, "更新任务状态(%s)" % task_name)

    def update_fields(self, task_name: str, now: Optional[str] = None, **fields) -> bool:
        """只改字段不改状态（worker 心跳式刷新用）。"""
        now_iso = now or utcnow_iso()
        allowed = [k for k in fields if k in _MUTABLE_FIELDS]

        def _do():
            with self._write_tx() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM %s WHERE task_name = ?" % self.table, (task_name,)
                ).fetchone()
                if exists is None:
                    raise TaskNotFound("任务不存在: %s" % task_name)
                sets = ["updated_at = ?", "version = version + 1"]
                params = [now_iso]
                for key in allowed:
                    sets.append("%s = ?" % key)
                    params.append(_to_db_value(key, fields[key]))
                params.append(task_name)
                cur = conn.execute(
                    "UPDATE %s SET %s WHERE task_name = ?" % (self.table, ", ".join(sets)),
                    params,
                )
                return cur.rowcount == 1

        return self._retry(_do, "更新任务字段(%s)" % task_name)

    def claim_next(self, worker_id: str, now: Optional[str] = None,
                   lock_ttl_sec: Optional[float] = None) -> Optional[TaskRecord]:
        """原子领取：事务内选行（依赖门控在 Python 侧做，兼容无 JSON1 的老 SQLite）。"""
        now_iso = now or utcnow_iso()
        ttl = float(lock_ttl_sec if lock_ttl_sec is not None else self.lock_ttl_sec)
        expire = iso_add_seconds(now_iso, ttl)

        def _do():
            with self._write_tx() as conn:
                done = set(
                    r[0] for r in conn.execute(
                        "SELECT task_name FROM %s WHERE state = ?" % self.table,
                        (TaskState.COMPLETED,),
                    ).fetchall()
                )
                rows = conn.execute(
                    "SELECT * FROM %s WHERE state IN (?, ?) AND cancel_requested = 0 "
                    "AND (scheduled_at IS NULL OR scheduled_at <= ?) "
                    "ORDER BY priority DESC, task_id ASC LIMIT ?" % self.table,
                    (TaskState.PENDING, TaskState.RETRY_PENDING, now_iso, self.claim_scan_limit),
                ).fetchall()
                for row in rows:
                    rec = TaskRecord.from_row(row)
                    if rec.deps and not set(rec.deps).issubset(done):
                        continue
                    # 每行的锁有效期：取「全局 lock_ttl」与「该任务自己的 timeout_min」的较大者，
                    # 避免长任务被别的 worker 误判为失效而重复执行。
                    row_ttl = max(ttl, float(rec.timeout_min or 0) * 60.0)
                    row_expire = iso_add_seconds(now_iso, row_ttl)
                    cur = conn.execute(
                        "UPDATE %s SET state = ?, worker_id = ?, lock_time = ?, expire_time = ?, "
                        "version = version + 1, updated_at = ? "
                        "WHERE task_id = ? AND state IN (?, ?) AND cancel_requested = 0" % self.table,
                        (TaskState.LOCKED, worker_id, now_iso, row_expire, now_iso,
                         rec.task_id, TaskState.PENDING, TaskState.RETRY_PENDING),
                    )
                    if cur.rowcount == 1:
                        rec.state = TaskState.LOCKED
                        rec.worker_id = worker_id
                        rec.lock_time = now_iso
                        rec.expire_time = row_expire
                        rec.version = rec.version + 1
                        rec.updated_at = now_iso
                        return rec
                return None

        return self._retry(_do, "领取任务")

    def clean_stale_locks(self, now: Optional[str] = None,
                          lock_timeout_sec: Optional[float] = None) -> int:
        """回收失效锁（LOCKED→PENDING，RUNNING→RETRY_PENDING）。

        判定优先用每行自己的 ``expire_time``（领取时按该任务 timeout_min 定的），
        只在 expire_time 为空时退回 ``lock_time < now - lock_timeout_sec`` 的兜底口径。
        """
        now_iso = now or utcnow_iso()
        timeout = abs(float(lock_timeout_sec if lock_timeout_sec is not None else self.lock_ttl_sec))
        cutoff = iso_add_seconds(now_iso, -timeout)

        def _do():
            with self._write_tx() as conn:
                cur = conn.execute(
                    "UPDATE %s SET state = CASE WHEN state = ? THEN ? ELSE ? END, "
                    "lock_time = NULL, worker_id = NULL, updated_at = ?, version = version + 1 "
                    "WHERE state IN (?, ?) AND ("
                    "  (expire_time IS NOT NULL AND expire_time < ?) OR "
                    "  (expire_time IS NULL AND lock_time IS NOT NULL AND lock_time < ?))" % self.table,
                    (TaskState.LOCKED, TaskState.PENDING, TaskState.RETRY_PENDING,
                     now_iso, TaskState.LOCKED, TaskState.RUNNING, now_iso, cutoff),
                )
                return cur.rowcount

        return self._retry(_do, "回收失效锁")

    def reset_failed(self, now: Optional[str] = None) -> int:
        """FAILED → PENDING（运维重跑）。"""
        now_iso = now or utcnow_iso()

        def _do():
            with self._write_tx() as conn:
                cur = conn.execute(
                    "UPDATE %s SET state = ?, worker_id = NULL, lock_time = NULL, "
                    "updated_at = ?, version = version + 1 WHERE state = ?" % self.table,
                    (TaskState.PENDING, now_iso, TaskState.FAILED),
                )
                return cur.rowcount

        return self._retry(_do, "重置失败任务")

    def requeue(self, task_name: str, now: Optional[str] = None) -> bool:
        """强制把单个任务重置回 PENDING（force，跳过流转校验）。"""
        return self.set_state(task_name, TaskState.PENDING, force=True, now=now,
                              worker_id=None, lock_time=None, cancel_requested=0,
                              end_time=None)

    def set_cancel_requested(self, task_name: str, flag: bool = True,
                             now: Optional[str] = None) -> bool:
        """打/撤取消请求。"""
        return self.update_fields(task_name, now=now, cancel_requested=1 if flag else 0)

    def apply_task(self, record: TaskRecord) -> str:
        """同步落地：按 version 幂等 upsert 任务定义。"""
        rec = record if isinstance(record, TaskRecord) else TaskRecord.from_dict(record)
        if not rec.task_name:
            raise StoreError("同步任务缺少 task_name")

        def _do():
            with self._write_tx() as conn:
                row = conn.execute(
                    "SELECT * FROM %s WHERE task_name = ?" % self.table, (rec.task_name,)
                ).fetchone()
                now_iso = utcnow_iso()
                if row is None:
                    data = rec.to_row()
                    data["created_at"] = data.get("created_at") or now_iso
                    data["updated_at"] = now_iso
                    cols = [c for c in TASK_COLUMNS if c != "task_id"]
                    sql = "INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % (
                        self.table, ",".join(cols), ",".join("?" for _ in cols))
                    cur = conn.execute(sql, [_to_db_value(c, data.get(c)) for c in cols])
                    return "inserted" if cur.rowcount == 1 else "stale"
                local = TaskRecord.from_row(row)
                if rec.version <= local.version:
                    return "stale"
                sets = ["version = ?", "updated_at = ?"]
                params: List[Any] = [rec.version, now_iso]
                for key in DEFINITION_FIELDS:
                    sets.append("%s = ?" % key)
                    params.append(_to_db_value(key, getattr(rec, key)))
                params.append(rec.task_name)
                conn.execute(
                    "UPDATE %s SET %s WHERE task_name = ?" % (self.table, ", ".join(sets)),
                    params,
                )
                return "updated"

        return self._retry(_do, "同步任务(%s)" % rec.task_name)

    def apply_state(self, data: Dict[str, Any]) -> str:
        """同步落地：按 version 幂等应用状态更新（旧版本丢弃）。"""
        payload = dict(data or {})
        task_name = payload.get("task_name")
        if not task_name:
            raise StoreError("同步状态缺少 task_name")
        target = TaskState.normalize(payload.get("state"))

        def _do():
            with self._write_tx() as conn:
                row = conn.execute(
                    "SELECT * FROM %s WHERE task_name = ?" % self.table, (task_name,)
                ).fetchone()
                if row is None:
                    return "missing"
                local = TaskRecord.from_row(row)
                incoming = int(payload.get("version") or 0)
                if incoming <= local.version:
                    return "stale"
                now_iso = utcnow_iso()
                sets = ["state = ?", "version = ?", "updated_at = ?"]
                params: List[Any] = [target, incoming, now_iso]
                for key in ("worker_id", "lock_time", "start_time", "end_time",
                            "scheduled_at", "expire_time", "back_info", "last_err",
                            "retry_count", "cancel_requested"):
                    if key in payload:
                        sets.append("%s = ?" % key)
                        params.append(_to_db_value(key, payload.get(key)))
                params.append(task_name)
                conn.execute(
                    "UPDATE %s SET %s WHERE task_name = ?" % (self.table, ", ".join(sets)),
                    params,
                )
                return "updated"

        return self._retry(_do, "同步状态(%s)" % task_name)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_task(self, task_name: str) -> Optional[TaskRecord]:
        """按 task_name 读一条。"""
        row = self._conn.execute(
            "SELECT * FROM %s WHERE task_name = ?" % self.table, (task_name,)
        ).fetchone()
        return TaskRecord.from_row(row) if row is not None else None

    def list_tasks(self, state: Optional[str] = None, limit: int = 200,
                   order: str = "priority") -> List[TaskRecord]:
        """列出任务（可按状态过滤；limit<=0 表示不限制）。"""
        order_sql = _ORDER_COLUMNS.get(str(order or "priority"), _ORDER_COLUMNS["priority"])
        params: List[Any] = []
        sql = "SELECT * FROM %s" % self.table
        if state:
            sql += " WHERE state = ?"
            params.append(TaskState.normalize(state))
        sql += " ORDER BY %s" % order_sql
        if limit and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [TaskRecord.from_row(r) for r in rows]

    def all_task_names(self) -> List[str]:
        """全部 task_name。"""
        rows = self._conn.execute("SELECT task_name FROM %s" % self.table).fetchall()
        return [str(r[0]) for r in rows]

    def count_by_state(self) -> Dict[str, int]:
        """按状态计数（只返回出现过的状态）。"""
        rows = self._conn.execute(
            "SELECT state, COUNT(*) AS n FROM %s GROUP BY state" % self.table
        ).fetchall()
        return {str(r["state"]): int(r["n"]) for r in rows}

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭连接（幂等）。"""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._conn = None


__all__ = ["SqliteTaskStore", "resolve_shared_db_path"]


def resolve_shared_db_path(spec: dict, ctx: dict) -> str:
    """为 sqlite-shared 解析共享库文件路径（缺省 <shared>/rhop-tasks.db）。"""
    template = str((spec or {}).get("path") or "")
    if not template:
        root = require_shared_root(ctx)
        return os.path.join(root, "rhop-%s.db" % str(ctx.get("name") or "tasks"))
    return resolve_path_template(template, ctx)