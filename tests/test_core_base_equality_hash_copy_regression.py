# -*- coding: utf-8 -*-
"""回归测试：VoolsBase 的相等/哈希/拷贝语义（BUG-415）。

`vools/core/base.py` 的 `VoolsBase` 被 40+ 类继承（`Seq`/`Table`/`Encoder`/
`TaskQueue`/…），其三个魔法方法原实现均有缺陷：

1. **`__eq__` 只比较 `__dict__`**，忽略 `__slots__` 中的数据：

       Seq([1, 2]) == Seq([1, 3])     # 修复前 -> True（不同内容判相等！）

2. **`__hash__` = `hash(tuple(sorted(self.__dict__.items())))`**：状态里有
   list/dict 时抛内部错误：

       hash(Seq([1, 2]))              # TypeError: unhashable type: 'list'

3. **`copy()` 把状态字典当构造参数**：

       Seq([1, 2]).copy()             # 修复前 -> Seq(['_ops', '_active_op'])
       VList([1, 2]).copy()           # 同样把属性名当元素

修复：
- `__eq__`：类型一致 + 合并 `__slots__` 与 `__dict__` 状态逐项比较，跳过
  函数/生成器等无相等语义的值；
- `SeqBase` 覆写为**按内容**比较（与 list/tuple 互比也成立），并 `__hash__ = None`；
- `__hash__`：内容可变对象给出明确 TypeError（不再泄漏内部错误）；
- `copy()`：使用标准库 `copy.copy`。
"""

import pytest

from vools.crypto.core import Encryptor
from vools.data.seq import Seq
from vools.data.table import Table
from vools.data.vlist import VList


class TestEquality:
    def test_seq_different_content_not_equal(self):
        # 修复前：True（数据在 __slots__ 里，__dict__ 只含操作管道）
        assert (Seq([1, 2]) == Seq([1, 3])) is False

    def test_seq_same_content_equal(self):
        assert (Seq([1, 2]) == Seq([1, 2])) is True

    def test_seq_compares_with_list(self):
        assert (Seq([1, 2]) == [1, 2]) is True
        assert (Seq([1, 2]) == [1, 3]) is False

    def test_seq_after_map(self):
        assert (Seq([1, 2]).map(lambda x: x * 2) == [2, 4]) is True

    def test_vlist(self):
        assert (VList([1, 2]) == VList([1, 2])) is True
        assert (VList([1, 2]) == VList([1, 3])) is False

    def test_table(self):
        assert (Table([[1]], columns=['a']) == Table([[1]], columns=['a'])) is True
        assert (Table([[1]], columns=['a']) == Table([[2]], columns=['a'])) is False

    def test_cross_type_not_equal(self):
        # VList 有自己的 __eq__（与 list 语义对齐），跨类型不承诺相等
        assert (Seq([1]) == Table([[1]], columns=['a'])) is False


class TestHash:
    def test_seq_hash_raises_clear_error(self):
        # 修复前：TypeError: unhashable type: 'list'（看不出是 Seq 不可哈希）
        with pytest.raises(TypeError) as ei:
            hash(Seq([1, 2]))
        assert 'Seq' in str(ei.value)

    def test_table_hash_raises_clear_error(self):
        with pytest.raises(TypeError) as ei:
            hash(Table([[1]], columns=['a']))
        assert 'Table' in str(ei.value)

    def test_hashless_objects_still_usable_in_lists(self):
        items = [Seq([1]), Seq([2])]
        assert len(items) == 2


class TestCopy:
    def test_seq_copy_content(self):
        # 修复前：Seq(['_ops', '_active_op'])
        assert list(Seq([1, 2]).copy()) == [1, 2]

    def test_vlist_copy_content(self):
        assert list(VList([1, 2]).copy()) == [1, 2]

    def test_table_copy(self):
        t = Table([[1, 'a']], columns=['id', 'name'], name='T')
        c = t.copy()
        assert type(c).__name__ == 'Table'
        assert c._data == [[1, 'a']]
        assert c._columns == ['id', 'name']

    def test_copy_is_shallow(self):
        t = Table([[1]], columns=['a'])
        c = t.copy()
        c._data[0][0] = 99
        assert t._data[0][0] == 99   # 浅拷贝：行对象共享

    def test_encoder_copy(self):
        e = Encryptor('hello')
        assert e.copy() is not e


class TestOtherMixinsUnchanged:
    def test_do_returns_self(self):
        s = Seq([1, 2])
        assert s.do(lambda x: None) is s

    def test_to_dict_public_attrs(self):
        e = Encryptor('hello')
        assert isinstance(e.to_dict(), dict)

    def test_update_sets_existing_attrs(self):
        from vools.core.base import VoolsBase

        class Demo(VoolsBase):
            def __init__(self):
                self.value = 1

        d = Demo()
        assert d.update(value=2) is d
        assert d.value == 2

    def test_update_ignores_unknown_attrs(self):
        from vools.core.base import VoolsBase

        class Demo(VoolsBase):
            def __init__(self):
                self.value = 1

        d = Demo()
        d.update(nope=3)          # 未知属性静默忽略（既有契约）
        assert not hasattr(d, 'nope')