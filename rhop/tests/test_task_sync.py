"""各自持库模式（sqlite-local）的加密同步测试：收敛、版本单调、取消传播、介质加密。"""

import json
import os
import sys

import pytest

from vools.rhop.task.config import TaskConfig
from vools.rhop.task.errors import RhopTaskError
from vools.rhop.task.models import TaskState
from vools.rhop.task.queue import TaskQueue
from vools.rhop.task.sync import TaskSync

PY = sys.executable.replace("\\", "/")


def _wire(role, base_dir, share, **queue_overrides):
    queue_cfg = {"store": {"kind": "sqlite-local"}}
    queue_cfg.update(queue_overrides)
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": role, "key": "unit-key",
         "shared": {"write": str(share)}, "queue": queue_cfg,
         "exec": {"allow": ["cli:python"]}},
        base_dir=str(base_dir), warn_plaintext=False)
    store = cfg.build_store()
    crypto = cfg.build_crypto()
    syncer = TaskSync(store, crypto, cfg.role, shared=cfg.build_shared(), name=cfg.name)
    return TaskQueue(cfg, store=store, crypto=crypto, syncer=syncer)


@pytest.fixture
def pair(tmp_path):
    share = tmp_path / "share"
    work_a = tmp_path / "a"
    work_b = tmp_path / "b"
    for d in (share, work_a, work_b):
        os.makedirs(str(d))
    qa = _wire("A", work_a, share)
    qb = _wire("B", work_b, share)
    yield qa, qb, share
    qa.close()
    qb.close()


def _ok_cmd(text="done"):
    return '"%s" -c "print(\'%s\')"' % (PY, text)


class TestConvergence:
    def test_separate_databases(self, pair):
        qa, qb, _ = pair
        assert qa.store.path != qb.store.path
        assert os.path.basename(qa.store.path) == "rhop-a.db"
        assert os.path.basename(qb.store.path) == "rhop-b.db"

    def test_submit_pushes_tasks_and_b_pulls(self, pair):
        qa, qb, _ = pair
        result = qa.submit([{"task_name": "j1", "cli": {"cmd": _ok_cmd()}},
                            {"task_name": "j2", "deps": ["j1"]}])
        assert result["submitted"] == 2
        assert qb.store.count_by_state() == {}      # B 本地库还没拉
        pull = qb.pull_sync()
        assert pull["inserted"] == 2
        assert qb.store.count_by_state() == {TaskState.PENDING: 2}
        assert qb.get_task("j2").deps == ["j1"]
        assert qb.decrypt_payload(qb.get_task("j1"))["cli"]["cmd"]

    def test_second_pull_is_idempotent(self, pair):
        qa, qb, _ = pair
        qa.submit(["j1"])
        qb.pull_sync()
        again = qb.pull_sync()
        assert again["inserted"] == 0
        assert again["stale"] == 1

    def test_dependency_order_across_sync(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "first", "cli": {"cmd": _ok_cmd()}},
                   {"task_name": "second", "deps": ["first"], "cli": {"cmd": _ok_cmd()}}])
        qb.pull_sync()
        assert qb.run_once()["task_name"] == "first"
        assert qb.run_once()["task_name"] == "second"

    def test_b_states_flow_back_to_a(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "j1", "cli": {"cmd": _ok_cmd("local-out")}}])
        qb.pull_sync()
        assert qb.run_once()["action"] == "completed"
        assert qa.get_task("j1").state == TaskState.PENDING   # 还没拉
        pull = qa.pull_sync()
        assert pull["updated"] == 1
        assert qa.get_task("j1").state == TaskState.COMPLETED
        assert qa.status()[0]["result"]["result"]["stdout"].strip() == "local-out"

    def test_run_once_auto_pulls_and_pushes(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "auto", "cli": {"cmd": _ok_cmd()}}])
        # run_once 内部先 pull（B 拿到任务）再 push（状态回 A）
        assert qb.run_once()["action"] == "completed"
        qa.pull_sync()
        assert qa.get_task("auto").state == TaskState.COMPLETED

    def test_cancel_propagates_to_b(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "victim", "cli": {"cmd": _ok_cmd()}}])
        qb.pull_sync()
        qa.cancel("victim")                        # A 取消 → push_tasks 带上 cancels
        pull = qb.pull_sync()
        assert pull["cancels"] == 1
        assert qb.get_task("victim").cancel_requested is True
        assert qb.run_once()["action"] == "idle"   # 取消的任务不会被领取

    def test_stale_definition_does_not_overwrite_newer_state(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "j", "cli": {"cmd": _ok_cmd()}}])
        qb.pull_sync()
        qb.run_once()
        completed = qb.get_task("j")
        assert completed.state == TaskState.COMPLETED
        # A 再推一次旧定义（version=1）→ B 必须保持自己的新状态
        qa.syncer.push_tasks([qa.get_task("j")])
        qb.pull_sync()
        assert qb.get_task("j").state == TaskState.COMPLETED
        assert qb.get_task("j").version >= completed.version

    def test_cancel_requested_flag_is_pushed(self, pair):
        qa, qb, _ = pair
        qa.submit([{"task_name": "r", "cli": {"cmd": _ok_cmd()}}])
        qa.store.set_cancel_requested("r", True)
        qa.syncer.push_tasks()
        qb.pull_sync()
        assert qb.get_task("r").cancel_requested is True


class TestDocuments:
    def test_document_is_encrypted_on_medium(self, pair):
        qa, _, share = pair
        qa.submit([{"task_name": "top-secret-name", "cli": {"cmd": _ok_cmd()}}])
        path = os.path.join(str(share), qa.syncer.a2b_file)
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        assert "top-secret-name" not in raw          # 介质上只有密文
        assert json.loads(raw)["alg"] == "fernet"

    def test_direction_files_are_separate(self, pair):
        qa, qb, _ = pair
        assert qa.syncer.a2b_file != qa.syncer.b2a_file
        qa.submit(["x"])
        qb.pull_sync()
        qb.syncer.push_states()
        assert os.path.exists(os.path.join(str(qa.syncer.shared.read_view.path), qa.syncer.a2b_file))
        assert os.path.exists(os.path.join(str(qa.syncer.shared.read_view.path), qa.syncer.b2a_file))

    def test_missing_document_is_skipped(self, pair):
        qa, qb, _ = pair
        stats = qb.pull_sync()
        assert stats["skipped"] is True

    def test_wrong_key_cannot_read_document(self, pair):
        from vools.rhop.crypto import RhopCrypto
        qa, qb, _ = pair
        qa.submit(["x"])
        qb.syncer.crypto = RhopCrypto("another-key")
        stats = qb.pull_sync()
        assert stats["skipped"] is True          # 解不开就当没有，不炸掉循环

    def test_describe(self, pair):
        qa, _, _ = pair
        info = qa.syncer.describe()
        assert info["mode"] == "sqlite-local"
        assert info["has_shared"] is True


class TestErrors:
    def test_sync_without_shared_is_clear(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        store = cfg.build_store()
        syncer = TaskSync(store, cfg.build_crypto(), cfg.role, shared=None)
        queue = TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)
        try:
            stats = queue.pull_sync()
            assert "error" in stats and "shared" in stats["error"]
        finally:
            queue.close()

    def test_push_without_shared_raises(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        store = cfg.build_store()
        syncer = TaskSync(store, cfg.build_crypto(), cfg.role, shared=None)
        try:
            with pytest.raises(RhopTaskError):
                syncer.push_tasks([])
        finally:
            store.close()