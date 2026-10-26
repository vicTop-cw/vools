# -*- coding: utf-8 -*-
"""回归测试：rate_limit 参数零校验 + 无条件调试打印（BUG-523）。

修复前：

    @rate_limit(2, -1)          # 静默接受：窗口过滤 `now - t < period` 恒为假，
    def f(): ...                #   调用记录永远为空 → **限流被完全绕过**
    @rate_limit(0, 60)          # 每次调用都被拒 → 函数永久返回 None
    @rate_limit("x", 60)        # 直到调用期才在 `len(calls) >= 'x'` 抛 TypeError
    f(1)                        # 每次都 print("调用 f，参数: (1,), {}") 与
                                #   print("f 返回: ...") —— 参数/返回值直打 stdout

修复：
- max_calls 必须正整数（bool 拒绝）、period 必须为正数（复用 _require_duration）；
- 未提供 logger 时不再打印每次调用的参数/返回值（仅保留超限提示）；
- 显式传 logger 时记录行为不变。
"""

import importlib

import pytest

sc = importlib.import_module("vools.decorators.shotcut")


class TestMaxCallsValidation:
    @pytest.mark.parametrize("bad", ["x", 1.5, True, None])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            sc.rate_limit(bad, 60)
        assert "max_calls" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            sc.rate_limit(bad, 60)
        assert "max_calls" in str(ei.value)


class TestPeriodValidation:
    @pytest.mark.parametrize("bad", [0, -1, -0.5])
    def test_non_positive(self, bad):
        with pytest.raises(ValueError) as ei:
            sc.rate_limit(1, bad)
        assert "period" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None, [1]])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            sc.rate_limit(1, bad)
        assert "period" in str(ei.value)


class TestNoUnconditionalDebugPrint:
    def test_silent_without_logger(self, capsys):
        @sc.rate_limit(100, 60)
        def f(x):
            return x * 2

        assert f(1) == 2
        out = capsys.readouterr().out
        assert "调用 f" not in out
        assert "参数" not in out
        assert "返回" not in out

    def test_over_limit_still_notice(self, capsys):
        @sc.rate_limit(1, 60)
        def f():
            return "ok"

        assert f() == "ok"
        assert f() is None
        assert "超过速率限制" in capsys.readouterr().out


class TestBehaviourUnchanged:
    def test_limit_hit(self):
        calls = [0]

        @sc.rate_limit(2, 60)
        def f():
            calls[0] += 1
            return calls[0]

        assert f() == 1
        assert f() == 2
        assert f() is None
        assert calls[0] == 2

    def test_window_reset(self):
        import time

        calls = [0]

        @sc.rate_limit(1, 0.01)
        def f():
            calls[0] += 1
            return calls[0]

        assert f() == 1
        assert f() is None
        time.sleep(0.02)
        assert f() == 2

    def test_logger_channel(self):
        class L:
            def __init__(self):
                self.msgs = []

            def info(self, m):
                self.msgs.append(m)

            def warning(self, m):
                self.msgs.append(m)

        log = L()

        @sc.rate_limit(100, 60, logger=log)
        def f():
            return "hi"

        assert f() == "hi"
        assert len(log.msgs) >= 2

    def test_separate_quota_per_function(self):
        """BUG-162：同一 rate_limit(...) 装饰多个函数时配额不共享。"""

        @sc.rate_limit(1, 60)
        def a():
            return "a"

        @sc.rate_limit(1, 60)
        def b():
            return "b"

        assert a() == "a"
        assert b() == "b"
