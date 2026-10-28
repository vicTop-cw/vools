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
from .base import LEASE_RECLAIM_LAST_ERR, TaskStore

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

#: 显式列清单。禁止 SELECT *：psycopg2 元组按物理列序返回，一旦旧表的物理列序
#: 与 TASK_COLUMNS 不同（历史 ALTER / 不同建表版本），dict(zip(...)) 会静默错位。
_SELECT_COLS = ", ".join(TASK_COLUMNS)

#: 允许被列表排序的列
_ORDER_COLUMNS = {
    "priority": "priority DESC, task_id ASC",
    "created": "created_at ASC, task_id ASC",
    "created_desc": "created_at DESC, task_id DESC",
    "name": "task_name ASC",
    "updated": "updated_at DESC",
}

#: 当前 PG schema 版本。列集/语义发生**不兼容**变化时 +1：
#: 启动时与元数据表比对，落后即补列（迁移），领先则拒绝启动（代码比库旧）。
#: PG 没有 SQLite 的 ``PRAGMA user_version``，只能用专用元数据表承载。
_SCHEMA_VERSION = 1

#: 迁移时跳过的身份列（任何版本的表都存在；补齐反而引入 UNIQUE/序列冲突）
_MIGRATION_SKIP = ("task_id", "task_name")

#: 迁移互斥锁的**命名空间**（两段式 advisory lock 的第一段）。
#: 用固定常量而不是临时哈希：同一个 PG 实例上可能有别的应用也在用 advisory lock，
#: 固定命名空间把我们的锁限制在「本包 + 本表」，不与别人撞 int4 键。
_MIGRATION_LOCK_NAMESPACE = "vools.rhop.task.store.schema"

#: 迁移锁的默认等待上限（毫秒）。拿不到就报「另一个会话正在迁移」，绝不无限等。
#: 0 表示不设上限（退化成旧行为，仅调试用）。
_DEFAULT_MIGRATION_LOCK_TIMEOUT_MS = 5000


def _is_lock_timeout(exc) -> bool:
    """异常是否属于「等锁超时 / 死锁被 PG 中止 / 语句被取消」。

    不导入 psycopg2 也能判：优先看 SQLSTATE（55P03 lock_not_available、
    40P01 deadlock_detected、57014 query_canceled），再用报错文本兜底。
    """
    code = getattr(exc, "pgcode", None)
    if code in ("55P03", "40P01", "57014"):
        return True
    text = str(exc).lower()
    return ("lock timeout" in text) or ("deadlock detected" in text) \
        or ("canceling statement due to lock" in text)

#: 列定义单一来源：CREATE TABLE 与「旧表补列」迁移都从这里生成，避免两处漂移。
#: 顺序必须与 models.TASK_COLUMNS 一致（有测试自校）。
_COLUMN_DDL = (
    ("task_id", "SERIAL PRIMARY KEY"),
    ("task_name", "TEXT NOT NULL UNIQUE"),
    ("task_type", "TEXT NOT NULL DEFAULT 'CLI'"),
    ("value", "TEXT"),
    ("deps", "TEXT NOT NULL DEFAULT '[]'"),
    ("state", "TEXT NOT NULL DEFAULT 'PENDING' "
              + "CHECK (state IN ('PENDING','LOCKED','RUNNING','COMPLETED',"
              "'FAILED','RETRY_PENDING','CANCELLED'))"),
    ("priority", "INTEGER NOT NULL DEFAULT 0"),
    ("timeout_min", "DOUBLE PRECISION NOT NULL DEFAULT 60"),
    ("retry_delay_min", "DOUBLE PRECISION NOT NULL DEFAULT 5"),
    ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
    ("max_retries", "INTEGER NOT NULL DEFAULT 3"),
    ("scheduled_at", "TEXT"),
    ("worker_id", "TEXT"),
    ("lock_time", "TEXT"),
    ("expire_time", "TEXT"),
    ("start_time", "TEXT"),
    ("end_time", "TEXT"),
    ("cancel_requested", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("version", "INTEGER NOT NULL DEFAULT 1"),
    ("payload_enc", "TEXT"),
    ("payload_sha", "TEXT"),
    ("back_info", "TEXT"),
    ("last_err", "TEXT"),
    ("tags", "TEXT NOT NULL DEFAULT '[]'"),
    ("queue", "TEXT NOT NULL DEFAULT ''"),
    ("owner", "TEXT NOT NULL DEFAULT ''"),
    ("team", "TEXT NOT NULL DEFAULT ''"),
    ("group_name", "TEXT NOT NULL DEFAULT ''"),
    ("extra_desc", "TEXT"),
    ("created_at", "TEXT NOT NULL"),
    ("updated_at", "TEXT NOT NULL"),
)


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
        # 迁移等锁上限（毫秒）：并发启动时把「建表 + 补列 + 版本」串行化，
        # 但绝不无限等；超时抛 StoreError 让调用方重试。
        self.migration_lock_timeout_ms = int(
            self.spec.get("migration_lock_timeout_ms")
            if self.spec.get("migration_lock_timeout_ms") is not None
            else _DEFAULT_MIGRATION_LOCK_TIMEOUT_MS)

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

    def migration_lock_sql(self):
        """迁移互斥语句 + 参数：`pg_advisory_xact_lock(namespace, hashtext(table))`。

        为什么必须用它（BUG-368，实测）：多个 worker 同时启动时，各进程的 `init_schema`
        都会跑「建表 + 29 条 ALTER TABLE + 3 条版本语句」；这些 DDL 各自要取表的
        AccessExclusiveLock，交错执行就会互相等成死锁 —— 实测「10 轮 × 4 会话同时
        create_store」→ **20 次失败，全部是 deadlock detected**。

        * **事务级锁**（`_xact_`）：随 COMMIT/ROLLBACK 自动释放，无需手动 unlock，
          因此调用点必须在本方法所在的同一个事务里；
        * **两段式**：第一段固定命名空间，第二段 `hashtext(表名)` —— 不同表互不阻塞，
          也不与同实例上其它应用的单段 advisory lock 撞键；
        * hashtext 的理论碰撞只会导致「两张无关表偶然串行化」，不影响正确性。
        """
        return ("SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))",
                (_MIGRATION_LOCK_NAMESPACE, self.table))

    def init_schema(self) -> None:
        """建表 + 建索引 + 幂等补列（旧库自愈，BUG-362）。

        并发启动安全（BUG-368）：整个迁移在**一个事务**里，开头先取事务级 advisory lock
        串行化，再用 `SET LOCAL lock_timeout` 给「拿锁 + 后续 DDL」设上限 ——
        拿不到锁时抛可读的 StoreError（提示另一个会话正在迁移、可重试），不无限等。
        单进程/无竞争时只多一次 advisory lock（亚毫秒级），行为与之前一致。
        """
        timeout_ms = max(0, int(self.migration_lock_timeout_ms))
        lock_sql, lock_params = self.migration_lock_sql()
        try:
            with self._conn.cursor() as cur:
                # SET LOCAL 只作用于本事务；0 = 不设上限（旧行为）
                if timeout_ms > 0:
                    cur.execute("SET LOCAL lock_timeout = %s", ("%dms" % timeout_ms,))
                cur.execute(lock_sql, lock_params)
                cur.execute(self.schema_sql())
                for stmt in self.migration_sql():
                    cur.execute(stmt)
                for stmt in self.schema_version_sql():
                    cur.execute(stmt)
            self._conn.commit()
        except Exception as exc:
            try:
                self._conn.rollback()
            except Exception:
                pass
            if _is_lock_timeout(exc):
                raise StoreError(
                    "初始化 PostgreSQL 表 %s 时等锁超时（%dms）：另一个会话正在做同样的"
                    "建表/迁移。并发启动会短暂串行化（属正常现象），请稍后重试；"
                    "若频繁发生，可调大 spec.migration_lock_timeout_ms。%s"
                    % (self.table, timeout_ms, exc))
            raise StoreError("初始化 PostgreSQL 表 %s 失败: %s" % (self.table, exc))

    def schema_sql(self) -> str:
        """建表 + 建索引 SQL（列定义来自 _COLUMN_DDL，表名动态且已校验）。"""
        table = self.table
        ip = "idx_%s" % table
        cols = ",\n".join(
            "            %-17s %s" % (name, ddl) for name, ddl in _COLUMN_DDL)
        head = """
        CREATE TABLE IF NOT EXISTS {table} (
%s
        );
""" % cols
        indexes = """
        CREATE INDEX IF NOT EXISTS {ip}_state       ON {table}(state);
        CREATE INDEX IF NOT EXISTS {ip}_priority    ON {table}(priority);
        CREATE INDEX IF NOT EXISTS {ip}_lock_time   ON {table}(lock_time);
        CREATE INDEX IF NOT EXISTS {ip}_scheduled   ON {table}(scheduled_at);
        CREATE INDEX IF NOT EXISTS {ip}_worker      ON {table}(worker_id);
        CREATE INDEX IF NOT EXISTS {ip}_type        ON {table}(task_type);
        CREATE INDEX IF NOT EXISTS {ip}_queue       ON {table}(queue);
        """
        return (head + indexes).format(table=table, ip=ip)

    def migration_sql(self) -> List[str]:
        """旧表自愈（BUG-362）：对每列发一条幂等 ADD COLUMN IF NOT EXISTS。

        ``CREATE TABLE IF NOT EXISTS`` 不会给既有表补列，TASK_COLUMNS 演进后
        老库会缺列（INSERT 响亮失败）或列序漂移。这里在启动时按 _COLUMN_DDL
        逐列补齐；NOT NULL 且无 DEFAULT 的列补 ``DEFAULT ''``，否则非空表加列会失败。
        """
        out = []
        for name, ddl in _COLUMN_DDL:
            if name in _MIGRATION_SKIP:
                continue  # 身份列不迁移：SERIAL 主键无法 ADD COLUMN；task_name 有 UNIQUE 且是逻辑主键
            frag = ddl
            if "NOT NULL" in frag and "DEFAULT" not in frag:
                frag += " DEFAULT ''"
            out.append("ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s" % (
                self.table, name, frag))
        return out

    def _meta_table(self) -> str:
        """版本元数据表名（与业务表同前缀，便于清理时成对处理）。

        标识符由配置的表名派生，后者在 config 层已校验（``^[A-Za-z_][A-Za-z0-9_]*$``）。
        """
        return "%s_schema_meta" % self.table

    def schema_version_sql(self) -> List[str]:
        """schema 版本标记：建元数据表 + 首启写入版本 + 落后时推进。

        三句都幂等：重复启动不新增行、不回退版本；版本推进只在
        ``version < _SCHEMA_VERSION`` 时发生（升级方向单向）。
        """
        meta = self._meta_table()
        return [
            "CREATE TABLE IF NOT EXISTS %s (version INTEGER NOT NULL)" % meta,
            "INSERT INTO %s (version) SELECT %d "
            "WHERE NOT EXISTS (SELECT 1 FROM %s)" % (meta, _SCHEMA_VERSION, meta),
            "UPDATE %s SET version = %d WHERE version < %d"
            % (meta, _SCHEMA_VERSION, _SCHEMA_VERSION),
        ]

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": "postgres",
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "table": self.table,
            "user": self.user,
            "columns": len(_COLUMN_DDL),
            "schema_version": _SCHEMA_VERSION,
            "meta_table": self._meta_table(),
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
                    "SELECT %s FROM %s WHERE task_name = %%s" % (_SELECT_COLS, self.table),
                    (task_name,))
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
                    "SELECT %s FROM %s WHERE state IN (%%s, %%s) AND cancel_requested = FALSE "
                    "AND (scheduled_at IS NULL OR scheduled_at <= %%s) "
                    "ORDER BY priority DESC, task_id ASC LIMIT %%s"
                    % (_SELECT_COLS, self.table),
                    (TaskState.PENDING, TaskState.RETRY_PENDING, now_iso, self.claim_scan_limit))
                rows = cur.fetchall()
                for row in rows:
                    rec = TaskRecord.from_row(dict(zip(TASK_COLUMNS, row)))
                    if rec.deps and not set(rec.deps).issubset(done):
                        continue
                    row_ttl = max(ttl, float(rec.timeout_min or 0) * 60.0)
                    row_expire = iso_add_seconds(now_iso, row_ttl)
                    # 原子领取：带状态守卫的 UPDATE
                    update_sql = (
                        "UPDATE %s SET state = %%s, worker_id = %%s, lock_time = %%s, "
                        "expire_time = %%s, version = version + 1, updated_at = %%s "
                        "WHERE task_id = %%s AND state IN (%%s, %%s) "
                        "AND cancel_requested = FALSE RETURNING " + _SELECT_COLS) % self.table
                    cur.execute(
                        update_sql,
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
        """回收失效锁（LOCKED→PENDING，RUNNING→RETRY_PENDING / FAILED）。

        语义与 sqlite 后端逐字一致（契约见 ``base.TaskStore.clean_stale_locks``）：
        ``RUNNING`` 回收计入重试预算（BUG-366，毒任务最终 MUST 落 FAILED），
        ``LOCKED`` 回收只回 PENDING、不计数。
        """
        now_iso = now or utcnow_iso()
        timeout = abs(float(lock_timeout_sec if lock_timeout_sec is not None else self.lock_ttl_sec))
        cutoff = iso_add_seconds(now_iso, -timeout)
        try:
            with self._conn.cursor() as cur:
                # PostgreSQL 的 SET 子句同样按「更新前的行值」求值，四个 CASE 互不干扰。
                cur.execute(
                    "UPDATE %s SET "
                    "state = CASE "
                    "  WHEN state = %%s THEN %%s "
                    "  WHEN retry_count < max_retries THEN %%s "
                    "  ELSE %%s END, "
                    "retry_count = retry_count + CASE WHEN state = %%s THEN 1 ELSE 0 END, "
                    "last_err = CASE WHEN state = %%s THEN %%s ELSE last_err END, "
                    "end_time = CASE WHEN state = %%s THEN %%s ELSE end_time END, "
                    "lock_time = NULL, worker_id = NULL, updated_at = %%s, version = version + 1 "
                    "WHERE state IN (%%s, %%s) AND ("
                    "  (expire_time IS NOT NULL AND expire_time < %%s) OR "
                    "  (expire_time IS NULL AND lock_time IS NOT NULL AND lock_time < %%s))"
                    % self.table,
                    (TaskState.LOCKED, TaskState.PENDING,
                     TaskState.RETRY_PENDING, TaskState.FAILED,
                     TaskState.RUNNING,
                     TaskState.RUNNING, LEASE_RECLAIM_LAST_ERR,
                     TaskState.RUNNING, now_iso,
                     now_iso,
                     TaskState.LOCKED, TaskState.RUNNING,
                     now_iso, cutoff))
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
                    "SELECT %s FROM %s WHERE task_name = %%s" % (_SELECT_COLS, self.table),
                    (rec.task_name,))
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
                    "SELECT %s FROM %s WHERE task_name = %%s" % (_SELECT_COLS, self.table),
                    (task_name,))
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
                    "SELECT %s FROM %s WHERE task_name = %%s" % (_SELECT_COLS, self.table),
                    (task_name,))
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
        sql = "SELECT %s FROM %s" % (_SELECT_COLS, self.table)
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
