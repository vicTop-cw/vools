# -*- coding: utf-8 -*-
"""回归测试：submit 的任务选项与函数参数同名冲突（BUG-385）。

`TaskQueue.submit` 把 ``priority`` / ``max_retries`` / ``depends_on`` 从 kwargs
里 **pop** 出来当任务选项。如果函数本身有同名形参（或 ``**kwargs``），这些
参数就被**静默吞掉**，函数永远收不到：

    def f(priority=None): ...
    q.submit(f, priority=7)     # 任务 priority=7，但 f 收到 priority=None

修复：
1. 检测冲突（函数形参 / ``**kwargs`` 会接收该名字）→ 显式 ``ValueError``，
   说明原实现会吞参并给出替代写法；
2. 新增显式通道 ``submit(func, ..., task_options={...})``：提供后 ``**kwargs``
   **全部转发给函数**，任务选项只从 ``task_options`` 读取。
"""

import pytest

from vools.task.core.queue import TaskQueue
from vools.task.core.worker import Worker

# 任务函数由 worker 按模块属性解析，故放在模块级
def takes_priority(priority=None):
    return priority


def accepts_var_kwargs(**kwargs):
    return kwargs


def takes_depends_on(depends_on=None):
    return depends_on


def plain(a=0):
    return a


@pytest.fixture()
def env(tmp_path):
    db = str(tmp_path / 'tasks.db')
    return TaskQueue(db), db


class TestCollisionDetected:
    def test_positional_param_collision(self, env):
        q, _ = env
        # 修复前：静默吞参（任务 kwargs 变空）
        with pytest.raises(ValueError) as ei:
            q.submit(takes_priority, priority=7)
        msg = str(ei.value)
        assert '冲突' in msg and 'task_options' in msg

    def test_var_kwargs_collision(self, env):
        q, _ = env
        with pytest.raises(ValueError):
            q.submit(accepts_var_kwargs, priority=1)

    def test_depends_on_collision(self, env):
        q, _ = env
        first = q.submit(plain, 1)
        with pytest.raises(ValueError):
            q.submit(takes_depends_on, depends_on={first})

    def test_no_collision_unchanged(self, env):
        q, _ = env
        tid = q.submit(plain, a=3, priority=9)
        task = q.get_task(tid)
        assert task.kwargs == {'a': 3}
        assert task.priority == 9


class TestExplicitTaskOptions:
    def test_kwargs_forwarded(self, env):
        q, _ = env
        tid = q.submit(takes_priority, priority=7,
                       task_options={'priority': 5, 'max_retries': 2})
        task = q.get_task(tid)
        # 函数参数原样保留
        assert task.kwargs == {'priority': 7}
        # 任务选项来自 task_options
        assert task.priority == 5
        assert task.max_retries == 2

    def test_depends_on_via_options(self, env):
        q, _ = env
        first = q.submit(plain, 1)
        tid = q.submit(takes_depends_on, depends_on={first},
                       task_options={'depends_on': {first}})
        task = q.get_task(tid)
        assert task.kwargs == {'depends_on': {first}}
        assert task.dependencies == {first}

    def test_execution_passes_function_args(self, env):
        q, db = env
        tid = q.submit(takes_priority, priority=7,
                       task_options={'priority': 1})
        Worker('w1', db, lease_seconds=30)._process_one_task()
        assert q.get_result(tid, timeout=5) == 7