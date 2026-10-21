"""存储抽象层测试：schema、幂等、原子领取、依赖门控、失效锁、版本同步、后端注册。"""

import os
import sqlite3

import pytest

from vools.rhop.task.errors import StoreError, StoreUnavailable, TaskNotFound
from vools.rhop.task.models import TaskRecord, TaskState, utcnow_iso
from vools.rhop.task.store import (
    DEFAULT_STORE_KIND,
    SqliteTaskStore,
    available_store_kinds,
    create_store,
    register_store,
)


def _ctx(base_dir, shared=True):
    return {"name": "unit", "role": "B", "base_dir": str(base_dir),
            "shared_root": str(base_dir) if shared else None}


def _store(tmp_path, kind=DEFAULT_STORE_KIND, **spec):
    spec = dict(spec)
    spec.setdefault("kind", kind)
    return create_store(spec, _ctx(tmp_path))


class TestRegistry:
    def test_builtin_kinds_registered(self):
        kinds = available_store_kinds()
        assert "sqlite-shared" in kinds
        assert "sqlite-local" in kinds

    def test_unknown_kind_lists_available(self, tmp_path):
        with pytest.raises(StoreUnavailable) as exc:
            create_store({"kind": "postgres"}, _ctx(tmp_path))
        message = str(exc.value)
        assert "postgres" in message
        assert "sqlite-shared" in message
        assert "register_store" in message

    def test_register_custom_backend(self, tmp_path):
        made = {}

        class Dummy(SqliteTaskStore):
            pass

        def factory(spec, ctx):
            made["called"] = spec.get("kind")
            return Dummy({"kind": "sqlite-shared", "path": os.path.join(str(tmp_path), "d.db")}, ctx)

        register_store("unit-dummy", factory)
        store = create_store({"kind": "unit-dummy"}, _ctx(tmp_path))
        assert made["called"] == "unit-dummy"
        assert isinstance(store, SqliteTaskStore)
        assert "unit-dummy" in available_store_kinds()
        store.close()

    def test_factory_must_return_store(self, tmp_path):
        register_store("unit-broken", lambda spec, ctx: object())
        with pytest.raises(StoreUnavailable):
            create_store({"kind": "unit-broken"}, _ctx(tmp_path))


class TestSchemaAndKinds:
    def test_shared_uses_delete_journal(self, tmp_path):
        store = _store(tmp_path, "sqlite-shared")
        info = store.describe()
        assert info["journal_mode"] == "DELETE"
        assert info["synchronous"] == "FULL"
        assert info["schema_version"] == 1
        store.close()

    def test_local_uses_wal(self, tmp_path):
        store = _store(tmp_path, "sqlite-local")
        assert store.describe()["journal_mode"] == "WAL"
        store.close()

    def test_default_paths(self, tmp_path):
        shared = _store(tmp_path, "sqlite-shared")
        assert shared.path.startswith(str(tmp_path))
        local = _store(tmp_path, "sqlite-local")
        assert os.path.basename(local.path) == "rhop-b.db"
        shared.close()
        local.close()

    def test_shared_without_shared_path_is_clear_error(self, tmp_path):
        with pytest.raises(StoreUnavailable) as exc:
            create_store({"kind": "sqlite-shared"}, _ctx(tmp_path, shared=False))
        assert "sqlite-local" in str(exc.value)

    def test_schema_has_expected_columns(self, tmp_path):
        store = _store(tmp_path)
        conn = sqlite3.connect(store.path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        conn.close()
        for name in ("task_name", "deps", "state", "payload_enc", "payload_sha",
                     "back_info", "last_err", "version", "worker_id", "expire_time"):
            assert name in cols
        store.close()

    def test_bad_table_name_rejected(self, tmp_path):
        with pytest.raises(StoreUnavailable):
            create_store({"kind": "sqlite-shared", "table": "bad;drop"}, _ctx(tmp_path))

    def test_init_schema_is_idempotent(self, tmp_path):
        store = _store(tmp_path)
        store.init_schema()
        store.init_schema()
        assert store.count_by_state() == {}
        store.close()


class TestInsertAndIdempotency:
    def test_insert_and_count(self, tmp_path):
        store = _store(tmp_path)
        n = store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        assert n == 2
        assert store.insert_tasks([TaskRecord(task_name="a")]) == 0
        assert sorted(store.all_task_names()) == ["a", "b"]
        store.close()

    def test_missing_task_name_rejected(self, tmp_path):
        store = _store(tmp_path)
        with pytest.raises(StoreError):
            store.insert_tasks([TaskRecord()])
        store.close()

    def test_deps_and_tags_round_trip(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a", deps=["x", "y"], tags=["t1", "t2"])])
        rec = store.get_task("a")
        assert rec.deps == ["x", "y"]
        assert rec.tags == ["t1", "t2"]
        store.close()

    def test_unknown_task_lookup(self, tmp_path):
        store = _store(tmp_path)
        assert store.get_task("nope") is None
        with pytest.raises(TaskNotFound):
            store.require_task("nope")
        store.close()


class TestStateMachine:
    def test_legal_transition(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        assert store.set_state("a", TaskState.LOCKED, worker_id="w1")
        assert store.set_state("a", TaskState.RUNNING, start_time=utcnow_iso())
        assert store.set_state("a", TaskState.COMPLETED, end_time=utcnow_iso())
        assert store.get_task("a").state == TaskState.COMPLETED
        assert store.get_task("a").version == 4
        store.close()

    def test_illegal_transition_blocked(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        with pytest.raises(StoreError):
            store.set_state("a", TaskState.COMPLETED)
        store.close()

    def test_force_skips_validation(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        assert store.set_state("a", TaskState.COMPLETED, force=True)
        store.close()

    def test_expect_version_guard(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        assert store.set_state("a", TaskState.LOCKED, expect_version=0) is False
        assert store.set_state("a", TaskState.LOCKED, expect_version=1) is True
        store.close()

    def test_requeue_and_reset_failed(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        store.set_state("a", TaskState.LOCKED, worker_id="w1")
        store.set_state("a", TaskState.RUNNING)
        store.set_state("a", TaskState.FAILED, last_err="boom")
        assert store.reset_failed() == 1
        assert store.get_task("a").state == TaskState.PENDING
        assert store.requeue("b") is True
        store.close()

    def test_cancel_flag(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        assert store.set_cancel_requested("a", True)
        assert store.get_task("a").cancel_requested is True
        assert store.set_cancel_requested("a", False)
        assert store.get_task("a").cancel_requested is False
        store.close()

    def test_count_and_all_done(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b")])
        assert store.is_all_done() is False
        assert store.count_by_state() == {TaskState.PENDING: 2}
        store.set_state("a", TaskState.LOCKED)
        store.set_state("a", TaskState.RUNNING)
        store.set_state("a", TaskState.COMPLETED)
        store.set_state("b", TaskState.LOCKED)
        store.set_state("b", TaskState.RUNNING)
        store.set_state("b", TaskState.FAILED)
        assert store.is_all_done() is True
        store.close()


class TestClaim:
    def test_claim_priority_order(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="low", priority=1),
                            TaskRecord(task_name="high", priority=9)])
        assert store.claim_next("w1").task_name == "high"
        store.close()

    def test_claim_sets_lock_fields(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a", timeout_min=1)])
        rec = store.claim_next("w1")
        assert rec.state == TaskState.LOCKED
        assert rec.worker_id == "w1"
        assert rec.lock_time and rec.expire_time
        assert rec.version == 2
        store.close()

    def test_claim_returns_none_when_empty(self, tmp_path):
        store = _store(tmp_path)
        assert store.claim_next("w1") is None
        store.close()

    def test_dependency_gating(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a"), TaskRecord(task_name="b", deps=["a"])])
        assert store.claim_next("w1").task_name == "a"
        assert store.claim_next("w1") is None       # b 被 a 挡住
        store.set_state("a", TaskState.RUNNING)
        store.set_state("a", TaskState.COMPLETED)
        assert store.claim_next("w1").task_name == "b"
        store.close()

    def test_dependency_on_missing_task_blocks_forever(self, tmp_path):
        """依赖不存在的任务不会被执行（提交时应被 DAG 校验挡住；这里验证存储层保守行为）。"""
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="b", deps=["ghost"])])
        assert store.claim_next("w1") is None
        store.close()

    def test_scheduled_at_in_future_not_claimable(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a", scheduled_at="2999-01-01T00:00:00Z")])
        assert store.claim_next("w1") is None
        assert store.claim_next("w1", now="2999-01-02T00:00:00Z").task_name == "a"
        store.close()

    def test_cancel_requested_not_claimed(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        store.set_cancel_requested("a", True)
        assert store.claim_next("w1") is None
        store.close()

    def test_claim_is_atomic_across_two_connections(self, tmp_path):
        """两个独立连接指同一个共享库：不会领到同一条（等价于两个 worker 竞争）。

        模拟"两台机器各开一个连接"：每个线程自己建连接、自己关闭
        （store 的连接默认不跨线程复用，与 daemon 单线程访问存储的设计一致）。
        """
        import threading
        path = os.path.join(str(tmp_path), "shared.db")
        setup = create_store({"kind": "sqlite-shared", "path": path}, _ctx(tmp_path))
        setup.insert_tasks([TaskRecord(task_name="only-one")])
        setup.close()

        claimed = []
        errors = []
        barrier = threading.Barrier(2)

        def worker(wid):
            store = create_store({"kind": "sqlite-shared", "path": path}, _ctx(tmp_path))
            try:
                barrier.wait()
                rec = store.claim_next(wid)
                if rec is not None:
                    claimed.append(rec.task_name)
            except Exception as exc:  # 线程内异常要带回主线程断言
                errors.append(exc)
            finally:
                store.close()

        threads = [threading.Thread(target=worker, args=("w%d" % i,)) for i in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert errors == []
        assert claimed == ["only-one"]


class TestStaleLocks:
    def test_running_lock_timeout_goes_retry_pending(self, tmp_path):
        store = _store(tmp_path, lock_ttl_sec=1)
        store.insert_tasks([TaskRecord(task_name="a", timeout_min=0)])
        store.claim_next("w1", now=utcnow_iso())
        store.set_state("a", TaskState.RUNNING)
        reclaimed = store.clean_stale_locks(now="2999-01-01T00:00:00Z")
        assert reclaimed == 1
        assert store.get_task("a").state == TaskState.RETRY_PENDING
        store.close()

    def test_locked_lock_timeout_goes_pending(self, tmp_path):
        store = _store(tmp_path, lock_ttl_sec=1)
        store.insert_tasks([TaskRecord(task_name="a", timeout_min=0)])
        store.claim_next("w1")
        assert store.clean_stale_locks(now="2999-01-01T00:00:00Z") == 1
        assert store.get_task("a").state == TaskState.PENDING
        store.close()

    def test_fresh_lock_not_reclaimed(self, tmp_path):
        store = _store(tmp_path, lock_ttl_sec=3600)
        store.insert_tasks([TaskRecord(task_name="a", timeout_min=60)])
        store.claim_next("w1")
        assert store.clean_stale_locks() == 0
        store.close()


class TestSyncApply:
    def test_apply_task_insert_then_stale(self, tmp_path):
        store = _store(tmp_path)
        assert store.apply_task(TaskRecord(task_name="a", version=2)) == "inserted"
        assert store.apply_task(TaskRecord(task_name="a", version=2)) == "stale"
        assert store.apply_task(TaskRecord(task_name="a", version=3, priority=7)) == "updated"
        assert store.get_task("a").priority == 7
        store.close()

    def test_apply_state_version_monotonic(self, tmp_path):
        store = _store(tmp_path)
        store.insert_tasks([TaskRecord(task_name="a")])
        assert store.apply_state({"task_name": "a", "state": TaskState.COMPLETED, "version": 1}) == "stale"
        assert store.apply_state({"task_name": "a", "state": TaskState.COMPLETED, "version": 5,
                                  "back_info": "{}"}) == "updated"
        assert store.get_task("a").state == TaskState.COMPLETED
        assert store.apply_state({"task_name": "ghost", "state": TaskState.COMPLETED,
                                  "version": 9}) == "missing"
        store.close()

    def test_apply_task_without_name_rejected(self, tmp_path):
        store = _store(tmp_path)
        with pytest.raises(StoreError):
            store.apply_task(TaskRecord())
        store.close()