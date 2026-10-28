# -*- coding: utf-8 -*-
"""PG 后端并发启动回归：``init_schema`` 的 DDL 不得互相死锁（BUG-368）。

背景（实测，不是推测）
----------------------
``PgTaskStore.__init__`` → ``init_schema()`` 会跑「建表 + 29 条 ``ALTER TABLE`` 补列 +
3 条版本元数据语句」。多个 worker / 多个进程**同时启动**时，这些 DDL 各自要取表的
``AccessExclusiveLock``，交错执行就会互相等待成死锁：

    10 轮 × 4 会话同时 create_store（表已存在 → 走 ALTER 迁移路径）
        → 20 次失败，**全部是 deadlock detected**

修复
----
``init_schema`` 开头在**同一个事务**里取事务级 advisory lock::

    SELECT pg_advisory_xact_lock(hashtext(<命名空间>), hashtext(<表名>))

把整个迁移串行化；同时 ``SET LOCAL lock_timeout = <spec.migration_lock_timeout_ms>ms``
（默认 5000）给「拿锁 + 后续 DDL」设上限，拿不到锁时抛**可读的** ``StoreError``
（提示另一个会话正在迁移、可重试），绝不无限等。

本文件用真实 PostgreSQL（无 PG 时整组 skip，与 ``test_pg_store.py`` 一致）：

1. ``test_concurrent_init_schema_does_not_deadlock`` —— 回归用例，改前必红；
2. ``test_init_schema_lock_timeout_reports_clear_error`` —— 超时保护（不是无限等）；
3. ``test_migration_lock_is_table_scoped`` —— 锁按表隔离，A 表迁移不阻塞 B 表；
4. ``test_single_process_repeated_init_is_idempotent`` —— 无竞争时行为不变。
"""

from __future__ import absolute_import

import os
import sys
import threading
import time
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pg_probe import pg_gate  # noqa: E402  （共享放行探针，见 tests/_pg_probe.py）

from vools.rhop.task.errors import StoreError
from vools.rhop.task.models import TASK_COLUMNS, TaskRecord
from vools.rhop.task.store import create_store
from vools.rhop.task.store.pg_store import (
    _DEFAULT_MIGRATION_LOCK_TIMEOUT_MS,
    _MIGRATION_LOCK_NAMESPACE,
)

PG_SPEC = {
    "kind": "postgres",
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "123456",
    "dbname": "postgres",
}
CTX = {"name": "pg-concurrency", "role": "B", "base_dir": "."}


_PG_ALLOWED, _PG_SKIP_REASON = pg_gate()

# 只在「探活阶段判定为不可靠」时 skip；放行之后用例里的真实失败仍然是 failure。
pytestmark = pytest.mark.skipif(not _PG_ALLOWED, reason=_PG_SKIP_REASON)


def _spec(table, **over):
    spec = dict(PG_SPEC)
    spec["table"] = table
    spec.update(over)
    return spec


def _connect():
    import psycopg2
    conn = psycopg2.connect(host=PG_SPEC["host"], port=PG_SPEC["port"],
                            user=PG_SPEC["user"], password=PG_SPEC["password"],
                            dbname=PG_SPEC["dbname"], connect_timeout=3)
    conn.autocommit = True
    return conn


def _drop(table):
    """删表 + 删 schema 元数据表（吞异常：清理失败不该让用例失败）。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS %s CASCADE" % table)
                cur.execute("DROP TABLE IF EXISTS %s_schema_meta CASCADE" % table)
        finally:
            conn.close()
    except Exception:
        pass


@pytest.fixture()
def tables():
    """按需发唯一表名，用例结束统一清理。"""
    made = []

    def new():
        name = "rhop_test_pg_conc_%s" % uuid.uuid4().hex[:12]
        made.append(name)
        return name

    yield new
    for name in made:
        _drop(name)


def _boot(table):
    """串行建一次表（让后续并发会话走「表已存在 → ALTER 迁移」这条死锁路径）。"""
    store = create_store(_spec(table), dict(CTX))
    store.close()


# ---------------------------------------------------------------------------
# 1) 回归主线：并发启动不再死锁
# ---------------------------------------------------------------------------

def test_concurrent_init_schema_does_not_deadlock(tables):
    table = tables()
    _boot(table)

    n_sessions = 4
    barrier = threading.Barrier(n_sessions)
    results = []
    lock = threading.Lock()

    def one(idx):
        try:
            barrier.wait(timeout=30)          # 对齐起跑：同时 init_schema
        except Exception:
            pass
        try:
            store = create_store(_spec(table), dict(CTX))
            try:
                store.insert_tasks([TaskRecord(task_name="probe-%d" % idx)])
                got = store.get_task("probe-%d" % idx)
                assert got is not None, "并发 init 后写入的任务读不回来"
            finally:
                store.close()
            outcome = ("ok", idx, "")
        except Exception as exc:             # noqa: BLE001 - 失败详情要原样报出来
            outcome = ("err", idx, "%s: %s" % (type(exc).__name__, str(exc)[:300]))
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n_sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    failures = [r for r in results if r[0] != "ok"]
    assert len(results) == n_sessions, "有会话既没成功也没报错: %r" % (results,)
    assert not failures, (
        "并发 init_schema 出现失败（BUG-368 回归）：%r" % (failures,))
    # 死锁在修复前是 deadlock detected；这里再兜一层：错误信息里不许出现死锁字样
    assert not any("deadlock" in r[2].lower() for r in failures)


# ---------------------------------------------------------------------------
# 2) 超时保护：拿不到锁时有明确错误，而不是无限等
# ---------------------------------------------------------------------------

def test_init_schema_lock_timeout_reports_clear_error(tables):
    table = tables()
    _boot(table)

    holder = _connect()
    try:
        with holder.cursor() as cur:
            # 会话级 advisory lock（与 init_schema 的事务级锁用同一组键）
            cur.execute("SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))",
                        (_MIGRATION_LOCK_NAMESPACE, table))
        started = time.time()
        with pytest.raises(StoreError) as excinfo:
            create_store(_spec(table, migration_lock_timeout_ms=150), dict(CTX))
        elapsed = time.time() - started
        msg = str(excinfo.value)
        assert "等锁超时" in msg, "错误信息应说明等锁超时而非裸 SQL 报错: %s" % msg
        assert "迁移" in msg, "错误信息应提示「另一个会话正在迁移」: %s" % msg
        # 150ms 的锁等待 + 建连，不该拖成无限等
        assert elapsed < 10, "等锁超时没有生效，耗时 %.1fs" % elapsed
    finally:
        try:
            with holder.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))",
                            (_MIGRATION_LOCK_NAMESPACE, table))
        finally:
            holder.close()


# ---------------------------------------------------------------------------
# 3) 锁按表隔离：A 表迁移不该阻塞 B 表
# ---------------------------------------------------------------------------

def test_migration_lock_is_table_scoped(tables):
    table_a = tables()
    table_b = tables()
    _boot(table_a)
    _boot(table_b)

    holder = _connect()
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))",
                        (_MIGRATION_LOCK_NAMESPACE, table_a))
        # A 的迁移锁被占着，但 B 是另一把锁 → 必须照常成功
        started = time.time()
        store = create_store(_spec(table_b, migration_lock_timeout_ms=3000), dict(CTX))
        store.close()
        elapsed = time.time() - started
        assert elapsed < 3.0, (
            "B 表 init_schema 被 A 表迁移锁阻塞（锁未按表隔离），耗时 %.1fs" % elapsed)
    finally:
        try:
            with holder.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))",
                            (_MIGRATION_LOCK_NAMESPACE, table_a))
        finally:
            holder.close()


# ---------------------------------------------------------------------------
# 4) 无竞争时行为不变：单进程重复 init 幂等
# ---------------------------------------------------------------------------

def test_single_process_repeated_init_is_idempotent(tables):
    table = tables()
    first = create_store(_spec(table), dict(CTX))
    columns = first.describe()["columns"]
    first.close()

    second = create_store(_spec(table), dict(CTX))
    try:
        assert second.describe()["columns"] == columns == len(TASK_COLUMNS)
        second.insert_tasks([TaskRecord(task_name="idem")])
        assert second.get_task("idem") is not None
    finally:
        second.close()


def test_default_lock_timeout_is_positive():
    """默认值必须是正数毫秒：0 代表「不设上限」，不该是默认。"""
    assert isinstance(_DEFAULT_MIGRATION_LOCK_TIMEOUT_MS, int)
    assert _DEFAULT_MIGRATION_LOCK_TIMEOUT_MS > 0
