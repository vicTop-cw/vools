"""v2 镜像数据库测试：mirror.py（SQLite + schema + CRUD + 乐观锁）。

Phase 0 里程碑：本地构造信封、写入 mirror DB、校验通过。
"""

import os
import tempfile

import pytest

from vools.rhop.core import Side, TaskStatus
from vools.rhop.envelope import Envelope
from vools.rhop.mirror import MirrorDB, StaleVersionError


def _make_env(task_id="job-001", status=TaskStatus.PENDING, version=1, **over):
    defaults = dict(
        task_id=task_id,
        status=status,
        payload={"cmd": "echo hi"},
        side=Side.REQUESTER,
        version=version,
        created_at="2026-10-21T10:00:00Z",
        updated_at="2026-10-21T10:00:00Z",
    )
    defaults.update(over)
    return Envelope(**defaults)


@pytest.fixture
def mirror(tmp_path):
    db_path = str(tmp_path / "mirror.db")
    m = MirrorDB(db_path)
    yield m
    m.close()


class TestMirrorCRUD:
    def test_upsert_and_get(self, mirror):
        env = _make_env()
        mirror.upsert_task(env)
        got = mirror.get_task("job-001")
        assert got is not None
        assert got.task_id == "job-001"
        assert got.status == TaskStatus.PENDING

    def test_get_nonexistent_returns_none(self, mirror):
        assert mirror.get_task("nope") is None

    def test_list_tasks(self, mirror):
        mirror.upsert_task(_make_env("job-001"))
        mirror.upsert_task(_make_env("job-002", status=TaskStatus.DONE))
        tasks = mirror.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_filter_by_status(self, mirror):
        mirror.upsert_task(_make_env("job-001", status=TaskStatus.PENDING))
        mirror.upsert_task(_make_env("job-002", status=TaskStatus.DONE))
        pending = mirror.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].task_id == "job-001"


class TestMirrorVersioning:
    def test_stale_version_rejected(self, mirror):
        env = _make_env(version=1)
        mirror.upsert_task(env)
        # 用相同 version 再次写入 → 抛 StaleVersionError
        with pytest.raises(StaleVersionError):
            mirror.upsert_task(_make_env(version=1))
        # 用更低 version 也拒绝
        with pytest.raises(StaleVersionError):
            mirror.upsert_task(_make_env(version=0))

    def test_newer_version_accepted(self, mirror):
        mirror.upsert_task(_make_env(version=1))
        mirror.upsert_task(_make_env(version=2))
        got = mirror.get_task("job-001")
        assert got.version == 2

    def test_update_status_increments_version(self, mirror):
        mirror.upsert_task(_make_env(version=1))
        mirror.update_status("job-001", TaskStatus.CLAIMED)
        got = mirror.get_task("job-001")
        assert got.status == TaskStatus.CLAIMED
        assert got.version == 2


class TestMirrorStateTransitions:
    def test_pending_to_claimed_allowed(self, mirror):
        mirror.upsert_task(_make_env())
        mirror.update_status("job-001", TaskStatus.CLAIMED)
        assert mirror.get_task("job-001").status == TaskStatus.CLAIMED

    def test_pending_to_done_rejected(self, mirror):
        mirror.upsert_task(_make_env())
        with pytest.raises(ValueError):
            mirror.update_status("job-001", TaskStatus.DONE)

    def test_terminal_no_transition(self, mirror):
        mirror.upsert_task(_make_env())
        mirror.update_status("job-001", TaskStatus.CLAIMED)
        mirror.update_status("job-001", TaskStatus.RUNNING)
        mirror.update_status("job-001", TaskStatus.DONE)
        with pytest.raises(ValueError):
            mirror.update_status("job-001", TaskStatus.PENDING)


class TestMirrorClaim:
    def test_claim_pending_task(self, mirror):
        mirror.upsert_task(_make_env())
        claimed = mirror.claim_task(worker_id="test")
        assert claimed is not None
        assert claimed.status == TaskStatus.CLAIMED
        assert mirror.get_task("job-001").status == TaskStatus.CLAIMED

    def test_claim_no_pending(self, mirror):
        assert mirror.claim_task(worker_id="test") is None

    def test_claim_skips_non_pending(self, mirror):
        mirror.upsert_task(_make_env(status=TaskStatus.DONE))
        assert mirror.claim_task(worker_id="test") is None


class TestMirrorSyncLog:
    def test_log_sync(self, mirror):
        mirror.log_sync("pull", "local", "job-001", True, bytes_xfer=1024)
        # sync_log 通过 pending_sync 返回（events 和 sync_log 都在其中）
        events = mirror.pending_sync()
        assert len(events) >= 0  # log_sync 写 sync_log 表，不写 events
        # 验证 sync_log 直接读取
        cur = mirror._conn.execute("SELECT COUNT(*) AS n FROM sync_log")
        row = cur.fetchone()
        assert row["n"] == 1

    def test_count_by_status(self, mirror):
        mirror.upsert_task(_make_env("job-001", status=TaskStatus.PENDING))
        mirror.upsert_task(_make_env("job-002", status=TaskStatus.DONE))
        mirror.upsert_task(_make_env("job-003", status=TaskStatus.DONE))
        counts = mirror.count_by_status()
        assert counts.get("pending") == 1
        assert counts.get("done") == 2
