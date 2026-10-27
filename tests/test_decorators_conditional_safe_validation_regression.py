# -*- coding: utf-8 -*-
"""回归测试：conditional 的 action/condition 零校验 + safe 接受非可调用（BUG-524）。

修复前：

    @conditional(check, action='bogus')     # 既不 skip 也不 warn → **静默无条件执行**
    def f(): ...                            #   （装饰器形同不存在）
    conditional(None)                       # 装饰期不报错；调用期才 TypeError:
                                            #   'NoneType' object is not callable
    safe(123)                               # 把 int 当函数包起来，调用期才炸
                                            #   'int' object is not callable

修复后：condition 必须可调用、action 只接受 'skip'/'warn'、safe 的 func 必须是
可调用或 None，全部在装饰期报错。

注：safe(default=0/''/False/None) 一直是正确的（用 _MISSING 哨兵区分"未传"），
本文件同时锁定该契约，防止未来被误改成 falsy 判断。
"""

import importlib

import pytest

sc = importlib.import_module("vools.decorators.shotcut")


class TestConditionalValidation:
    @pytest.mark.parametrize("bad", [None, 123, "x"])
    def test_condition_must_be_callable(self, bad):
        with pytest.raises(TypeError) as ei:
            sc.conditional(bad)
        assert "condition" in str(ei.value)

    @pytest.mark.parametrize("bad", ["bogus", "raise", "", None])
    def test_action_must_be_supported(self, bad):
        with pytest.raises(ValueError) as ei:
            sc.conditional(lambda: True, bad)
        assert "action" in str(ei.value)


class TestConditionalBehaviourUnchanged:
    def test_skip(self):
        @sc.conditional(lambda: True, "skip")
        def f():
            return "ran"

        assert f() is None

    def test_warn_still_executes(self):
        import warnings

        @sc.conditional(lambda: True, "warn")
        def f():
            return "executed"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert f() == "executed"
            assert len(caught) == 1

    def test_condition_false_runs(self):
        @sc.conditional(lambda: False)
        def f():
            return "ran"

        assert f() == "ran"

    def test_condition_receives_args(self):
        # 语义：condition 为**真**时执行 action（默认 skip → 跳过并返回 None）；
        # 为假时正常执行函数。
        @sc.conditional(lambda x: x > 0)
        def f(x):
            return x

        assert f(5) is None        # 条件成立 → skip
        assert f(-1) == -1         # 条件不成立 → 执行


class TestSafeValidation:
    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_non_callable_rejected(self, bad):
        with pytest.raises(TypeError) as ei:
            sc.safe(bad)
        assert "func" in str(ei.value)

    def test_none_still_returns_decorator(self):
        assert callable(sc.safe(None))
        assert callable(sc.safe())


class TestSafeDefaultContract:
    @pytest.mark.parametrize("default", [0, "", False, None, [], {}])
    def test_falsy_defaults_are_respected(self, default):
        """显式 default 即便是 falsy 也必须生效（_MISSING 哨兵契约）。"""

        def boom():
            raise ValueError("x")

        assert sc.safe(default=default)(boom)() == default

    def test_missing_default_returns_tuple(self):
        def boom():
            raise ValueError("x")

        result = sc.safe(boom)()
        assert isinstance(result, tuple)
        assert result[0] is None
        assert isinstance(result[1], ValueError)

    def test_success_passthrough(self):
        assert sc.safe(lambda: 42)() == 42

    def test_exceptions_filter(self):
        def boom():
            raise KeyError("k")

        # 只捕获 ValueError → KeyError 继续外抛
        with pytest.raises(KeyError):
            sc.safe(exceptions=(ValueError,))(boom)()
