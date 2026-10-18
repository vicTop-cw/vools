# -*- coding: utf-8 -*-
"""tests/decorators/test_repeat_positional.py — repeat 位置参数校验（钉 BUG-93）

BUG-93: @repeat(3) 误用——位置参数 3 被赋给 func，而非 cnt。
decorator(3) 用 @wraps(3) 创建 wrapper，int 无 __name__ 等属性，
wraps 静默跳过，返回一个生成器函数。再用 @repeat(3) 装饰真实函数 f 时，
f 被赋值为 wrapper(f)，而 wrapper 是生成器函数（含 yield），
调用 wrapper(f) 返回生成器对象而非执行函数体，导致 f 变成
「不可调用对象」（generator object is not callable）。

修复：repeat() 在 func 非 None 但不可调用时显式 raise TypeError。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.decorators.control import repeat  # noqa: E402


class TestRepeatPositionalGuard:
    """位置参数必须是可调用对象"""

    def test_positional_int_raises(self):
        """@repeat(3) 应显式报错"""
        with pytest.raises(TypeError, match="first positional arg must be callable"):
            @repeat(3)
            def f():
                return 1

    def test_positional_float_raises(self):
        with pytest.raises(TypeError, match="first positional arg must be callable"):
            @repeat(1.5)
            def f():
                return 1

    def test_positional_string_raises(self):
        with pytest.raises(TypeError, match="first positional arg must be callable"):
            @repeat("abc")
            def f():
                return 1


class TestRepeatCorrectUsage:
    """正确用法不受影响"""

    def test_no_args(self):
        @repeat
        def f():
            return 1
        assert list(f()) == [1]

    def test_cnt_keyword(self):
        @repeat(cnt=3, delay=0)
        def f():
            return 1
        assert list(f()) == [1, 1, 1]

    def test_cnt_zero(self):
        @repeat(cnt=0)
        def f():
            return 1
        assert list(f()) == []

    def test_cnt_callable(self):
        counter = {'n': 0}

        def should_continue():
            counter['n'] += 1
            return counter['n'] <= 2

        @repeat(cnt=should_continue, delay=0)
        def f():
            return 'x'
        assert list(f()) == ['x', 'x']

    def test_cnt_negative_infinite(self):
        @repeat(cnt=-1, delay=0)
        def f():
            return 'x'
        gen = f()
        results = [next(gen) for _ in range(3)]
        assert results == ['x', 'x', 'x']