# -*- coding: utf-8 -*-
"""回归测试：VText 三个入口的参数零校验（BUG-342）。

修复前（全部裸错，看不出是哪个参数、期望什么）：

    VText("abc").like(None)                     # AttributeError: 'NoneType' object has no attribute 'lower'
    VText("abc").like(123)                      # AttributeError: 'int' object has no attribute 'lower'
    VText("{run_date}").replace_run_date("bogus")   # ValueError: invalid literal for int() with base 10: 'bogu'
                                                #   （切片后的 4 字符，完全指不到"日期"）
    VText("hi").toZipB64(level=99)              # zlib.error: Bad compression level
    VText("hi").toZipB64(level="x")             # TypeError: 'str' object cannot be interpreted as an integer

修复后统一带参数名的 TypeError/ValueError；合法路径（通配符、ignorecase、四种
run_date 占位符形态、date 对象、压缩往返）保持不变。
"""

import datetime

import pytest

from vools.data.vtext import VText


class TestLikeValidation:
    @pytest.mark.parametrize("bad", [None, 123, ["a"]])
    def test_non_str_pattern(self, bad):
        with pytest.raises(TypeError) as ei:
            VText("abc").like(bad)
        assert "pattern" in str(ei.value)


class TestLikeBehaviourUnchanged:
    @pytest.mark.parametrize("text,pattern,expected", [
        ("abc", "a*", True),
        ("abc", "a?c", True),
        ("abc", "*z", False),
        ("abc", "abc", True),
    ])
    def test_wildcards(self, text, pattern, expected):
        assert VText(text).like(pattern) is expected

    def test_ignorecase(self):
        assert VText("abc").like("A?C") is True
        assert VText("abc").like("A?C", False) is False


class TestReplaceRunDateValidation:
    @pytest.mark.parametrize("bad", ["bogus", "2024", "2024-1-1", "", None if False else 123])
    def test_bad_run_date(self, bad):
        with pytest.raises(ValueError) as ei:
            VText("select {run_date}").replace_run_date(bad)
        assert "run_date" in str(ei.value)

    def test_invalid_calendar_date(self):
        with pytest.raises(ValueError) as ei:
            VText("select {run_date}").replace_run_date("20241301")
        assert "run_date" in str(ei.value)

    def test_no_placeholder_passthrough(self):
        # 无占位符时不解析 run_date（保持既有短路语义）
        assert str(VText("plain").replace_run_date("bogus")) == "plain"


class TestReplaceRunDateBehaviourUnchanged:
    def test_plain(self):
        assert str(VText("select {run_date}").replace_run_date("20240101")) == "select 20240101"

    def test_minus_one(self):
        assert str(VText("select {run_date-1}").replace_run_date("20240101")) == "select 20231231"

    def test_plus_one(self):
        assert str(VText("select {run_date+1}").replace_run_date("20240101")) == "select 20240102"

    def test_std(self):
        assert str(VText("select {run_date_std}").replace_run_date("20240101")) == "select 2024-01-01"

    def test_std_plus_one(self):
        assert (
            str(VText("select {run_date_std+1}").replace_run_date("20240101"))
            == "select 2024-01-02"
        )

    def test_dashed_input(self):
        assert str(VText("{run_date}").replace_run_date("2024-01-01")) == "20240101"

    def test_date_object(self):
        assert str(VText("{run_date}").replace_run_date(datetime.date(2024, 1, 1))) == "20240101"

    def test_default_run_date_is_today(self):
        out = str(VText("{run_date}").replace_run_date())
        assert len(out) == 8 and out.isdigit()

    def test_returns_vtext(self):
        assert isinstance(VText("{run_date}").replace_run_date("20240101"), VText)


class TestToZipB64Validation:
    @pytest.mark.parametrize("bad", ["x", 1.5, None, True])
    def test_wrong_type(self, bad):
        with pytest.raises(TypeError) as ei:
            VText("hi").toZipB64(level=bad)
        assert "level" in str(ei.value)

    @pytest.mark.parametrize("bad", [0, -1, 99])
    def test_out_of_range(self, bad):
        with pytest.raises(ValueError) as ei:
            VText("hi").toZipB64(level=bad)
        assert "level" in str(ei.value)


class TestToZipB64BehaviourUnchanged:
    @pytest.mark.parametrize("level", [1, 5, 9])
    def test_roundtrip(self, level):
        encoded = VText("hello world " * 20).toZipB64(level=level)
        assert isinstance(encoded, VText)
        # 前缀必须是 Z: 或 R:
        assert str(encoded)[:2] in ("Z:", "R:")

    def test_small_text_falls_back_to_raw(self):
        # 压缩膨胀时回退 R: 前缀（既有 force=False 语义）
        assert str(VText("hi").toZipB64()).startswith("R:")

    def test_repetitive_text_compresses(self):
        assert str(VText("abc" * 200).toZipB64()).startswith("Z:")
