# -*- coding: utf-8 -*-
"""回归测试：@bridge 装饰器参数校验（BUG-476）。

修复前零校验：

    @bridge("python", None)     # 装饰期 TypeError: argument of type 'NoneType' is not iterable
    @bridge(123, "x")           # 静默接受，_bridge_lang 存成 123（非字符串）
    @bridge("python", "x", fallback=123)
                                # 直到**调用期**才炸 "'int' object is not callable"

修复后：lang/symbol 必须是非空字符串，fallback 必须是可调用对象或 None。

语义保持不变（文档化）：桥接不可用且无 fallback → RuntimeError；
有 fallback → 调 fallback；colon 格式 ``":func"`` 语言取 lang 参数。
"""

import pytest

import vools.decorators as d


class TestParamValidation:
    @pytest.mark.parametrize("bad", [None, 123, "", "   ", 1.5])
    def test_bad_lang(self, bad):
        with pytest.raises(ValueError) as ei:
            d.bridge(bad, "x")
        assert "lang" in str(ei.value)

    @pytest.mark.parametrize("bad", [None, 123, "", "   "])
    def test_bad_symbol(self, bad):
        with pytest.raises(ValueError) as ei:
            d.bridge("python", bad)
        assert "symbol" in str(ei.value)

    @pytest.mark.parametrize("bad", [123, "x", [1]])
    def test_bad_fallback(self, bad):
        with pytest.raises(TypeError) as ei:
            d.bridge("python", "x", fallback=bad)
        assert "fallback" in str(ei.value)

    def test_none_issues_at_decoration(self):
        """修复前这里抛的是 'NoneType' is not iterable（内部实现细节）。"""
        with pytest.raises(ValueError):
            d.bridge("python", None)


class TestSemanticsUnchanged:
    def test_fallback_used_when_bridge_missing(self):
        @d.bridge("python", "len", fallback=lambda x: -1)
        def my_len(x):
            return "impl"

        assert my_len([1, 2]) == -1
        assert my_len._bridge_lang == "python"
        assert my_len._bridge_symbol == "len"
        assert my_len._is_bridge_func is True

    def test_no_fallback_raises_runtime_error(self):
        @d.bridge("python", "no_such_symbol")
        def fn(x):
            return "impl"

        with pytest.raises(RuntimeError) as ei:
            fn(1)
        assert "No bridge implementation available" in str(ei.value)

    def test_colon_format_parsing(self):
        @d.bridge("python", ":x")
        def fn(x):
            return "impl"

        assert fn._bridge_symbol == "x"
        assert fn._bridge_lang == "python"

    def test_dot_format_parsing(self):
        @d.bridge("nim", "serialize.pickle_encode", fallback=lambda o: b"py")
        def fn(o):
            return b"impl"

        assert fn._bridge_symbol == "serialize.pickle_encode"
        assert fn(o=1) in (b"py", b"impl") or isinstance(fn(o=1), bytes)

    def test_none_fallback_allowed(self):
        @d.bridge("python", "len", fallback=None)
        def fn(x):
            return "impl"

        assert fn._bridge_fallback is None
