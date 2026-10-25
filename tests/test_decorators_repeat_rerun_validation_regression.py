# -*- coding: utf-8 -*-
"""回归测试：repeat/rerun 参数校验（BUG-478）。

修复前：

    repeat(cnt='x')          # 既不命中 callable 也不命中 int 分支 → 静默异常行为
    repeat(delay='x')        # 直到 time.sleep 才炸
    rerun(unknown_kw=1)      # **未知参数被静默忽略**，看起来配置成功、实际全用默认
    rerun(until=123)         # 调用期 TypeError 'int' object is not callable
    rerun(interval='x')      # 调用期才炸；interval=0 / time_out<0 也被接受

修复后装饰期即校验。文档语义保持不变：cnt>0 执行 N 次、cnt=0 不执行、
cnt<0 无限循环、cnt 为可调用时返回 False 停止；repeat 返回**生成器**需迭代。
"""

import pytest

import vools.decorators.control as ctl


class TestRepeatValidation:
    @pytest.mark.parametrize("bad", ["x", None, 1.5, [3]])
    def test_bad_cnt(self, bad):
        with pytest.raises(TypeError) as ei:
            ctl.repeat(cnt=bad)
        assert "cnt" in str(ei.value)

    @pytest.mark.parametrize("bad", ["x", None, [1]])
    def test_bad_delay(self, bad):
        with pytest.raises(TypeError) as ei:
            ctl.repeat(delay=bad)
        assert "delay" in str(ei.value)

    def test_bare_non_callable_guard_kept(self):
        """BUG-93 的守卫保持：位置参数必须是可调用对象。"""
        with pytest.raises(TypeError):
            ctl.repeat(3)


class TestRepeatSemanticsUnchanged:
    def test_count(self):
        calls = []

        @ctl.repeat(cnt=3)
        def f():
            calls.append(1)
            return len(calls)

        assert list(f()) == [1, 2, 3]

    def test_zero_means_no_execution(self):
        calls = []

        @ctl.repeat(cnt=0)
        def f():
            calls.append(1)

        assert list(f()) == []
        assert calls == []

    def test_callable_stop_condition(self):
        runs = []

        @ctl.repeat(cnt=lambda: len(runs) < 2)
        def f():
            runs.append(1)
            return len(runs)

        assert list(f()) == [1, 2]

    def test_delay_numeric_allowed(self):
        assert list(ctl.repeat(cnt=1, delay=0)(lambda: "x")()) == ["x"]


class TestRerunValidation:
    def test_unknown_kwargs_rejected(self):
        with pytest.raises(TypeError) as ei:
            ctl.rerun(unknown_kw=1)
        assert "unknown_kw" in str(ei.value)

    def test_until_must_be_callable(self):
        with pytest.raises(TypeError) as ei:
            ctl.rerun(until=123)
        assert "until" in str(ei.value)

    @pytest.mark.parametrize("kw", [{"interval": "x"}, {"time_out": "x"}, {"interval": None}])
    def test_numeric_types(self, kw):
        with pytest.raises(TypeError):
            ctl.rerun(**kw)

    @pytest.mark.parametrize("kw", [{"interval": 0}, {"time_out": 0}, {"interval": -1}, {"time_out": -1}])
    def test_positive_numbers(self, kw):
        with pytest.raises(ValueError):
            ctl.rerun(**kw)


class TestRerunSemanticsUnchanged:
    def test_until_satisfied(self):
        calls = []

        @ctl.rerun(until=lambda x: x == "ok", interval=0.01, time_out=2)
        def f():
            calls.append(1)
            return "ok" if len(calls) >= 2 else "pending"

        assert f() == "ok"
        assert len(calls) >= 2

    def test_bare_rerun(self):
        @ctl.rerun
        def f():
            return "v"

        assert f() == "v"

    def test_timeout_is_loud(self):
        @ctl.rerun(until=lambda x: False, interval=0.01, time_out=0.1)
        def f():
            return "never"

        with pytest.raises(TimeoutError):
            f()
