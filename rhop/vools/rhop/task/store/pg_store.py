"""vools.rhop.task.store.pg_store - PostgreSQL 任务存储后端

实现 TaskStore ABC 契约，与 SqliteTaskStore 语义对齐：

* ``insert_tasks`` 幂等（INSERT ON CONFLICT DO NOTHING）
* ``claim_next`` 原子（状态守卫 UPDATE，PostgreSQL 行级原子性保证）
* ``set_state`` 乐观锁（version 单调递增）
* ``apply_task`` / ``apply_state`` 同步幂等（版本单调门）
* deps/tags 用 TEXT 存 JSON 字符串（与 SQLite 实现一致，避免 JSONB 适配器坑）

连接管理：单连接 + 事务上下文管理器，与 SqliteTaskStore 的 _write_tx 模式一致。
"""

from __future__ import absolute_import

import contextlib
import json
import re
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
from .base import TaskStore

#: 表名/列名安全校验
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: set_state/update_fields 允许写的附加列白名单
_MUTABLE_FIELDS = (
    "task_type", "value", "deps", "priority", "timeout_min",
    "retry_delay_min", "retry_count", "max_retries", "scheduled_at",
    "worker_id", "lock_time", "expire_time", "start_time", "end_time",
    "cancel_requested", "payload_enc", "payload_sha", "back_info",
    "last_err", "tags", "queue", "owner", "team", "group_name", "extra_desc",
)

#: 允许被列表排序的列
_ORDER_COLUMNS = {
    "priority": "priority DESC, task_id ASC",
    "created": "created_at ASC, task_id ASC",
    "created_desc": "created_at DESC, task_id DESC",
    "name": "task_name ASC",
    "updated": "updated_at DESC",
}


def _validate_identifier(name: str, what: str) -> str:
    text = str(name or "").strip()
    if not _IDENT_RE.match(text):
        raise StoreUnavailable("%s 不合法: %r（只允许字母/数字/下划线，且不以数字开头）" % (what, name))
    return text


def _to_pg_value(column: str, value: Any) -> Any:
    """把 Python 值转成 PostgreSQL 可写值。

    deps/tags 列是 TEXT（存 JSON 字符串），与 SQLite 实现一致。
    cancel_requested 列是 BOOLEAN。
    """
    if column in ("deps", "tags"):
        if value is None or value == "":
            return "[]"
        if isinstance(value, str):
            return value
        # VList / list / tuple 等任意非字符串可迭代对象统一转 list 再序列化
        return json.dumps(list(value), ensure_ascii=False)
    if column == "cancel_requested":
        return bool(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return value
    return value


class PgTaskStore(TaskStore):
    """PostgreSQL 后端。

    配置 spec 键：
        host, port, user, password, dbname, table, sslmode, connect_timeout
    """

    kind = "postgres"

    def __init__(self, spec: Optional[dict] = None, ctx: Optional[dict] = None):
        TaskStore.__init__(self, spec, ctx)
        self.table = _validate_identifier(self.spec.get("table") or "tasks", "表名")
        self.host = str(self.spec.get("host") or "127.0.0.1")
        self.port = int(self.spec.get("port") or 5432)
        self.user = str(self.spec.get("user") or "postgres")
        self.password = str(self.spec.get("password") or "")
        self.dbname = str(self.spec.get("dbname") or "postgres")
        self.sslmode = str(self.spec.get("sslmode") or "prefer")
        self.connect_timeout = int(self.spec.get("connect_timeout") or 10)
        self.lock_ttl_sec = float(self.spec.get("lock_ttl_sec") or 900)
        self.claim_scan_limit = int(self.spec.get("claim_scan_limit") or 500)

        self._conn = self._connect()
        self.init_schema()

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------

    def _connect(self):
        try:
            import psycopg2
        except ImportError:
            raise StoreUnavailable(
                "PostgreSQL 后端需要 psycopg2：pip install psycopg2-binary"
            )
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.dbname,
                sslmode=self.sslmode,
                connect_timeout=self.connect_timeout,
            )
            conn.autocommit = False  # 手动管理事务
        except Exception as exc:
            raise StoreUnavailable(
                "打开 PostgreSQL 失败 %s:%s/%s: %s" % (
                    self.host, self.port, self.dbname, exc)
            )
        return conn

    def init_schema(self) -> None:
        """建表 + 建索引（幂等）。"""
        sql = self.schema_sql()
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql)
            self._conn.commit()
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("初始化 PostgreSQL 表 %s 失败: %s" % (self.table, exc))

    def schema_sql(self) -> str:
        """建表 + 建索引 SQL（表名动态，标识符已校验）。"""
        table = self.table
        ip = "idx_%s" % table
        return """
        CREATE TABLE IF NOT EXISTS {table} (
            task_id           SERIAL PRIMARY KEY,
            task_name         TEXT NOT NULL UNIQUE,
            task_type         TEXT NOT NULL DEFAULT 'CLI',
            value             TEXT,
            deps              TEXT NOT NULL DEFAULT '[]',
            state             TEXT NOT NULL DEFAULT 'PENDING'
                              CHECK (state IN ('PENDING','LOCKED','RUNNING','COMPLETED',
                                                'FAILED','RETRY_PENDING','CANCELLED')),
            priority          INTEGER NOT NULL DEFAULT 0,
            timeout_min       DOUBLE PRECISION NOT NULL DEFAULT 60,
            retry_delay_min   DOUBLE PRECISION NOT NULL DEFAULT 5,
            retry_count       INTEGER NOT NULL DEFAULT 0,
            max_retries       INTEGER NOT NULL DEFAULT 3,
            scheduled_at      TEXT,
            worker_id         TEXT,
            lock_time         TEXT,
            expire_time       TEXT,
            start_time        TEXT,
            end_time          TEXT,
            cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
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
        """.format(table=table, ip=ip)

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": "postgres",
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "table": self.table,
            "user": self.user,
        }

    # ------------------------------------------------------------------
    # 事务
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def _write_tx(self):
        """显式写事务：BEGIN → yield → COMMIT / ROLLBACK。"""
        try:
            yield self._conn
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def insert_tasks(self, records: List[TaskRecord]) -> int:
        """批量幂等写入（INSERT ON CONFLICT DO NOTHING）。"""
        items = list(records or [])
        if not items:
            return 0
        inserted = 0
        for item in items:
            rec = item if isinstance(item, TaskRecord) else TaskRecord.from_dict(item)
            if not rec.task_name:
                raise StoreError("任务缺少 task_name，无法写入")
            row = rec.to_row()
            now = row.get("updated_at") or utcnow_iso()
            row["created_at"] = row.get("created_at") or now
            row["updated_at"] = now
            cols = [c for c in TASK_COLUMNS if c != "task_id"]
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            sql = "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (task_name) DO NOTHING" % (
                self.table, col_names, placeholders)
            values = [_to_pg_value(c, row.get(c)) for c in cols]
            try:
                with self._conn.cursor() as cur:
                    cur.execute(sql, values)
                    inserted += cur.rowcount
            except Exception as exc:
                self._conn.rollback()
                raise StoreError("写入任务失败: %s" % exc)
        self._conn.commit()
        return inserted

    def set_state(self, task_name: str, state: str, expect_version: Optional[int] = None,
                  force: bool = False, now: Optional[str] = None, **fields) -> bool:
        """更新状态 + 附加字段（含流转合法性校验与乐观锁）。"""
        target = TaskState.normalize(state)
        now_iso = now or utcnow_iso()
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM %s WHERE task_name = %%s" % self.table, (task_name,))
                row = cur.fetchone()
                if row is None:
                    raise TaskNotFound("任务不存在: %s" % task_name)
                current = TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
                if expect_version is not None and current.version > int(expect_version):
                    return False
                if not force and current.state != target \
                        and not TaskState.can_transition(current.state, target):
                    raise StoreError("非法状态流转: %s -> %s (task %s)" % (
                        current.state, target, task_name))
                sets = ["state = %s", "version = version + 1", "updated_at = %s"]
                params: List[Any] = [target, fields.pop("updated_at", None) or now_iso]
                for key in _MUTABLE_FIELDS:
                    if key in fields:
                        sets.append("%s = %%s" % key)
                        params.append(_to_pg_value(key, fields.pop(key)))
                params.append(task_name)
                cur.execute(
                    "UPDATE %s SET %s WHERE task_name = %%s" % (self.table, ", ".join(sets)),
                    params)
                result = cur.rowcount == 1
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            if isinstance(exc, (TaskNotFound, StoreError)):
                raise
            raise StoreError("更新任务状态(%s)失败: %s" % (task_name, exc))

    def update_fields(self, task_name: str, now: Optional[str] = None, **fields) -> bool:
        """只改字段不改状态。"""
        now_iso = now or utcnow_iso()
        allowed = [k for k in fields if k in _MUTABLE_FIELDS]
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM %s WHERE task_name = %%s" % self.table, (task_name,))
                if cur.fetchone() is None:
                    raise TaskNotFound("任务不存在: %s" % task_name)
                sets = ["updated_at = %s", "version = version + 1"]
                params: List[Any] = [now_iso]
                for key in allowed:
                    sets.append("%s = %%s" % key)
                    params.append(_to_pg_value(key, fields[key]))
                params.append(task_name)
                cur.execute(
                    "UPDATE %s SET %s WHERE task_name = %%s" % (self.table, ", ".join(sets)),
                    params)
                result = cur.rowcount == 1
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            if isinstance(exc, (TaskNotFound, StoreError)):
                raise
            raise StoreError("更新任务字段(%s)失败: %s" % (task_name, exc))

    def claim_next(self, worker_id: str, now: Optional[str] = None,
                   lock_ttl_sec: Optional[float] = None) -> Optional[TaskRecord]:
        """原子领取：事务内 SELECT + 状态守卫 UPDATE（PostgreSQL 行级原子性）。"""
        now_iso = now or utcnow_iso()
        ttl = float(lock_ttl_sec if lock_ttl_sec is not None else self.lock_ttl_sec)
        try:
            with self._conn.cursor() as cur:
                # 先查已完成依赖
                cur.execute(
                    "SELECT task_name FROM %s WHERE state = %%s" % self.table,
                    (TaskState.COMPLETED,))
                done = set(r[0] for r in cur.fetchall())
                # 查可领取任务
                cur.execute(
                    "SELECT * FROM %s WHERE state IN (%%s, %%s) AND cancel_requested = FALSE "
                    "AND (scheduled_at IS NULL OR scheduled_at <= %%s) "
                    "ORDER BY priority DESC, task_id ASC LIMIT %%s" % self.table,
                    (TaskState.PENDING, TaskState.RETRY_PENDING, now_iso, self.claim_scan_limit))
                rows = cur.fetchall()
                for row in rows:
                    rec = TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
                    if rec.deps and not set(rec.deps).issubset(done):
                        continue
                    row_ttl = max(ttl, float(rec.timeout_min or 0) * 60.0)
                    row_expire = iso_add_seconds(now_iso, row_ttl)
                    # 原子领取：带状态守卫的 UPDATE
                    cur.execute(
                        "UPDATE %s SET state = %%s, worker_id = %%s, lock_time = %%s, "
                        "expire_time = %%s, version = version + 1, updated_at = %%s "
                        "WHERE task_id = %%s AND state IN (%%s, %%s) AND cancel_requested = FALSE "
                        "RETURNING *" % self.table,
                        (TaskState.LOCKED, worker_id, now_iso, row_expire, now_iso,
                         rec.task_id, TaskState.PENDING, TaskState.RETRY_PENDING))
                    result = cur.fetchone()
                    if result is not None:
                        rec = TaskRecord.from_row(dict(zip(TASK_COLUMNS, result)))
                        rec.state = TaskState.LOCKED
                        rec.worker_id = worker_id
                        rec.lock_time = now_iso
                        rec.expire_time = row_expire
                        self._conn.commit()
                        return rec
            self._conn.commit()
            return None
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("领取任务失败: %s" % exc)

    def clean_stale_locks(self, now: Optional[str] = None,
                          lock_timeout_sec: Optional[float] = None) -> int:
        """回收失效锁（LOCKED→PENDING，RUNNING→RETRY_PENDING）。"""
        now_iso = now or utcnow_iso()
        timeout = abs(float(lock_timeout_sec if lock_timeout_sec is not None else self.lock_ttl_sec))
        cutoff = iso_add_seconds(now_iso, -timeout)
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "UPDATE %s SET state = CASE WHEN state = %%s THEN %%s ELSE %%s END, "
                    "lock_time = NULL, worker_id = NULL, updated_at = %%s, version = version + 1 "
                    "WHERE state IN (%%s, %%s) AND ("
                    "  (expire_time IS NOT NULL AND expire_time < %%s) OR "
                    "  (expire_time IS NULL AND lock_time IS NOT NULL AND lock_time < %%s))" % self.table,
                    (TaskState.LOCKED, TaskState.PENDING, TaskState.RETRY_PENDING,
                     now_iso, TaskState.LOCKED, TaskState.RUNNING, now_iso, cutoff))
                result = cur.rowcount
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("回收失效锁失败: %s" % exc)

    def reset_failed(self, now: Optional[str] = None) -> int:
        """FAILED → PENDING。"""
        now_iso = now or utcnow_iso()
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "UPDATE %s SET state = %%s, worker_id = NULL, lock_time = NULL, "
                    "updated_at = %%s, version = version + 1 WHERE state = %%s" % self.table,
                    (TaskState.PENDING, now_iso, TaskState.FAILED))
                result = cur.rowcount
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("重置失败任务失败: %s" % exc)

    def requeue(self, task_name: str, now: Optional[str] = None) -> bool:
        """强制把单个任务重置回 PENDING。"""
        return self.set_state(task_name, TaskState.PENDING, force=True, now=now,
                              worker_id=None, lock_time=None, cancel_requested=False,
                              end_time=None)

    def set_cancel_requested(self, task_name: str, flag: bool = True,
                             now: Optional[str] = None) -> bool:
        """打/撤取消请求。"""
        return self.update_fields(task_name, now=now, cancel_requested=flag)

    def apply_task(self, record: TaskRecord) -> str:
        """同步落地：按 version 幂等 upsert 任务定义。"""
        rec = record if isinstance(record, TaskRecord) else TaskRecord.from_dict(record)
        if not rec.task_name:
            raise StoreError("同步任务缺少 task_name")
        now_iso = utcnow_iso()
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM %s WHERE task_name = %%s" % self.table, (rec.task_name,))
                row = cur.fetchone()
                if row is None:
                    data = rec.to_row()
                    data["created_at"] = data.get("created_at") or now_iso
                    data["updated_at"] = now_iso
                    cols = [c for c in TASK_COLUMNS if c != "task_id"]
                    placeholders = ", ".join(["%s"] * len(cols))
                    col_names = ", ".join(cols)
                    sql = "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (task_name) DO NOTHING" % (
                        self.table, col_names, placeholders)
                    values = [_to_pg_value(c, data.get(c)) for c in cols]
                    cur.execute(sql, values)
                    result = "inserted" if cur.rowcount == 1 else "stale"
                else:
                    local = TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
                    if rec.version <= local.version:
                        return "stale"
                    sets = ["version = %s", "updated_at = %s"]
                    params: List[Any] = [rec.version, now_iso]
                    for key in DEFINITION_FIELDS:
                        sets.append("%s = %%s" % key)
                        params.append(_to_pg_value(key, getattr(rec, key)))
                    params.append(rec.task_name)
                    cur.execute(
                        "UPDATE %s SET %s WHERE task_name = %%s" % (self.table, ", ".join(sets)),
                        params)
                    result = "updated"
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("同步任务(%s)失败: %s" % (rec.task_name, exc))

    def apply_state(self, data: Dict[str, Any]) -> str:
        """同步落地：按 version 幂等应用状态更新。"""
        payload = dict(data or {})
        task_name = payload.get("task_name")
        if not task_name:
            raise StoreError("同步状态缺少 task_name")
        target = TaskState.normalize(payload.get("state"))
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM %s WHERE task_name = %%s" % self.table, (task_name,))
                row = cur.fetchone()
                if row is None:
                    return "missing"
                local = TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
                incoming = int(payload.get("version") or 0)
                if incoming <= local.version:
                    return "stale"
                now_iso = utcnow_iso()
                sets = ["state = %s", "version = %s", "updated_at = %s"]
                params: List[Any] = [target, incoming, now_iso]
                for key in ("worker_id", "lock_time", "start_time", "end_time",
                            "scheduled_at", "expire_time", "back_info", "last_err",
                            "retry_count", "cancel_requested"):
                    if key in payload:
                        sets.append("%s = %%s" % key)
                        params.append(_to_pg_value(key, payload.get(key)))
                params.append(task_name)
                cur.execute(
                    "UPDATE %s SET %s WHERE task_name = %%s" % (self.table, ", ".join(sets)),
                    params)
                result = "updated"
            self._conn.commit()
            return result
        except Exception as exc:
            self._conn.rollback()
            raise StoreError("同步状态(%s)失败: %s" % (task_name, exc))

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_task(self, task_name: str) -> Optional[TaskRecord]:
        """按 task_name 读一条。"""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM %s WHERE task_name = %%s" % self.table, (task_name,))
                row = cur.fetchone()
            if row is None:
                return None
            return TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
        except Exception as exc:
            raise StoreError("读取任务(%s)失败: %s" % (task_name, exc))

    def list_tasks(self, state: Optional[str] = None, limit: int = 200,
                   order: str = "priority") -> List[TaskRecord]:
        """列出任务（可按状态过滤）。"""
        order_sql = _ORDER_COLUMNS.get(str(order or "priority"), _ORDER_COLUMNS["priority"])
        params: List[Any] = []
        sql = "SELECT * FROM %s" % self.table
        if state:
            sql += " WHERE state = %s"
            params.append(TaskState.normalize(state))
        sql += " ORDER BY %s" % order_sql
        if limit and int(limit) > 0:
            sql += " LIMIT %s"
            params.append(int(limit))
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
            return [TaskRecord.from_row(dict(zip(TASK_COLUMNS, r))) for r in rows]
        except Exception as exc:
            raise StoreError("列出任务失败: %s" % exc)

    def all_task_names(self) -> List[str]:
        """全部 task_name。"""
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT task_name FROM %s" % self.table)
                rows = cur.fetchall()
            return [str(r[0]) for r in rows]
        except Exception as exc:
            raise StoreError("获取任务名列表失败: %s" % exc)

    def count_by_state(self) -> Dict[str, int]:
        """按状态计数（表不存在时返回空 dict）。"""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT state, COUNT(*) AS n FROM %s GROUP BY state" % self.table)
                rows = cur.fetchall()
            return {str(r[0]): int(r[1]) for r in rows}
        except Exception as exc:
            # 表不存在（pgcode 42P01 undefined_table）时返回空 dict
            # is_all_done 依赖此行为
            pgcode = getattr(exc, "pgcode", None)
            if pgcode == "42P01" or "does not exist" in str(exc):
                self._conn.rollback()  # 清理 aborted 事务，避免影响后续调用
                return {}
            self._conn.rollback()
            raise StoreError("状态计数失败: %s" % exc)

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭连接（幂等）。"""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._conn = None


__all__ = ["PgTaskStore"]
