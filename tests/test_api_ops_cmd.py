# -*- coding: utf-8 -*-
"""测试 vools.api.ops_cmd。"""

import pytest
from typer.testing import CliRunner

from vools.api.ops_cmd import (
    parse_lambda, pipe, filter_op, map_op, sum_op, ops_app
)

runner = CliRunner()

__all__ = ["TestParseLambda", "TestPipe", "TestFilterOp", "TestMapOp",
           "TestSumOp", "TestImport"]


class TestParseLambda:
    """parse_lambda 测试。"""

    def test_basic(self):
        f = parse_lambda("lambda x: x * 2")
        assert f(3) == 6


class TestPipe:
    """pipe 命令测试。"""

    def test_basic(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3", "4", "5"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_filter(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3", "4", "5",
            "--filter", "lambda x: x % 2 == 0"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_map(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3",
            "--map", "lambda x: x * 2"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_filter_map(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3", "4", "5",
            "--filter", "lambda x: x % 2 == 0",
            "--map", "lambda x: x ** 2"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_sum(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3", "--sum"
        ])
        assert result.exit_code == 0
        assert "求和" in result.output

    def test_min(self):
        result = runner.invoke(ops_app, [
            "pipe", "3", "1", "2", "--min"
        ])
        assert result.exit_code == 0
        assert "最小值" in result.output

    def test_max(self):
        result = runner.invoke(ops_app, [
            "pipe", "3", "1", "2", "--max"
        ])
        assert result.exit_code == 0
        assert "最大值" in result.output

    def test_count(self):
        result = runner.invoke(ops_app, [
            "pipe", "3", "1", "2", "--count"
        ])
        assert result.exit_code == 0
        assert "计数" in result.output

    def test_no_collect(self):
        result = runner.invoke(ops_app, [
            "pipe", "1", "2", "3", "--no-collect"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output


class TestFilterOp:
    """filter_op 命令测试。"""

    def test_basic(self):
        result = runner.invoke(ops_app, [
            "filter-op", "1", "2", "3", "4", "lambda x: x % 2 == 0"
        ])
        assert result.exit_code == 0
        assert "过滤结果" in result.output


class TestMapOp:
    """map_op 命令测试。"""

    def test_basic(self):
        result = runner.invoke(ops_app, [
            "map-op", "1", "2", "3", "lambda x: x * 2"
        ])
        assert result.exit_code == 0
        assert "映射结果" in result.output


class TestSumOp:
    """sum_op 命令测试。"""

    def test_basic(self):
        result = runner.invoke(ops_app, [
            "sum-op", "1", "2", "3"
        ])
        assert result.exit_code == 0
        assert "求和结果" in result.output


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.api.ops_cmd import __all__
        assert "pipe" in __all__
        assert "filter_op" in __all__
        assert "map_op" in __all__
        assert "sum_op" in __all__
        assert "ops_app" in __all__
        assert "parse_lambda" in __all__
