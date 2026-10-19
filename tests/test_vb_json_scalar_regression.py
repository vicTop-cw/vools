# -*- coding: utf-8 -*-
"""回归测试：VBJsonBackend 顶层标量 round-trip（BUG-203）。

parse 入口曾只分派 { / [，顶层标量（数字/字符串/bool/null）一律返回 None，
导致 dumps_str(1.5) -> parse 得 None 数据丢失。另 _stringify 对 inf/nan 输出
非标准 'inf'/'nan'，_parse_number 把 'inf' 吞成 0。
"""

import math

from vools.serialize.backends.vb_json_backend import VBJsonBackend


class TestVBJsonTopLevelScalars:
    """顶层标量必须可 round-trip（BUG-203）。"""

    def test_int(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str(100)) == 100

    def test_float(self):
        b = VBJsonBackend()
        assert math.isclose(b.parse(b.dumps_str(1.5)), 1.5)

    def test_zero_float(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str(0.0)) == 0.0

    def test_negative_float(self):
        b = VBJsonBackend()
        assert math.isclose(b.parse(b.dumps_str(-0.5)), -0.5)

    def test_string(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str("hi")) == "hi"

    def test_true(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str(True)) is True

    def test_false(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str(False)) is False

    def test_none(self):
        b = VBJsonBackend()
        assert b.parse(b.dumps_str(None)) is None


class TestVBJsonSpecialFloats:
    """非有限浮点必须按标准 JSON 字面量 round-trip（BUG-203）。"""

    def test_inf(self):
        b = VBJsonBackend()
        assert b.dumps_str(float('inf')) == 'Infinity'
        assert b.parse('Infinity') == float('inf')

    def test_neg_inf(self):
        b = VBJsonBackend()
        assert b.dumps_str(float('-inf')) == '-Infinity'
        assert b.parse('-Infinity') == float('-inf')

    def test_nan(self):
        b = VBJsonBackend()
        assert b.dumps_str(float('nan')) == 'NaN'
        assert math.isnan(b.parse('NaN'))


class TestVBJsonNestedContainers:
    """嵌套容器仍正常（既有行为未回归）。"""

    def test_nested(self):
        b = VBJsonBackend()
        obj = {"a": [1, 2.5, "x"], "b": {"c": True}}
        assert b.parse(b.dumps_str(obj)) == obj