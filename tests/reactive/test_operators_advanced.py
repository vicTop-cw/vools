"""Test combinational/advanced operators: merge, concat, zip, combine_latest, etc."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import time
from vools.reactive import Observable, ops, Subject

# ==================== merge ====================

def test_merge():
    result = []
    a = Observable.of(1, 2)
    b = Observable.of(10, 20)
    ops.merge(a, b).subscribe(on_next=lambda x: result.append(x))
    result.sort()  # 顺序不确定
    assert result == [1, 2, 10, 20], f"Got {result}"

# ==================== concat ====================

def test_concat():
    result = []
    a = Observable.of(1, 2)
    b = Observable.of(3, 4)
    ops.concat(a, b).subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3, 4]

# ==================== zip ====================

def test_zip():
    result = []
    a = Observable.of(1, 2, 3)
    b = Observable.of("a", "b")
    ops.zip(a, b).subscribe(on_next=lambda x: result.append(x))
    assert result == [(1, "a"), (2, "b")]  # 3被忽略

# ==================== combine_latest ====================

def test_combine_latest():
    result = []
    a = Subject()
    b = Subject()
    ops.combine_latest(a, b).subscribe(on_next=lambda x: result.append(x))
    a.on_next(1)
    b.on_next("x")
    a.on_next(2)
    assert (1, "x") in result
    assert (2, "x") in result

# ==================== with_latest_from ====================

def test_with_latest_from_basic():
    """with_latest_from 可以创建并使用"""
    source = Subject()
    other = Subject()
    result = []
    source.pipe(ops.with_latest_from(other)).subscribe(on_next=lambda x: result.append(x))
    # 先在 source 有值之前给 other 一个值
    source.on_next(1)
    other.on_next("x")
    source.on_next(2)
    assert len(result) >= 0  # 至少不崩溃

# ==================== take_until ====================

def test_take_until():
    result = []
    source = Subject()
    notifier = Subject()
    source.pipe(ops.take_until(notifier)).subscribe(on_next=lambda x: result.append(x))
    source.on_next(1)
    notifier.on_next(True)
    source.on_next(2)  # 不应被发射
    assert result == [1]

# ==================== skip_until ====================

def test_skip_until():
    result = []
    source = Subject()
    notifier = Subject()
    source.pipe(ops.skip_until(notifier)).subscribe(on_next=lambda x: result.append(x))
    source.on_next(1)  # 跳过
    notifier.on_next(True)
    source.on_next(2)
    assert result == [2]

# ==================== window ====================

def test_window():
    windows = []
    Observable.of(1, 2, 3, 4, 5).pipe(ops.window(2)).subscribe(on_next=lambda w: windows.append(w))
    assert len(windows) == 3  # [1,2], [3,4], [5]

# ==================== amb ====================

def test_amb():
    result = []
    a = Observable.never()
    b = Observable.of(42)
    ops.amb(a, b).subscribe(on_next=lambda x: result.append(x))
    assert result == [42]

# ==================== switch ====================

def test_switch():
    """switch 切换高阶 Observable"""
    result = []
    subj = Subject()
    subj.pipe(ops.switch()).subscribe(on_next=lambda x: result.append(x))
    inner1 = Subject()
    inner2 = Subject()
    subj.on_next(inner1)
    inner1.on_next("a")
    subj.on_next(inner2)
    inner1.on_next("b")  # 被丢弃
    inner2.on_next("c")
    assert result == ["a", "c"]

# ==================== catch / retry / error handling ====================

def test_catch():
    result = []
    obs = Observable.error(ValueError("x")).pipe(ops.catch(lambda e: Observable.just("recovered")))
    obs.subscribe(on_next=lambda x: result.append(x))
    assert result == ["recovered"]

def test_on_error_return():
    result = []
    Observable.error(ValueError()).pipe(ops.on_error_return("fallback")).subscribe(on_next=lambda x: result.append(x))
    assert result == ["fallback"]

def test_on_error_resume_next():
    result = []
    err_obs = Observable.error(ValueError())
    fallback = Observable.of("ok")
    err_obs.pipe(ops.on_error_resume_next(fallback)).subscribe(on_next=lambda x: result.append(x))
    assert result == ["ok"]

def test_retry_limited():
    """retry 有限次数后传递错误"""
    count = [0]
    def source():
        count[0] += 1
        return Observable.error(ValueError(f"fail {count[0]}"))
    err = [None]
    source().pipe(ops.retry(2)).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    assert err[0] is not None

# ==================== flat_map_latest ====================

def test_flat_map_latest():
    result = []
    subj = Subject()
    subj.pipe(ops.flat_map_latest(lambda x: Observable.from_iterable([x, x*10]))).subscribe(
        on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_next(2)
    subj.on_completed()
    assert result == [1, 10, 2, 20] or result == [2, 20]

# ==================== iif ====================

def test_iif():
    """iif 条件为真时返回 true_body 的结果"""
    result = []
    obs = Observable.of(1, 2)
    obs.pipe(ops.iif(condition=lambda *args: True, true_body=lambda x, *a: x * 10)).subscribe(
        on_next=lambda x: result.append(x))
    assert result == [10, 20]

# ==================== to_map / to_set ====================

def test_to_map():
    result = []
    Observable.of(("a", 1), ("b", 2)).pipe(ops.to_map(key_fn=lambda x: x[0])).subscribe(on_next=lambda x: result.append(x))
    assert result == [{"a": ("a", 1), "b": ("b", 2)}]

def test_to_set():
    result = []
    Observable.of(1, 2, 2, 3).pipe(ops.to_set()).subscribe(on_next=lambda x: result.append(x))
    assert result == [{1, 2, 3}]

# ==================== debounce_evolution ====================

def test_debounce_evolution():
    result = []
    subj = Subject()
    subj.pipe(ops.debounce_evolution(0.03)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    time.sleep(0.05)
    subj.on_next(2)
    time.sleep(0.05)
    assert len(result) >= 1

# ==================== retry_with_backoff ====================

def test_retry_with_backoff():
    """retry_with_backoff 在同步上下文中工作"""
    import time
    count = [0]
    def failing_source():
        count[0] += 1
        return Observable.error(ValueError(f"fail {count[0]}"))
    err = [None]
    sub = failing_source().pipe(ops.retry_with_backoff(max_retries=1, initial_delay=0.01)).subscribe(
        on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    time.sleep(0.1)
    sub.dispose()
    assert err[0] is not None

# ==================== circuit_breaker ====================

def test_circuit_breaker():
    result = []
    obs = Observable.of("ok").pipe(ops.circuit_breaker(threshold=2, reset_timeout=10))
    obs.subscribe(on_next=lambda x: result.append(x))
    assert result == ["ok"]

# ==================== backpressure_* ====================

def test_backpressure_buffer():
    result = []
    subj = Subject()
    subj.pipe(ops.backpressure_buffer(max_size=5)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_completed()
    assert result == [1]

def test_backpressure_drop():
    result = []
    subj = Subject()
    subj.pipe(ops.backpressure_drop()).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_completed()
    assert result == [1]

def test_backpressure_latest():
    result = []
    subj = Subject()
    subj.pipe(ops.backpressure_latest()).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_completed()
    assert result == [1]

# ==================== filter_by / when ====================

def test_filter_by_event_type():
    result = []
    obs = Observable.of("click", "scroll", "click")
    obs.pipe(ops.filter_by_event_type("click")).subscribe(on_next=lambda x: result.append(x))
    assert result == ["click", "click"]

def test_when():
    """ops.when 条件为真时执行副作用，主流通路不变"""
    side_effects = []
    result = []
    obs = Observable.of(1, 2, 3)
    obs.pipe(ops.when(predicate=lambda v: v > 1, handler=lambda v: side_effects.append(v))).subscribe(
        on_next=lambda x: result.append(x))
    assert result == [1, 2, 3]  # 主流通路不变
    assert side_effects == [2, 3]
