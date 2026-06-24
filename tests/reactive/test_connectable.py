#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试 vools-reactive Connectable Observable
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.reactive import Observable, Subject, BehaviorSubject, ReplaySubject, ops
from vools.reactive.core.connectable import (
    ConnectableObservable,
    publish,
    share,
    ref_count,
    replay,
    publish_replay,
    auto_connect
)


def test_publish_basic():
    """测试 publish 操作符基础功能"""
    print("=== publish 基础测试 ===")

    result1 = []
    result2 = []

    source = Observable.from_iterable([1, 2, 3])

    # 创建可连接 Observable
    connectable = source.pipe(publish())

    # 在 connect 之前订阅，不应该收到任何数据
    sub1 = connectable.subscribe(on_next=lambda x: result1.append(x))

    # 尚未 connect，result1 应该为空
    assert result1 == [], f"Expected [], got {result1}"
    print("[OK] subscribe before connect - no emission")

    # connect 后开始发射
    connection = connectable.connect()
    assert result1 == [1, 2, 3], f"Expected [1,2,3], got {result1}"
    print("[OK] connect triggers emission")

    # 取消第一个订阅
    sub1.unsubscribe()

    # 第二个订阅者在 connect 之后订阅
    sub2 = connectable.subscribe(on_next=lambda x: result2.append(x))
    # 由于已经 connect，sub2 不会收到任何数据（因为数据已经发射完了）
    # 这是 publish 的预期行为

    print("[OK] publish basic")


def test_publish_multicast():
    """测试 publish 多播功能"""
    print("\n=== publish 多播测试 ===")

    results = []

    source = Observable.from_iterable([1, 2, 3])
    connectable = source.pipe(publish())

    # 两个订阅者
    sub1_results = []
    sub2_results = []

    sub1 = connectable.subscribe(on_next=lambda x: sub1_results.append(x))
    sub2 = connectable.subscribe(on_next=lambda x: sub2_results.append(x))

    # connect 触发发射
    connectable.connect()

    # 两个订阅者都应该收到相同的数据
    assert sub1_results == [1, 2, 3], f"Expected [1,2,3], got {sub1_results}"
    assert sub2_results == [1, 2, 3], f"Expected [1,2,3], got {sub2_results}"
    print("[OK] multicast to multiple subscribers")

    # 清理
    sub1.unsubscribe()
    sub2.unsubscribe()


def test_share():
    """测试 share 操作符 - 自动连接"""
    print("\n=== share 测试 ===")

    results = []

    source = Observable.from_iterable([1, 2, 3])
    shared = source.pipe(share())

    # share 是热 Observable，第一个订阅自动触发连接
    sub1_results = []
    shared.subscribe(on_next=lambda x: sub1_results.append(x))

    # 由于是热 Observable，数据应该立即开始流动
    assert sub1_results == [1, 2, 3], f"Expected [1,2,3], got {sub1_results}"
    print("[OK] first subscriber triggers auto-connect")

    # 第二个订阅者
    sub2_results = []
    shared.subscribe(on_next=lambda x: sub2_results.append(x))

    # share 会在订阅时立即重放已有数据
    assert sub2_results == [1, 2, 3], f"Expected [1,2,3], got {sub2_results}"
    print("[OK] second subscriber receives replayed values")


def test_ref_count():
    """测试 ref_count 操作符"""
    print("\n=== ref_count 测试 ===")

    emit_count = [0]
    subscribe_count = [0]

    def make_counter_source():
        """创建一个记录发射次数的 source"""
        return Observable.from_iterable([1, 2, 3]).pipe(
            ops.do_on_next(lambda x: emit_count.__setitem__(0, emit_count[0] + 1))
        )

    # 使用 ref_count
    source = make_counter_source().pipe(ref_count())

    # 第一个订阅 - 应该触发连接
    result1 = []
    sub1 = source.subscribe(on_next=lambda x: result1.append(x))
    # emit_count = 3 因为 source 发射了 [1, 2, 3]，每个值都触发一次 do_on_next
    assert emit_count[0] == 3, f"Expected 3 emissions (one per value), got {emit_count[0]}"
    print("[OK] first subscriber triggers connection")

    # 第二个订阅 - 不应该重新触发连接
    result2 = []
    sub2 = source.subscribe(on_next=lambda x: result2.append(x))
    # emit_count 仍然是 3，因为 source 没有重新发射
    assert emit_count[0] == 3, f"Expected still 3 emissions, got {emit_count[0]}"
    print("[OK] second subscriber does not re-trigger connection")

    # 两个订阅者都收到数据
    assert result1 == [1, 2, 3], f"Expected [1,2,3], got {result1}"
    assert result2 == [1, 2, 3], f"Expected [1,2,3], got {result2}"

    # 取消第一个订阅
    sub1.unsubscribe()
    # 取消第二个订阅
    sub2.unsubscribe()

    print("[OK] ref_count")


def test_replay():
    """测试 replay 操作符"""
    print("\n=== replay 测试 ===")

    results = []

    source = Observable.from_iterable([1, 2, 3])
    connectable = source.pipe(replay())

    # 在 connect 之前订阅
    sub1_results = []
    sub1 = connectable.subscribe(on_next=lambda x: sub1_results.append(x))

    # connect
    connectable.connect()

    # 第一个订阅者应该收到所有数据
    assert sub1_results == [1, 2, 3], f"Expected [1,2,3], got {sub1_results}"
    print("[OK] first subscriber receives all values")

    # 第二个订阅者（connect之后订阅）- 也应该收到所有数据（replay功能）
    sub2_results = []
    sub2 = connectable.subscribe(on_next=lambda x: sub2_results.append(x))

    assert sub2_results == [1, 2, 3], f"Expected [1,2,3], got {sub2_results}"
    print("[OK] second subscriber receives replayed values")

    sub1.unsubscribe()
    sub2.unsubscribe()


def test_replay_with_buffer_size():
    """测试带缓冲大小的 replay"""
    print("\n=== replay(buffer_size) 测试 ===")

    source = Observable.from_iterable([1, 2, 3, 4, 5])
    connectable = source.pipe(replay(buffer_size=2))

    sub1 = connectable.subscribe()
    connectable.connect()

    # 第一个订阅者收到所有数据（因为是源订阅者）
    # 第二个订阅者只收到最近2个（buffer_size=2）
    sub2_results = []
    sub2 = connectable.subscribe(on_next=lambda x: sub2_results.append(x))

    # replay 应该重放最后的 buffer_size 个值
    assert sub2_results == [4, 5], f"Expected [4,5], got {sub2_results}"
    print("[OK] replay with buffer_size=2")

    sub1.unsubscribe()
    sub2.unsubscribe()


def test_publish_replay():
    """测试 publish_replay 操作符"""
    print("\n=== publish_replay 测试 ===")

    results = []

    source = Observable.from_iterable([1, 2, 3])
    connectable = source.pipe(publish_replay())

    # connect 之前订阅
    sub1_results = []
    sub1 = connectable.subscribe(on_next=lambda x: sub1_results.append(x))

    connectable.connect()

    assert sub1_results == [1, 2, 3], f"Expected [1,2,3], got {sub1_results}"
    print("[OK] publish_replay first subscriber")

    # connect之后订阅的应该收到重放的数据
    sub2_results = []
    sub2 = connectable.subscribe(on_next=lambda x: sub2_results.append(x))

    assert sub2_results == [1, 2, 3], f"Expected [1,2,3], got {sub2_results}"
    print("[OK] publish_replay second subscriber")

    sub1.unsubscribe()
    sub2.unsubscribe()


def test_auto_connect():
    """测试 auto_connect 操作符"""
    print("\n=== auto_connect 测试 ===")

    emit_count = [0]

    source = Observable.from_iterable([1, 2, 3]).pipe(
        ops.do_on_next(lambda x: emit_count.__setitem__(0, emit_count[0] + 1))
    )

    connectable = source.pipe(publish())
    auto = connectable.pipe(auto_connect(num_subscriptions=2))

    # 第一个订阅 - 不触发连接（因为 num_subscriptions=2）
    result1 = []
    sub1 = auto.subscribe(on_next=lambda x: result1.append(x))
    assert emit_count[0] == 0, f"Expected 0, got {emit_count[0]}"
    print("[OK] first subscriber does not trigger auto-connect")

    # 第二个订阅 - 触发连接，source 发射 3 个值
    result2 = []
    sub2 = auto.subscribe(on_next=lambda x: result2.append(x))
    # emit_count = 3 因为 source 发射了 [1, 2, 3]，每个值都触发一次 do_on_next
    assert emit_count[0] == 3, f"Expected 3, got {emit_count[0]}"
    print("[OK] second subscriber triggers auto-connect")

    assert result1 == [1, 2, 3], f"Expected [1,2,3], got {result1}"
    assert result2 == [1, 2, 3], f"Expected [1,2,3], got {result2}"

    sub1.unsubscribe()
    sub2.unsubscribe()


def test_connectable_observable_connect_twice():
    """测试 ConnectableObservable 的 connect 方法只会连接一次"""
    print("\n=== connect only once 测试 ===")

    emission_count = [0]

    source = Observable.from_iterable([1, 2, 3]).pipe(
        ops.do_on_next(lambda x: emission_count.__setitem__(0, emission_count[0] + 1))
    )

    connectable = source.pipe(publish())

    sub1 = connectable.subscribe()
    connectable.connect()
    connectable.connect()  # 第二次调用不应该重新触发

    # source 发射了 3 个值 (1, 2, 3)，每个值都会触发 do_on_next
    # 所以 emission_count = 3
    # 但关键是 connect() 被调用了多次，source 只被订阅了一次
    assert emission_count[0] == 3, f"Expected 3 (one per value), got {emission_count[0]}"
    print("[OK] connect() only triggers source subscription once")

    sub1.unsubscribe()


def test_connectable_unsubscribe_before_connect():
    """测试在 connect 之前取消订阅"""
    print("\n=== unsubscribe before connect 测试 ===")

    results = []

    source = Observable.from_iterable([1, 2, 3])
    connectable = source.pipe(publish())

    sub1 = connectable.subscribe(on_next=lambda x: results.append(x))
    sub1.unsubscribe()  # 在 connect 之前取消

    # connect
    connectable.connect()

    # 第一个订阅者已取消，不应该收到数据
    assert results == [], f"Expected [], got {results}"
    print("[OK] unsubscribed before connect receives no values")


if __name__ == "__main__":
    tests = [
        test_publish_basic,
        test_publish_multicast,
        test_share,
        test_ref_count,
        test_replay,
        test_replay_with_buffer_size,
        test_publish_replay,
        test_auto_connect,
        test_connectable_observable_connect_twice,
        test_connectable_unsubscribe_before_connect,
    ]

    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"Connectable Observable Tests: {passed}/{len(tests)} passed")
    print(f"Coverage: {passed/len(tests)*100:.1f}%")