# -*- coding: utf-8 -*-
"""回归测试：StuffConfig 的 debug/strict 开关真实生效（BUG-230）。

原 `StuffConfig` 的 `debug`/`strict` 字段全库零读取——docstring 承诺
「打印调试信息」「启用严格参数校验」且构造赋值，却从未被消费（同族
cache_duration/max_workers 均有真实消费）。

修复（消费点 `_evalate`）：
- debug=True：评估时 print 主函数名 + 已绑定参数名 + max_workers；
- strict=True：评估前校验主函数签名，必需参数（无默认值、非 self/cls、
  未绑定）缺失时抛 StuffExecutionError 并列出缺参名。
"""

import io
import contextlib

import pytest

from vools.utils.stuff import StuffConfig, StuffExecutionError, stuff


class TestDebugSwitch:
    """BUG-230 ①：debug 输出评估信息。"""

    def test_debug_prints(self):
        @stuff
        def calc(a, b, c):
            return a + b + c

        calc.config = StuffConfig(debug=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert calc(1, 2, 3)() == 6
        out = buf.getvalue()
        assert "[stuff] evaluate" in out
        assert "calc" in out

    def test_debug_off_silent(self):
        @stuff
        def calc(a, b):
            return a + b

        calc.config = StuffConfig(debug=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            calc(1, 2)()
        assert buf.getvalue() == ""


class TestStrictSwitch:
    """BUG-230 ②：strict 对缺必需参数早失败。"""

    def test_strict_missing_raises(self):
        @stuff
        def need(a, b, c=10):
            return a + b + c

        need.config = StuffConfig(strict=True)
        with pytest.raises(StuffExecutionError) as ei:
            need(1)()
        msg = str(ei.value)
        assert "'b'" in msg          # 缺的必需参数被点名
        assert "'a'" not in msg      # 已绑定不误报
        assert "'c'" not in msg      # 有默认值不误报

    def test_strict_complete_ok(self):
        @stuff
        def need(a, b, c=10):
            return a + b + c

        need.config = StuffConfig(strict=True)
        assert need(1, 2)() == 13

    def test_strict_di_complete_no_false_positive(self):
        # 全部走 provider 注入 + strict 不误报
        @stuff
        def calculate_total(price, quantity, tax_rate):
            return price * quantity * (1 + tax_rate)

        @calculate_total.provide(name='price')
        def get_price():
            return 100

        @calculate_total.provide_with(names=['quantity', 'tax_rate'])
        def get_quantity_and_tax():
            return 2, 0.1

        calculate_total.config = StuffConfig(strict=True)
        assert round(calculate_total(), 6) == 220.0


class TestDefaultBehaviorUnchanged:
    """strict=False（默认）旧行为不变：缺参静默部分应用。"""

    def test_default_partial_application(self):
        @stuff
        def plain(a, b):
            return a + b

        assert type(plain(1)).__name__ == "Stuff"
        assert plain(1)(2)() == 3