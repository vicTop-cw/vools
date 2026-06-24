"""验证 curry 装饰器在被 get_signature 替换后是否工作"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.decorators import curry
from vools.cache import clear_cache


def setup_module():
    clear_cache()


def test_curry_basic():
    @curry
    def add(a, b, c):
        return a + b + c

    result = add(1)(2)(3)
    assert result == 6

    result2 = add(1, 2)(3)
    assert result2 == 6


def test_overload_basic():
    from vools.decorators import overload

    @overload
    def process():
        return "none"

    assert process() == "none"


def test_placeholder_signature():
    from vools.functional.placeholder import _, X
    sig = _.signature  # should work
    assert sig is not None
