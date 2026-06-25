"""Test Observable core class methods & Subscription"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import time
import threading
from vools.reactive import Observable, Subscription, DefaultObserver, ops

def _fail(*args, **kwargs):
    raise AssertionError("should not be called")

# ===== Subscription =====

def test_subscription_basic():
    unsub_called = [False]
    def unsubscribe():
        unsub_called[0] = True
    sub = Subscription(unsubscribe)
    assert not sub.is_closed
    sub.unsubscribe()
    assert unsub_called[0]
    assert sub.is_closed

def test_subscription_dispose_alias():
    unsub = [False]
    sub = Subscription(lambda: setitem(unsub, 0, True))
    setitem = lambda lst, i, v: lst.__setitem__(i, v)
    sub.dispose()
    assert unsub[0]

def test_subscription_double_unsubscribe():
    count = [0]
    sub = Subscription(lambda: count.__setitem__(0, count[0] + 1))
    sub.unsubscribe()
    sub.unsubscribe()
    assert count[0] == 1  # 只调用一次

def test_subscription_children():
    child_called = [False]
    child = Subscription(lambda: child_called.__setitem__(0, True))
    parent = Subscription(lambda: None)
    parent.add_child(child)
    parent.unsubscribe()
    assert child_called[0]

def test_subscription_context_manager():
    unsub = [False]
    with Subscription(lambda: unsub.__setitem__(0, True)):
        pass
    assert unsub[0]

# ===== Observable factory methods =====

def test_observable_from_iterable():
    result = []
    Observable.from_iterable([10, 20, 30]).subscribe(on_next=lambda x: result.append(x))
    assert result == [10, 20, 30]

def test_observable_just():
    result = []
    Observable.just(42).subscribe(on_next=lambda x: result.append(x))
    assert result == [42]

def test_observable_of():
    result = []
    Observable.of("a", "b").subscribe(on_next=lambda x: result.append(x))
    assert result == ["a", "b"]

def test_observable_from_range():
    result = []
    Observable.from_range(3).subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 1, 2]

def test_observable_empty():
    completed = [False]
    Observable.empty().subscribe(on_next=lambda x: _fail(), on_completed=lambda: completed.__setitem__(0, True))
    assert completed[0]

def test_observable_never():
    called = [False]
    sub = Observable.never().subscribe(on_next=lambda x: called.__setitem__(0, True))
    time.sleep(0.05)
    assert not called[0]
    sub.unsubscribe()

def test_observable_error():
    err = [None]
    Observable.error(ValueError("test")).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert isinstance(err[0], ValueError)

def test_observable_throw():
    err = [None]
    Observable.throw(RuntimeError("x")).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert isinstance(err[0], RuntimeError)

# ===== Observable subscribe API =====

def test_observable_subscribe_observer():
    """测试通过 DefaultObserver 订阅"""
    result = []
    obs = Observable.from_iterable([1, 2])
    obs.subscribe(observer=DefaultObserver(on_next=lambda x: result.append(x)))
    assert result == [1, 2]

def test_observable_subscribe_callback():
    """测试通过回调订阅"""
    result = []
    Observable.from_iterable([5, 6]).subscribe_(on_next=lambda x: result.append(x))
    assert result == [5, 6]

def test_observable_subscribe_return_subscription():
    sub = Observable.from_iterable([1]).subscribe(on_next=lambda x: None)
    assert isinstance(sub, Subscription)

def test_observable_on_error_callback():
    err = [None]
    Observable.error(KeyError("k")).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert isinstance(err[0], KeyError)

def test_observable_on_completed_callback():
    comp = [False]
    Observable.just(1).subscribe(on_next=lambda x: None, on_completed=lambda: comp.__setitem__(0, True))
    assert comp[0]

# ===== Observable.pipe =====

def test_observable_pipe():
    from vools.reactive import ops
    result = []
    obs = Observable.of(1, 2, 3, 4)
    obs.pipe(
        ops.filter(lambda x: x > 2),
        ops.map(lambda x: x * 10)
    ).subscribe(on_next=lambda x: result.append(x))
    assert result == [30, 40]

def test_observable_pipe_empty():
    """空管道应返回原始流"""
    result = []
    Observable.of(7).pipe().subscribe(on_next=lambda x: result.append(x))
    assert result == [7]

# ===== Observable factory: repeat =====

def test_observable_repeat():
    result = []
    Observable.repeat("x", times=3).subscribe(on_next=lambda x: result.append(x))
    assert result == ["x", "x", "x"]

# ===== Observable factory: from_callable =====

def test_observable_from_callable():
    result = []
    Observable.from_callable(lambda: 99).subscribe(on_next=lambda x: result.append(x))
    assert result == [99]

def test_observable_from_callable_error():
    err = [None]
    def failing():
        raise RuntimeError("boom")
    Observable.from_callable(failing).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert isinstance(err[0], RuntimeError)

# ===== Observable factory: defer =====

def test_observable_defer():
    result = []
    Observable.defer(lambda: Observable.just("deferred")).subscribe(on_next=lambda x: result.append(x))
    assert result == ["deferred"]

# ===== Observable factory: from_future =====

def test_observable_from_future():
    """from_future 从已完成的 future 取值"""
    import asyncio
    from vools.core.asyncio_compat import get_running_loop as _get_running_loop
    try:
        loop = _get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    fut = asyncio.ensure_future(asyncio.sleep(0, result=42))
    loop.run_until_complete(asyncio.sleep(0.01))
    result = []
    Observable.from_future(fut).subscribe(on_next=lambda x: result.append(x))
    loop.run_until_complete(asyncio.sleep(0.01))
    assert result == [42]
    loop.close()

# ===== Observable: from_range with start/stop/step =====

def test_observable_from_range_start_stop():
    result = []
    Observable.from_range(2, 5).subscribe(on_next=lambda x: result.append(x))
    assert result == [2, 3, 4]

def test_observable_from_range_start_stop_step():
    result = []
    Observable.from_range(0, 10, 3).subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 3, 6, 9]

# ===== Observable: __rshift__ =====

def test_observable_rshift():
    from vools.reactive import ops
    result = []
    obs = Observable.of(1, 2, 3)
    (obs >> ops.map(lambda x: x * 2) >> ops.filter(lambda x: x > 3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [4, 6]

# ===== Observable: PipeBuilder =====

def test_observable_pipebuilder():
    result = []
    obs = Observable.of(10, 20, 30)
    obs.p().map(lambda x: x + 1).filter(lambda x: x > 20).subscribe(on_next=lambda x: result.append(x))
    assert result == [21, 31]

def test_observable_pipebuilder_rshift():
    from vools.reactive import ops
    result = []
    (Observable.of(5, 6).p() >> ops.map(lambda x: x * 3)).subscribe(on_next=lambda x: result.append(x))
    assert result == [15, 18]
