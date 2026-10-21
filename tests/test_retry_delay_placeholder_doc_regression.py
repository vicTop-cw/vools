# -*- coding: utf-8 -*-
"""回归测试：task backends 的 retry_delay_min 文档与真实行为一致（BUG-231）。

`retry_delay_min` 在三后端（memory/sqlite/pg）均只存储、零读取，重试实际
无退避等待；此前无任何文档说明，测试仅锁定存储值，用户会误以为退避生效
（失败任务无间隔热循环重试）。

本轮采取文档对齐（真实退避实现需改状态机时序且单位未约定，留作后续）：
三后端类 docstring 明确声明该参数「仅为 API 兼容占位，不影响重试时序」。
本测试锁住该声明与「立即重试」的真实行为，防止文档漂移回虚假承诺。
"""

import pytest

from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend


class TestDocDeclaresPlaceholder:
    """文档必须声明 retry_delay_min 为占位（不是可用退避开关）。"""

    @pytest.mark.parametrize("cls", [MemoryTaskBackend, SqliteTaskBackend])
    def test_class_doc_mentions_placeholder(self, cls):
        doc = cls.__doc__ or ""
        assert "retry_delay_min" in doc
        assert "占位" in doc
        assert "退避" in doc

    def test_pg_class_doc(self):
        # pg 后端依赖 psycopg2，只读源码 docstring 静态校验
        import os
        import re
        p = os.path.join(os.path.dirname(__file__), "..", "vools",
                         "task", "backends", "pg.py")
        src = open(p, encoding="utf-8").read()
        m = re.search(r"class PgTaskBackend:.*?def __init__", src, re.S)
        assert m, "PgTaskBackend 定义未找到"
        doc = m.group(0)
        assert "retry_delay_min" in doc and "占位" in doc


class TestBehaviorMatchesPlaceholderSemantics:
    """行为与占位声明一致：失败后立即重试可领取（无延迟）。"""

    def test_immediate_retry_claimable(self):
        backend = MemoryTaskBackend(retry_delay_min=5)
        tid = backend.submit("t", {"x": 1})
        task = backend.acquire(worker_id="w1", timeout_min=5)
        assert task is not None
        backend.fail(tid, "w1", "boom")
        backend.retry(tid)
        # 文档声明无退避 → 立即应可再次领取
        assert backend.acquire(worker_id="w2", timeout_min=5) is not None

    def test_retry_delay_value_has_no_behavior_effect(self):
        # 不同 retry_delay_min 对时序无影响（占位语义，不是"bug 又回来了"）
        for v in (0, 1, 5, 999):
            backend = MemoryTaskBackend(retry_delay_min=v)
            tid = backend.submit("t", {})
            backend.acquire(worker_id="w", timeout_min=5)
            backend.fail(tid, "w", "err")
            backend.retry(tid)
            assert backend.acquire(worker_id="w2", timeout_min=5) is not None