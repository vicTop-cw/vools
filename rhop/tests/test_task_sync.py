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


class TestRequeueConvergence:
    """BUG-280 回归：本地库模式下 A 端 requeue/retry_failed 不得造成双方状态发散。

    发散的旧路径：A 本地把已完成任务重置成 PENDING 且 version+1 → 版本超过 B →
    B 之后的状态回推被 apply_state 的『版本必须严格递增』永久丢弃 → A 永远等不到完成。
    新语义：A 只登记重置意图（TaskSync.resets），由 B 重跑并回推，A 再收敛。
    """

    def _wire(self, role, base, share):
        cfg = TaskConfig.from_dict(
            {"name": "link", "role": role, "key": "unit-key",
             "shared": {"write": str(share)}, "queue": {"store": {"kind": "sqlite-local"}},
             "exec": {"allow": ["cli:python"]}}, base_dir=str(base), warn_plaintext=False)
        store = cfg.build_store()
        syncer = TaskSync(store, cfg.build_crypto(), cfg.role,
                          shared=cfg.build_shared(), name=cfg.name)
        return TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)

    def _ok_cmd(self, work):
        path = os.path.join(str(work), "ok.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("print('done')\n")
        return '"%s" "%s"' % (PY.replace("\\", "/"), path.replace("\\", "/"))

    def _completed_pair(self, qa, qb, work):
        qa.submit([{"task_name": "j", "cli": {"cmd": self._ok_cmd(work)}}])
        qb.pull_sync()
        assert qb.run_once()["action"] == "completed"
        qa.pull_sync()
        assert qa.get_task("j").state == TaskState.COMPLETED

    def test_requeue_does_not_advance_local_version(self, tmp_path):
        share = tmp_path / "share"
        share.mkdir()
        qa = self._wire("A", tmp_path / "a", share)
        qb = self._wire("B", tmp_path / "b", share)
        try:
            self._completed_pair(qa, qb, tmp_path)
            version = qa.get_task("j").version
            assert qa.requeue("j") is True
            # A 端不得本地改状态/版本（发散根因）
            assert qa.get_task("j").state == TaskState.COMPLETED
            assert qa.get_task("j").version == version
            # 重置意图已登记，且 B 拉取后真正重跑
            assert "j" in qa.syncer._resets
            qb.pull_sync()
            assert qb.get_task("j").state == TaskState.PENDING
            assert qb.get_task("j").version == version + 1
        finally:
            qa.close()
            qb.close()

    def test_requeue_converges_after_b_executes(self, tmp_path):
        share = tmp_path / "share"
        share.mkdir()
        qa = self._wire("A", tmp_path / "a", share)
        qb = self._wire("B", tmp_path / "b", share)
        try:
            self._completed_pair(qa, qb, tmp_path)
            qa.requeue("j")
            qb.pull_sync()
            assert qb.run_once()["action"] == "completed"       # B 真的重跑了一遍
            assert qb.get_task("j").state == TaskState.COMPLETED
            qb.syncer.push_states()
            qa.pull_sync()
            a, b = qa.get_task("j"), qb.get_task("j")
            assert a.state == TaskState.COMPLETED
            assert a.version == b.version                        # 版本对齐 ⇒ 无发散
            assert qa.is_all_done() is True
            assert qa.syncer._resets == {}                       # 重置被消费，意图撤销
        finally:
            qa.close()
            qb.close()

    def test_retry_failed_sends_resets_in_local_mode(self, tmp_path):
        share = tmp_path / "share"
        share.mkdir()
        qa = self._wire("A", tmp_path / "a", share)
        qb = self._wire("B", tmp_path / "b", share)
        try:
            fail = '"%s" -c "import sys; sys.exit(1)"' % PY.replace("\\", "/")
            qa.submit([{"task_name": "bad", "cli": {"cmd": fail}, "max_retries": 0}])
            qb.pull_sync()
            qb.run_once()
            qa.pull_sync()
            assert qa.get_task("bad").state == TaskState.FAILED
            assert qa.retry_failed() == 1
            assert qa.get_task("bad").state == TaskState.FAILED  # 本地不直接重置
            assert "bad" in qa.syncer._resets
            qb.pull_sync()
            assert qb.get_task("bad").state == TaskState.PENDING  # 意图到了对端
        finally:
            qa.close()
            qb.close()

    def test_requeue_unknown_task_returns_false(self, tmp_path):
        share = tmp_path / "share"
        share.mkdir()
        qa = self._wire("A", tmp_path / "a", share)
        try:
            assert qa.requeue("ghost") is False
            assert qa.syncer._resets == {}
        finally:
            qa.close()


class TestControlIntentPrecedence:
    """BUG-290 收口：reset 优先于 cancel —— 两种顺序都应收敛到「重置后的状态」。

    取消只作用于尚未结束的任务；对已完成任务的取消是 no-op（并留 warning）。
    """

    def _wire(self, role, base, share):
        cfg = TaskConfig.from_dict(
            {"name": "link", "role": role, "key": "unit-key",
             "shared": {"write": str(share)}, "queue": {"store": {"kind": "sqlite-local"}},
             "exec": {"allow": ["cli:python"]}}, base_dir=str(base), warn_plaintext=False)
        store = cfg.build_store()
        syncer = TaskSync(store, cfg.build_crypto(), cfg.role,
                          shared=cfg.build_shared(), name=cfg.name)
        return TaskQueue(cfg, store=store, crypto=cfg.build_crypto(), syncer=syncer)

    def _run_order(self, order, tmp_path):
        share = tmp_path / "share"
        share.mkdir()
        script = os.path.join(str(tmp_path), "ok.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("print('done')\n")
        qa = self._wire("A", tmp_path / "a", share)
        qb = self._wire("B", tmp_path / "b", share)
        try:
            qa.submit([{"task_name": "j", "cli": {"cmd": self._ok(script)}, "timeout_min": 5}])
            qb.pull_sync()
            assert qb.run_once()["action"] == "completed"
            qa.pull_sync()
            assert qa.get_task("j").state == TaskState.COMPLETED

            for action in order:
                if action == "requeue":
                    qa.requeue("j")
                else:
                    qa.cancel("j")
            qb.pull_sync()
            qb.syncer.push_states()
            qa.pull_sync()
            return (qa.get_task("j").state, qb.get_task("j").state)
        finally:
            qa.close()
            qb.close()

    def _ok(self, script):
        return '"%s" "%s"' % (PY.replace("\\", "/"), script.replace("\\", "/"))

    def test_reset_then_cancel_converges_to_reset(self, tmp_path):
        assert self._run_order(["requeue", "cancel"], tmp_path) == \
            (TaskState.PENDING, TaskState.PENDING)

    def test_cancel_then_reset_converges_to_reset(self, tmp_path):
        assert self._run_order(["cancel", "requeue"], tmp_path) == \
            (TaskState.PENDING, TaskState.PENDING)