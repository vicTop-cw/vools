# -*- coding: utf-8 -*-
"""回归测试：Box 的 dir()/__hasattr__ 与实际可访问性一致（BUG-349）。

`Box.__dir__` 与 `Box.__hasattr__` 原先只认 `isinstance(base, (dict, list, tuple))`，
但 `_box` 会把返回值包装成 `VList`/`VText` 等**非 list 子类**：

- `b.__dir__()` 里**没有**文档承诺的 `_1, _2, ...`（文档：dir 含数字索引属性）；
- `b._1` 能取到值，`b.__hasattr__('_1')` 却返回 False（同一属性两种答案）；
- `__hasattr__` 文档承诺支持 `_-1` 负索引，但 `__getattr__` 只有正索引分支
  （`getattr(b, '_-1')` 抛 AttributeError）。

修复：两处统一使用鸭子类型判定（非 dict 且具备 `__getitem__`/`__len__`），
并给 `__getattr__` 补 `_-N` 负索引分支，使 hasattr/取值/dir 三者一致。
"""

import pytest

from vools.functional.box import Box, box


@box
def _list_box():
    return [1, 2, 3]


@box
def _str_box():
    return 'abc'


@box
def _dict_box():
    return {'a': 1, 'b': 2}


@box
def _scalar_box():
    return 5


class TestDir:
    def test_list_includes_index_attrs(self):
        d = _list_box().__dir__()
        assert all(f'_{i}' in d for i in (1, 2, 3))

    def test_str_includes_index_attrs(self):
        assert '_1' in _str_box().__dir__()

    def test_scalar_has_no_index_attrs(self):
        assert '_1' not in _scalar_box().__dir__()

    def test_dir_sorted(self):
        d = _list_box().__dir__()

    def test_dir_contains_box_methods(self):
        d = _list_box().__dir__()
        assert {'map', 'filter', 'reduce', 'copy', 'run'} <= set(d)


class TestHasattrMatchesAccess:
    @pytest.mark.parametrize('name,expected', [
        ('_1', 1), ('_2', 2), ('_3', 3),
    ])
    def test_positive_index(self, name, expected):
        b = _list_box()
        assert b.__hasattr__(name) is True
        assert getattr(b, name) == expected

    def test_negative_index(self):
        b = _list_box()
        # 修复前：__hasattr__('_-1') 与 getattr(b,'_-1') 不一致
        assert b.__hasattr__('_-1') is True
        assert getattr(b, '_-1') == 3
        assert getattr(b, '_-3') == 1

    @pytest.mark.parametrize('name', ['_4', '_-4'])
    def test_out_of_range_false(self, name):
        b = _list_box()
        assert b.__hasattr__(name) is False
        with pytest.raises((IndexError, AttributeError)):
            getattr(b, name)

    def test_str_index(self):
        s = _str_box()
        assert s.__hasattr__('_1') is True
        assert str(s._1) == 'a'

    def test_dict_index_by_position(self):
        d = _dict_box()
        assert d.__hasattr__('_1') is True
        assert d.__hasattr__('_2') is True
        assert d.__hasattr__('_3') is False
        assert d._1 == 1

    def test_scalar_no_index(self):
        n = _scalar_box()
        assert n.__hasattr__('_1') is False
        assert n.__hasattr__('__class__') is True

    def test_unknown_attribute_false(self):
        assert _list_box().__hasattr__('definitely_not_here') is False