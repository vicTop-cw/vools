"""
BUG-188 回归：VList.islice(step=0) 不再无限循环挂死。

根因：islice 循环 `i += step`，step=0 时 i 永不推进，start > stop 场景下
循环条件 i > stop 且 i < len 恒真，构成 while True 死循环。
"""

import concurrent.futures

import pytest

from vools.data.vlist import VList

_TIMEOUT = 3.0


def _run_islice(vlist, start, stop, step):
    """在带超时的线程池里跑 islice，避免死循环挂死 pytest。"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(vlist.islice, start, stop, step).result(timeout=_TIMEOUT)


def test_islice_step_zero_raises_value_error():
    """start > stop 且 step=0 时抛 ValueError，而非无限循环（BUG-188）。"""
    with pytest.raises(ValueError):
        _run_islice(VList([1, 2, 3, 4, 5]), 2, 1, 0)


def test_islice_step_zero_start_before_stop_raises():
    """start < stop 且 step=0 同样抛 ValueError（原实现静默返回空）。"""
    with pytest.raises(ValueError):
        _run_islice(VList([1, 2, 3, 4, 5]), 0, 3, 0)


def test_islice_normal_behavior_preserved():
    """正常切片行为不受修复影响。"""
    v = VList([1, 2, 3, 4, 5])
    assert list(_run_islice(v, 1, 4, 1)) == [2, 3, 4]
    assert list(_run_islice(v, 0, None, 2)) == [1, 3, 5]
    assert list(_run_islice(v, 0, 5, -1)) == []
    assert list(_run_islice(v, 0, 3, 1)) == [1, 2, 3]


def test_islice_returns_vlist():
    """islice 返回类型仍是 VList（继承关系不被破坏）。"""
    v = VList([1, 2, 3, 4, 5]).islice(0, 2)
    assert isinstance(v, VList)
    assert v == VList([1, 2])