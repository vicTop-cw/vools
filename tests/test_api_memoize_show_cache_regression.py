# -*- coding: utf-8 -*-
"""回归测试：memoize CLI 的 --show-cache 选项被声明却从未使用（BUG-522）。

修复前：

    @memoize_app.command()
    def call(..., show_cache: bool = typer.Option(False, "--show-cache/--no-show-cache",
                                                 help="显示缓存状态")):
        ...
        # 函数体里从不出现 show_cache
        cache_status = "缓存命中" if i > 0 else "首次计算"     # 无条件打印

结果：不给 --show-cache 也会打印"缓存命中/首次计算"；给了也照样打，开关形同虚设。

修复：缓存状态行只在 show_cache 为真时输出，并把状态措辞明确为
"按 memorize 语义推断"（vools.cache.memorize 不暴露 cache_info）。
"""

import importlib

import pytest

typer_testing = pytest.importorskip("typer.testing")
CliRunner = typer_testing.CliRunner

mc = importlib.import_module("vools.api.memoize_cmd")


@pytest.fixture()
def runner():
    return CliRunner()


def _invoke(runner, args):
    return runner.invoke(mc.memoize_app, args)


class TestShowCacheFlagIsEffective:
    def test_default_hides_cache_status(self, runner):
        result = _invoke(runner, ["call", "lambda x: x * 2", "2", "-r", "2"])
        assert result.exit_code == 0
        out = result.output
        assert "首次计算" not in out
        assert "缓存命中" not in out

    def test_flag_shows_cache_status(self, runner):
        result = _invoke(
            runner, ["call", "lambda x: x * 2", "2", "-r", "2", "--show-cache"]
        )
        assert result.exit_code == 0
        out = result.output
        assert "首次计算" in out
        assert "缓存命中" in out

    def test_no_show_cache_explicit(self, runner):
        result = _invoke(
            runner, ["call", "lambda x: x * 2", "2", "-r", "1", "--no-show-cache"]
        )
        assert result.exit_code == 0
        assert "首次计算" not in result.output


class TestCallBehaviourUnchanged:
    def test_result_and_consistency(self, runner):
        result = _invoke(runner, ["call", "lambda x: x * 2", "2", "-r", "3"])
        assert result.exit_code == 0
        assert "结果一致: True" in result.output
        assert "第 3 次" in result.output

    def test_repeat_must_be_positive(self, runner):
        result = _invoke(runner, ["call", "lambda x: x", "1", "-r", "0"])
        assert result.exit_code != 0
        assert "重复次数必须为正数" in result.output

    def test_unparsable_expression_loud(self, runner):
        result = _invoke(runner, ["call", "definitely not an expr", "1"])
        assert result.exit_code != 0


class TestOtherMemoizeCommands:
    def test_benchmark_runs(self, runner):
        result = _invoke(runner, ["benchmark", "lambda x: x + 1", "1", "-n", "2"])
        assert result.exit_code == 0

    def test_benchmark_iterations_positive(self, runner):
        result = _invoke(runner, ["benchmark", "lambda x: x", "1", "-n", "0"])
        assert result.exit_code != 0
