"""BUG-97 回归测试：FileLock 锁竞争静默失败

FileLock.acquire() 原实现把锁竞争失败（PermissionError/OSError）静默吞掉，
调用方无法感知是否真的拿到了锁。多线程并发写缓存文件时可导致数据竞争。

修复：acquire() 返回 bool 表示锁是否获取成功，失败不再静默。
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.cache.persist import FileLock, persist


class TestFileLockAcquire:
    """FileLock.acquire() 锁竞争检测"""

    def test_first_acquire_succeeds(self, tmp_path):
        lock_path = str(tmp_path / 'cache.json')
        lock = FileLock(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_second_acquire_fails_when_held(self, tmp_path):
        """锁被持有时，第二个 acquire() 必须返回 False"""
        lock_path = str(tmp_path / 'cache.json')
        lock_a = FileLock(lock_path)
        assert lock_a.acquire() is True
        try:
            lock_b = FileLock(lock_path)
            assert lock_b.acquire() is False
            lock_b.release()
        finally:
            lock_a.release()

    def test_acquire_after_release_succeeds(self, tmp_path):
        lock_path = str(tmp_path / 'cache.json')
        lock_a = FileLock(lock_path)
        assert lock_a.acquire() is True
        lock_a.release()
        # 释放后可以再次获取
        lock_b = FileLock(lock_path)
        assert lock_b.acquire() is True
        lock_b.release()

    def test_thread_race_second_fails(self, tmp_path):
        """多线程竞争：第一个线程拿到锁，第二个必须失败"""
        lock_path = str(tmp_path / 'cache.json')
        results = []

        def worker(name):
            lock = FileLock(lock_path)
            acquired = lock.acquire()
            try:
                results.append((name, acquired))
                time.sleep(0.2)
            finally:
                lock.release()

        t1 = threading.Thread(target=worker, args=('A',))
        t2 = threading.Thread(target=worker, args=('B',))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join()
        t2.join()

        acqs = dict(results)
        assert acqs['A'] is True, '第一个线程应拿到锁'
        assert acqs['B'] is False, '第二个线程应拿不到锁'


class TestPersistDecorator:
    """persist 装饰器在锁修复后仍正常"""

    @pytest.fixture(autouse=True)
    def _cleanup(self, tmp_path):
        self.cache_dir = str(tmp_path / '__persist__')
        yield
        # 清理缓存
        if os.path.exists(self.cache_dir):
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_persist_read_write(self, tmp_path):
        call_count = [0]

        @persist(file_key='bug97_persist', target_folder=self.cache_dir)
        def compute():
            call_count[0] += 1
            return {'value': 42}

        # 第一次调用
        result = compute()
        assert result['value'] == 42
        assert call_count[0] == 1

        # 第二次调用命中缓存
        result = compute()
        assert result['value'] == 42
        assert call_count[0] == 1, '第二次调用应命中缓存'

        # 强制刷新
        result = compute(force=True)
        assert result['value'] == 42
        assert call_count[0] == 2

    def test_persist_force_when(self, tmp_path):
        call_count = [0]

        @persist(file_key='bug97_persist_fw', target_folder=self.cache_dir)
        def compute():
            call_count[0] += 1
            return {'v': call_count[0]}

        # 第一次
        r1 = compute(force_when=lambda r, s, e: False)
        assert r1['v'] == 1

        # 第二次：force_when 返回 False → 命中缓存
        r2 = compute(force_when=lambda r, s, e: False)
        assert r2['v'] == 1

        # 第三次：force_when 返回 True → 强制刷新
        r3 = compute(force_when=lambda r, s, e: True)
        assert r3['v'] == 2