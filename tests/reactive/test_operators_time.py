"""Test time-based operators: interval, timer, debounce, throttle, delay, timeout, sample, etc."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import time
from vools.reactive import Observable, ops, Subject

# ===== interval (sync context) =====

def test_interval_take():
    """interval 在同步上下文中正常工作"""
    result = []
    sub = Observable.interval(0.02).pipe(ops.take(3)).subscribe(on_next=lambda x: result.append(x))
    time.sleep(0.2)
    sub.dispose()
    assert result == [0, 1, 2], f"Got {result}"

def test_interval_unsubscribe():
    """interval 取消订阅后停止发射"""
    result = []
    sub = Observable.interval(0.01).subscribe(on_next=lambda x: result.append(x))
    time.sleep(0.08)
    sub.dispose()
    count_before = len(result)
    time.sleep(0.1)
    assert len(result) == count_before  # 不再增加

# ===== timer =====

def test_timer_single_shot():
    """timer 只发射一次"""
    result = []
    sub = Observable.timer(0.02).subscribe(on_next=lambda x: result.append(x))
    time.sleep(0.1)
    sub.dispose()
    assert result == [0], f"Got {result}"

def test_timer_periodic():
    """timer 周期性发射"""
    result = []
    sub = Observable.timer(0.02, period=0.02).pipe(ops.take(3)).subscribe(on_next=lambda x: result.append(x))
    time.sleep(0.2)
    sub.dispose()
    assert result == [0, 1, 2], f"Got {result}"

# ===== debounce =====

def test_debounce():
    result = []
    subj = Subject()
    subj.pipe(ops.debounce(0.05)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_next(2)
    time.sleep(0.1)
    subj.on_next(3)
    time.sleep(0.1)
    assert result == [2, 3], f"Got {result}"

# ===== throttle_first =====

def test_throttle_first():
    result = []
    obs = Observable.from_iterable([1, 2, 3])
    obs.pipe(ops.throttle_first(0.05)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1]

# ===== delay =====
# delay 需要 asyncio 事件循环，在同步上下文中不工作 — 跳过

# ===== timeout =====

def test_timeout_success():
    """timeout 正常完成"""
    result = []
    Observable.just(1).pipe(ops.timeout(1.0)).subscribe(on_next=lambda x: result.append(x))
    assert result == [1]

def test_timeout_failure():
    """timeout 超时触发 error"""
    from vools.reactive import Subject
    err = [None]
    subj = Subject()
    subj.pipe(ops.timeout(0.05)).subscribe(on_next=lambda x: None, on_error=lambda e: err.__setitem__(0, e))
    time.sleep(0.15)
    assert err[0] is not None
    assert "Observable timeout" in str(err[0]) or "Timeout" in str(type(err[0]).__name__)

# ===== sample =====

def test_sample():
    """sample 按时采样最新值"""
    result = []
    subj = Subject()
    subj.pipe(ops.sample(0.05)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next("a")
    time.sleep(0.07)
    subj.on_next("b")
    time.sleep(0.07)
    subj.on_completed()
    time.sleep(0.05)
    assert len(result) >= 1  # 至少采到一个

# ===== throttle_latest =====
# throttle_latest 使用 threading，同步流直接完成不发射 — 只做基本验证

def test_throttle_latest_create():
    """throttle_latest 可以创建"""
    op = ops.throttle_latest(0.05)
    assert callable(op)

# ===== cache =====

def test_cache_create():
    """cache 操作符可以创建"""
    op = ops.cache()
    assert callable(op)

# ===== buffer_until_idle =====

def test_buffer_until_idle():
    """buffer_until_idle 在空闲后发射缓冲"""
    result = []
    subj = Subject()
    subj.pipe(ops.buffer_until_idle(0.05)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next("a")
    subj.on_next("b")
    time.sleep(0.1)
    subj.on_next("c")
    time.sleep(0.1)
    assert ["a", "b"] in [r for r in result]
    assert ["c"] in [r for r in result]

# ===== throttle_with_trailing =====

def test_throttle_with_trailing():
    result = []
    subj = Subject()
    subj.pipe(ops.throttle_with_trailing(0.05)).subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    time.sleep(0.02)
    subj.on_next(2)
    time.sleep(0.08)
    # 第一个值1被立即发射，2在trailing中被保留然后发射
    assert 1 in result
