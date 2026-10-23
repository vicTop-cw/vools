# -*- coding: utf-8 -*-
"""回归测试：Box 数字索引/切片支持 vools 包装类型（BUG-343）。

`_box` 会把被装饰函数的返回值包装成 vools 类型：
`list -> VList`、`str -> VText`、`datetime -> VDate`。但 `Box.__getitem__` /
`_getitem_by_index` / `_getitem_by_slice` / `_get_keys` 只接受
`isinstance(base, (list, tuple))` —— 而 **VList/VText 支持下标却不是 list 子类**，
于是 Box 自己产出的对象无法索引（主功能失效）：

    @box
    def f(): return [1, 2, 3]
    f()[0]      # TypeError: 类型 'VList' 不支持数字索引
    f()._1      # 同上
    f()[0:2]    # TypeError: 类型 'VList' 不支持切片

修复：改为**鸭子类型**判断（非 dict 且具备 `__getitem__` 与 `__len__`），
索引/切片/键列表统一走可索引序列路径；标量仍抛清晰的 TypeError。
"""

import pytest

from vools.functional.box import Box, box


@box
def _get_list():
    return [1, 2, 3]


@box
def _get_str():
    return 'abc'


@box
def _get_dict():
    return {'a': 1, 'b': 2}


@box
def _get_tuple():
    return (1, 2)


@box
def _get_scalar():
    return 42


class TestListIndexing:
    def test_index(self):
        b = _get_list()
        # 修复前：TypeError 类型 'VList' 不支持数字索引
        assert b[0] == 1
        assert b[2] == 3

    def test_negative_index(self):
        assert _get_list()[-1] == 3

    def test_attribute_index(self):
        b = _get_list()
        assert b._1 == 1
        assert b._3 == 3

    def test_slice(self):
        sl = _get_list()[0:2]
        assert isinstance(sl, Box)
        assert list(sl.__wrapped__) == [1, 2]

    def test_get_keys(self):
        assert _get_list()._get_keys() == [0, 1, 2]

    def test_out_of_range(self):
        with pytest.raises(IndexError):
            _get_list()[5]


class TestStrAndTuple:
    def test_str_index(self):
        s = _get_str()
        assert str(s[0]) == 'a'

    def test_str_slice(self):
        assert str(_get_str()[0:2]) == 'ab'

    def test_tuple_index(self):
        assert _get_tuple()[0] == 1


class TestDictUnchanged:
    def test_by_key(self):
        d = _get_dict()
        assert d['a'] == 1
        assert d['b'] == 2

    def test_by_position(self):
        d = _get_dict()
        assert d[0] == 1
        assert d[1] == 2
        assert d._1 == 1

    def test_slice_by_key_order(self):
        sl = _get_dict()[0:1]
        assert isinstance(sl, Box)
        assert dict(sl.__wrapped__) == {'a': 1}

    def test_get_keys(self):
        assert _get_dict()._get_keys() == ['a', 'b']


class TestScalarStillRejected:
    def test_index_raises_type_error(self):
        with pytest.raises(TypeError):
            _get_scalar()[0]

    def test_slice_raises_type_error(self):
        with pytest.raises(TypeError):
            _get_scalar()[0:1]

    def test_get_keys_none(self):
        assert _get_scalar()._get_keys() is None


class TestChainedOperations:
    def test_map_filter_reduce(self):
        b = _get_list()
        assert list(b.map(lambda x: x * 2).__wrapped__) == [2, 4, 6]
        assert list(b.filter(lambda x: x > 1).__wrapped__) == [2, 3]
        assert b.reduce(lambda a, c: a + c).__wrapped__ == 6

    def test_map_then_index(self):
        # 链式结果同样是 Box(VList)，索引应可用
        assert _get_list().map(lambda x: x + 10)[0] == 11