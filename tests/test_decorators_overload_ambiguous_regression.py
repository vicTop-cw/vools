# -*- coding: utf-8 -*-
"""回归测试：overload 的 Ambiguous 语义与"兜底主函数"写法（BUG-360）。

模块文档原先声称「显式开启 Ambiguous 即可按类型分派」，但实际语义是
候选按 ``(-priority, 注册顺序)`` 排序后**取第一个匹配**；主函数最先注册
（priority 默认 0），所以**无注解主函数会命中一切**，吞掉后注册的类型重载：

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b): return 'MAIN'
    @add.register
    def add_int(a: int, b: int): return 'INT'
    add(1, 2)   # -> 'MAIN'（按类型分派失败）

该行为被 tests/decorators/test_overload_bug107.py 显式锁定（"主函数先注册，
Ambiguous 取第一个"），因此**不改变行为**，而是修正文档并锁定正确写法：

- 给主函数低优先级：``@overload(..., priority=-1)`` → 有注解重载优先，
  主函数成为真正的"兜底"（推荐）；
- 或让主函数自身带注解（如 ``x: object``）作为显式兜底。

本测试同时锁住：默认注册顺序语义、Non-Ambiguous 的模糊调用报错、
priority 排序。
"""

import pytest

from vools.decorators.overload import (
    AllowSyncName,
    Ambiguous,
    Priority,
    Strict,
    overload,
    reset_registry,
)

MODE = Priority | AllowSyncName | Strict | Ambiguous


@pytest.fixture(autouse=True)
def _reset():
    reset_registry()


class TestFallbackViaLowPriority:
    """推荐写法：主函数 priority=-1 作为兜底，类型重载优先。"""

    def test_type_dispatch(self):
        @overload(mode=MODE, priority=-1)
        def add(a, b):
            return 'MAIN'

        @add.register
        def add_int(a: int, b: int):
            return 'INT'

        @add.register
        def add_str(a: str, b: str):
            return 'STR'

        assert add(1, 2) == 'INT'
        assert add('a', 'b') == 'STR'

    def test_fallback_when_no_typed_match(self):
        @overload(mode=MODE, priority=-1)
        def add(a, b):
            return 'MAIN'

        @add.register
        def add_int(a: int, b: int):
            return 'INT'

        assert add(1.0, 2.0) == 'MAIN'
        assert add(1, 'a') == 'MAIN'


class TestAnnotatedObjectFallback:
    def test_object_annotation_is_fallback_by_order(self):
        @overload(mode=MODE)
        def f(x: object):
            return 'OBJECT'

        @f.register
        def f_str(x: str):
            return 'STR'

        # object 注解先注册 -> Ambiguous 取第一个 -> OBJECT
        assert f('a') == 'OBJECT'


class TestRegistrationOrderSemantics:
    """既有契约（tests/decorators/test_overload_bug107.py 锁定）。"""

    def test_untyped_main_wins_first(self):
        @overload(mode=MODE)
        def calc(x):
            return 'untyped'

        @calc.register
        def calc_str(x: str):
            return f'str:{x}'

        assert calc('hi') == 'untyped'
        assert calc(42) == 'untyped'

    def test_priority_respected(self):
        @overload(mode=MODE)
        def pick(a):
            return 'MAIN'

        @pick.register(priority=5)
        def pick_high(a: int):
            return 'HIGH'

        @pick.register(priority=1)
        def pick_low(a: int):
            return 'LOW'

        assert pick(1) == 'HIGH'


class TestNonAmbiguous:
    def test_ambiguous_call_raises(self):
        @overload(mode=Priority | AllowSyncName | Strict)
        def fn(x):
            return x

        @fn.register
        def fn_int(x: int):
            return x

        with pytest.raises(TypeError, match='模糊调用'):
            fn(1)

    def test_no_match_raises(self):
        @overload(mode=MODE, priority=-1)
        def only_int(a: int):
            return 'I'

        with pytest.raises(TypeError):
            only_int('x')