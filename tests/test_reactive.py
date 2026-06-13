#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试 vools.reactive 模块
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive import Observable, Subject, BehaviorSubject, ops


def test_observable_basic():
    """测试 Observable 基础功能"""
    print("=== Observable 基础测试 ===")
    
    result = []
    obs = Observable.from_iterable([1, 2, 3])
    obs.subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3], f"Expected [1,2,3], got {result}"
    print("[OK] from_iterable")
    
    result = []
    obs = Observable.of(1, 2, 3)
    obs.subscribe(on_next=lambda x: result.append(x))
    assert result == [1, 2, 3], f"Expected [1,2,3], got {result}"
    print("[OK] of")
    
    result = []
    obs = Observable.from_range(3)
    obs.subscribe(on_next=lambda x: result.append(x))
    assert result == [0, 1, 2], f"Expected [0,1,2], got {result}"
    print("[OK] from_range")


def test_observable_pipe():
    """测试管道操作"""
    print("\n=== 管道操作测试 ===")
    
    result = []
    obs = Observable.from_iterable([1, 2, 3, 4, 5])
    obs.pipe(
        ops.filter(lambda x: x > 2),
        ops.map(lambda x: x * 2),
        ops.take(2)
    ).subscribe(on_next=lambda x: result.append(x))
    assert result == [6, 8], f"Expected [6,8], got {result}"
    print("[OK] pipe")
    
    result = []
    (Observable.from_iterable([1,2,3,4,5]) >> ops.filter(lambda x: x > 2) >> ops.map(lambda x: x * 2)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [6, 8, 10], f"Expected [6,8,10], got {result}"
    print("[OK] >> operator")


def test_subject():
    """测试 Subject"""
    print("\n=== Subject 测试 ===")
    
    result1 = []
    result2 = []
    
    subj = Subject()
    subj.subscribe(on_next=lambda x: result1.append(x))
    subj.on_next(1)
    subj.on_next(2)
    
    subj.subscribe(on_next=lambda x: result2.append(x))
    subj.on_next(3)
    subj.on_completed()
    
    assert result1 == [1, 2, 3], f"Expected [1,2,3], got {result1}"
    assert result2 == [3], f"Expected [3], got {result2}"
    print("[OK] Subject")


def test_behavior_subject():
    """测试 BehaviorSubject"""
    print("\n=== BehaviorSubject 测试 ===")
    
    result = []
    subj = BehaviorSubject(0)
    subj.subscribe(on_next=lambda x: result.append(x))
    subj.on_next(1)
    subj.on_next(2)
    
    assert result == [0, 1, 2], f"Expected [0,1,2], got {result}"
    assert subj.value == 2, f"Expected value 2, got {subj.value}"
    print("[OK] BehaviorSubject")


def test_operators():
    """测试基础操作符"""
    print("\n=== 基础操作符测试 ===")
    
    result = []
    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(ops.filter(lambda x: x % 2 == 0)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [2, 4], f"Expected [2,4], got {result}"
    print("[OK] filter")
    
    result = []
    Observable.from_iterable([1, 2, 3]).pipe(ops.map(lambda x: x * 2)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [2, 4, 6], f"Expected [2,4,6], got {result}"
    print("[OK] map")
    
    result = []
    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(ops.take(3)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [1, 2, 3], f"Expected [1,2,3], got {result}"
    print("[OK] take")


def test_error_handling():
    """测试异常处理操作符"""
    print("\n=== 异常处理测试 ===")
    
    errors = []
    obs = Observable.throw(Exception("test"))
    obs.subscribe(on_error=lambda e: errors.append(e))
    assert len(errors) == 1, "Error not caught"
    print("[OK] throw")
    
    result = []
    Observable.throw(Exception("test")).pipe(ops.catch(lambda e: Observable.of("recovered"))).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == ["recovered"], f"Expected ['recovered'], got {result}"
    print("[OK] catch")
    
    result = []
    Observable.throw(Exception("test")).pipe(ops.on_error_return("recovered")).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == ["recovered"], f"Expected ['recovered'], got {result}"
    print("[OK] on_error_return")
    
    result = []
    Observable.throw(Exception("test")).pipe(ops.on_error_resume_next(Observable.of("a", "b"))).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == ["a", "b"], f"Expected ['a', 'b'], got {result}"
    print("[OK] on_error_resume_next")
    
    result = []
    Observable.throw(Exception("test")).pipe(ops.retry_when(lambda errors: Observable.empty())).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [], f"Expected [], got {result}"
    print("[OK] retry_when")


def test_combine_operators():
    """测试组合操作符"""
    print("\n=== 组合操作符测试 ===")
    
    result = []
    ops.zip(Observable.of(1, 2, 3), Observable.of('a', 'b', 'c')).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [(1, 'a'), (2, 'b'), (3, 'c')], f"Expected [(1,'a'), (2,'b'), (3,'c')], got {result}"
    print("[OK] zip")
    
    result = []
    ops.combine_latest(Observable.of(1, 2, 3), Observable.of('a', 'b')).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [(3, 'b')], f"Expected [(3,'b')], got {result}"
    print("[OK] combine_latest")
    
    result = []
    Observable.of(1, 2, 3).pipe(ops.with_latest_from(Observable.of('a', 'b'))).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [(1, 'b'), (2, 'b'), (3, 'b')], f"Expected [(1,'b'), (2,'b'), (3,'b')], got {result}"
    print("[OK] with_latest_from")


def test_math_operators():
    """测试数学聚合操作符"""
    print("\n=== 数学聚合操作符测试 ===")
    
    result = []
    Observable.from_iterable([1, 2, 3]).pipe(ops.sum()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [6.0], f"Expected [6.0], got {result}"
    print("[OK] sum")
    
    result = []
    Observable.from_iterable([1, 2, 3, 4]).pipe(ops.average()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [2.5], f"Expected [2.5], got {result}"
    print("[OK] average")
    
    result = []
    Observable.from_iterable([3, 1, 4, 2]).pipe(ops.minimum()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [1], f"Expected [1], got {result}"
    print("[OK] minimum")
    
    result = []
    Observable.from_iterable([3, 1, 4, 2]).pipe(ops.maximum()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [4], f"Expected [4], got {result}"
    print("[OK] maximum")


def test_conditional_operators():
    """测试条件判断操作符"""
    print("\n=== 条件判断操作符测试 ===")
    
    result = []
    Observable.from_iterable([2, 4, 6]).pipe(ops.all(lambda x: x % 2 == 0)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [True], f"Expected [True], got {result}"
    print("[OK] all (true)")
    
    result = []
    Observable.from_iterable([2, 3, 6]).pipe(ops.all(lambda x: x % 2 == 0)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [False], f"Expected [False], got {result}"
    print("[OK] all (false)")
    
    result = []
    Observable.from_iterable([1, 3, 4]).pipe(ops.any(lambda x: x % 2 == 0)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [True], f"Expected [True], got {result}"
    print("[OK] any (true)")
    
    result = []
    Observable.from_iterable([1, 3, 5]).pipe(ops.any(lambda x: x % 2 == 0)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [False], f"Expected [False], got {result}"
    print("[OK] any (false)")
    
    result = []
    Observable.from_iterable([1, 2, 3]).pipe(ops.contains(2)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [True], f"Expected [True], got {result}"
    print("[OK] contains (true)")
    
    result = []
    Observable.from_iterable([1, 2, 3]).pipe(ops.contains(4)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [False], f"Expected [False], got {result}"
    print("[OK] contains (false)")
    
    result = []
    Observable.empty().pipe(ops.is_empty()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [True], f"Expected [True], got {result}"
    print("[OK] is_empty (true)")
    
    result = []
    Observable.of(1).pipe(ops.is_empty()).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [False], f"Expected [False], got {result}"
    print("[OK] is_empty (false)")


def test_interval():
    """测试 interval 方法"""
    print("\n=== Interval 测试 ===")
    
    import asyncio
    
    result = []
    async def test():
        with Observable.interval(0.1).pipe(ops.take(3)).subscribe(on_next=lambda x: result.append(x)) as sub:
            await asyncio.sleep(0.5)
    
    asyncio.run(test())
    assert result == [0, 1, 2], f"Expected [0,1,2], got {result}"
    print("[OK] interval")


def test_debounce_throttle():
    """测试防抖和节流操作符"""
    print("\n=== 防抖节流测试 ===")
    
    import asyncio
    
    result = []
    async def test_debounce():
        obs = Observable.from_iterable([1, 2, 3])
        obs.pipe(ops.debounce(0.1)).subscribe(on_next=lambda x: result.append(x))
        await asyncio.sleep(0.2)
    
    asyncio.run(test_debounce())
    assert result == [3], f"Expected [3], got {result}"
    print("[OK] debounce")
    
    result = []
    async def test_throttle():
        obs = Observable.from_iterable([1, 2, 3])
        obs.pipe(ops.throttle_first(0.1)).subscribe(on_next=lambda x: result.append(x))
        await asyncio.sleep(0.2)
    
    asyncio.run(test_throttle())
    assert result == [1], f"Expected [1], got {result}"
    print("[OK] throttle_first")


def test_subscription_context_manager():
    """测试 Subscription 上下文管理器"""
    print("\n=== Subscription 上下文管理器测试 ===")
    
    sub = None
    with Observable.from_iterable([1, 2, 3]).subscribe(on_next=lambda x: None) as s:
        sub = s
        assert not sub.is_closed, "Subscription should not be closed during with block"
    assert sub.is_closed, "Subscription should be closed after with block"
    print("[OK] Subscription with statement")


def test_edge_cases():
    """测试边界条件"""
    print("\n=== 边界条件测试 ===")
    
    result = []
    Observable.from_iterable([]).subscribe(on_next=lambda x: result.append(x))
    assert result == [], f"Expected [], got {result}"
    print("[OK] empty")
    
    result = []
    Observable.from_iterable([None, 1, None]).subscribe(on_next=lambda x: result.append(x))
    assert result == [None, 1, None], f"Expected [None,1,None], got {result}"
    print("[OK] None values")


def test_integration():
    """测试集成"""
    print("\n=== 集成测试 ===")
    
    from vools.decorators import curry
    
    @curry
    def multiply(a, b):
        return a * b
    
    result = []
    Observable.from_iterable([1, 2, 3]).pipe(ops.map(multiply(2))).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [2, 4, 6], f"Expected [2,4,6], got {result}"
    print("[OK] curry integration")
    
    from vools.functional.placeholder import _
    
    result = []
    Observable.from_iterable([1, 2, 3, 4, 5]).pipe(ops.filter(_ > 2)).subscribe(
        on_next=lambda x: result.append(x)
    )
    assert result == [3, 4, 5], f"Expected [3,4,5], got {result}"
    print("[OK] placeholder integration")


if __name__ == "__main__":
    tests = [
        test_observable_basic,
        test_observable_pipe,
        test_subject,
        test_behavior_subject,
        test_operators,
        test_error_handling,
        test_combine_operators,
        test_math_operators,
        test_conditional_operators,
        test_interval,
        test_debounce_throttle,
        test_subscription_context_manager,
        test_edge_cases,
        test_integration,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
    
    print(f"\n{'='*50}")
    print(f"Tests: {passed}/{len(tests)} passed")
    print(f"Coverage: {passed/len(tests)*100:.1f}%")