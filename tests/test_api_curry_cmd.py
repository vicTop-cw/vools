# -*- coding: utf-8 -*-
"""测试 vools.api.curry_cmd。"""

import pytest
from typer.testing import CliRunner

from vools.api.curry_cmd import (
    parse_lambda_or_func, call, curry_func, curry_app
)

runner = CliRunner()

__all__ = ["TestParseLambda", "TestCall", "TestCurryFunc", "TestApp",
           "TestImport"]


class TestParseLambda:
    """parse_lambda_or_func 测试。"""

    def test_lambda(self):
        f = parse_lambda_or_func("lambda x, y: x + y")
        assert f(1, 2) == 3

    def test_builtin(self):
        f = parse_lambda_or_func("abs")
        assert f(-3) == 3

    def test_unknown(self):
        with pytest.raises(ValueError):
            parse_lambda_or_func("no_such_func")


class TestCall:
    """call 命令测试。"""

    def test_two_args(self):
        result = runner.invoke(curry_app, [
            "call", "lambda x, y: x + y", "3", "4"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output

    def test_with_kwargs(self):
        result = runner.invoke(curry_app, [
            "call", "lambda x, y, z=0: x + y + z", "3", "4",
            "--kwargs", "z=5"
        ])
        assert result.exit_code == 0
        assert "结果" in result.output


class TestCurryFunc:
    """curry_func 命令测试。"""

    def test_basic(self):
        result = runner.invoke(curry_app, [
            "curry-func", "lambda x, y: x + y"
        ])
        assert result.exit_code == 0
        assert "原始函数" in result.output
        assert "柯里化函数" in result.output


class TestApp:
    """curry_app 测试。"""

    def test_help(self):
        result = runner.invoke(curry_app, ["--help"])
        assert result.exit_code == 0
        assert "Curry" in result.output


class TestImport:
    """__all__ 测试。"""

    def test_all(self):
        from vools.api.curry_cmd import __all__
        assert "call" in __all__
        assert "curry_app" in __all__
        assert "curry_func" in __all__
        assert "parse_lambda_or_func" in __all__
