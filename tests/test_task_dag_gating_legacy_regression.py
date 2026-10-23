# -*- coding: utf-8 -*-
"""回归测试：旧版 task core 的 DAG 依赖真正生效（BUG-384）。

`TaskQueue.submit(func, depends_on={...})` 会把依赖写入 `task_dependencies`
表（可由 `get_task().dependencies` 读回），但 `TaskStorage.claim_task` 的 SQL
只有 `WHERE status = 'PENDING'`，**完全没有依赖门控**：

    f = q.submit(boom, max_retries=0)        # 上游失败
    g = q.submit(ok_fn, depends_on={f})      # 下游
    worker 执行 -> f FAILED，g 照常执行并 SUCCESS

即依赖只是「记录」，从不影响执行顺序；而同仓库新后端
（`vools.task.backends._dag`）实现了完整状态机（PENDING→READY、失败级联
SKIPPED），两套语义不一致。

修复（对齐新后端语义）：
1. `claim_task` 增加门控：所有上游依赖必须 `SUCCESS`/`COMPLETED` 才可领取；
2. 上游终态 `FAILED` / `CANCEL` 时，尚未启动的（传递）下游级联 `SKIPPED`，
   并写入原因（避免永久 PENDING 卡死或错误执行）；
3. `retry_task` 同时接受 `SKIPPED`（复活后仍受门控约束，上游成功才执行）。
"""

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.core.storage import TaskStorage
from vools.task.core.worker import Worker

# 任务函数由 worker 按「模块属性」解析（局部函数无法解析），故置于模块级
_UPSTREAM_STATE = {'fail': True}


def upstream():
    if _UPSTREAM_STATE['fail']:
        raise RuntimeError('boom')
    return 'UP_OK'


@pytest.fixture()
def env(tmp_path):
    db = str(tmp_path / 'tasks.db')
    return TaskQueue(db), TaskStorage(db), db


class TestClaimGating:
    def test_downstream_not_claimable_before_dependency_succeeds(self, env):
        q, st, _ = env
        a = q.submit(lambda: 'A')
        b = q.submit(lambda: 'B', depends_on={a})
        claimed = st.claim_task('w1', 30)          # 修复前：可能拿到 b
        assert claimed is not None and claimed.id == a
        # a 仍在运行，b 不可领取
        assert st.claim_task('w2', 30) is None
        st.update_task_status(a, __import__(
            'vools.task.core.models', fromlist=['TaskStatus']).TaskStatus.SUCCESS,
            result='A', worker_id='w1')
        claimed2 = st.claim_task('w2', 30)
        assert claimed2 is not None and claimed2.id == b

    def test_no_dependency_unaffected(self, env):
        q, st, _ = env
        t = q.submit(lambda: 'X')
        claimed = st.claim_task('w1', 30)
        assert claimed is not None and claimed.id == t


class TestCascadeSkip:
    def test_upstream_failure_skips_downstream(self, env):
        q, _, db = env

        def boom():
            raise RuntimeError('dep fail')

        f = q.submit(boom, max_retries=0)
        g = q.submit(lambda: 'G', depends_on={f})
        Worker('w1', db, lease_seconds=30)._process_one_task()
        # 修复前：g 会正常执行并 SUCCESS
        assert q.get_task(f).status.value == 'FAILED'
        assert q.get_task(g).status.value == 'SKIPPED'
        assert '级联' in str(q.get_task(g).error_message)

    def test_transitive_skip(self, env):
        q, _, db = env

        def boom():
            raise RuntimeError('x')

        f = q.submit(boom, max_retries=0)
        g = q.submit(lambda: 'G', depends_on={f})
        h = q.submit(lambda: 'H', depends_on={g})
        Worker('w1', db, lease_seconds=30)._process_one_task()
        assert q.get_task(g).status.value == 'SKIPPED'
        assert q.get_task(h).status.value == 'SKIPPED'

    def test_cancel_skips_downstream(self, env):
        q, _, _ = env
        c = q.submit(lambda: 'C')
        d = q.submit(lambda: 'D', depends_on={c})
        assert q.cancel_task(c) is True
        assert q.get_task(c).status.value == 'CANCEL'
        assert q.get_task(d).status.value == 'SKIPPED'


class TestReviveAfterFix:
    def test_retry_upstream_then_downstream_runs(self, env):
        q, _, db = env
        _UPSTREAM_STATE['fail'] = True
        x = q.submit(upstream, max_retries=0)
        y = q.submit(lambda: 'Y', depends_on={x})
        Worker('w1', db, lease_seconds=30)._process_one_task()
        assert q.get_task(y).status.value == 'SKIPPED'

        assert q.retry_task(x) is True
        # 修复点：SKIPPED 也能复活
        assert q.retry_task(y) is True
        assert q.get_task(y).status.value == 'PENDING'

        _UPSTREAM_STATE['fail'] = False
        w = Worker('w1', db, lease_seconds=30)
        for _ in range(3):
            w._process_one_task()
        assert q.get_task(x).status.value == 'SUCCESS'
        assert q.get_task(y).status.value == 'SUCCESS'
        assert q.get_result(y, timeout=5) == 'Y'