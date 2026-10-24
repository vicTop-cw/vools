# -*- coding: utf-8 -*-
"""回归测试：Seq 的 n 参数校验与 LINQ 表达式形式提示（BUG-414）。

**问题 1**：`take/skip/grouper/tee` 对 n **零校验**，非法值一律静默返回空序列：

    list(Seq([1, 2]).take(-1))       # 修复前 -> []（像是"没有元素"，实为参数错）
    list(Seq([1, 2]).skip(-1))       # -> [1, 2]（负跳过被静默当成 0）
    list(Seq([1, 2]).grouper(0))     # -> []
    list(Seq([1, 2]).tee(-1))        # -> []

**问题 2**：`where('x > 1')`（非 lambda 形式）最终生成 0 参 lambda，调用时报
``TypeError: <lambda>() takes 0 positional arguments but 1 was given``——与
"表达式写法不对"毫无关联。修复后提前抛 ValueError 并给出正确写法。

正常路径（含 `take(0)`、`take(action=True)`、lambda 字符串表达式、可调用谓词）
行为不变。
"""

import pytest

from vools.data.seq import Seq


class TestTakeValidation:
    @pytest.mark.parametrize('bad', [-1, -100])
    def test_negative(self, bad):
        with pytest.raises(ValueError):
            Seq([1, 2]).take(bad)

    @pytest.mark.parametrize('bad', ['2', 2.5, None, True])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            Seq([1, 2]).take(bad)

    def test_normal(self):
        assert list(Seq([1, 2, 3]).take(2)) == [1, 2]
        assert list(Seq([1, 2, 3]).take(0)) == []
        assert list(Seq([1, 2, 3]).take(99)) == [1, 2, 3]
        assert Seq([1, 2, 3]).take(2, action=True) == [1, 2]


class TestSkipValidation:
    @pytest.mark.parametrize('bad', [-1, -5])
    def test_negative(self, bad):
        with pytest.raises(ValueError):
            Seq([1, 2]).skip(bad)

    @pytest.mark.parametrize('bad', ['1', 1.5, None])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            Seq([1, 2]).skip(bad)

    def test_normal(self):
        assert list(Seq([1, 2, 3]).skip(1)) == [2, 3]
        assert list(Seq([1, 2, 3]).skip(0)) == [1, 2, 3]
        assert list(Seq([1, 2, 3]).skip(9)) == []


class TestGrouperValidation:
    @pytest.mark.parametrize('bad', [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError):
            Seq([1, 2]).grouper(bad)

    @pytest.mark.parametrize('bad', ['2', None, 2.0])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            Seq([1, 2]).grouper(bad)

    def test_normal(self):
        assert list(Seq([1, 2, 3]).grouper(2)) == [(1, 2), (3, None)]
        assert list(Seq([1, 2, 3]).grouper(2, fillvalue=0)) == [(1, 2), (3, 0)]


class TestTeeValidation:
    @pytest.mark.parametrize('bad', [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError):
            Seq([1, 2]).tee(bad)

    @pytest.mark.parametrize('bad', ['2', None, 2.0])
    def test_bad_type(self, bad):
        with pytest.raises(TypeError):
            Seq([1, 2]).tee(bad)

    def test_normal(self):
        assert list(Seq([1, 2, 3]).tee(2)) == [(1, 2), (3, None)]
        assert list(Seq([1, 2, 3]).tee(3, fillvalue='-')) == [(1, 2, 3)]


class TestExpressionFormHint:
    @pytest.mark.parametrize('expr', ['x > 1', 'x', ''])
    def test_where_requires_lambda_form(self, expr):
        with pytest.raises(ValueError) as ei:
            Seq([1, 2]).where(expr)
        assert 'lambda' in str(ei.value)

    def test_wherenot_requires_lambda_form(self):
        with pytest.raises(ValueError):
            Seq([1, 2]).wherenot('x > 1')

    def test_lambda_string_still_works(self):
        assert list(Seq([1, 2, 3]).where('lambda x: x > 1')) == [2, 3]

    def test_callable_still_works(self):
        assert list(Seq([1, 2, 3]).where(lambda x: x > 1)) == [2, 3]
        assert list(Seq([1, 2, 3]).wherenot(lambda x: x > 1)) == [1]

    def test_chain_ops_still_apply_on_iteration(self):
        # BUG-412 契约保持
        assert list(Seq([1, 2]).map(lambda x: x * 2)) == [2, 4]