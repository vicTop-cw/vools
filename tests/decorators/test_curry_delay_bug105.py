"""BUG-105: curry_delay 参数满后立即执行"""
from vools.decorators.curry_delay import delay_curry, DelayCurried


@delay_curry
def add(a, b, c):
    return a + b + c


@delay_curry
def greet(name, greeting='Hello'):
    return f'{greeting}, {name}!'


def test_all_args_returns_result():
    """所有参数一次传入应立即执行返回结果。"""
    assert add(1, 2, 3) == 6


def test_chain_args_returns_result():
    """链式柯里化参数传齐后应立即执行返回结果。"""
    assert add(1)(2)(3) == 6


def test_mixed_args_returns_result():
    """混合位置+关键字参数传齐后应立即执行返回结果。"""
    assert add(1, 2)(c=3) == 6
    assert add(1)(2, 3) == 6


def test_default_args():
    """带默认值的参数不传也能执行。"""
    assert greet('World') == 'Hello, World!'
    assert greet('World', greeting='Hi') == 'Hi, World!'


def test_partial_returns_delaycurried():
    """参数未传齐时返回 DelayCurried。"""
    result = add(1)
    assert isinstance(result, DelayCurried)
    assert result.is_ready is False


def test_zero_args_returns_delaycurried():
    """不传参数时返回 DelayCurried。"""
    result = add()
    assert isinstance(result, DelayCurried)


def test_ready_property():
    """参数传齐后 is_ready 应为 True。"""
    c = add(1, 2, 3)
    # add(1,2,3) 现在直接返回 6
    assert c == 6