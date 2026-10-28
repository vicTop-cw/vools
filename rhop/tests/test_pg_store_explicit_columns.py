# -*- coding: utf-8 -*-
"""PG 后端列映射回归：禁止 ``SELECT *`` + 位置 zip（BUG-361）。

背景
----
``PgTaskStore`` 早期写法是 ``SELECT * FROM t`` + ``dict(zip(TASK_COLUMNS, row))``。
psycopg2 返回的是**按物理列序**的元组，因此这条链路的正确性隐含依赖：

    PG 表的物理列序 == TASK_COLUMNS 的声明顺序

``CREATE TABLE IF NOT EXISTS`` 不会迁移既有表；一旦 TASK_COLUMNS 追加/调整列
（本仓库 31 列且仍在演进），旧库的物理列序就可能与 TASK_COLUMNS 不一致，
``zip`` 会把值静默塞进错误的字段（同类型列对调时连异常都没有）。

修复：所有读取路径改成显式列清单 ``SELECT <cols> FROM ...`` / ``RETURNING <cols>``，
使返回顺序由语句决定，而不是由表结构历史决定。

本文件用**假 DB-API 层**（不需要真实 PG）验证：

1. 存储层发出的查询请求的是显式列，返回顺序因此可控；
2. 即便底层行按"旧物理列序"返回，读出的 TaskRecord 字段也不会错位；
3. 静态守卫：源码里不允许再出现 ``SELECT *`` / ``RETURNING *``。
"""

from __future__ import absolute_import

import io
import os
import re

import pytest

from vools.rhop.task.models import TASK_COLUMNS, TaskRecord, TaskState
from vools.rhop.task.store.pg_store import PgTaskStore

PG_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vools", "rhop", "task", "store", "pg_store.py")

#: 模拟"旧版表"的物理列序：worker_id 与 owner 两列位置对调。
#: 两者都是 TEXT，对调后完全同型，正是最危险的一类错位（不抛异常）。
_LEGACY_ORDER = list(TASK_COLUMNS)
_i_worker = _LEGACY_ORDER.index("worker_id")
_i_owner = _LEGACY_ORDER.index("owner")
_LEGACY_ORDER[_i_worker], _LEGACY_ORDER[_i_owner] = _LEGACY_ORDER[_i_owner], _LEGACY_ORDER[_i_worker]
assert _LEGACY_ORDER != list(TASK_COLUMNS)


def _sample_row():
    rec = TaskRecord(task_name="job-x", state=TaskState.PENDING, priority=7,
                     worker_id="worker-1", owner="alice",
                     back_info='{"result":"ok"}', last_err="boom")
    return rec.to_row()


class _FakeCursor(object):
    """最小 DB-API 游标：按 SQL 请求的列序返回元组。

    - ``SELECT *``  → 按"旧物理列序"返回（模拟历史表结构）
    - ``SELECT c1, c2, ...`` → 按语句里声明的列序返回
    - ``UPDATE ... RETURNING c1, ...`` → 同样按 RETURNING 声明的列序返回
    """

    def __init__(self, conn):
        self._conn = conn
        self._rows = []
        self.rowcount = 0
        self.issued = []

    # -- 上下文管理 --
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    # -- 执行 --
    def execute(self, sql, params=None):
        self.issued.append((sql, params))
        self._conn.issued.append((sql, params))
        flat = re.sub(r"\s+", " ", sql).strip()
        self._rows = []
        self.rowcount = 0
        if re.match(r"(?i)^select", flat):
            cols = self._select_columns(flat)
            self._rows = [tuple(self._conn.row[c] for c in cols)]
        elif re.match(r"(?i)^update", flat) and "returning" in flat.lower():
            cols = self._returning_columns(flat)
            self._rows = [tuple(self._conn.row[c] for c in cols)]
            self.rowcount = 1
        elif re.match(r"(?i)^(insert|update|delete)", flat):
            self.rowcount = 1

    @staticmethod
    def _select_columns(flat):
        expr = re.search(r"(?is)^select (.+?) from ", flat).group(1).strip()
        return _LEGACY_ORDER if expr == "*" else [c.strip() for c in expr.split(",")]

    @staticmethod
    def _returning_columns(flat):
        expr = re.split(r"(?i)returning ", flat, maxsplit=1)[1].strip()
        return _LEGACY_ORDER if expr.startswith("*") else [c.strip() for c in expr.split(",")]

    # -- 取值 --
    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn(object):
    """最小连接：一条固定行 + 由它派生出的列序无关读。"""

    def __init__(self):
        self.row = _sample_row()
        self.issued = []
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        pass


def _fresh_store():
    """绕过 __init__（不连真库），直接注入假连接与所需属性。"""
    store = PgTaskStore.__new__(PgTaskStore)
    store.table = "t_tasks"
    store.lock_ttl_sec = 600
    store.claim_scan_limit = 50
    store._conn = _FakeConn()
    return store


# ----------------------------------------------------------------------
# 1. 行为：即便底层行是"旧物理列序"，读出也不错位
# ----------------------------------------------------------------------

def test_get_task_maps_by_explicit_column_list():
    store = _fresh_store()
    rec = store.get_task("job-x")

    assert rec is not None
    assert rec.worker_id == "worker-1"
    assert rec.owner == "alice"
    assert rec.back_info == '{"result":"ok"}'
    assert rec.last_err == "boom"


def test_list_tasks_maps_by_explicit_column_list():
    store = _fresh_store()
    rows = store.list_tasks(limit=10)

    assert len(rows) == 1
    assert rows[0].worker_id == "worker-1"
    assert rows[0].owner == "alice"
    assert rows[0].task_name == "job-x"


def test_claim_next_returning_maps_by_explicit_column_list():
    store = _fresh_store()
    rec = store.claim_next("worker-2")

    assert rec is not None
    assert rec.state == TaskState.LOCKED
    assert rec.worker_id == "worker-2"      # claim 显式写入的 worker
    assert rec.task_name == "job-x"
    assert rec.owner == "alice"             # 未被 worker_id 串味


def test_all_issued_queries_avoid_star():
    """存储层发出的每条 SELECT/UPDATE RETURNING 都点名了列。"""
    store = _fresh_store()
    store.get_task("job-x")
    store.list_tasks(limit=5)
    store.claim_next("worker-2")

    issued = [" ".join(sql.split()).lower() for sql, _ in store._conn.issued]
    assert issued, "假连接没有记录到任何语句"
    assert all("select *" not in s for s in issued), "存在 SELECT *"
    assert all("returning *" not in s for s in issued), "存在 RETURNING *"


# ----------------------------------------------------------------------
# 2. 控制组：证明"旧写法"确实会错位（否则上面的测试没有意义）
# ----------------------------------------------------------------------

def test_old_positional_zip_would_swap_same_typed_columns():
    row_by_name = _sample_row()
    legacy_row = tuple(row_by_name[c] for c in _LEGACY_ORDER)

    old_way = TaskRecord.from_row(dict(zip(TASK_COLUMNS, legacy_row)))

    assert old_way.worker_id == "alice"
    assert old_way.owner == "worker-1"
    assert (old_way.worker_id, old_way.owner) != ("worker-1", "alice")


# ----------------------------------------------------------------------
# 3. 静态守卫：源码不允许再出现 SELECT * / RETURNING *
# ----------------------------------------------------------------------

def test_pg_store_source_has_no_select_star():
    src = io.open(PG_STORE_PATH, encoding="utf-8").read()
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.strip().startswith("#") and not ln.strip().startswith("--")
    ]
    joined = "\n".join(code_lines)

    assert "SELECT *" not in joined, "pg_store 仍存在 SELECT *，列映射会依赖表物理列序"
    assert "RETURNING *" not in joined, "pg_store 仍存在 RETURNING *，列映射会依赖表物理列序"


def test_schema_column_order_matches_task_columns():
    """建表语句的列序应与 TASK_COLUMNS 一致（新库天然对齐；不一致即提示重排风险）。"""
    store = _fresh_store()
    block = store.schema_sql().split("CREATE TABLE IF NOT EXISTS %s (" % store.table, 1)[1].split(");", 1)[0]
    cols = []
    for line in block.strip().splitlines():
        name = line.split()[0] if line.split() else ""
        if re.match(r"^[a-z_]+$", name):
            cols.append(name)
    assert tuple(cols) == tuple(TASK_COLUMNS)
