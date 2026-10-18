"""BUG-105: curry_delay 参数满后需空调用 () 触发执行（文档示例修正）"""
from vools.decorators.curry_delay import delay_curry, DelayCurried


@delay_curry
def add(a, b, c):
    return a + b + c


@delay_curry
def greet(name, greeting='Hello'):
    return f'{greeting}, {name}!'


def test_chain_args_requires_empty_call():
    """链式柯里化参数传齐后，需空调用 () 触发执行。"""
    assert add(1)(2)(3)() == 6


def test_all_args_requires_empty_call():
    """所有参数一次传入后，需空调用 () 触发执行。"""
    assert add(1, 2, 3)() == 6


def test_mixed_args_requires_empty_call():
    """混合位置+关键字参数传齐后，需空调用 () 触发执行。"""
    assert add(1, 2)(c=3)() == 6
    assert add(1)(2, 3)() == 6


def test_default_args_empty_call():
    """带默认值的参数不传，空调用触发执行。"""
    assert greet('World')() == 'Hello, World!'
    assert greet('World', greeting='Hi')() == 'Hi, World!'


def test_partial_returns_delaycurried():
    """参数未传齐时返回 DelayCurried。"""
    result = add(1)
    assert isinstance(result, DelayCurried)
    assert result.is_ready is False


def test_zero_args_returns_delaycurried():
    """不传参数时返回 DelayCurried。"""
    result = add()
    assert isinstance(result, DelayCurried)


def test_full_args_returns_delaycurried_not_result():
    """参数传齐但未空调用时，返回 DelayCurried 而非函数结果（BUG-105 契约）。"""
    result = add(1, 2, 3)
    assert isinstance(result, DelayCurried)
    assert result.is_ready is True