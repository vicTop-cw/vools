# -*- coding: utf-8 -*-
"""审计锁定：memorize / once 的缓存语义（本轮审计确认无缺陷）。

锁定要点（防后续误改）：
1. ``memorize`` 的键**包含类型信息**：``f([1, 2])`` 与 ``f("[1, 2]")`` 不会串味，
   不可哈希参数（list/dict）也可用；不同调用签名（位置 vs 关键字）各自成一键。
2. ``memorize(duration=...)`` 到期后重算一次。
3. ``once``：函数只执行一次并缓存结果；``once(force=True)`` 强制重跑；
   ``once(force_default=True)`` **每次都重跑**（文档明示"每次都重新执行"）；
   ``@once`` 修饰类 → 单例（实例共享）。
4. 参数校验：``once(force_default=非布尔)`` 响亮 TypeError。
"""

import pytest

import vools.cache as ca


class TestMemorizeKeying:
    def test_unhashable_args_supported(self):
        calls = []

        @ca.memorize(duration=60)
        def f(x):
            calls.append(x)
            return len(x)

        assert f([1, 2]) == 2
        assert f([1, 2]) == 2          # 命中缓存
        assert len(calls) == 1

    def test_no_collision_between_list_and_repr_string(self):
        calls = []

        @ca.memorize(duration=60)
        def f(x):
            calls.append(x)
            return repr(x)

        assert f([1, 2]) == "[1, 2]"
        assert f("[1, 2]") == "'[1, 2]'"   # 不同键 → 各自计算
        assert len(calls) == 2

    def test_kwargs_distinguished(self):
        calls = []

        @ca.memorize(duration=60)
        def f(*, a=1):
            calls.append(a)
            return a

        assert f(a=1) == 1
        assert f(a=2) == 2
        assert len(calls) == 2

    def test_expiry_recomputes(self):
        import time
        calls = []

        @ca.memorize(duration=0.2)
        def f(x):
            calls.append(x)
            return x * 2

        assert f(3) == 6
        assert f(3) == 6
        assert len(calls) == 1
        time.sleep(0.3)
        assert f(3) == 6
        assert len(calls) == 2

    def test_recursive_use(self):
        @ca.memorize(duration=60)
        def fib(n):
            return n if n < 2 else fib(n - 1) + fib(n - 2)

        assert fib(10) == 55


class TestOnceSemantics:
    def test_runs_once(self):
        calls = []

        @ca.once
        def f():
            calls.append(1)
            return "v"

        assert f() == "v"
        assert f() == "v"
        assert len(calls) == 1

    def test_force_reexecutes(self):
        calls = []

        @ca.once
        def f():
            calls.append(1)
            return len(calls)

        assert f() == 1
        assert f(force=True) == 2

    def test_force_default_true_always_reexecutes(self):
        """文档语义：force_default=True 表示"每次都重新执行"。"""
        calls = []

        @ca.once(force_default=True)
        def f():
            calls.append(1)
            return len(calls)

        assert f() == 1
        assert f() == 2
        assert len(calls) == 2

    def test_singleton_class(self):
        @ca.once
        class Singleton:
            def __init__(self, value=0):
                self.value = value

        a = Singleton(1)
        b = Singleton(2)
        assert a is b
        assert a.value == 1     # 首次初始化值保留

    def test_first_result_returned_regardless_of_args(self):
        calls = []

        @ca.once
        def f(x):
            calls.append(x)
            return x

        assert f(1) == 1
        assert f(2) == 1        # once 语义：返回首次结果
        assert calls == [1]


class TestOnceValidation:
    @pytest.mark.parametrize("bad", ["yes", 1, None])
    def test_force_default_must_be_bool(self, bad):
        with pytest.raises(TypeError) as ei:
            ca.once(force_default=bad)
        assert "force_default" in str(ei.value)
