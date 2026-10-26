# -*- coding: utf-8 -*-
"""回归锁：三后端 ``retry_delay_min`` 的真实退避（BUG-231）。

缺陷原形：``retry_delay_min`` 三后端构造时收下并校验，但**从不消费**——
``fail()`` 后任务立即置 RETRY_PENDING，``acquire()`` 立刻能再领取，失败任务
热循环打库（docstring 自述「仅为 API 兼容占位，不影响重试时序」）。

修复：``fail()`` 在还有重试次数时写 ``next_retry_at = now + N 分钟``，
``acquire()`` 跳过未到期项，``retry()``（人工）清空退避立即放行，``0`` = 不退避。
"""

import os
import sqlite3
import sys
import tempfile
import time

import pytest

from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend

BACKENDS = ["memory", "sqlite"]


def _make(kind, retry_delay_min=5, max_retries=3):
    """构造指定后端；sqlite 用临时库。"""
    if kind == "memory":
        b = MemoryTaskBackend(max_retries=max_retries,
                              retry_delay_min=retry_delay_min)
        b.init_table()
        return b
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    b = SqliteTaskBackend(db_path=path, max_retries=max_retries,
                          retry_delay_min=retry_delay_min)
    b.init_table()
    return b


def _fail_once(b):
    """提交一个任务 → 领取 → 失败一次，返回 (tid, 任务快照)。"""
    tid = b.submit("flaky", {"v": 1})
    t = b.acquire("w1")
    assert t is not None and t["id"] == tid
    b.fail(tid, "w1", "boom")
    return tid, b.get(tid)


@pytest.mark.parametrize("kind", BACKENDS)
def test_delay_blocks_immediate_reacquire(kind):
    """retry_delay_min=5：fail 后不得立刻被再领取（防热循环）。"""
    b = _make(kind, retry_delay_min=5)
    tid, snap = _fail_once(b)
    assert snap["status"] == "RETRY_PENDING"
    # 退避时间已写入（memory 是 datetime，sqlite 是字符串，统一只断言非空）
    assert snap.get("next_retry_at") is not None
    # 立刻领取：不许拿到这条任务
    assert b.acquire("w1") is None


@pytest.mark.parametrize("kind", BACKENDS)
def test_zero_delay_allows_immediate_reacquire(kind):
    """retry_delay_min=0：保持旧行为，失败后可立即再领取。"""
    b = _make(kind, retry_delay_min=0)
    tid, snap = _fail_once(b)
    assert snap["status"] == "RETRY_PENDING"
    assert snap.get("next_retry_at") is None
    t = b.acquire("w1")
    assert t is not None and t["id"] == tid


@pytest.mark.parametrize("kind", BACKENDS)
def test_manual_retry_clears_backoff(kind):
    """人工 retry()=立即放行：清空 next_retry_at 且转 READY。"""
    b = _make(kind, retry_delay_min=5)
    tid, _ = _fail_once(b)
    b.retry(tid)
    snap = b.get(tid)
    assert snap["status"] == "READY"
    assert snap.get("next_retry_at") is None
    t = b.acquire("w1")
    assert t is not None and t["id"] == tid


@pytest.mark.parametrize("kind", BACKENDS)
def test_expired_backoff_becomes_acquirable(kind):
    """退避到期后必须能领取（把 next_retry_at 改到过去模拟时间流逝）。"""
    b = _make(kind, retry_delay_min=5)
    tid, _ = _fail_once(b)
    assert b.acquire("w1") is None
    if kind == "memory":
        # 直接把退避时间挪到过去
        b._tasks[tid]["next_retry_at"] = b._tasks[tid]["next_retry_at"].replace(
            year=2000)
    else:
        with b._lock, b._conn:
            b._conn.execute(
                'UPDATE "{}" SET next_retry_at=? WHERE id=?'.format(b.table),
                ("2000-01-01 00:00:00", tid))
    t = b.acquire("w1")
    assert t is not None and t["id"] == tid


def test_final_failure_clears_backoff():
    """达到重试上限转 FAILED 时不应残留退避时间。"""
    b = _make("memory", retry_delay_min=5, max_retries=1)
    tid, snap = _fail_once(b)
    assert snap["status"] == "FAILED"
    assert snap.get("next_retry_at") is None


def test_sqlite_old_db_migration_adds_column():
    """旧库（无 next_retry_at 列）打开后应幂等补列。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # 手工建一张「旧 schema」表（缺 next_retry_at）
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE "vic_tasks_task" (
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
            """
        )
        conn.commit()
        conn.close()

        b = SqliteTaskBackend(db_path=path, retry_delay_min=5)
        cols = {r[1] for r in b._conn.execute(
            'PRAGMA table_info("{}")'.format(b.table)).fetchall()}
        assert "next_retry_at" in cols
        # 迁移后功能可用：fail 会写入退避
        tid = b.submit("t", {})
        b.acquire("w1")
        b.fail(tid, "w1", "x")
        assert b.get(tid)["next_retry_at"] is not None
        b.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(path + suffix)
            except OSError:
                pass


def test_delay_is_minutes_not_seconds():
    """单位是分钟：5 分钟退避的到期时间应远大于 1 秒后。"""
    from datetime import datetime

    b = _make("memory", retry_delay_min=5)
    tid, _ = _fail_once(b)
    nra = b._tasks[tid]["next_retry_at"]
    # memory 后端存 naive UTC datetime，必须与 utcnow() 比较
    delta = (nra - datetime.utcnow()).total_seconds()
    assert 250 < delta <= 300, f"5 分钟退避的剩余时间应落在 (250, 300]s，实测 {delta:.0f}s"
