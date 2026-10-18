# -*- coding: utf-8 -*-
"""tests/decorators/test_retry_and_logic.py — retry logic='and' 异常传播（钉 BUG-92）

BUG-92: retry 装饰器在 logic='and' 模式下，当函数抛异常但 check_func 未提供
（retry_by_result=False），should_retry=False，直接 return result（此时为 None），
异常被静默吞掉。用户拿到 None 而不是 ValueError。

修复：在 not should_retry 分支中，若 retry_by_exception 为 True，则 raise
last_exception，确保异常不丢失。
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vools.decorators.control import retry  # noqa: E402


class TestRetryAndLogicException:
    """logic='and' 模式异常必须传播，不能吞掉"""

    def test_and_no_check_func_raises(self):
        """logic='and' + 无 check_func：异常必须传播"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='and')
        def should_raise():
            calls['count'] += 1
            raise ValueError("expected error")

        with pytest.raises(ValueError, match="expected error"):
            should_raise()

    def test_and_check_func_always_true_raises(self):
        """logic='and' + check_func 恒 True：异常必须传播"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='and', check_func=lambda x: True)
        def should_raise():
            calls['count'] += 1
            raise ValueError("expected error")

        with pytest.raises(ValueError, match="expected error"):
            should_raise()

    def test_and_check_func_false_raises(self):
        """logic='and' + check_func 恒 False：异常必须传播（双条件真则重试）"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='and', check_func=lambda x: False)
        def should_raise():
            calls['count'] += 1
            raise ValueError("expected error")

        with pytest.raises(ValueError, match="expected error"):
            should_raise()


class TestRetryOtherLogicException:
    """其他逻辑模式异常传播不受影响"""

    def test_or_default_raises(self):
        """默认 logic='or'：异常传播（现有行为）"""
        calls = {'count': 0}

        @retry(tries=3, delay=0)
        def should_raise():
            calls['count'] += 1
            raise ValueError("expected error")

        with pytest.raises(ValueError, match="expected error"):
            should_raise()

    def test_xor_raises(self):
        """logic='xor'：异常传播（现有行为）"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='xor')
        def should_raise():
            calls['count'] += 1
            raise ValueError("expected error")

        with pytest.raises(ValueError, match="expected error"):
            should_raise()


class TestRetryNormalReturn:
    """正常返回不受影响"""

    def test_or_success_first_attempt(self):
        @retry(tries=3, delay=0)
        def ok():
            return 42

        assert ok() == 42

    def test_and_success_first_attempt(self):
        @retry(tries=3, delay=0, logic='and', check_func=lambda x: x == 42)
        def ok():
            return 42

        assert ok() == 42

    def test_and_check_func_rejects_returns_first_result(self):
        """logic='and' + check_func 拒绝：无异常时不重试，返回首次结果
        （'and' 语义要求异常与结果失败同时发生，二者互斥故永不重试）"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='and', check_func=lambda x: x == 'success')
        def flaky():
            calls['count'] += 1
            return 'fail'

        assert flaky() == 'fail'
        assert calls['count'] == 1

    def test_or_check_func_rejects_retries_then_succeeds(self):
        """logic='or' + check_func 拒绝：重试至成功（对照行为）"""
        calls = {'count': 0}

        @retry(tries=3, delay=0, logic='or', check_func=lambda x: x == 'success')
        def flaky():
            calls['count'] += 1
            if calls['count'] < 3:
                return 'fail'
            return 'success'

        assert flaky() == 'success'
        assert calls['count'] == 3