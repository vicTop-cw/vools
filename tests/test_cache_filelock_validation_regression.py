# -*- coding: utf-8 -*-
"""回归测试：FileLock 路径校验与 acquire 幂等（BUG-471）。

修复前 ``FileLock.__init__`` 直接拼 ``f"{file_path}.lock"`` 且零校验：

    FileLock(None)   # 在**当前工作目录**创建 None.lock（静默错误路径）
    FileLock(123)    # 创建 123.lock
    FileLock('')     # 创建 .lock
    FileLock('   ')  # 创建 '   .lock'

且已持锁时重复 ``acquire()`` 会重新 ``open``（覆盖 ``_lock_fd``，旧句柄泄漏）。

修复后 ``file_path`` 必须是非空字符串；``acquire()`` 对已持锁实例幂等返回 True。
"""

import os

import pytest

from vools.cache import FileLock


class TestPathValidation:
    @pytest.mark.parametrize("bad", [None, 123, "", "   ", True, 1.5])
    def test_invalid_path_rejected(self, bad):
        with pytest.raises(ValueError) as ei:
            FileLock(bad)
        assert "file_path" in str(ei.value)

    def test_no_stray_files_created(self, tmp_path, monkeypatch):
        """非法构造不得在 cwd 落下 None.lock/123.lock 之类文件。"""
        monkeypatch.chdir(tmp_path)
        for bad in (None, 123, ""):
            with pytest.raises(ValueError):
                FileLock(bad)
        assert not [f for f in os.listdir(tmp_path) if f.endswith(".lock")]

    def test_valid_path(self, tmp_path):
        lock = FileLock(str(tmp_path / "x"))
        assert lock.lock_file_path.endswith(".lock")


class TestAcquireIdempotent:
    def test_double_acquire_same_instance(self, tmp_path):
        lock = FileLock(str(tmp_path / "x"))
        assert lock.acquire() is True
        assert lock.acquire() is True
        assert lock._lock_fd is not None
        lock.release()
        assert lock._locked is False

    def test_mutual_exclusion_between_instances(self, tmp_path):
        a = FileLock(str(tmp_path / "x"))
        b = FileLock(str(tmp_path / "x"))
        assert a.acquire() is True
        try:
            assert b.acquire() is False
        finally:
            a.release()
        assert b.acquire() is True
        b.release()

    def test_release_without_acquire_is_noop(self, tmp_path):
        lock = FileLock(str(tmp_path / "x"))
        lock.release()          # 不抛
        assert lock._locked is False

    def test_acquire_release_cycle(self, tmp_path):
        for _ in range(3):
            lock = FileLock(str(tmp_path / "x"))
            assert lock.acquire() is True
            lock.release()


class TestMissingDirectory:
    def test_loud_error(self, tmp_path):
        bad = FileLock(str(tmp_path / "nodir" / "x"))
        with pytest.raises((FileNotFoundError, OSError)):
            bad.acquire()
