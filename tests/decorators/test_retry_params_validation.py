# -*- coding: utf-8 -*-
"""tests/decorators/test_retry_params_validation.py — retry 装饰器参数校验（钉 BUG-252）

BUG-252: ``_retry_decorator`` 在装饰时对 ``tries``/``delay``/``backoff``/``logger``
不校验 —— 传入非法值（如 ``logger='str'``、``delay='abc'``、``tries=0``）时装饰
阶段静默通过，直到首次重试才崩溃。修复：在 ``_retry_decorator`` 入口处前置校验，
非法值立即抛 ``ValueError`` 或 ``TypeError``。
"""
import logging
import sys
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.decorators.control import retry, _retry_decorator  # noqa: E402


class TestRetryTriesValidation:
    """tries 必须为正整数"""

    def test_tries_zero_raises(self):
        with pytest.raises(ValueError, match="tries 必须为正整数"):
            _retry_decorator(tries=0)

    def test_tries_negative_raises(self):
        with pytest.raises(ValueError, match="tries 必须为正整数"):
            _retry_decorator(tries=-1)

    def test_tries_float_raises(self):
        with pytest.raises(ValueError, match="tries 必须为正整数"):
            _retry_decorator(tries=1.5)

    def test_tries_string_raises(self):
        with pytest.raises(ValueError, match="tries 必须为正整数"):
            _retry_decorator(tries="abc")


class TestRetryDelayValidation:
    """delay 必须为非负数"""

    def test_delay_string_raises(self):
        with pytest.raises(ValueError, match="delay 必须为非负数"):
            _retry_decorator(delay="abc")

    def test_delay_negative_raises(self):
        with pytest.raises(ValueError, match="delay 必须为非负数"):
            _retry_decorator(delay=-1)


class TestRetryBackoffValidation:
    """backoff 必须为非负数"""

    def test_backoff_string_raises(self):
        with pytest.raises(ValueError, match="backoff 必须为非负数"):
            _retry_decorator(backoff="abc")

    def test_backoff_negative_raises(self):
        with pytest.raises(ValueError, match="backoff 必须为非负数"):
            _retry_decorator(backoff=-1)


class TestRetryLoggerValidation:
    """logger 必须有 .info 方法（或 None）"""

    def test_logger_string_raises(self):
        with pytest.raises(TypeError, match="logger 必须为 logging.Logger"):
            _retry_decorator(logger="not_a_logger")

    def test_logger_int_raises(self):
        with pytest.raises(TypeError, match="logger 必须为 logging.Logger"):
            _retry_decorator(logger=123)

    def test_logger_none_ok(self):
        d = _retry_decorator(logger=None)
        assert callable(d)

    def test_logger_real_logger_ok(self):
        d = _retry_decorator(logger=logging.getLogger("test"))
        assert callable(d)


class TestRetryDecoratorRejects:
    """retry(...) 带参数时同样应在装饰阶段拒绝"""

    def test_retry_with_bad_logger_rejects(self):
        with pytest.raises(TypeError, match="logger 必须为 logging.Logger"):
            @retry(tries=3, delay=0, logger="bad")
            def f():
                pass

    def test_retry_with_bad_tries_rejects(self):
        with pytest.raises(ValueError, match="tries 必须为正整数"):
            @retry(tries=0)
            def f():
                pass

    def test_retry_with_bad_delay_rejects(self):
        with pytest.raises(ValueError, match="delay 必须为非负数"):
            @retry(delay="abc")
            def f():
                pass


class TestRetryValidUsageStillWorks:
    """合法用法不受影响"""

    def test_basic_success(self):
        @retry(tries=3, delay=0)
        def ok():
            return 42
        assert ok() == 42

    def test_with_check_func(self):
        calls = {"n": 0}

        @retry(tries=3, delay=0, check_func=lambda x: x == "ok")
        def flaky():
            calls["n"] += 1
            return "ok" if calls["n"] == 2 else "fail"

        assert flaky() == "ok"
        assert calls["n"] == 2

    def test_exception_propagates(self):
        @retry(tries=2, delay=0)
        def boom():
            raise ValueError("expected")

        with pytest.raises(ValueError, match="expected"):
            boom()

    def test_logic_and_no_check_func(self):
        """logic='and' + 无 check_func：异常必须传播（BUG-92）"""
        @retry(tries=3, delay=0, logic="and")
        def boom():
            raise ValueError("expected")

        with pytest.raises(ValueError, match="expected"):
            boom()
