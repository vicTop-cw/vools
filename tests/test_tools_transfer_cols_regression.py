# -*- coding: utf-8 -*-
"""回归测试：utils.tools 两处静默错误（BUG-292）。

① `transferCols` 对既非 str 也非 Iterable 的输入走到函数末尾无 return →
   隐式返回 None（docstring 承诺「Returns: 列名列表」）。下游症状完全指不到
   真因：`build_text(..., lst=123)` → `len(None)` TypeError；
   `generate_lambda('x+1', None)` → 误报 `ExpressionSecurityError`。
② `transfer` 装饰器把 dict 返回值当 Iterable → 转成 VList(仅键)，字典的值
   被静默丢弃。

修复：① 不支持的类型显式 raise TypeError；② dict 在 Iterable 分支前直通。
"""

import pytest

from vools.utils.tools import (
    build_text,
    generate_lambda,
    toOrderedDict,
    transfer,
    transferCols,
)


class TestTransferColsExplicitError:
    @pytest.mark.parametrize('bad', [123, 1.5, True, object()])
    def test_non_iterable_raises(self, bad):
        with pytest.raises(TypeError, match='transferCols'):
            transferCols(bad)

    def test_valid_inputs_unchanged(self):
        assert transferCols('a,b') == ['a', 'b']
        assert transferCols('a') == ['a']
        assert transferCols([' a ', 'b']) == ['a', 'b']
        assert transferCols(None) == []
        assert transferCols('') == []
        assert transferCols([]) == []

    def test_downstream_errors_now_clear(self):
        # 修复前分别是 len(None) / 'NoneType' not iterable / 误报安全错误
        with pytest.raises(TypeError):
            build_text('v={item}', lst=123)
        with pytest.raises(TypeError):
            generate_lambda('x+1', 123)

    def test_to_ordered_dict_non_iterable_still_works(self):
        # toOrderedDict 自己把非可迭代包成 [x]，不受影响
        assert dict(toOrderedDict(123)) == {'col_0': 123}


class TestTransferDictPassthrough:
    def test_dict_returned_unchanged(self):
        @transfer
        def f():
            return {'a': 1, 'b': 2}

        # 修复前：VList(['a', 'b'])，1/2 丢失
        assert f() == {'a': 1, 'b': 2}

    def test_str_still_wrapped(self):
        @transfer
        def f():
            return 'txt'

        assert str(f()) == 'txt'
        assert type(f()).__name__ == 'VText'

    def test_list_still_wrapped(self):
        @transfer
        def f():
            return [1, 2, 3]

        assert list(f()) == [1, 2, 3]
        assert type(f()).__name__ == 'VList'

    def test_scalar_returned_unchanged(self):
        @transfer
        def f():
            return 42

        assert f() == 42