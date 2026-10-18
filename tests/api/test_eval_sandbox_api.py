"""BUG-102: vools/api eval 沙箱逃逸回归测试。

`vools/api/memoize_cmd.py`、`curry_cmd.py`、`ops_cmd.py`、`seq_cmd.py`
使用 `eval(expr, {"__builtins__": {}})` 解析 lambda/参数，
但 `{"__builtins__": {}}` 无法阻止 Python 对象模型逃逸。
"""

import pytest
from vools.api.memoize_cmd import parse_lambda_or_func as memoize_parse
from vools.api.curry_cmd import parse_lambda_or_func as curry_parse
from vools.api.ops_cmd import parse_lambda as ops_parse
from vools.api.seq_cmd import parse_lambda as seq_parse


class TestLambdaStillWorks:
    """合法的 lambda 解析必须继续工作（不破坏 DSL）"""

    def test_simple_lambda(self):
        f = memoize_parse("lambda x: x * 2")
        assert f(5) == 10

    def test_multi_arg_lambda(self):
        f = memoize_parse("lambda x, y: x + y")
        assert f(3, 4) == 7

    def test_builtin_name(self):
        f = memoize_parse("abs")
        assert f(-5) == 5

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError):
            memoize_parse("no_such_func_xyz")

    def test_ops_parse_lambda(self):
        f = ops_parse("lambda x: x + 1")
        assert f(1) == 2

    def test_seq_parse_lambda(self):
        f = seq_parse("lambda x: x * 3")
        assert f(2) == 6

    def test_curry_parse_lambda(self):
        f = curry_parse("lambda x, y: x - y")
        assert f(10, 3) == 7


class TestSandboxEscapeBlocked:
    """对象模型逃逸必须被阻断（BUG-102 修复后）"""

    @pytest.mark.parametrize("parse_fn", [memoize_parse, curry_parse, ops_parse, seq_parse])
    @pytest.mark.parametrize("payload", [
        "().__class__.__base__.__subclasses__()",
        "().__class__.__base__.__bases__",
        "().__class__.__mro__",
        "().__class__.__init__.__globals__",
        "().__class__.__dict__",
    ])
    def test_reject_object_model_escape(self, parse_fn, payload):
        with pytest.raises((ValueError, Exception)):
            parse_fn(payload)

    def test_reject_os_module_via_subclasses(self):
        """_TrivialRe.__init__.__globals__['os'] 不应可达"""
        payload = (
            '[x for x in ().__class__.__base__.__subclasses__() '
            'if x.__name__ == "_TrivialRe"]'
            '[0].__init__.__globals__.get("os")'
        )
        with pytest.raises((ValueError, Exception)):
            memoize_parse(payload)

    def test_reject_import_builtins(self):
        with pytest.raises((ValueError, Exception)):
            memoize_parse("__import__('os')")


class TestBuiltinFallback:
    """函数名回退必须仍工作"""

    def test_memoize_fallback(self):
        f = memoize_parse("abs")
        assert f(-3) == 3

    def test_curry_fallback(self):
        f = curry_parse("len")
        assert f([1, 2, 3]) == 3