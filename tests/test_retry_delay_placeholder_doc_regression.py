# -*- coding: utf-8 -*-
"""回归测试：task backends 的 ``retry_delay_min`` 文档与真实行为一致（BUG-231）。

历史：该参数曾「只存储、零读取」——重试无任何退避，文档只能诚实写
「仅为 API 兼容占位，不影响重试时序」，本文件当时锁的就是那句占位声明。

现状：**退避已真实实现**（``fail()`` 写 ``next_retry_at = now + N 分钟``，
``acquire()`` 跳过未到期项，人工 ``retry()`` 清空退避立即放行），因此本文件
改写为锁「新契约」，防止文档退回虚假承诺、也防止实现退回零读取：

1. 文档**不得**再出现「占位 / 不影响重试时序」这类否认退避的措辞；
2. 文档必须写清**单位（分钟）**与 ``0`` 的语义；
3. 行为与文档一致：``retry_delay_min=5`` 时 ``fail`` 后不可立刻领取，
   ``=0`` 时可立刻领取（等价旧行为）。

时序细节（到期后可领、旧库迁移、上限转 FAILED 清退避）由
``tests/task/test_retry_backoff.py`` 覆盖。
"""

import os
import re

import pytest

from vools.task.backends.memory_backend import MemoryTaskBackend
from vools.task.backends.sqlite_backend import SqliteTaskBackend

BACKEND_CLASSES = [MemoryTaskBackend, SqliteTaskBackend]


def _pg_class_doc() -> str:
    """pg 后端依赖 psycopg2，只读源码 docstring 静态校验。"""
    p = os.path.join(os.path.dirname(__file__), "..", "vools",
                     "task", "backends", "pg.py")
    src = open(p, encoding="utf-8").read()
    m = re.search(r"class PgTaskBackend:.*?def __init__", src, re.S)
    assert m, "PgTaskBackend 定义未找到"
    return m.group(0)


class TestDocDeclaresRealBackoff:
    """文档必须声明「真实退避」，不得退回占位口径。"""

    @pytest.mark.parametrize("cls", BACKEND_CLASSES)
    def test_class_doc_describes_backoff(self, cls):
        doc = cls.__doc__ or ""
        assert "retry_delay_min" in doc
        assert "退避" in doc
        assert "分钟" in doc, "必须写清单位是分钟"
        # 旧占位口径必须消失
        assert "占位" not in doc, "退避已实现，不得再自称占位"
        assert "不影响重试时序" not in doc

    def test_pg_class_doc_describes_backoff(self):
        doc = _pg_class_doc()
        assert "retry_delay_min" in doc and "退避" in doc and "分钟" in doc
        assert "占位" not in doc and "不影响重试时序" not in doc


class TestBehaviorMatchesDoc:
    """行为与文档一致：退避真的生效。"""

    def test_delay_blocks_immediate_reclaim(self):
        backend = MemoryTaskBackend(retry_delay_min=5)
        tid = backend.submit("t", {"x": 1})
        assert backend.acquire(worker_id="w1", timeout_min=5) is not None
        backend.fail(tid, "w1", "boom")
        assert backend.acquire(worker_id="w2", timeout_min=5) is None

    def test_zero_delay_keeps_legacy_immediate_retry(self):
        backend = MemoryTaskBackend(retry_delay_min=0)
        tid = backend.submit("t", {"x": 1})
        assert backend.acquire(worker_id="w1", timeout_min=5) is not None
        backend.fail(tid, "w1", "boom")
        got = backend.acquire(worker_id="w2", timeout_min=5)
        assert got is not None and got["id"] == tid

    def test_manual_retry_is_immediate(self):
        backend = MemoryTaskBackend(retry_delay_min=5)
        tid = backend.submit("t", {})
        backend.acquire(worker_id="w1", timeout_min=5)
        backend.fail(tid, "w1", "boom")
        backend.retry(tid)              # 人工放行
        assert backend.acquire(worker_id="w2", timeout_min=5) is not None
