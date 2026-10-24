# -*- coding: utf-8 -*-
"""回归测试：VList.starmap / VList.run 对非法回调静默返回 []（BUG-445）。

与 BUG-444 同族的两个内部静默分支：

    VList([(1, 2), (3, 4)]).starmap(123)   # -> []   ← 静默丢数据
    VList([1, 2]).run(123)                 # -> []   ← run 本应返回单值，[] 是错误形状

修复后入口即抛带方法名的 TypeError；可调用对象与表达式字符串路径不变。
"""

import pytest

from vools.data.vlist import VList
from vools.security import ExpressionSecurityError


class TestStarmapValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"], object()])
    def test_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            VList([(1, 2), (3, 4)]).starmap(bad)
        assert "starmap" in str(ei.value)

    def test_callable_unchanged(self):
        assert VList([(1, 2), (3, 4)]).starmap(lambda a, b: a + b) == [3, 7]

    def test_expression_with_matching_symbols(self):
        assert VList([(1, 2), (3, 4)]).starmap("x + y") == [3, 7]

    def test_expression_with_unknown_symbols_rejected(self):
        """表达式里的变量不在允许集合时会抛出安全异常（不含静默空列表）。"""
        with pytest.raises(ExpressionSecurityError):
            VList([(1, 2)]).starmap("a + b")


class TestRunValidation:
    @pytest.mark.parametrize("bad", [123, 1.5, True, ["x"]])
    def test_non_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            VList([1, 2]).run(bad)
        assert "run" in str(ei.value)

    def test_callable_unchanged(self):
        assert VList([1, 2]).run(lambda lst: len(lst)) == 2

    def test_expression_unchanged(self):
        assert VList([1, 2]).run("len(x)") == 2


class TestLoudPathsUnchanged:
    def test_any_bad_pred_loud(self):
        with pytest.raises(TypeError):
            VList([1, 2]).any(123)

    def test_map_filter_still_guarded(self):
        """BUG-444 的守卫保持。"""
        with pytest.raises(TypeError):
            VList([1, 2]).map(123)
        with pytest.raises(TypeError):
            VList([1, 2]).filter(123)
