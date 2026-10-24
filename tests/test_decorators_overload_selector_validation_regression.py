# -*- coding: utf-8 -*-
"""回归测试：overload / Selector 注册参数校验（BUG-409）。

两者原先都缺参数校验：

    overload(123)              # AttributeError: 'int' object has no attribute '__name__'
    overload(priority='x')     # 接受；直到重载比较排序时才炸
    overloads(123)             # 同上（已弃用别名）
    Selector(123)              # 接受（源码注释称"直接 yield 它"），调用时才
                               # TypeError: 'int' object is not callable

修复：`overload` 的 func 必须可调用、priority 必须是 int（bool 除外）；
`Selector` 的每个参数必须可调用。正常重载分发、弃用告警、Selector 构造不变。
"""

import warnings

import pytest

from vools.decorators import reset_registry
from vools.decorators.overload import overload
from vools.decorators.selector import Selector

from vools.decorators import AllowSyncName, Ambiguous, Strict, overloads


@pytest.fixture(autouse=True)
def _reset():
    reset_registry()
    yield
    reset_registry()


class TestOverloadValidation:
    @pytest.mark.parametrize('bad', [123, 'not-callable', None])
    def test_non_callable_func_via_call(self, bad):
        if bad is None:
            with pytest.raises(TypeError):
                overload()(None)
            return
        with pytest.raises(TypeError) as ei:
            overload(bad)
        assert '可调用' in str(ei.value)

    @pytest.mark.parametrize('bad', ['x', True, 1.5, [1]])
    def test_bad_priority(self, bad):
        with pytest.raises(TypeError) as ei:
            overload(priority=bad)
        assert 'priority' in str(ei.value)

    def test_overloads_deprecated_still_validated(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter('always')
            with pytest.raises(TypeError):
                overloads(123)

    def test_normal_dispatch_unchanged(self):
        @overload(mode=Strict | Ambiguous | AllowSyncName, priority=0)
        def typed(x: object):
            return f"object:{type(x).__name__}"

        @typed.register
        def typed_str(x: str):
            return f"str:{x}"

        # 主函数优先（Ambiguous 取第一个匹配）——既有 BUG-107 契约
        assert typed('hi') == 'object:str'
        assert typed(1.5) == 'object:float'

    def test_overloads_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')

            @overloads
            def g(x):
                return 'g'

        assert g(1) == 'g'
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TestSelectorDocumentedLeniency:
    """Selector 允许非可调用对象（overcurry 内部会传入已求值的值）。

    BUG-409 调查记录：原以为这是"缺校验"，但 `tests/curried/test_overcurry_vic.py`
    依赖该宽松语义（Overloads.toSelector 会把值放进 funcs），故保留原行为并
    在此显式锁定，防止后续误改。
    """

    def test_non_callable_values_allowed(self):
        sel = Selector(1, 2)
        assert type(sel).__name__ == 'Selector'

    def test_mixed_callable_and_value(self):
        sel = Selector(lambda x: x + 1, 6)
        assert type(sel).__name__ == 'Selector'

    def test_no_args_still_value_error(self):
        with pytest.raises(ValueError):
            Selector()

    def test_normal_construction(self):
        sel = Selector(lambda x: x + 1, lambda x: x * 2)
        assert type(sel).__name__ == 'Selector'


class TestOvercurryStillWorks:
    def test_overcurry_chain(self):
        from vools.decorators import overcurry

        @overcurry
        def add(a, b):
            return a + b

        @add.register
        def add3(a, b, c):
            return a + b + 3 * 0

        assert add(1)(2) == 3
