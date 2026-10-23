# -*- coding: utf-8 -*-
"""回归测试：Table.substr 的位置参数校验（BUG-392）。

`substr` 文档声明 `start_pos` **从 1 开始**，但原实现对位置参数无任何校验：

    t.substr('sub', 'text', 0, 3)    # start = max(0, 0-1) = 0 → 静默从头截取 'Hel'
    t.substr('sub', 'text', -2, 3)   # 同样静默从头
    t.substr('sub', 'text', 1, -1)   # val[0:-1] → 静默丢掉末字符（Python 负索引语义）

三种都是「用户以为非法/无操作，实际拿到了错值」。修复：`start_pos` / `end_pos`
必须是 int（非 bool）且 >= 1，否则 TypeError / ValueError。

合法用法（1-based 起点、无 end_pos、Qax 子类）行为不变。
"""

import pytest

from vools.data.qax import Qax
from vools.data.table import Table


def _fresh():
    return Table([[1, 'Hello World'], [2, 'foo,bar']],
                 columns=['id', 'text'])


class TestValidUsage:
    def test_basic(self):
        t = _fresh()
        t.substr('sub', 'text', 1, 5)
        assert t._data[0][-1] == 'Hello'
        assert t._data[1][-1] == 'foo,b'

    def test_offset_start(self):
        t = _fresh()
        t.substr('sub', 'text', 2, 5)
        assert t._data[0][-1] == 'ello'

    def test_no_end(self):
        t = _fresh()
        t.substr('sub', 'text', 7)
        assert t._data[0][-1] == 'World'

    def test_qax_inherits(self):
        q = Qax([[1, 'Hello World']], columns=['id', 'text'])
        q.substr('sub', 'text', 1, 5)
        assert q._data[0][-1] == 'Hello'

    def test_end_equals_start(self):
        t = _fresh()
        t.substr('sub', 'text', 1, 1)
        assert t._data[0][-1] == 'H'


class TestInvalidPositions:
    @pytest.mark.parametrize('start', [0, -1, -2])
    def test_start_must_be_positive(self, start):
        with pytest.raises(ValueError) as ei:
            _fresh().substr('sub', 'text', start, 3)
        assert 'start_pos' in str(ei.value)

    @pytest.mark.parametrize('end', [-1, -5])
    def test_negative_end_rejected(self, end):
        with pytest.raises(ValueError) as ei:
            _fresh().substr('sub', 'text', 1, end)
        assert 'end_pos' in str(ei.value)

    def test_zero_end_means_empty_string(self):
        # BUG-249 既有语义：end_pos=0 → 截 0 个字符 = 空串（QAXSubstr length=0 走这条）
        t = _fresh()
        t.substr('sub', 'text', 1, 0)
        assert t._data[0][-1] == ''
        assert t._data[1][-1] == ''

    @pytest.mark.parametrize('bad', ['1', 1.5, True])
    def test_non_int_rejected(self, bad):
        with pytest.raises(TypeError):
            _fresh().substr('sub', 'text', bad, 3)

    def test_unknown_source_column_still_keyerror(self):
        with pytest.raises(KeyError):
            _fresh().substr('sub', 'nope', 1, 2)