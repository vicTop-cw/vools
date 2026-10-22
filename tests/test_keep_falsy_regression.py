"""
BUG-305 回归测试：keep 函数应只移除 None，不移除其他 falsy 值

原实现 filter(identity, iterable) 把 0/False/"" 等 falsy 值也过滤掉了。
修复后 filter(lambda x: x is not None, iterable) 只移除 None。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.curried.iteration import keep


class TestKeepFalsyValues:
    """keep 只移除 None，保留其他 falsy 值"""

    def test_none_removed(self):
        assert list(keep([1, None, 2, None, 3])) == [1, 2, 3]

    def test_zero_kept(self):
        assert list(keep([0, None, 2])) == [0, 2]

    def test_false_kept(self):
        assert list(keep([False, None, True])) == [False, True]

    def test_empty_string_kept(self):
        assert list(keep(['', None, 'hello'])) == ['', 'hello']

    def test_all_none(self):
        assert list(keep([None, None, None])) == []

    def test_empty_list(self):
        assert list(keep([])) == []

    def test_no_none(self):
        assert list(keep([1, 2, 3])) == [1, 2, 3]
