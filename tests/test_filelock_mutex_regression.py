# -*- coding: utf-8 -*-
"""回归测试：FileLock 未获锁必须显式失败；persist 读路径互斥（BUG-212）。

原 `FileLock.__enter__` 丢弃 `acquire()` 返回值——Windows msvcrt.LK_NBLCK
锁被占用时非阻塞失败，with 主体照常在无锁状态下执行，互斥契约静默失效；
且 acquire 失败路径泄漏已 open 的文件句柄。persist 读路径原走该 with 形态
（BUG-144 只修了写路径），并发时可读到半截 JSON，可解析前缀更导致静默数据
损坏。

修复：`__enter__` 未获锁抛 OSError；`acquire` 失败关闭并丢弃 fd；persist
读路径与写路径对称——显式检查 `acquire()`，未获锁按缓存未命中重算。
"""

import json
import os
import threading

import pytest

from vools.cache.persist import FileLock, persist


@pytest.fixture
def cache_path(tmp_path):
    return str(tmp_path / "data.json")


class TestEnterRaisesWhenBusy:
    """with 形态在锁被占用时必须显式失败（BUG-212 ①）。"""

    def test_with_raises_when_held(self, cache_path):
        a = FileLock(cache_path)
        assert a.acquire() is True
        try:
            with pytest.raises(OSError):
                with FileLock(cache_path):
                    pytest.fail("临界区在无锁状态下被执行")
        finally:
            a.release()

    def test_normal_with_still_works(self, cache_path):
        with FileLock(cache_path) as lock:
            assert lock._locked is True
        # 释放后可再获取
        with FileLock(cache_path) as lock2:
            assert lock2._locked is True

    def test_failed_acquire_no_fd_leak(self, cache_path):
        a = FileLock(cache_path)
        assert a.acquire() is True
        b = FileLock(cache_path)
        assert b.acquire() is False
        assert b._lock_fd is None, "失败路径必须关闭并丢弃句柄"
        a.release()


class TestPersistReadMutualExclusion:
    """persist 读路径：外部持锁时不得读缓存文件（BUG-212 ②）。"""

    def test_skips_read_under_external_lock(self, tmp_path, cache_path):
        calls = []

        @persist(target_folder=str(tmp_path), file_key="data")
        def compute():
            calls.append(1)
            return {"v": len(calls)}

        assert compute() == {"v": 1}          # 首轮：计算+落盘
        assert compute() == {"v": 1}          # 二轮：命中缓存
        assert len(calls) == 1

        # 外部持锁并把文件改成"截断半截"——读应跳过重算，不返回坏数据
        held = FileLock(cache_path)
        assert held.acquire() is True
        try:
            with open(cache_path, "w") as fh:
                fh.write('{"result": {"v": 999}, "star')  # 非法 JSON
            r = compute()
            assert r == {"v": 2} and len(calls) == 2
        finally:
            held.release()

    def test_ignores_uncommitted_legal_prefix(self, tmp_path, cache_path):
        calls = []

        @persist(target_folder=str(tmp_path), file_key="data2")
        def compute():
            calls.append(1)
            return {"v": len(calls)}

        path = str(tmp_path / "data2.json")
        compute()

        # 持锁者视角"还没写完"的合法 JSON——绝不能被并发读当成已提交结果
        held = FileLock(path)
        assert held.acquire() is True
        try:
            with open(path, "w") as fh:
                fh.write('{"result": {"v": 666}}')        # 合法但未提交
            r = compute()
            assert r != {"v": 666}, "读到未提交的合法前缀=静默数据损坏"
        finally:
            held.release()


class TestPersistThreadedFreshness:
    """多线程同时首跑：结果一致（允许重复计算，不允许坏数据）。"""

    def test_concurrent_first_run(self, tmp_path):
        n = {"count": 0}
        lock = threading.Lock()

        @persist(target_folder=str(tmp_path), file_key="mt")
        def work():
            with lock:
                n["count"] += 1
            return {"ok": True}

        results = []
        ts = [threading.Thread(target=lambda: results.append(work()))
              for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        assert all(r == {"ok": True} for r in results)
        assert len(results) == 4
        # 缓存文件最终必须是可解析的完整 JSON
        with open(str(tmp_path / "mt.json"), encoding="utf-8") as fh:
            json.load(fh)