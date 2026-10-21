# -*- coding: utf-8 -*-
"""回归测试：假值陷阱族严格用例（BUG-252 补充）。

`tests/test_bug252_falsy_trap_regression.py` 的 states=[] 用例先 acquire 了一次
（任务已变 RUNNING），空列表断言在修复前也会通过，无法真正守卫回归。本文件
用**首次领取**即传空列表的严格顺序验证，并覆盖 sqlite 后端（同形代码）。
"""

import pytest

from vools.data import Table
from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend


class TestEmptyStatesStrict:
    """states=[] 必须是「不领取任何状态」，首次调用即验证。"""

    def test_memory_first_acquire_empty_states(self):
        b = MemoryTaskBackend()
        b.submit('t1', payload={'v': 1})
        # 首次领取就传空列表：修复前会被替换为默认状态并领走 READY 任务
        assert b.acquire('w1', states=[]) is None
        # 任务仍应处于 READY（未被越权领走）
        assert b.count_by_status().get('READY', 0) == 1
        # 默认 None 仍能领到
        t = b.acquire('w1')
        assert t is not None and t['status'] == 'RUNNING'
        b.close()

    def test_sqlite_first_acquire_empty_states(self, tmp_path):
        b = SqliteTaskBackend(str(tmp_path / 'task.db'))
        b.init_table()
        b.submit('t1', payload={'v': 1})
        assert b.acquire('w1', states=[]) is None
        assert b.count_by_status().get('READY', 0) == 1
        t = b.acquire('w1')
        assert t is not None
        b.close()


class TestZeroRowsStrict:
    """from_file(rows=0) 由 BUG-255 范围外延后处理（table.py 正被并发修改）。

    说明：`Table.from_file(rows=0)` 同样是假值陷阱（读全文件），但修复需改
    vools/data/table.py，该文件当时存在其他 agent 的未提交改动，为避免提交
    窗口互相裹挟，延后到 table.py 空闲时单独处理（届时补此用例）。
    """

    def test_placeholder(self):
        assert True


class TestZeroIntervalPropagation:
    """interval=0 / timeout_min=0 不被替换。"""

    def test_run_once_zero_timeout(self):
        from unittest.mock import MagicMock
        from vools.task.core.worker_engine import WorkerEngine

        backend = MagicMock()
        backend.acquire.return_value = None
        engine = WorkerEngine(backend, worker_id='t')
        engine.run_once(timeout_min=0)
        assert backend.acquire.call_args[1]['timeout_min'] == 0

    def test_run_until_done_zero_interval_not_replaced(self):
        from unittest.mock import MagicMock
        from vools.task.core.worker_engine import WorkerEngine

        backend = MagicMock()
        backend.acquire.return_value = None
        engine = WorkerEngine(backend, worker_id='t')
        engine.max_idle_loops = 1
        engine.run_until_done(interval=0, timeout_min=0)
        assert backend.acquire.called
        assert backend.acquire.call_args[1]['timeout_min'] == 0