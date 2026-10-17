# -*- coding: utf-8 -*-
"""测试 vools.api.memoize_cmd。"""

import pytest
from typer.testing import CliRunner

from vools.api.memoize_cmd import (
    parse_lambda_or_func, timing_decorator, call, benchmark, memoize_app
)

runner = CliRunner()

__all__ = ["TestParseLambda", "TestTimingDecorator", "TestCall",
           "TestBenchmark", "TestBenchmarkZeroElapsed", "TestApp", "TestImport"]


class TestParseLambda:
    """parse_lambda_or_func 测试。"""

    def test_lambda(self):
        f = parse_lambda_or_func("lambda x: x * 2")
        assert f(3) == 6

    def test_builtin(self):
        f = parse_lambda_or_func("abs")
        assert f(-5) == 5

    def test_unknown(self):
        with pytest.raises(ValueError):
            parse_lambda_or_func("no_such_func_name")


class TestTimingDecorator:
    """timing_decorator 测试。"""

    def test_basic(self):
        @timing_decorator
        def f(x):
            return x * 2
        result, elapsed = f(3)
        assert result == 6
        assert elapsed >= 0


class TestCall:
    """call 命令测试。"""

    def test_basic(self):
        result = runner.invoke(memoize_app, [
            "call", "lambda x: x * 2", "3", "--repeat", "2"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_repeat_zero_no_crash(self):
        # 回归：--repeat 0 时 total_time/repeat 会除零崩溃
        result = runner.invoke(memoize_app, [
            "call", "lambda x: x * 2", "3", "--repeat", "0"
        ])
        assert result.exit_code != 0  # typer.BadParameter -> exit code 2
        assert "正数" in result.output

    def test_show_cache(self):
        result = runner.invoke(memoize_app, [
            "call", "lambda x: x * 2", "3", "--repeat", "2", "--show-cache"
        ])
        assert result.exit_code == 0

    def test_no_show_cache(self):
        result = runner.invoke(memoize_app, [
            "call", "lambda x: x * 2", "3", "--repeat", "1", "--no-show-cache"
        ])
        assert result.exit_code == 0


class TestBenchmark:
    """benchmark 命令测试。"""

    def test_basic(self):
        result = runner.invoke(memoize_app, [
            "benchmark", "lambda x: x + 1", "1", "--iterations", "10"
        ])
        assert result.exit_code == 0
        assert "总耗时" in result.output


class TestBenchmarkZeroElapsed:
    """回归：极快函数下 elapsed 可能为 0，除零直接崩溃（ZeroDivisionError）。"""

    def test_zero_elapsed_no_crash(self, monkeypatch):
        # 强制 perf_counter 恒返回同一值 -> elapsed = 0 -> 除零
        monkeypatch.setattr("vools.api.memoize_cmd._now_sec", lambda: 0.0)
        result = runner.invoke(memoize_app, [
            "benchmark", "lambda x: x + 1", "1", "--iterations", "10"
        ])
        assert result.exit_code == 0
        assert "每秒操作数" in result.output


class TestApp:
    """memoize_app 测试。"""

    def test_app_help(self):
        result = runner.invoke(memoize_app, ["--help"])
        assert result.exit_code == 0
        assert "Memoize" in result.output


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.api.memoize_cmd import __all__
        assert "call" in __all__
        assert "benchmark" in __all__
        assert "memoize_app" in __all__
        assert "parse_lambda_or_func" in __all__
        assert "timing_decorator" in __all__
