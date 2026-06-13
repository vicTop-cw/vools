#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
压力测试: vools-reactive vs RxPy 4.0
"""

import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_vools_reactive():
    """测试 vools-reactive"""
    from vools.reactive import Observable, ops
    
    start = time.time()
    
    for _ in range(1000):
        result = []
        Observable.from_iterable(range(1000)).pipe(
            ops.filter(lambda x: x % 2 == 0),
            ops.map(lambda x: x * 2),
            ops.take(100)
        ).subscribe(on_next=lambda x: result.append(x))
    
    elapsed = time.time() - start
    return elapsed

def test_rxpy():
    """测试 RxPy 4.0"""
    try:
        from rx import from_iterable, operators as rx_ops
        
        start = time.time()
        
        for _ in range(1000):
            result = []
            from_iterable(range(1000)).pipe(
                rx_ops.filter(lambda x: x % 2 == 0),
                rx_ops.map(lambda x: x * 2),
                rx_ops.take(100)
            ).subscribe(on_next=lambda x: result.append(x))
        
        elapsed = time.time() - start
        return elapsed
    except ImportError:
        return None

async def test_vools_reactive_async():
    """测试 vools-reactive 异步性能"""
    from vools.reactive import Observable, ops
    
    start = time.time()
    
    for _ in range(100):
        result = []
        with Observable.interval(0.001).pipe(ops.take(10)).subscribe(on_next=lambda x: result.append(x)) as sub:
            await asyncio.sleep(0.02)
    
    elapsed = time.time() - start
    return elapsed

async def test_rxpy_async():
    """测试 RxPy 4.0 异步性能"""
    try:
        from rx import interval, operators as rx_ops
        
        start = time.time()
        
        for _ in range(100):
            result = []
            sub = interval(0.001).pipe(rx_ops.take(10)).subscribe(on_next=lambda x: result.append(x))
            await asyncio.sleep(0.02)
            sub.dispose()
        
        elapsed = time.time() - start
        return elapsed
    except ImportError:
        return None

def test_vools_combine_latest():
    """测试 vools-reactive combine_latest"""
    from vools.reactive import Observable, ops
    
    start = time.time()
    
    for _ in range(1000):
        result = []
        ops.combine_latest(
            Observable.from_iterable(range(100)),
            Observable.from_iterable(range(100))
        ).subscribe(on_next=lambda x: result.append(x))
    
    elapsed = time.time() - start
    return elapsed

def test_rxpy_combine_latest():
    """测试 RxPy combine_latest"""
    try:
        from rx import from_iterable, operators as rx_ops
        
        start = time.time()
        
        for _ in range(1000):
            result = []
            from_iterable(range(100)).pipe(
                rx_ops.combine_latest(from_iterable(range(100)))
            ).subscribe(on_next=lambda x: result.append(x))
        
        elapsed = time.time() - start
        return elapsed
    except ImportError:
        return None

def run_benchmark():
    print("=" * 70)
    print("压力测试: vools-reactive vs RxPy 4.0")
    print("=" * 70)
    
    print("\n[同步操作性能测试]")
    print("-" * 50)
    
    print("测试 vools-reactive...")
    vools_time = test_vools_reactive()
    print(f"vools-reactive: {vools_time:.4f} 秒")
    
    print("\n测试 RxPy 4.0...")
    rxpy_time = test_rxpy()
    if rxpy_time is not None:
        print(f"RxPy 4.0: {rxpy_time:.4f} 秒")
        ratio = rxpy_time / vools_time
        print(f"\n性能对比: vools-reactive 比 RxPy 快 {ratio:.2f}x")
    else:
        print("RxPy 4.0 未安装")
    
    print("\n[combine_latest 性能测试]")
    print("-" * 50)
    
    print("测试 vools-reactive combine_latest...")
    vools_cl_time = test_vools_combine_latest()
    print(f"vools-reactive: {vools_cl_time:.4f} 秒")
    
    print("\n测试 RxPy combine_latest...")
    rxpy_cl_time = test_rxpy_combine_latest()
    if rxpy_cl_time is not None:
        print(f"RxPy 4.0: {rxpy_cl_time:.4f} 秒")
        ratio = rxpy_cl_time / vools_cl_time
        print(f"\n性能对比: vools-reactive combine_latest 比 RxPy 快 {ratio:.2f}x")
    else:
        print("RxPy 4.0 未安装")
    
    print("\n[异步操作性能测试]")
    print("-" * 50)
    
    print("测试 vools-reactive interval...")
    vools_async_time = asyncio.run(test_vools_reactive_async())
    print(f"vools-reactive: {vools_async_time:.4f} 秒")
    
    print("\n测试 RxPy interval...")
    rxpy_async_time = asyncio.run(test_rxpy_async())
    if rxpy_async_time is not None:
        print(f"RxPy 4.0: {rxpy_async_time:.4f} 秒")
        ratio = rxpy_async_time / vools_async_time
        print(f"\n性能对比: vools-reactive interval 比 RxPy 快 {ratio:.2f}x")
    else:
        print("RxPy 4.0 未安装")
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmark()