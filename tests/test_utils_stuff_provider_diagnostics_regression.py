# -*- coding: utf-8 -*-
"""回归测试：Stuff 提供者返回值不匹配时的可诊断错误（BUG-341）。

`provide_with` / `provide_multi_params` 把提供者返回值包装成 `IndexedDict`
后按名字/位置取值。当返回值**长度不足**时，原实现直接 `wrapper()[key]`，
用户只能看到裸异常：

    provide_with(lambda: 5, names=['a', 'b'])   -> StuffExecutionError: 'b'
    provide_multi_params(lambda: [1], count=2)  -> StuffExecutionError: tuple index out of range

既不知道是**哪个目标函数**、也不知道**期望几个/实际几个**。
修复：`_fill` 的取值访问器捕获 KeyError/IndexError，重抛 ValueError，说明
提供者、目标函数、缺失的键/位置、期望值与实际返回值。

成功路径与异常类型链（外层仍是 StuffExecutionError）保持不变。
"""

import pytest

from vools.utils.stuff import stuff


class TestProvideWithMismatch:
    def test_scalar_for_two_names(self):
        @stuff
        def f(a, b):
            return a, b

        f.provide_with(lambda: 5, names=['a', 'b'])
        with pytest.raises(Exception) as ei:
            f()
        msg = str(ei.value)
        # 修复前：消息只有 "'b'"
        assert 'f' in msg and "'b'" in msg
        assert '期望至少 2 个值' in msg
        assert '实际' in msg

    def test_short_tuple_for_three_names(self):
        @stuff
        def f(a, b, c):
            return a, b, c

        f.provide_with(lambda: (1, 2), names=['a', 'b', 'c'])
        with pytest.raises(Exception) as ei:
            f()
        msg = str(ei.value)
        assert "'c'" in msg and '期望至少 3 个值' in msg


class TestProvideMultiMismatch:
    def test_short_list_for_two_positions(self):
        @stuff
        def f(a, b):
            return a, b

        f.provide_multi_params(lambda: [1], count=2)
        with pytest.raises(Exception) as ei:
            f()
        msg = str(ei.value)
        # 修复前：'tuple index out of range'
        assert 'f' in msg and '期望至少 2 个值' in msg
        assert 'index out of range' not in msg


class TestSuccessPathsUnchanged:
    def test_provide_with(self):
        @stuff
        def f(a, b):
            return a * 10 + b

        f.provide_with(lambda: (1, 2), names=['a', 'b'])
        assert f() == 12

    def test_provide_multi_params(self):
        @stuff
        def f(a, b):
            return a + b

        f.provide_multi_params(lambda: [10, 20], count=2)
        assert f() == 30

    def test_provide_with_excess_values_ok(self):
        @stuff
        def f(a, b):
            return a, b

        f.provide_with(lambda: (1, 2, 3), names=['a', 'b'])
        assert f() == (1, 2)