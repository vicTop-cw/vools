# -*- coding: utf-8 -*-
"""PG 后端 retry_delay_min 真实退避的**集成**验证（BUG-231）。

本机可达的 PostgreSQL 上真跑（不 mock）：
  - schema 里有 next_retry_at
  - fail() 写退避 → acquire() 领不到
  - 人工 retry() 清退避 → 立刻可领
  - 退避到期 → 可领
  - 达到上限转 FAILED → 退避清空
  - **旧表迁移**：先建无 next_retry_at 的旧 schema 表，PgTaskBackend 初始化后
    应通过 ALTER TABLE ... ADD COLUMN IF NOT EXISTS 幂等补齐

连接串优先级：环境变量 ``VOOLS_TEST_PG_DSN``，否则默认本机
``host=127.0.0.1 port=5432 user=postgres password=123456 dbname=postgres``。
不可达时整文件 skip（不让无 PG 的环境变红）。
"""

import os
import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")

DSN = os.environ.get(
    "VOOLS_TEST_PG_DSN",
    "host=127.0.0.1 port=5432 user=postgres password=123456 dbname=postgres",
)


def _pg_available() -> bool:
    try:
        conn = psycopg2.connect(DSN, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason="本机 PostgreSQL 不可达（可用 VOOLS_TEST_PG_DSN 指定连接串）",
)


def _drop(table: str):
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute('DROP TABLE IF EXISTS "{}" CASCADE'.format(table))
        cur.execute('DROP TABLE IF EXISTS "{}_edges" CASCADE'.format(table))
        cur.close()
    finally:
        conn.close()


@pytest.fixture()
def backend(request):
    from vools.task.backends.pg import PgTaskBackend

    table = "vic_retry_test_{}".format(uuid.uuid4().hex[:10])
    b = PgTaskBackend(DSN, table=table, max_retries=3, retry_delay_min=5)
    b.init_table(drop_if_exists=True)
    yield b
    b.close()
    _drop(table)


def _fail_once(b):
    tid = b.submit("flaky", {"v": 1})
    t = b.acquire("w1")
    assert t is not None and t["id"] == tid
    b.fail(tid, "w1", "boom")
    return tid


def test_schema_has_next_retry_at(backend):
    rows = backend.query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=%s AND column_name='next_retry_at'", [backend.table])
    assert rows, "next_retry_at 列缺失"


def test_fail_sets_backoff_and_blocks_acquire(backend):
    tid = _fail_once(backend)
    snap = backend.get(tid)
    assert snap["status"] == "RETRY_PENDING"
    assert snap["next_retry_at"] is not None
    assert backend.acquire("w1") is None, "退避期内不应被再次领取（热循环防护失效）"


def test_manual_retry_clears_backoff(backend):
    tid = _fail_once(backend)
    backend.retry(tid)
    snap = backend.get(tid)
    assert snap["status"] == "READY"
    assert snap["next_retry_at"] is None
    got = backend.acquire("w1")
    assert got is not None and got["id"] == tid


def test_expired_backoff_is_acquirable(backend):
    tid = _fail_once(backend)
    assert backend.acquire("w1") is None
    # 把退避时间改到过去，模拟到期（用直连执行 UPDATE：PgTaskBackend.query
    # 是为 SELECT 设计的，对无结果集的 UPDATE 会 fetchall 报错）
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            'UPDATE "{}" SET next_retry_at=CURRENT_TIMESTAMP - INTERVAL \'1 minute\' '
            "WHERE id=%s".format(backend.table), (tid,))
        cur.close()
    finally:
        conn.close()
    got = backend.acquire("w1")
    assert got is not None and got["id"] == tid


def test_final_failure_clears_backoff():
    from vools.task.backends.pg import PgTaskBackend

    table = "vic_retry_fin_{}".format(uuid.uuid4().hex[:10])
    b = PgTaskBackend(DSN, table=table, max_retries=1, retry_delay_min=5)
    try:
        b.init_table(drop_if_exists=True)
        tid = b.submit("t", {})
        b.acquire("w1")
        b.fail(tid, "w1", "boom")
        snap = b.get(tid)
        assert snap["status"] == "FAILED"
        assert snap["next_retry_at"] is None
    finally:
        b.close()
        _drop(table)


def test_migration_adds_column_to_old_table():
    """旧表（缺 next_retry_at）打开后应幂等补列，且补列后退避功能可用。"""
    from vools.task.backends.pg import PgTaskBackend

    table = "vic_retry_old_{}".format(uuid.uuid4().hex[:10])
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        # 手工建「旧 schema」表（无 next_retry_at）
        cur.execute(
            'CREATE TABLE "{}" ('
            " id BIGSERIAL PRIMARY KEY,"
            " task_name VARCHAR(255) NOT NULL,"
            " task_type VARCHAR(32) NOT NULL DEFAULT 'PYTHON',"
            " task_value VARCHAR(255),"
            " payload JSONB,"
            " status VARCHAR(32) NOT NULL DEFAULT 'PENDING',"
            " priority INTEGER NOT NULL DEFAULT 0,"
            " retry_count INTEGER NOT NULL DEFAULT 0,"
            " max_retries INTEGER NOT NULL DEFAULT 3,"
            " error_message TEXT,"
            " back_info JSONB,"
            " dependencies JSONB NOT NULL DEFAULT '[]',"
            " worker_id VARCHAR(128),"
            " locked_by VARCHAR(128),"
            " lease_timeout TIMESTAMP,"
            " ts TIMESTAMP,"
            " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            " updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            " started_at TIMESTAMP,"
            " completed_at TIMESTAMP)".format(table))
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name=%s AND column_name='next_retry_at'", (table,))
        assert cur.fetchone()[0] == 0
        cur.close()
    finally:
        conn.close()

    b = PgTaskBackend(DSN, table=table, retry_delay_min=5)
    try:
        b.init_table()          # CREATE IF NOT EXISTS + ALTER ADD COLUMN IF NOT EXISTS
        rows = b.query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s AND column_name='next_retry_at'", [table])
        assert rows, "迁移未补上 next_retry_at 列"
        # 迁移后行为正常
        tid = b.submit("t", {})
        b.acquire("w1")
        b.fail(tid, "w1", "x")
        assert b.get(tid)["next_retry_at"] is not None
        assert b.acquire("w1") is None
    finally:
        b.close()
        _drop(table)
