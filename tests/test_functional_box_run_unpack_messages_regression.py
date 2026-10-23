# -*- coding: utf-8 -*-
"""回归测试：Box.run 的 unpack 参数错误信息可诊断（BUG-344）。

`run(..., unpack='*')` 需要 `__wrapped__` 可迭代、`unpack='**'` 需要 dict。
原实现不满足时抛：

    TypeError: object of type 'int' has no len()

但问题与 `len()` 无关（标量同样有 len 概念之外的原因），信息误导用户去检查
长度。修复后明确说明解包模式与实际的 `__wrapped__` 类型/取值。

（`run(func_str)` 走 `g` 解析：`"x*2"` 这类非文档格式会退化为 **0 参 lambda**
并在调用时抛 NameError——这是 `g` 支持 `env` 参数的既有设计，非缺陷。）
"""

import pytest

from vools.functional.box import box


@box
def _scalar():
    return 5


@box
def _num_list():
    return [1, 2, 3]


@box
def _mapping():
    return {'a': 1, 'b': 2}


class TestUnpackStarErrors:
    def test_scalar_message(self):
        with pytest.raises(TypeError) as ei:
            _scalar().run(lambda x: x, unpack='*')
        msg = str(ei.value)
        assert "unpack='*'" in msg
        assert '可迭代' in msg
        assert 'int' in msg
        # 修复前：误导性的 has no len()
        assert 'has no len()' not in msg

    def test_dict_ok_with_star(self):
        # dict 本身可迭代（键），unpack='*' 应正常工作
        assert _mapping().run(lambda a, b: (a, b), unpack='*') is not None


class TestUnpackDoubleStarErrors:
    def test_non_dict_message(self):
        with pytest.raises(TypeError) as ei:
            _scalar().run(lambda: 1, unpack='**')
        msg = str(ei.value)
        assert "unpack='**'" in msg
        assert '字典' in msg
        assert 'has no len()' not in msg


class TestUnpackSuccessUnchanged:
    def test_star(self):
        assert _num_list().run(lambda a, b, c: a + b + c, unpack='*') == 6

    def test_star_rerun(self):
        assert _num_list().run(lambda x: x * 2, unpack='*', rerun=True,
                               nobox=True) == [2, 4, 6]

    def test_double_star(self):
        assert _mapping().run(lambda a, b: a + b, unpack='**') == 3

    def test_double_star_rerun(self):
        assert _mapping().run(lambda v: v * 10, unpack='**', rerun=True,
                              nobox=True) == {'a': 10, 'b': 20}

    def test_default_mode(self):
        assert _num_list().run(lambda d: sum(d)) == 6

    def test_nobox(self):
        assert _num_list().run(lambda d: sum(d), nobox=True) == 6