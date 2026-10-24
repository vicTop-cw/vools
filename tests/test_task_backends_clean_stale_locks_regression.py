# -*- coding: utf-8 -*-
"""回归测试：clean_stale_locks 真正使用 timeout_min（BUG-406）。

三个后端（memory / sqlite / pg）的实现**完全忽略** ``timeout_min`` 参数：

    def clean_stale_locks(self, timeout_min: int = 10) -> int:
        ... WHERE status='RUNNING' AND lease_timeout < now
        # timeout_min 从未被引用

调用方传 ``timeout_min=30`` 以为只有超过 30 分钟的锁才被回收，实际任何
"lease 已过期" 的 RUNNING 都会被回收——参数静默无效；而 worker 在 acquire
之后、写 lease 之前崩溃留下的 **lease 为空的僵尸 RUNNING** 任务则永远回收不掉。

修复：真正使用 ``timeout_min``——除「lease 已过期」外，同时回收
「``lease_timeout`` 为空且 ``updated_at`` 早于 ``timeout_min`` 分钟」的僵尸任务；
并对 ``timeout_min`` 做类型/范围校验（数字、非 bool、>= 0）。

memory 与 sqlite 的行为一致性也在本文件中断言（pg 需要真实数据库，仅校验
签名/校验逻辑不在此覆盖）。
"""

import datetime
import uuid

import pytest

from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend


def _make(kind, tmp_path):
    if kind == 'memory':
        return MemoryTaskBackend()
    return SqliteTaskBackend(db_path=str(tmp_path / f'{uuid.uuid4().hex}.db'))


@pytest.fixture(params=['memory', 'sqlite'])
def backend(request, tmp_path):
    be = _make(request.param, tmp_path)
    try:
        yield be
    finally:
        try:
            be.close()
        except Exception:
            pass


def _force_lease_none(be, tid, age_min):
    """把任务改成「RUNNING + lease 为 NULL + updated_at 早于 age_min 分钟」。"""
    old_dt = datetime.datetime.utcnow() - datetime.timedelta(minutes=age_min)
    if hasattr(be, '_tasks'):
        be._tasks[tid]['lease_timeout'] = None
        be._tasks[tid]['updated_at'] = old_dt
    else:
        be._conn.execute(
            f'UPDATE "{be.table}" SET lease_timeout=NULL, updated_at=? WHERE id=?',
            (old_dt.isoformat(sep=" ", timespec="seconds"), tid))
        be._conn.commit()


class TestTimeoutValidation:
    @pytest.mark.parametrize('bad', ['x', None, True, [1]])
    def test_non_numeric(self, backend, bad):
        with pytest.raises(TypeError):
            backend.clean_stale_locks(timeout_min=bad)

    @pytest.mark.parametrize('bad', [-1, -10])
    def test_negative(self, backend, bad):
        with pytest.raises(ValueError):
            backend.clean_stale_locks(timeout_min=bad)


class TestTimeoutMinHonoured:
    def test_old_zombie_reclaimed(self, backend):
        tid = backend.submit('z', {})
        backend.acquire('w1')
        _force_lease_none(backend, tid, age_min=60)
        n = backend.clean_stale_locks(timeout_min=10)
        assert n == 1
        assert backend.get(tid)['status'] == 'RETRY_PENDING'

    def test_recent_zombie_kept_when_threshold_larger(self, backend):
        tid = backend.submit('z', {})
        backend.acquire('w1')
        _force_lease_none(backend, tid, age_min=5)
        n = backend.clean_stale_locks(timeout_min=10)
        # 修复前：参数被忽略，这里也会被回收吗？不会——旧实现只认 lease 过期，
        # lease 为 NULL 的僵尸**永远不回收**；修复后按 timeout_min 判断保留。
        assert n == 0
        assert backend.get(tid)['status'] == 'RUNNING'

    def test_recent_zombie_reclaimed_when_threshold_smaller(self, backend):
        tid = backend.submit('z', {})
        backend.acquire('w1')
        _force_lease_none(backend, tid, age_min=5)
        n = backend.clean_stale_locks(timeout_min=1)
        assert n == 1
        assert backend.get(tid)['status'] == 'RETRY_PENDING'

    def test_fresh_running_untouched(self, backend):
        tid = backend.submit('f', {})
        backend.acquire('w1')
        assert backend.clean_stale_locks(timeout_min=10) == 0
        assert backend.get(tid)['status'] == 'RUNNING'


class TestExpiredLeaseStillReclaimed:
    @pytest.mark.parametrize('kind', ['memory', 'sqlite'])
    def test_expired_lease(self, kind, tmp_path):
        be = _make(kind, tmp_path)
        try:
            tid = be.submit('e', {})
            be.acquire('w1')
            past = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
            if hasattr(be, '_tasks'):
                be._tasks[tid]['lease_timeout'] = past
            else:
                be._conn.execute(
                    f'UPDATE "{be.table}" SET lease_timeout=? WHERE id=?',
                    (past.isoformat(sep=" ", timespec="seconds"), tid))
                be._conn.commit()
            assert be.clean_stale_locks(timeout_min=10) == 1
            assert be.get(tid)['status'] == 'RETRY_PENDING'
        finally:
            try:
                be.close()
            except Exception:
                pass