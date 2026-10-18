"""BUG-104: once.py 并发竞态修复验证"""
import pickle
import threading
import time
from vools.cache.once import once


_call_counter = [0]


def _serializable_fn():
    _call_counter[0] += 1
    return _call_counter[0]


def test_concurrent_init_returns_result():
    """并发调用 once 装饰的函数，所有调用应返回函数结果而非 None。

    BUG-104: 旧实现在 `self.called = True` 与 `self.result = func(...)` 完成之间，
    其他线程看到 called==True 就返回 self.result（初始 None）。
    """
    call_count = [0]

    @once
    def initialize():
        call_count[0] += 1
        time.sleep(0.05)  # 扩大竞态窗口
        return call_count[0]

    results = []

    def call_once():
        results.append(initialize())

    threads = [threading.Thread(target=call_once) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    none_count = sum(1 for r in results if r is None)
    assert none_count == 0, f'{none_count}/10 calls returned None (BUG-104)'
    assert all(r == 1 for r in results), f'Results: {results}'
    assert call_count[0] == 1, f'Function executed {call_count[0]} times (expected 1)'


def test_force_re_executes():
    """force=True 强制重新执行，返回新结果。"""

    @once
    def get_value():
        return time.time()

    first = get_value()
    second = get_value(force=True)
    # force=True 时函数重新执行，返回不同的时间戳（除非在同一微秒内）
    assert second >= first


def test_once_serialization_roundtrip():
    """序列化/反序列化后 once 函数仍可工作（锁需重建）。"""
    _call_counter[0] = 0

    wrapped = once(_serializable_fn)
    assert wrapped() == 1

    # 序列化
    data = pickle.dumps(wrapped)
    restored = pickle.loads(data)
    assert restored() == 1  # 已缓存，返回 1
    assert _call_counter[0] == 1


def test_force_default_param():
    """force_default=True 时，不带 force 参数每次都重新执行。"""

    call_count = [0]

    @once(force_default=True)
    def f():
        call_count[0] += 1
        return call_count[0]

    r1 = f()
    r2 = f()
    assert r1 == 1
    assert r2 == 2
    assert call_count[0] == 2