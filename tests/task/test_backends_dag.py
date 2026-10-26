"""tests/task/test_backends_dag.py — 多后端任务队列状态机 / DAG 依赖门 / 级联测试。

覆盖 memory + sqlite 两个可在本机无外部服务运行的后端（pg 需 PostgreSQL，跳过）。
回归点：
  - sqlite 后端必须能真正领取任务并保留结构化 payload（曾因调用不存在的
    storage.acquire_task 而恒返回 None；payload/task_type 列缺失）。
  - 依赖未满足时下游停在 PENDING 不被抢跑；上游成功后点亮为 READY。
  - 上游终态 FAILED 级联 SKIPPED 到全部未启动的传递下游。
  - is_all_done 只看真实任务终态（曾枚举状态枚举本身而恒为 False）。
"""

import os
import tempfile

import pytest

from vools.task.backends import create_backend
from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend
from vools.task.core.worker_engine import WorkerEngine


def _all_backends():
    tmp = tempfile.mktemp(suffix=".db")
    return [MemoryTaskBackend(), SqliteTaskBackend(db_path=tmp)]


def _close(b):
    try:
        b.close()
    except Exception:
        pass


def test_submit_no_deps_is_ready():
    for b in _all_backends():
        try:
            b.init_table()
            tid = b.submit("a", {"value": "x"})
            assert b.get(tid)["status"] == "READY"
        finally:
            _close(b)


def test_dependency_gate_blocks_then_promotes():
    for b in _all_backends():
        try:
            b.init_table()
            t1 = b.submit("a", {"cli": {"cmd": "echo a"}})
            t2 = b.submit("b", {"value": "bb"}, dependencies=[t1])
            assert b.get(t2)["status"] == "PENDING"
            first = b.acquire("w1")
            assert first["id"] == t1
            assert b.acquire("w1") is None  # t2 还不能被抢跑
            b.complete(t1, "w1", {"ok": True})
            assert b.get(t2)["status"] == "READY"
            got2 = b.acquire("w1")
            assert got2 is not None and got2["id"] == t2
        finally:
            _close(b)


def test_diamond_dependency_promotes_once_all_succeed():
    for b in _all_backends():
        try:
            b.init_table()
            top = b.submit("top", {"value": "t"})
            left = b.submit("l", {"value": "l"}, dependencies=[top])
            right = b.submit("r", {"value": "r"}, dependencies=[top])
            leaf = b.submit("leaf", {"value": "f"}, dependencies=[left, right])
            b.complete(b.acquire("w1")["id"], "w1", {})   # top
            b.complete(b.acquire("w1")["id"], "w1", {})   # left
            assert b.get(leaf)["status"] == "PENDING"      # right 未完成
            b.complete(b.acquire("w1")["id"], "w1", {})   # right
            assert b.get(leaf)["status"] == "READY"
        finally:
            _close(b)


def _force_fail(b, tid, worker="w1", err="boom"):
    """把某任务一路 fail 到终态 FAILED。

    BUG-231 起 ``fail`` 会写 ``next_retry_at`` 退避，本用例考的是「DAG 级联
    SKIPPED」而不是退避时序，故每次重试点用 ``b.retry()`` 人工放行（=立即）。
    """
    while True:
        t = b.get(tid)
        if t["status"] == "FAILED":
            return
        if t["status"] == "RETRY_PENDING":
            b.retry(tid)          # 清退避，立即放行
        g = b.acquire(worker)
        assert g is not None and g["id"] == tid
        b.fail(tid, worker, err)


def test_upstream_failure_cascades_skip():
    for b in _all_backends():
        try:
            b.init_table()
            t1 = b.submit("a", {"value": "x"})
            t2 = b.submit("b", {"value": "y"}, dependencies=[t1])
            t3 = b.submit("c", {"value": "z"}, dependencies=[t2])
            _force_fail(b, t1)
            assert b.get(t1)["status"] == "FAILED"
            assert b.get(t2)["status"] == "SKIPPED"
            assert b.get(t3)["status"] == "SKIPPED"
            assert b.is_all_done()
        finally:
            _close(b)


def test_sqlite_payload_roundtrip_and_acquire():
    tmp = tempfile.mktemp(suffix=".db")
    b = SqliteTaskBackend(db_path=tmp)
    try:
        b.init_table()
        payload = {"cli": {"cmd": "echo hi"}, "value": "v"}
        tid = b.submit("a", payload, task_type="CLI")
        got = b.acquire("w1")
        assert got["id"] == tid
        assert got["payload"] == payload
        assert got["task_type"] == "CLI"
        b.complete(got["id"], "w1", {"stdout": "hi"})
        assert b.get(tid)["back_info"] == {"stdout": "hi"}
        assert b.is_all_done()
    finally:
        b.close()


def test_worker_engine_e2e_memory():
    b = create_backend("memory")
    b.init_table()
    for v in ("a", "b", "c"):
        b.submit("upper", {"value": v})
    eng = WorkerEngine(b, task_function=str.upper, worker_id="w1",
                       interval=0.01, max_idle_loops=1)
    n = eng.run_until_done()
    assert n == 3
    assert b.is_all_done()


def test_retry_then_success():
    # BUG-231: 本用例测「重试流程」（失败→再领取→成功），不是退避时序；
    # 显式 retry_delay_min=0 保持立即再领取的原意（退避由
    # tests/task/test_retry_backoff.py 单独锁）。
    b = MemoryTaskBackend(max_retries=2, retry_delay_min=0)
    b.init_table()
    tid = b.submit("flaky", {"value": "x"}, max_retries=2)

    calls = {"n": 0}

    def fn(_):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    eng = WorkerEngine(b, task_function=fn, worker_id="w1", interval=0.0)
    # 手动驱动：第一次失败后 RETRY_PENDING，引擎再次领取
    t = b.acquire("w1")
    try:
        eng.execute_task(t)
        b.complete(tid, "w1", {})
    except Exception as e:
        b.fail(tid, "w1", str(e))
    assert b.get(tid)["status"] == "RETRY_PENDING"
    t = b.acquire("w1")
    b.complete(tid, "w1", eng.execute_task(t))
    assert b.get(tid)["status"] == "SUCCESS"
