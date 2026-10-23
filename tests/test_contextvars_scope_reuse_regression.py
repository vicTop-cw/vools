# -*- coding: utf-8 -*-
"""回归测试：ContextScope 可复用 + 上下文工具整体语义（BUG-342）。

`ContextScope.__exit__` 原本会 `self._bindings = []` 清空登记的绑定，导致
**同一个 scope 实例第二次 `with` 静默不生效**：

    s = ContextScope().set('a', 1)
    with s:  assert a.get() == 1     # ✓
    with s:  assert a.get() == 0     # ✗ 静默什么都不做（无异常、无告警）

修复：退出时保留 `_bindings`，每次 `__enter__` 重新应用；`with` 内 `set`
仍是「立即应用 + 记录 Token」，退出恢复。

本文件同时固化该模块其余语义（基础 set/reset、with_value、contextual、
copy/restore、ContextChain、异步任务隔离），防止后续漂移。
"""

import asyncio

import pytest

from vools.vconcurrent.contextvars_mod import (
    ContextChain,
    ContextScope,
    VContextVar,
    contextual,
    copy_context_dict,
    restore_context_dict,
)


class TestVContextVar:
    def test_default_and_is_set(self):
        v = VContextVar('t_default', default=10)
        assert v.get() == 10
        assert v.is_set() is False

    def test_set_reset(self):
        v = VContextVar('t_setreset', default=0)
        token = v.set(5)
        assert v.get() == 5
        assert v.is_set() is True
        v.reset(token)
        assert v.get() == 0
        assert v.is_set() is False

    def test_set_if_none(self):
        v = VContextVar('t_sin', default=0)
        assert v.set_if_none(1) is True
        assert v.set_if_none(2) is False
        assert v.get() == 1

    def test_with_value_restores(self):
        v = VContextVar('t_wv', default=1)
        with v.with_value(42):
            assert v.get() == 42
        assert v.get() == 1

    def test_no_default_raises(self):
        with pytest.raises(LookupError):
            VContextVar('t_nodefault').get()


class TestContextScopeReuse:
    """BUG-342 核心：同一实例可重复进入。"""

    def test_reuse_applies_bindings_again(self):
        a = VContextVar('t_r_a', default=0)
        b = VContextVar('t_r_b', default=0)
        s = ContextScope().set('t_r_a', 1).set('t_r_b', 2)

        with s:
            assert (a.get(), b.get()) == (1, 2)
        assert (a.get(), b.get()) == (0, 0)

        # 修复前这里静默保持 0
        with s:
            assert (a.get(), b.get()) == (1, 2)
        assert (a.get(), b.get()) == (0, 0)

    def test_three_times(self):
        v = VContextVar('t_r3', default=0)
        s = ContextScope().set('t_r3', 9)
        for _ in range(3):
            with s:
                assert v.get() == 9
            assert v.get() == 0

    def test_set_inside_with_still_immediate_and_restored(self):
        a = VContextVar('t_inside', default=0)
        s = ContextScope().set('t_inside', 1)
        with s:
            s.set('t_inside', 9)
            assert a.get() == 9
        assert a.get() == 0

    def test_nested_scopes(self):
        a = VContextVar('t_nest', default=0)
        outer = ContextScope().set('t_nest', 1)
        inner = ContextScope().set('t_nest', 7)
        with outer:
            assert a.get() == 1
            with inner:
                assert a.get() == 7
            assert a.get() == 1
        assert a.get() == 0

    def test_exception_safety(self):
        b = VContextVar('t_exc', default=0)
        s = ContextScope().set('t_exc', 5)
        with pytest.raises(RuntimeError):
            with s:
                raise RuntimeError('boom')
        assert b.get() == 0


class TestContextual:
    def test_reads_from_context(self):
        uid = VContextVar('t_uid', default=0)

        @contextual(uid, 'u')
        def f(x, u=None):
            return (x, u)

        token = uid.set(7)
        try:
            assert f(1) == (1, 7)
        finally:
            uid.reset(token)

    def test_explicit_argument_wins(self):
        uid = VContextVar('t_uid2', default=0)

        @contextual(uid, 'u')
        def f(x, u=None):
            return (x, u)

        token = uid.set(7)
        try:
            assert f(1, u=3) == (1, 3)
        finally:
            uid.reset(token)


class TestCopyRestore:
    def test_roundtrip(self):
        v1 = VContextVar('t_cr1', default=0)
        v2 = VContextVar('t_cr2', default=0)
        t1, t2 = v1.set(11), v2.set(22)
        try:
            snapshot = copy_context_dict()
            assert snapshot.get('t_cr1') == 11
            assert snapshot.get('t_cr2') == 22

            tokens = restore_context_dict({'t_cr1': 111})
            assert v1.get() == 111
            for var, token in tokens:
                var.reset(token)
            assert v1.get() == 11
        finally:
            v1.reset(t1)
            v2.reset(t2)


class TestContextChain:
    def test_child_overrides_parent(self):
        p = ContextChain()
        p.set('a', 1)
        p.set('b', 2)
        c = p.child()
        c.set('b', 3)
        assert p.get('a') == 1
        assert c.get('a') == 1      # 继承
        assert c.get('b') == 3      # 覆盖

    def test_nested_with(self):
        c1 = ContextChain()
        c1.set('k', 1)
        c2 = ContextChain()
        c2.set('k', 2)
        with c1:
            with c2:
                assert c2.get('k') == 2
            assert c1.get('k') == 1


class TestAsyncIsolation:
    def test_tasks_are_isolated(self):
        async def main():
            var = VContextVar('t_async', default='root')
            results = {}

            async def worker(name, delay):
                var.set(name)
                await asyncio.sleep(delay)
                results[name] = var.get()

            await asyncio.gather(worker('t1', 0.02), worker('t2', 0.01))
            return results, var.get()

        results, root = asyncio.run(main())
        assert results == {'t1': 't1', 't2': 't2'}
        assert root == 'root'