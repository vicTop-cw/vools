"""v2 业务 API / daemon 端到端测试：daemon.py + requester.py + executor.py。

Phase 2 / Phase 3 里程碑：两个 daemon 进程在本地跑起来，任务从 A 到 B 自动执行并回结果。
"""

import json
import os
import tempfile
import time

import pytest

from vools.rhop.core import Side, TaskStatus
from vools.rhop.envelope import Envelope
from vools.rhop.mirror import MirrorDB
from vools.rhop.requester import Requester
from vools.rhop.executor import Executor
from vools.rhop.daemon import RelayDaemon


def _setup_dirs(tmp_path):
    data_a = str(tmp_path / "data_a")
    data_b = str(tmp_path / "data_b")
    share = str(tmp_path / "share")
    os.makedirs(data_a)
    os.makedirs(data_b)
    os.makedirs(share)
    return data_a, data_b, share


class TestRequester:
    def test_submit_creates_envelope(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        r = Requester({"data_dir": data_dir})
        tid = r.submit({"cmd": "echo hi"})
        assert tid.startswith("job-")
        # 信封已写入 inbox
        inbox_file = os.path.join(data_dir, "inbox", "%s.rhop" % tid)
        assert os.path.exists(inbox_file)
        # 已写入 mirror
        got = r.mirror.get_task(tid)
        assert got is not None
        assert got.status == TaskStatus.PENDING
        r.close()

    def test_get_result_immediate_when_done(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        r = Requester({"data_dir": data_dir})
        tid = r.submit({"cmd": "echo hi"})
        # 手动标记完成
        r.mirror.update_status(tid, TaskStatus.CLAIMED)
        r.mirror.update_status(tid, TaskStatus.RUNNING)
        r.mirror.update_status(tid, TaskStatus.DONE, result={"stdout": "ok"})
        result = r.get_result(tid, timeout=5)
        assert result is not None
        assert result["status"] == "done"
        assert result["result"]["stdout"] == "ok"
        r.close()

    def test_cancel_pending(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        r = Requester({"data_dir": data_dir})
        tid = r.submit({"cmd": "echo hi"})
        assert r.cancel(tid)
        got = r.mirror.get_task(tid)
        assert got.status == TaskStatus.CANCELLED
        r.close()


class TestExecutor:
    def test_claim_and_execute(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        e = Executor({"data_dir": data_dir})
        # 直接写入一个 PENDING 任务
        env = Envelope(
            task_id="job-manual",
            status=TaskStatus.PENDING,
            payload={"cmd": "echo hello"},
            side=Side.REQUESTER,
            created_at="2026-10-21T10:00:00Z",
            updated_at="2026-10-21T10:00:00Z",
        )
        inbox_path = os.path.join(data_dir, "inbox", "job-manual.rhop")
        os.makedirs(os.path.dirname(inbox_path))
        with open(inbox_path, "wb") as fh:
            fh.write(env.to_rhop_bytes())
        e.mirror.upsert_task(env)
        # 领任务
        claimed = e.claim(worker_id="test")
        assert claimed is not None
        assert claimed.task_id == "job-manual"
        # 执行
        result = e.execute(claimed)
        assert result["status"] == "done"
        got = e.mirror.get_task("job-manual")
        assert got.status == TaskStatus.DONE
        assert got.result["stdout"].strip() == "hello"
        e.close()

    def test_list_pending(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        e = Executor({"data_dir": data_dir})
        env = Envelope(
            task_id="p1", status=TaskStatus.PENDING,
            payload={"cmd": "x"}, side=Side.REQUESTER,
            created_at="2026-10-21T10:00:00Z", updated_at="2026-10-21T10:00:00Z",
        )
        e.mirror.upsert_task(env)
        pending = e.list_pending()
        assert len(pending) == 1
        assert pending[0]["task_id"] == "p1"
        e.close()


class TestDaemonEndToEnd:
    def test_daemon_local_full_flow(self, tmp_path):
        """A submit → A daemon push → B daemon pull → B execute → B push result → A pull result。

        用本地目录直接模拟：双方 data_dir 互为 shared path（A outbox ↔ B inbox）。
        简化：单进程内手动轮询一个 cycle，验证镜像 DB + 状态流转。
        """
        data_a, data_b, share = _setup_dirs(tmp_path)

        # 需求端提交任务
        req = Requester({"data_dir": data_a})
        tid = req.submit({"cmd": "echo e2e"})

        # 模拟 A daemon push：信封从 A inbox → B inbox（共享介质）
        src = os.path.join(data_a, "inbox", "%s.rhop" % tid)
        dst = os.path.join(data_b, "inbox", "%s.rhop" % tid)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fh:
            raw = fh.read()
        with open(dst, "wb") as fh:
            fh.write(raw)

        # 任务端 daemon 处理 B inbox
        exe = Executor({"data_dir": data_b})
        # 先 upsert 到 mirror（daemon pull 后会做）
        env = Envelope.from_rhop_bytes(raw)
        exe.mirror.upsert_task(env)
        # 执行
        claimed = exe.claim(worker_id="daemon-test")
        assert claimed is not None
        exe.execute(claimed)

        # 验证结果
        result = req.get_result(tid, timeout=5)
        # A 端 mirror 还没同步，需要手动同步结果到 A
        done_env = exe.mirror.get_task(tid)
        assert done_env.status == TaskStatus.DONE
        req.mirror.upsert_task(done_env)

        result = req.get_result(tid, timeout=5)
        assert result is not None
        assert result["status"] == "done"
        assert "e2e" in result["result"]["stdout"]
        req.close()
        exe.close()

    def test_daemon_stop_sets_running_false(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir)
        d = RelayDaemon({"data_dir": data_dir, "side": "requester"})
        d.stop()
        assert not d._running
