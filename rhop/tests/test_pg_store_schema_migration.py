# -*- coding: utf-8 -*-
"""PG 旧库自愈迁移回归（BUG-362）。

背景
----
``CREATE TABLE IF NOT EXISTS`` 对**既有表**是空操作：TASK_COLUMNS 演进后，
老库既不会补列，也不会报警——缺列时 INSERT 响亮失败，列序/语义漂移时更难诊断。

修复：把列定义收敛成单一来源 ``_COLUMN_DDL``，启动时在建表之后逐列发幂等
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``：

* 身份列（task_id / task_name）跳过——任何版本的表都有，补列反而引入
  SERIAL / UNIQUE 冲突；
* ``NOT NULL`` 且无 ``DEFAULT`` 的列补 ``DEFAULT ''``，否则非空表加列会失败。

本文件用假连接验证**发出的语句**（不需要真实 PG）。
"""

from __future__ import absolute_import

import pytest

from vools.rhop.task.errors import StoreError
from vools.rhop.task.models import TASK_COLUMNS
from vools.rhop.task.store.pg_store import (
    PgTaskStore,
    _COLUMN_DDL,
    _MIGRATION_SKIP,
    _SCHEMA_VERSION,
)


class _RecordingCursor(object):
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._conn.statements.append(sql)

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _RecordingConn(object):
    def __init__(self):
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _RecordingCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _store():
    store = PgTaskStore.__new__(PgTaskStore)
    store.table = "t_tasks"
    store.host = "127.0.0.1"
    store.port = 5432
    store.dbname = "postgres"
    store.user = "postgres"
    store.lock_ttl_sec = 600
    store.claim_scan_limit = 50
    store._conn = _RecordingConn()
    return store


# ----------------------------------------------------------------------
# 1. 迁移覆盖面：除身份列外，每一列都必须有补列语句
# ----------------------------------------------------------------------

def test_migration_covers_every_non_identity_column():
    store = _store()
    stmts = store.migration_sql()

    covered = set()
    for stmt in stmts:
        covered.add(stmt.split("ADD COLUMN IF NOT EXISTS ", 1)[1].split(" ", 1)[0])

    # 独立探针：白名单本身被写死在这里，不从被测模块读取，
    # 否则「少覆盖一列」的变异会同时改变 expectation 而逃过检测。
    assert tuple(_MIGRATION_SKIP) == ("task_id", "task_name")
    expected = set(TASK_COLUMNS) - {"task_id", "task_name"}
    assert covered == expected, "未覆盖: %s" % sorted(expected - covered)
    assert "task_id" not in covered
    assert "task_name" not in covered


def test_migration_statements_are_idempotent_alters():
    store = _store()
    for stmt in store.migration_sql():
        assert stmt.startswith("ALTER TABLE t_tasks ADD COLUMN IF NOT EXISTS "), stmt
        assert "DROP" not in stmt.upper(), "迁移不得包含破坏性语句"


def test_migration_not_null_columns_carry_default():
    """非空表加 NOT NULL 列必须带 DEFAULT，否则 ALTER 会失败。"""
    store = _store()
    for stmt in store.migration_sql():
        tail = stmt.split(" IF NOT EXISTS ", 1)[1]
        frag = tail.split(" ", 1)[1]
        if "NOT NULL" in frag:
            assert "DEFAULT" in frag, "缺 DEFAULT: %s" % stmt


def test_migration_types_match_create_table():
    store = _store()
    create_block = store.schema_sql().split("CREATE TABLE IF NOT EXISTS t_tasks (", 1)[1].split(");", 1)[0]
    from_create = {}
    for line in create_block.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in TASK_COLUMNS:
            from_create[parts[0]] = parts[1].rstrip(",")

    for stmt in store.migration_sql():
        rest = stmt.split(" IF NOT EXISTS ", 1)[1]
        name, frag = rest.split(" ", 1)
        assert frag.split()[0] == from_create[name], "列 %s 类型与建表不一致" % name


# ----------------------------------------------------------------------
# 2. init_schema：先建表再逐列补，一次性提交
# ----------------------------------------------------------------------

def test_init_schema_executes_create_then_all_migrations():
    store = _store()
    store.init_schema()

    stmts = store._conn.statements
    assert stmts, "没有发出任何语句"
    assert "CREATE TABLE IF NOT EXISTS t_tasks" in stmts[0]
    alters = [s for s in stmts if s.startswith("ALTER TABLE t_tasks ADD COLUMN IF NOT EXISTS ")]
    assert len(alters) == len(store.migration_sql())
    assert store._conn.commits == 1
    assert store._conn.rollbacks == 0


def test_init_schema_rolls_back_on_failure():
    store = _store()

    class _Boom(object):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            raise RuntimeError("boom")

    store._conn.cursor = lambda: _Boom()
    with pytest.raises(StoreError):
        store.init_schema()
    assert store._conn.rollbacks == 1


# ----------------------------------------------------------------------
# 3. 可观测性：describe() 暴露列数
# ----------------------------------------------------------------------

def test_describe_reports_column_count():
    store = _store()
    assert store.describe()["columns"] == len(_COLUMN_DDL)
    assert store.describe()["table"] == "t_tasks"


# ----------------------------------------------------------------------
# 4. schema 版本标记（PG 无 PRAGMA user_version，用元数据表承载）
# ----------------------------------------------------------------------

def test_schema_version_statements_bootstrap_meta_table():
    store = _store()
    stmts = store.schema_version_sql()

    assert len(stmts) == 3
    assert stmts[0] == (
        "CREATE TABLE IF NOT EXISTS t_tasks_schema_meta (version INTEGER NOT NULL)")
    assert "INSERT INTO t_tasks_schema_meta (version) SELECT %d" % _SCHEMA_VERSION in stmts[1]
    assert "WHERE NOT EXISTS" in stmts[1]
    assert stmts[2] == "UPDATE t_tasks_schema_meta SET version = %d WHERE version < %d" % (
        _SCHEMA_VERSION, _SCHEMA_VERSION)


def test_schema_version_is_forward_only():
    """版本推进必须单向：不得出现把版本写小的语句。"""
    store = _store()
    for stmt in store.schema_version_sql():
        if "UPDATE" in stmt:
            assert "version <" in stmt, "版本回退语句: %s" % stmt
            assert ">=" not in stmt


def test_meta_table_name_derived_from_business_table():
    store = _store()
    assert store._meta_table() == "t_tasks_schema_meta"
    store.table = "odd_name"
    assert store._meta_table() == "odd_name_schema_meta"


def test_init_schema_writes_version_after_migrations():
    store = _store()
    store.init_schema()
    stmts = store._conn.statements

    version_stmts = store.schema_version_sql()
    assert stmts[-len(version_stmts):] == version_stmts, "版本语句必须在补列之后"
    assert store._conn.commits == 1


def test_describe_exposes_schema_version():
    store = _store()
    d = store.describe()
    assert d["schema_version"] == _SCHEMA_VERSION
    assert d["meta_table"] == "t_tasks_schema_meta"
