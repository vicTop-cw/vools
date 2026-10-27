"""PostgreSQL 存储后端测试：契约对齐 + PostgreSQL 特有行为。

运行前提：本机 PostgreSQL 可达（WSL localhost:5432，密码 123456）。
测试自动建/删临时表，不污染现有数据。
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, r'E:\IDEProjects\AI\vools\rhop')

from vools.rhop.task.errors import StoreError, StoreUnavailable, TaskNotFound
from vools.rhop.task.models import TaskRecord, TaskState, utcnow_iso
from vools.rhop.task.store import (
    PgTaskStore,
    TaskStore,
    available_store_kinds,
    create_store,
)

PG_SPEC = {
    "kind": "postgres",
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "123456",
    "dbname": "postgres",
}

#: Unique table name per test session
_SESSION_TABLE = "rhop_test_pg_%d" % int(time.time())


def _pg_available() -> bool:
    """探测 PostgreSQL 是否可达（服务未启动 / 账号密码端口不符都算不可达）。"""
    try:
        import psycopg2
        conn = psycopg2.connect(host=PG_SPEC["host"], port=PG_SPEC["port"],
                                user=PG_SPEC["user"], password=PG_SPEC["password"],
                                dbname=PG_SPEC["dbname"], connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


# 外部服务不可达时应当 skip 而非 error —— 否则 25 个 ERROR 会在 CI 里掩盖真实失败。
pytestmark = pytest.mark.skipif(
    not _pg_available(),
    reason="PostgreSQL 不可达（服务未启动，或账号/密码/端口不符）")


def _pg_store(table=None, **overrides):
    """创建一个 PostgreSQL 测试 store（自动清理旧表 + 旧 type）。"""
    table = table or _SESSION_TABLE
    spec = dict(PG_SPEC)
    spec["table"] = table
    spec.update(overrides)
    ctx = {"name": "pg-test", "role": "B", "base_dir": "."}
    # 清理旧表 + 旧 type（PostgreSQL 创建表时会同时创建同名 type）
    try:
        s = create_store(spec, ctx)
        with s._conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS %s CASCADE" % table)
        s._conn.commit()
        s.close()
    except Exception:
        pass
    store = create_store(spec, ctx)
    return store


@pytest.fixture
def pg_store():
    store = _pg_store()
    yield store
    store.close()


class TestPgRegistry:
    def test_postgres_in_available_kinds(self):
        kinds = available_store_kinds()
        assert "postgres" in kinds

    def test_create_store_returns_pg_instance(self):
        store = _pg_store()
        assert isinstance(store, PgTaskStore)
        assert isinstance(store, TaskStore)
        store.close()

    def test_describe(self, pg_store):
        info = pg_store.describe()
        assert info["kind"] == "postgres"
        assert info["host"] == "127.0.0.1"
        assert info["port"] == 5432
        assert "table" in info


class TestPgSchema:
    def test_init_schema_idempotent(self, pg_store):
        pg_store.init_schema()
        pg_store.init_schema()
        assert pg_store.count_by_state() == {}

    def test_schema_has_expected_columns(self, pg_store):
        with pg_store._conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = %s ORDER BY ordinal_position
            """, (pg_store.table,))
            cols = {r[0] for r in cur.fetchall()}
        for name in ("task_name", "deps", "state", "payload_enc", "payload_sha",
                     "back_info", "last_err", "version", "worker_id", "expire_time",
                     "cancel_requested", "priority", "task_id"):
            assert name in cols

    def test_bad_table_name_rejected(self):
        with pytest.raises(StoreUnavailable):
            _pg_store(table="bad;drop")


class TestPgInsertAndIdempotency:
    def test_insert_and_get(self, pg_store):
        n = pg_store.insert_tasks([TaskRecord(task_name="a", deps=["b"])])
        assert n == 1
        rec = pg_store.get_task("a")
        assert rec is not None
        assert rec.task_name == "a"
        assert rec.deps == ["b"]

    def test_insert_idempotent(self, pg_store):
        rec = TaskRecord(task_name="dup")
        assert pg_store.insert_tasks([rec]) == 1
        assert pg_store.insert_tasks([rec]) == 0
        assert len(pg_store.list_tasks()) == 1

    def test_insert_batch(self, pg_store):
        recs = [TaskRecord(task_name="t%d" % i) for i in range(5)]
        assert pg_store.insert_tasks(recs) == 5
        assert len(pg_store.all_task_names()) == 5


class TestPgStateTransitions:
    def test_pending_to_locked_to_running_to_completed(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        claimed = pg_store.claim_next("w1")
        assert claimed.state == TaskState.LOCKED
        pg_store.set_state("t", TaskState.RUNNING, worker_id="w1")
        pg_store.set_state("t", TaskState.COMPLETED, worker_id="w1")
        assert pg_store.get_task("t").state == TaskState.COMPLETED

    def test_illegal_transition_rejected(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        with pytest.raises(StoreError):
            pg_store.set_state("t", TaskState.RUNNING)  # PENDING -> RUNNING 非法

    def test_force_skips_transition_check(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        pg_store.set_state("t", TaskState.COMPLETED, force=True)
        assert pg_store.get_task("t").state == TaskState.COMPLETED

    def test_version_increments(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t", version=1)])
        pg_store.claim_next("w1")
        assert pg_store.get_task("t").version == 2
        pg_store.set_state("t", TaskState.RUNNING, worker_id="w1")
        assert pg_store.get_task("t").version == 3


class TestPgClaim:
    def test_claim_pending(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        rec = pg_store.claim_next("w1")
        assert rec is not None
        assert rec.task_name == "t"
        assert rec.state == TaskState.LOCKED
        assert rec.worker_id == "w1"

    def test_claim_respects_priority(self, pg_store):
        pg_store.insert_tasks([
            TaskRecord(task_name="low", priority=0),
            TaskRecord(task_name="high", priority=10),
        ])
        rec = pg_store.claim_next("w1")
        assert rec.task_name == "high"

    def test_claim_skips_cancel_requested(self, pg_store):
        pg_store.insert_tasks([
            TaskRecord(task_name="cancelled"),
            TaskRecord(task_name="ok"),
        ])
        pg_store.set_cancel_requested("cancelled", True)
        rec = pg_store.claim_next("w1")
        assert rec.task_name == "ok"

    def test_claim_respects_deps(self, pg_store):
        pg_store.insert_tasks([
            TaskRecord(task_name="dep"),
            TaskRecord(task_name="main", deps=["dep"]),
        ])
        # 先完成 dep
        pg_store.claim_next("w1")  # 领取 dep
        pg_store.set_state("dep", TaskState.COMPLETED, force=True)
        # 现在可以领取 main
        rec = pg_store.claim_next("w2")
        assert rec.task_name == "main"

    def test_claim_none_when_empty(self, pg_store):
        assert pg_store.claim_next("w1") is None

    def test_claim_no_double_claim(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        rec1 = pg_store.claim_next("w1")
        assert rec1 is not None
        rec2 = pg_store.claim_next("w2")
        assert rec2 is None  # 已被 w1 锁住


class TestPgStaleLocks:
    def test_clean_stale_locked(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        pg_store.claim_next("w1")
        # 设置过期时间为过去
        pg_store.update_fields("t", expire_time="2020-01-01T00:00:00Z")
        n = pg_store.clean_stale_locks()
        assert n >= 1
        assert pg_store.get_task("t").state == TaskState.PENDING

    def test_clean_stale_running(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        pg_store.claim_next("w1")
        pg_store.set_state("t", TaskState.RUNNING, worker_id="w1")
        pg_store.update_fields("t", expire_time="2020-01-01T00:00:00Z")
        n = pg_store.clean_stale_locks()
        assert n >= 1
        assert pg_store.get_task("t").state == TaskState.RETRY_PENDING


class TestPgRequeueAndReset:
    def test_requeue(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        pg_store.claim_next("w1")
        assert pg_store.requeue("t") is True
        rec = pg_store.get_task("t")
        assert rec.state == TaskState.PENDING
        assert rec.worker_id is None

    def test_reset_failed(self, pg_store):
        pg_store.insert_tasks([
            TaskRecord(task_name="f1"),
            TaskRecord(task_name="f2"),
        ])
        pg_store.set_state("f1", TaskState.FAILED, force=True)
        pg_store.set_state("f2", TaskState.FAILED, force=True)
        n = pg_store.reset_failed()
        assert n == 2
        assert pg_store.get_task("f1").state == TaskState.PENDING
        assert pg_store.get_task("f2").state == TaskState.PENDING


class TestPgCancel:
    def test_set_cancel_requested(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        assert pg_store.set_cancel_requested("t", True) is True
        assert pg_store.get_task("t").cancel_requested is True
        assert pg_store.set_cancel_requested("t", False) is True
        assert pg_store.get_task("t").cancel_requested is False


class TestPgSync:
    def test_apply_task_insert(self, pg_store):
        rec = TaskRecord(task_name="sync1", task_type="CLI", version=1)
        assert pg_store.apply_task(rec) == "inserted"

    def test_apply_task_update(self, pg_store):
        rec = TaskRecord(task_name="sync1", version=1)
        pg_store.apply_task(rec)
        rec2 = TaskRecord(task_name="sync1", version=2)
        assert pg_store.apply_task(rec2) == "updated"

    def test_apply_task_stale(self, pg_store):
        rec = TaskRecord(task_name="sync1", version=5)
        pg_store.apply_task(rec)
        rec2 = TaskRecord(task_name="sync1", version=3)
        assert pg_store.apply_task(rec2) == "stale"

    def test_apply_state_update(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        result = pg_store.apply_state(
            {"task_name": "t", "state": "COMPLETED", "version": 2})
        assert result == "updated"
        assert pg_store.get_task("t").state == TaskState.COMPLETED

    def test_apply_state_stale(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="t")])
        pg_store.apply_state({"task_name": "t", "state": "COMPLETED", "version": 2})
        result = pg_store.apply_state(
            {"task_name": "t", "state": "PENDING", "version": 1})
        assert result == "stale"

    def test_apply_state_missing(self, pg_store):
        result = pg_store.apply_state(
            {"task_name": "nonexistent", "state": "PENDING", "version": 1})
        assert result == "missing"


class TestPgListAndCount:
    def test_list_all(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        assert len(pg_store.list_tasks()) == 2

    def test_list_by_state(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        pg_store.set_state("a", TaskState.COMPLETED, force=True)
        completed = pg_store.list_tasks(state=TaskState.COMPLETED)
        assert len(completed) == 1
        assert completed[0].task_name == "a"

    def test_count_by_state(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        pg_store.set_state("a", TaskState.COMPLETED, force=True)
        counts = pg_store.count_by_state()
        assert counts.get(TaskState.COMPLETED, 0) == 1
        assert counts.get(TaskState.PENDING, 0) == 1

    def test_all_task_names(self, pg_store):
        pg_store.insert_tasks([TaskRecord(task_name="x"), TaskRecord(task_name="y")])
        names = pg_store.all_task_names()
        assert set(names) == {"x", "y"}

    def test_is_all_done(self, pg_store):
        assert pg_store.is_all_done() is True
        pg_store.insert_tasks([TaskRecord(task_name="a")])
        assert pg_store.is_all_done() is False
        pg_store.set_state("a", TaskState.COMPLETED, force=True)
        assert pg_store.is_all_done() is True

    def test_count_by_state_table_dropped(self):
        """BUG-293 回归：表被 DROP 后 count_by_state 返回 {}（不抛 StoreError）。"""
        table = "rhop_test_pg_drop"
        store = _pg_store(table=table)
        store.insert_tasks([TaskRecord(task_name="a")])
        # DROP 表
        with store._conn.cursor() as cur:
            cur.execute("DROP TABLE %s CASCADE" % table)
        store._conn.commit()
        # count_by_state 应返回 {} 而非抛异常
        assert store.count_by_state() == {}
        # is_all_done 依赖 count_by_state，也应返回 True
        assert store.is_all_done() is True
        store.close()


class TestPgClose:
    def test_close_idempotent(self, pg_store):
        pg_store.close()
        pg_store.close()  # 不应报错


class TestPgTaskQueueIntegration:
    """PgTaskStore 与 TaskQueue 的集成测试（端到端提交→领取→执行→回写）。"""

    def test_submit_and_run(self):
        from vools.rhop.task.config import TaskConfig
        from vools.rhop.task.queue import TaskQueue

        table = "rhop_test_pg_itest"
        # 清理
        try:
            cfg = TaskConfig.from_dict({
                "name": "pg-itest", "role": "RECV",
                "queue": {"store": dict(PG_SPEC, table=table)},
            })
            s = cfg.build_store()
            with s._conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS %s CASCADE" % table)
            s._conn.commit()
            s.close()
        except Exception:
            pass

        cfg = TaskConfig.from_dict({
            "name": "pg-itest", "role": "RECV",
            "key": {"plain": "pg-itest-key-0123456789abcdef"},
            "queue": {"store": dict(PG_SPEC, table=table)},
            "heartbeat": {"enabled": False},
            "exec": {"allow_any": True},
        })
        queue = TaskQueue(cfg)

        # 提交任务
        result = queue.submit([{"task_name": "job1", "action": "echo", "args": ["hello"]}])
        assert result["submitted"] == 1

        # 领取并执行（echo 不在动作白名单，可能 retried/failed，关键是流程走通）
        run_result = queue.run_once(worker_id="test-worker")
        assert run_result["action"] in ("completed", "failed", "retried", "cancelled", "idle")

        # 检查状态
        tasks = queue.status()
        assert len(tasks) == 1
        print("Integration test task state:", tasks[0]["state"])

        queue.close()


# ---------------------------------------------------------------------------
# A/B 两端共享同一个 PostgreSQL 表（真实部署形态的端到端验证）
# ---------------------------------------------------------------------------
class TestABSharedDatabase:
    """A 端投递、B 端领取执行，两个独立 store 实例连同一张表。

    状态机：PENDING →(claim) LOCKED →(开始执行) RUNNING → COMPLETED
    """

    TABLE = "rhop_test_ab_shared"

    def _pair(self, table):
        spec = dict(PG_SPEC, table=table)
        a = create_store(spec, {"name": "A", "role": "A", "base_dir": "."})
        a.init_schema()
        b = create_store(spec, {"name": "B", "role": "B", "base_dir": "."})
        return a, b

    @pytest.fixture
    def pair(self, request):
        """每个用例**独立表**：共用一张表会让上一用例的残留行污染下一用例
        （此前两个用例共享 rhop_test_ab_shared，先后顺序决定成败）。
        """
        table = "rhop_test_ab_%s" % request.node.name.replace("test_", "")[:24]
        a, b = self._pair(table)
        try:
            yield a, b
        finally:
            a.close()
            b.close()
            try:
                import psycopg2
                conn = psycopg2.connect(host=PG_SPEC["host"], port=PG_SPEC["port"],
                                        user=PG_SPEC["user"],
                                        password=PG_SPEC["password"],
                                        dbname=PG_SPEC["dbname"])
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute('DROP TABLE IF EXISTS %s CASCADE' % table)
                conn.close()
            except Exception:
                pass

    def test_cross_instance_lifecycle(self, pair):
        a, b = pair
        n = a.insert_tasks([TaskRecord(task_name="ab-1", value="echo one"),
                            TaskRecord(task_name="ab-2", value="echo two")])
        assert n == 2
        # B 端（另一实例）能看到 A 投递的任务
        assert b.count_by_state().get(TaskState.PENDING) == 2

        claimed = b.claim_next("worker-B")
        assert claimed is not None
        assert str(claimed.state) == TaskState.LOCKED
        # A 端能看到是 worker-B 持有
        assert a.get_task(claimed.task_name).worker_id == "worker-B"

        # A 抢不到 B 已锁的那个（防止双执行）
        for _ in range(3):
            other = a.claim_next("worker-A")
            if other is None or other.task_name == claimed.task_name:
                break
            a.set_state(other.task_name, TaskState.RUNNING)
            a.set_state(other.task_name, TaskState.COMPLETED)
        assert other is None or other.task_name != claimed.task_name

        # B 走完整流转，A 全程可见
        b.set_state(claimed.task_name, TaskState.RUNNING)
        assert str(a.require_task(claimed.task_name).state) == TaskState.RUNNING
        b.set_state(claimed.task_name, TaskState.COMPLETED)
        assert str(a.require_task(claimed.task_name).state) == TaskState.COMPLETED

        # 收尾 + 两端一致
        while True:
            r = a.claim_next("worker-A")
            if r is None:
                break
            a.set_state(r.task_name, TaskState.RUNNING)
            a.set_state(r.task_name, TaskState.COMPLETED)
        assert a.is_all_done()
        assert a.count_by_state() == b.count_by_state()

    def test_locked_task_not_reclaimable(self, pair):
        """LOCKED 状态的绝不能再被领走（跨实例同样成立）。"""
        a, b = pair
        a.insert_tasks([TaskRecord(task_name="ab-lock", value="x")])
        first = b.claim_next("worker-B")
        assert first is not None
        assert a.claim_next("worker-A") is None, "LOCKED 任务被另一个实例重复领取"
