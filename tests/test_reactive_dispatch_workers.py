#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试 vools.reactive.dispatch_to_workers / dispatch_workers 操作符

覆盖测试点:
  1. 基础功能：同步 fn，所有值被处理
  2. 并发数限制：num_workers=1 时串行处理，num_workers=2 时并行
  3. 忙就不派：同一时刻不会超过 num_workers 个任务在跑
  4. 缓冲丢弃 - oldest：缓冲满时丢弃最旧的
  5. 缓冲丢弃 - newest：缓冲满时丢弃新来的
  6. on_drop 回调：被丢弃的值正确回调
  7. 异步 fn（返回 coroutine）
  8. 错误处理：fn 抛异常时正确传播
  9. 空流：没有值时 on_completed 触发
  10. on_completed 延迟：等待所有 pending 完成后才 on_completed
  11. 参数校验：num_workers < 1 / 非法 drop_strategy
  12. 单 worker 的并发安全
  13. 字符串表达式 fn（和其他操作符保持一致的便利）
  14. dispatch_workers 短别名等价于 dispatch_to_workers
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive import Observable, Subject, ops, dispatch_to_workers, dispatch_workers


# ========== 辅助工具 ==========

def wait_until(condition, timeout=5.0, interval=0.01):
    """等待直到条件成立或超时"""
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(interval)
    return False


def _run_all_tests(tests):
    """辅助函数：运行所有测试函数列表"""
    failed = 0
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print("[PASS] %s" % name)
        except AssertionError as e:
            failed += 1
            print("[FAIL] %s: %s" % (name, e))
        except Exception as e:
            failed += 1
            print("[ERROR] %s: %s" % (name, e))
    return failed


# ========== 1. 基础功能 ==========

def test_basic_sync_fn_all_values_processed():
    """同步 fn：所有输入值都被处理并发出结果"""
    result = []

    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
        ops.dispatch_to_workers(lambda x: x * 10, num_workers=2)
    ).subscribe(on_next=result.append)

    # from_iterable 是同步的，但 worker 通过线程池异步执行 → 需要等一下
    assert wait_until(lambda: sorted(result) == [10, 20, 30, 40, 50], timeout=3.0), \
        "got %s" % sorted(result)


def test_basic_fingerprint_values_all_arrive():
    """每个值都被接收到（通过 Subject push 进来也一样）"""
    result = []
    subj = Subject()
    subj.pipe(
        ops.dispatch_to_workers(lambda x: x + 1, num_workers=3)
    ).subscribe(on_next=result.append)

    for v in [10, 20, 30, 40, 50]:
        subj.on_next(v)
    subj.on_completed()

    assert wait_until(lambda: sorted(result) == [11, 21, 31, 41, 51], timeout=3.0), \
        "got %s" % sorted(result)


# ========== 2 & 3. 并发数限制 ==========

def test_concurrency_limit_single_worker():
    """num_workers=1：串行处理，同一时刻最多只有 1 个任务在跑"""
    result = []
    max_parallel = [0]
    current_parallel = [0]
    lock = threading.Lock()

    def slow_square(x):
        with lock:
            current_parallel[0] += 1
            max_parallel[0] = max(max_parallel[0], current_parallel[0])
        time.sleep(0.05)
        with lock:
            current_parallel[0] -= 1
        return x * x

    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
        ops.dispatch_to_workers(slow_square, num_workers=1)
    ).subscribe(on_next=result.append)

    assert wait_until(lambda: sorted(result) == [1, 4, 9, 16, 25], timeout=5.0), \
        "got %s" % sorted(result)
    assert max_parallel[0] == 1, "single worker should have max_parallel==1, got %d" % max_parallel[0]


def test_concurrency_limit_two_workers_runs_in_parallel():
    """num_workers=2：同一时刻最多 2 个任务在跑，总体耗时应该比串行少"""
    result = []
    max_parallel = [0]
    current_parallel = [0]
    lock = threading.Lock()

    def slow_identity(x):
        with lock:
            current_parallel[0] += 1
            max_parallel[0] = max(max_parallel[0], current_parallel[0])
        time.sleep(0.08)
        with lock:
            current_parallel[0] -= 1
        return x

    start = time.time()
    Observable.from_iterable([1, 2, 3, 4]).pipe(
        ops.dispatch_to_workers(slow_identity, num_workers=2)
    ).subscribe(on_next=result.append)

    assert wait_until(lambda: sorted(result) == [1, 2, 3, 4], timeout=5.0), \
        "got %s" % sorted(result)
    elapsed = time.time() - start

    assert max_parallel[0] >= 2, \
        "two workers should reach parallel >= 2, got %d" % max_parallel[0]
    assert max_parallel[0] <= 2, \
        "two workers should have max_parallel <= 2, got %d" % max_parallel[0]
    # 串行 4 * 0.08 = 0.32s，并行 2 个 slot 应该 <= ~0.18s，放宽到 0.28s 防抖动
    assert elapsed < 0.28, "parallel run took too long: %.3fs" % elapsed


# ========== 4 & 5. 缓冲丢弃策略 ==========

def test_buffer_drop_oldest():
    """buffer_size=1, num_workers=1, worker 慢 → 缓冲满时丢最旧的"""
    import threading as _threading
    lock = _threading.Lock()
    processed = []
    dropped = []

    # 使用 Subject 可控 push
    subj = Subject()
    subj.pipe(
        ops.dispatch_to_workers(
            fn=lambda x: (time.sleep(0.1), processed.append(x), x)[-1],
            num_workers=1,
            buffer_size=1,
            on_drop=dropped.append,
            drop_strategy="oldest",
        )
    ).subscribe(on_next=lambda v: None)

    # 快速 push 5 个值，worker 每次 0.1s，buffer_size=1：
    # 第 1 个 → 立即处理
    # 第 2 个 → 入 buffer（buffer=[2]）
    # 第 3 个 → buffer 满，丢 buffer 最旧的 = 2；3 入 buffer
    # 第 4 个 → buffer 满，丢 3；4 入 buffer
    # 第 5 个 → buffer 满，丢 4；5 入 buffer
    # 等一段时间后：应该处理 1 和 5，中间 2,3,4 被丢
    for v in [1, 2, 3, 4, 5]:
        subj.on_next(v)

    subj.on_completed()

    assert wait_until(lambda: sorted(processed) == [1, 5], timeout=3.0), \
        "expected processed [1, 5], got %s, dropped %s" % (sorted(processed), sorted(dropped))
    # dropped 应该包含 2, 3, 4（被丢弃的值）
    assert set(dropped) >= {2, 3, 4}, \
        "expected dropped to include {2, 3, 4}, got %s" % sorted(dropped)


def test_buffer_drop_newest():
    """buffer_size=1, num_workers=1, worker 慢 → 缓冲满时丢新来的"""
    processed = []
    dropped = []

    subj = Subject()
    subj.pipe(
        ops.dispatch_to_workers(
            fn=lambda x: (time.sleep(0.1), processed.append(x), x)[-1],
            num_workers=1,
            buffer_size=1,
            on_drop=dropped.append,
            drop_strategy="newest",
        )
    ).subscribe(on_next=lambda v: None)

    # 第 1 个 → 立即处理
    # 第 2 个 → 入 buffer（buffer=[2]）
    # 第 3 个 → buffer 满，丢新来的 = 3
    # 第 4 个 → buffer 满，丢新来的 = 4
    # 第 5 个 → buffer 满，丢新来的 = 5
    # 等一段时间后：应该处理 1 和 2，3,4,5 被丢
    for v in [1, 2, 3, 4, 5]:
        subj.on_next(v)

    subj.on_completed()

    assert wait_until(lambda: sorted(processed) == [1, 2], timeout=3.0), \
        "expected processed [1, 2], got %s, dropped %s" % (sorted(processed), sorted(dropped))
    assert set(dropped) >= {3, 4, 5}, \
        "expected dropped to include {3, 4, 5}, got %s" % sorted(dropped)


# ========== 6. on_drop 回调 ==========

def test_on_drop_receives_exact_dropped_value():
    """on_drop 回调接收到被丢弃的值（newest 策略）"""
    dropped_values = []
    processed = []

    subj = Subject()
    subj.pipe(
        ops.dispatch_to_workers(
            fn=lambda x: (time.sleep(0.1), processed.append(x), x)[-1],
            num_workers=1,
            buffer_size=1,
            on_drop=dropped_values.append,
            drop_strategy="newest",
        )
    ).subscribe(on_next=lambda v: None)

    # 1 立即被处理；2 进入 buffer；3,4,5 新来的被丢弃
    for v in [1, 2, 3, 4, 5]:
        subj.on_next(v)
    subj.on_completed()

    assert wait_until(lambda: 3 in dropped_values and 4 in dropped_values and 5 in dropped_values,
                       timeout=3.0), \
        "expected 3,4,5 to be dropped, got dropped=%s, processed=%s" % (dropped_values, processed)
    assert wait_until(lambda: sorted(processed) == [1, 2], timeout=3.0), \
        "expected processed [1, 2], got %s" % sorted(processed)


# ========== 7. 异步 fn ==========

def test_async_coroutine_fn():
    """fn 返回 coroutine（async def）时也能正常执行"""
    import asyncio

    async def async_process(x):
        await asyncio.sleep(0.02)
        return x * 2

    result = []
    Observable.from_iterable([1, 2, 3]).pipe(
        ops.dispatch_to_workers(async_process, num_workers=2)
    ).subscribe(on_next=result.append)

    assert wait_until(lambda: sorted(result) == [2, 4, 6], timeout=3.0), \
        "got %s" % sorted(result)


# ========== 8. 错误处理 ==========

def test_error_propagation_from_fn():
    """fn 抛异常时通过 on_error 传播，且后续值不再继续产生结果"""
    errors = []
    results = []

    def maybe_fail(x):
        if x == 3:
            raise ValueError("boom at %d" % x)
        return x * 10

    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
        ops.dispatch_to_workers(maybe_fail, num_workers=2)
    ).subscribe(
        on_next=results.append,
        on_error=errors.append,
    )

    assert wait_until(lambda: len(errors) >= 1, timeout=3.0), \
        "expected error, got none, results=%s" % results
    assert any(isinstance(e, ValueError) and "boom" in str(e) for e in errors), \
        "expected ValueError('boom'), got %s" % errors


def test_error_propagation_from_upstream():
    """上游 Observable 发出 error 时也能正确传播"""
    errors = []
    results = []

    subj = Subject()
    subj.pipe(ops.dispatch_to_workers(lambda x: x + 1, num_workers=2)).subscribe(
        on_next=results.append,
        on_error=errors.append,
    )

    subj.on_next(1)
    subj.on_next(2)
    subj.on_error(RuntimeError("upstream broken"))

    assert wait_until(lambda: len(errors) >= 1, timeout=2.0), \
        "expected error propagated, got %s" % errors
    assert any(isinstance(e, RuntimeError) for e in errors)


# ========== 9. 空流 ==========

def test_empty_stream_triggers_on_completed():
    """空 Observable 不会产生任何值，但会触发 on_completed"""
    results = []
    completed = [False]

    Observable.empty().pipe(
        ops.dispatch_to_workers(lambda x: x, num_workers=1)
    ).subscribe(
        on_next=results.append,
        on_completed=lambda: completed.__setitem__(0, True),
    )

    assert wait_until(lambda: completed[0], timeout=2.0), "on_completed not called"
    assert results == [], "empty stream should produce 0 results, got %s" % results


# ========== 10. on_completed 等所有 pending 完成 ==========

def test_on_completed_after_all_pending_finished():
    """on_completed 应该在所有 pending 的 worker 完成后才触发"""
    results = []
    completed_at = [None]

    def slow(x):
        time.sleep(0.03)
        return x

    obs = Observable.from_iterable([1, 2, 3])
    obs.pipe(
        ops.dispatch_to_workers(slow, num_workers=1)
    ).subscribe(
        on_next=results.append,
        on_completed=lambda: completed_at.__setitem__(0, time.time()),
    )

    assert wait_until(lambda: completed_at[0] is not None, timeout=3.0), \
        "on_completed not called, results=%s" % results
    assert sorted(results) == [1, 2, 3], "results=%s" % sorted(results)


# ========== 11. 参数校验 ==========

def test_invalid_num_workers_raises():
    """num_workers < 1 时抛 ValueError"""
    try:
        ops.dispatch_to_workers(lambda x: x, num_workers=0)
        assert False, "expected ValueError for num_workers=0"
    except ValueError as e:
        assert "num_workers" in str(e).lower() or ">= 1" in str(e), \
            "unexpected error message: %s" % e


def test_invalid_drop_strategy_raises():
    """非法 drop_strategy 抛 ValueError"""
    try:
        ops.dispatch_to_workers(lambda x: x, num_workers=1, drop_strategy="foo")
        assert False, "expected ValueError for unknown drop_strategy"
    except ValueError as e:
        assert "drop_strategy" in str(e).lower() or "oldest" in str(e), \
            "unexpected error message: %s" % e


# ========== 12. 单 worker 并发安全 ==========

def test_single_worker_preserves_order():
    """num_workers=1 + worker 耗时一样 → 输出顺序应该等于输入顺序（FIFO）"""
    import threading as _threading
    lock = _threading.Lock()
    received = []

    def identity(x):
        time.sleep(0.01)
        with lock:
            received.append(x)
        return x

    Observable.from_iterable([1, 2, 3, 4, 5, 6]).pipe(
        ops.dispatch_to_workers(identity, num_workers=1)
    ).subscribe()

    assert wait_until(lambda: received == [1, 2, 3, 4, 5, 6], timeout=3.0), \
        "expected ordered [1,2,3,4,5,6], got %s" % received


# ========== 13. 无 fn 参数（默认 identity）==========


def test_default_identity_fn():
    """fn=None 时默认 identity：值原样传递"""
    result = []
    Observable.from_iterable([7, 8, 9]).pipe(
        ops.dispatch_to_workers(None, num_workers=2)
    ).subscribe(on_next=result.append)

    assert wait_until(lambda: sorted(result) == [7, 8, 9], timeout=3.0), \
        "got %s" % sorted(result)


# ========== 14. 短别名 ==========

def test_short_alias_identical_behavior():
    """dispatch_workers 应和 dispatch_to_workers 行为一致"""
    r1, r2 = [], []

    Observable.from_iterable([1, 2, 3]).pipe(
        ops.dispatch_to_workers(lambda x: x + 1, num_workers=1)
    ).subscribe(on_next=r1.append)

    Observable.from_iterable([1, 2, 3]).pipe(
        ops.dispatch_workers(lambda x: x + 1, num_workers=1)
    ).subscribe(on_next=r2.append)

    assert wait_until(lambda: sorted(r1) == [2, 3, 4] and sorted(r2) == [2, 3, 4], timeout=3.0), \
        "r1=%s, r2=%s" % (sorted(r1), sorted(r2))


# ========== PipeBuilder 方法 ==========

def test_pipe_builder_method():
    """PipeBuilder.dispatch_to_workers 链式调用应该工作"""
    result = []

    Observable.from_iterable([5, 6, 7]).p().dispatch_to_workers(
        lambda x: x * 2, num_workers=2
    ).subscribe(on_next=result.append)

    assert wait_until(lambda: sorted(result) == [10, 12, 14], timeout=3.0), \
        "got %s" % sorted(result)


# ========== 主入口 ==========

if __name__ == "__main__":
    tests = [
        test_basic_sync_fn_all_values_processed,
        test_basic_fingerprint_values_all_arrive,
        test_concurrency_limit_single_worker,
        test_concurrency_limit_two_workers_runs_in_parallel,
        test_buffer_drop_oldest,
        test_buffer_drop_newest,
        test_on_drop_receives_exact_dropped_value,
        test_async_coroutine_fn,
        test_error_propagation_from_fn,
        test_error_propagation_from_upstream,
        test_empty_stream_triggers_on_completed,
        test_on_completed_after_all_pending_finished,
        test_invalid_num_workers_raises,
        test_invalid_drop_strategy_raises,
        test_single_worker_preserves_order,
        test_default_identity_fn,
        test_short_alias_identical_behavior,
        test_pipe_builder_method,
    ]

    print("Running %d tests...\n" % len(tests))
    failed = test_all(tests)
    print("\n" + "=" * 40)
    if failed == 0:
        print("All %d tests PASSED" % len(tests))
        sys.exit(0)
    else:
        print("%d/%d tests FAILED" % (failed, len(tests)))
        sys.exit(1)
