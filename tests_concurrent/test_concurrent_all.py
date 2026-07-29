# -*- coding: utf-8 -*-
"""
vools.concurrent 综合测试
在独立测试文件夹中运行，不影响主项目测试
"""
from __future__ import annotations

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _add_fn(a, b):
    return a + b


def _raise_err_fn():
    raise ValueError("test error")


def _increment_fn(val):
    for _ in range(100):
        v = val.get()
        val.set(v + 1)


def _sender_fn(conn):
    conn.send("hello from process")
    conn.send_bytes(b"bytes data")


def _square_fn(x):
    return x * x


def _compute_fn(x):
    return x * 2


def _worker_fn(n):
    return n


def test_import_all_modules():
    """测试所有模块可以正常导入"""
    from vools.concurrent import threading_mod
    from vools.concurrent import multiprocessing_mod
    from vools.concurrent import futures
    from vools.concurrent import subprocess_mod
    from vools.concurrent import spawns
    from vools.concurrent import contextvars_mod
    from vools.concurrent import sched_mod
    from vools.concurrent import queues
    from vools.concurrent import delegates
    from vools.concurrent import bridges
    from vools.concurrent import asyncio_mod

    assert True


def test_vthread_basic():
    """测试 VThread 基本功能"""
    from vools.concurrent.threading_mod import VThread

    t = VThread(target=_add_fn, args=(2, 3))
    t.start()
    result = t.get_result()
    assert result == 5
    assert t.is_done()


def test_vthread_exception():
    """测试 VThread 异常捕获"""
    from vools.concurrent.threading_mod import VThread

    t = VThread(target=_raise_err_fn)
    t.start()
    t.join()
    assert t.has_exception
    assert isinstance(t.exception, ValueError)


def test_vlock_reentrant():
    """测试 VLock 可重入"""
    from vools.concurrent.threading_mod import VLock

    lock = VLock()
    with lock:
        with lock:
            assert lock.count == 2
    assert lock.count == 0


def test_vevent_wait_for():
    """测试 VEvent wait_for"""
    from vools.concurrent.threading_mod import VEvent

    evt = VEvent()
    results = []

    def setter():
        time.sleep(0.1)
        results.append(1)
        evt.set()

    threading.Thread(target=setter, daemon=True).start()
    evt.wait_for(lambda: len(results) > 0, timeout=2)
    assert len(results) == 1


def test_vsemaphore_timeout():
    """测试 VSemaphore 超时"""
    from vools.concurrent.threading_mod import VSemaphore

    sem = VSemaphore(0)
    assert sem.acquire_timeout(0.1) == False


def test_vlatch():
    """测试 VLatch (CountDownLatch)"""
    from vools.concurrent.threading_mod import VLatch

    latch = VLatch(3)
    results = []

    def worker(n):
        time.sleep(0.05 * n)
        results.append(n)
        latch.count_down()

    for i in range(1, 4):
        threading.Thread(target=worker, args=(i,), daemon=True).start()

    latch.wait(timeout=2)
    assert len(results) == 3


def test_synchronized_decorator():
    """测试 synchronized 装饰器"""
    from vools.concurrent.threading_mod import synchronized

    class Counter:
        def __init__(self):
            self.value = 0

        @synchronized
        def increment(self):
            v = self.value
            time.sleep(0.001)
            self.value = v + 1

    counter = Counter()
    threads = []
    for _ in range(10):
        t = threading.Thread(target=counter.increment)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    assert counter.value == 10


def test_run_in_thread_decorator():
    """测试 run_in_thread 装饰器"""
    from vools.concurrent.threading_mod import run_in_thread

    @run_in_thread(daemon=True)
    def compute(x):
        return x * 2

    t = compute(21)
    t.join()
    assert t.get_result() == 42


def test_vqueue_basic():
    """测试 VQueue 基本功能"""
    from vools.concurrent.queues import VQueue

    q = VQueue()
    q.put(1)
    q.put(2)
    q.put(3)
    assert q.peek() == 1
    assert q.get() == 1
    assert q.qsize() == 2
    assert not q.is_empty()

    q.clear()
    assert q.is_empty()


def test_vqueue_put_get_many():
    """测试 VQueue 批量操作"""
    from vools.concurrent.queues import VQueue

    q = VQueue()
    q.put_many([1, 2, 3, 4, 5])
    assert q.qsize() == 5

    items = q.get_many(3, timeout=1)
    assert items == [1, 2, 3]
    assert q.qsize() == 2


def test_vpriority_queue():
    """测试 VPriorityQueue"""
    from vools.concurrent.queues import VPriorityQueue

    q = VPriorityQueue()
    q.put("low", priority=10)
    q.put("high", priority=1)
    q.put("mid", priority=5)

    assert q.get() == "high"
    assert q.get() == "mid"
    assert q.get() == "low"


def test_vdeque():
    """测试 VDeque 双端队列"""
    from vools.concurrent.queues import VDeque

    dq = VDeque()
    dq.append_right(1)
    dq.append_right(2)
    dq.append_left(0)

    assert dq.pop_left() == 0
    assert dq.pop_right() == 2
    assert len(dq) == 1


def test_bounded_channel():
    """测试 BoundedChannel"""
    from vools.concurrent.queues import BoundedChannel

    ch = BoundedChannel(maxsize=2)
    ch.send(1)
    ch.send(2)
    assert ch.recv() == 1
    assert ch.recv() == 2

    ch.close()
    assert ch.is_closed


def test_delegate_multicast():
    """测试 Delegate 多播委托"""
    from vools.concurrent.delegates import Delegate

    results = []

    def handler1(x):
        results.append(("h1", x))

    def handler2(x):
        results.append(("h2", x))

    d = Delegate()
    d += handler1
    d += handler2
    d.invoke(42)

    assert len(results) == 2
    assert ("h1", 42) in results
    assert ("h2", 42) in results


def test_delegate_iadd_isub():
    """测试 Delegate += / -= 操作符"""
    from vools.concurrent.delegates import Delegate

    calls = []

    def fn():
        calls.append(1)

    d = Delegate()
    d += fn
    d.invoke()
    assert len(calls) == 1

    d -= fn
    d.invoke()
    assert len(calls) == 1


def test_event_bus():
    """测试 EventBus 事件总线"""
    from vools.concurrent.delegates import EventBus

    bus = EventBus()
    results = []

    def on_data(payload):
        results.append(payload)

    bus.subscribe("data", on_data)
    bus.publish("data", "hello")
    bus.publish("data", "world")

    assert results == ["hello", "world"]


def test_event_bus_wildcard():
    """测试 EventBus 通配符"""
    from vools.concurrent.delegates import EventBus

    bus = EventBus()
    results = []

    def on_all(event, payload):
        results.append((event, payload))

    bus.subscribe("*", on_all)
    bus.publish("evt1", 1)
    bus.publish("evt2", 2)

    assert len(results) == 2


def test_callback_chain():
    """测试 CallbackChain 回调链"""
    from vools.concurrent.delegates import CallbackChain

    results = []

    def step1(x):
        results.append(("s1", x))
        return True

    def step2(x):
        results.append(("s2", x))
        return False

    def step3(x):
        results.append(("s3", x))
        return True

    chain = CallbackChain()
    chain.add(step1)
    chain.add(step2)
    chain.add(step3)

    chain.execute(42)
    assert len(results) == 2
    assert results[-1] == ("s2", 42)


def test_future_result_basic():
    """测试 FutureResult 基本功能"""
    from vools.concurrent.futures import FutureResult
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: 42)
        fr = FutureResult(fut)
        assert fr.result() == 42
        assert fr.done()
        assert fr.success()


def test_gather_futures():
    """测试 gather_futures"""
    from vools.concurrent.futures import gather_futures
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(lambda x: x * 2, i) for i in range(5)]
        results = gather_futures(futs)
        assert results == [0, 2, 4, 6, 8]


def test_wait_any():
    """测试 wait_any"""
    from vools.concurrent.futures import wait_any
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        def slow():
            time.sleep(0.5)
            return "slow"

        def fast():
            return "fast"

        futs = [ex.submit(slow), ex.submit(fast)]
        done, not_done = wait_any(futs)
        assert len(done) == 1
        assert len(not_done) == 1


def test_run_async_thread():
    """测试 run_async 线程模式"""
    from vools.concurrent.futures import run_async

    fr = run_async(lambda x, y: x + y, 3, 4, pool_type="thread")
    assert fr.result() == 7


def test_vthreadpool_executor():
    """测试 VThreadPoolExecutor"""
    from vools.concurrent.futures import VThreadPoolExecutor

    with VThreadPoolExecutor(max_workers=2) as pool:
        fr = pool.submit(lambda x: x * 2, 21)
        assert fr.result() == 42


def test_map_async():
    """测试 map_async"""
    from vools.concurrent.futures import map_async

    results = list(map_async(lambda x: x ** 2, [1, 2, 3, 4, 5], max_workers=2))
    assert results == [1, 4, 9, 16, 25]


def test_vcontextvar_basic():
    """测试 VContextVar 基本功能"""
    from vools.concurrent.contextvars_mod import VContextVar

    var = VContextVar("test_var", default=0)
    assert var.get() == 0
    var.set(42)
    assert var.get() == 42
    assert var.is_set()


def test_vcontextvar_with_value():
    """测试 VContextVar with_value 上下文管理器"""
    from vools.concurrent.contextvars_mod import VContextVar

    var = VContextVar("test_with", default=0)
    var.set(10)
    with var.with_value(20):
        assert var.get() == 20
    assert var.get() == 10


def test_context_scope():
    """测试 ContextScope"""
    from vools.concurrent.contextvars_mod import ContextScope, VContextVar

    a = VContextVar("a_scope", default=0)
    b = VContextVar("b_scope", default="")

    with ContextScope() as scope:
        scope.set("a_scope", 42)
        scope.set("b_scope", "hello")
        assert a.get() == 42
        assert b.get() == "hello"

    assert a.get() == 0
    assert b.get() == ""


def test_contextual_decorator():
    """测试 contextual 装饰器"""
    from vools.concurrent.contextvars_mod import VContextVar, contextual

    user_var = VContextVar("current_user_ctx", default="anonymous")

    @contextual(user_var, "user")
    def greet(user=None):
        return f"Hello, {user}!"

    user_var.set("Alice")
    assert greet() == "Hello, Alice!"
    assert greet(user="Bob") == "Hello, Bob!"


def test_vscheduler():
    """测试 VScheduler"""
    from vools.concurrent.sched_mod import VScheduler

    scheduler = VScheduler()
    results = []

    def task(x):
        results.append(x)

    scheduler.schedule(0.05, task, 1)
    scheduler.schedule(0.1, task, 2)
    scheduler.run(blocking=True)

    assert results == [1, 2]


def test_timer_single():
    """测试 Timer 单次模式"""
    from vools.concurrent.sched_mod import Timer

    results = []

    def callback():
        results.append("done")

    t = Timer(0.05, callback, repeat=False)
    t.start()
    time.sleep(0.15)

    assert len(results) == 1


def test_periodic_task():
    """测试 PeriodicTask"""
    from vools.concurrent.sched_mod import PeriodicTask

    counter = [0]

    def tick():
        counter[0] += 1

    task = PeriodicTask(0.05, tick)
    task.start()
    time.sleep(0.2)
    task.stop()

    assert counter[0] >= 2


def test_delayed_call():
    """测试 delayed_call"""
    from vools.concurrent.sched_mod import delayed_call

    results = []

    def fn(x):
        results.append(x)

    t = delayed_call(0.05, fn, "hello")
    t.join()

    assert results == ["hello"]


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="multiprocessing test")
def test_vprocess_basic():
    """测试 VProcess 基本功能"""
    from vools.concurrent.multiprocessing_mod import VProcess

    p = VProcess(target=_add_fn, args=(2, 3))
    p.start()
    p.join()
    assert p.get_result() == 5


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="multiprocessing test")
def test_vprocess_exception():
    """测试 VProcess 异常捕获"""
    from vools.concurrent.multiprocessing_mod import VProcess

    p = VProcess(target=_raise_err_fn)
    p.start()
    p.join()
    try:
        p.get_result()
        assert False, "Should have raised"
    except ValueError:
        pass
    assert p.exception is not None
    assert isinstance(p.exception, ValueError)


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="multiprocessing test")
def test_shared_value():
    """测试 SharedValue"""
    from vools.concurrent.multiprocessing_mod import SharedValue, VProcess

    sv = SharedValue("i", 0)
    processes = [VProcess(target=_increment_fn, args=(sv,)) for _ in range(4)]

    for p in processes:
        p.start()
    for p in processes:
        p.join()

    assert sv.get() == 400


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="multiprocessing test")
def test_pipe_channel():
    """测试 PipeChannel"""
    from vools.concurrent.multiprocessing_mod import PipeChannel, VProcess

    ch = PipeChannel(duplex=False)
    p = VProcess(target=_sender_fn, args=(ch.child_conn,))
    p.start()

    msg = ch.recv()
    bmsg = ch.recv_bytes()
    p.join()
    ch.close()

    assert msg == "hello from process"
    assert bmsg == b"bytes data"


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="multiprocessing test")
def test_vprocess_pool():
    """测试 VProcessPool"""
    from vools.concurrent.multiprocessing_mod import VProcessPool

    with VProcessPool(processes=2) as pool:
        results = pool.map(_square_fn, [1, 2, 3, 4, 5])
        assert sorted(results) == [1, 4, 9, 16, 25]


def test_cpu_count():
    """测试 cpu_count"""
    from vools.concurrent.multiprocessing_mod import cpu_count
    assert cpu_count() >= 1


def test_subprocess_run_command():
    """测试 run_command"""
    from vools.concurrent.subprocess_mod import run_command

    returncode, stdout, stderr = run_command(
        ["python", "-c", "print('hello')"],
    )
    assert returncode == 0
    assert "hello" in stdout


def test_vprocess_subprocess():
    """测试 VProcess (subprocess 版本)"""
    from vools.concurrent.subprocess_mod import VProcess

    p = VProcess(["python", "-c", "print('test')"])
    p.start()
    out, err = p.communicate()
    assert p.returncode == 0
    assert "test" in (out or "")


def test_pipeline():
    """测试 Pipeline 管道"""
    from vools.concurrent.subprocess_mod import Pipeline

    result = Pipeline(["python", "-c", "print('hello world')"]).run()
    assert result[0] == 0
    assert "hello world" in result[1]


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="spawn test")
def test_spawn_handle():
    """测试 SpawnHandle"""
    from vools.concurrent.spawns import spawn

    handle = spawn(_compute_fn, args=(21,))
    handle.join()
    assert handle.exitcode == 0


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="spawn test")
def test_spawn_many():
    """测试 spawn_many"""
    from vools.concurrent.spawns import spawn_many

    handles = spawn_many(_square_fn, [(1,), (2,), (3,)])
    for h in handles:
        h.join()
    assert len(handles) == 3


@pytest.mark.skipif(sys.platform != "win32" and sys.platform != "linux", reason="spawn test")
def test_spawn_manager():
    """测试 SpawnManager"""
    from vools.concurrent.spawns import SpawnManager

    mgr = SpawnManager()
    mgr.register("w1", _worker_fn, args=(1,))
    mgr.register("w2", _worker_fn, args=(2,))

    mgr.start_all()
    mgr.monitor(timeout=5)
    mgr.stop_all()


def test_bridge_pipe_pair():
    """测试 PipePair"""
    from vools.concurrent.bridges import PipePair

    pair = PipePair()
    pair.a.send("hello")
    assert pair.b.recv() == "hello"
    pair.close()


def test_channel_bridge_json():
    """测试 ChannelBridge JSON 通信"""
    from vools.concurrent.bridges import ChannelBridge

    ch = ChannelBridge()
    data = {"key": "value", "num": 42, "list": [1, 2, 3]}
    ch.send_json(data)
    raw = ch.peer_connection.recv()
    assert isinstance(raw, tuple) and len(raw) == 2 and raw[0] == "__json__"
    import json
    received = json.loads(raw[1])
    assert received == data

    ch.peer_connection.send(("__json__", json.dumps({"reply": "ok"})))
    reply = ch.recv_json(timeout=1)
    assert reply == {"reply": "ok"}
    ch.close()


def test_queue_bridge():
    """测试 QueueBridge"""
    from vools.concurrent.bridges import QueueBridge
    import queue

    q1 = queue.Queue()
    q2 = queue.Queue()

    bridge = QueueBridge(q1, q2, transform_fn=lambda x: x * 2)
    bridge.start()

    q1.put(1)
    q1.put(2)
    q1.put(3)

    time.sleep(0.2)
    bridge.stop()

    assert q2.get() == 2
    assert q2.get() == 4
    assert q2.get() == 6


def test_event_bridge():
    """测试 EventBridge"""
    from vools.concurrent.bridges import EventBridge

    evt = EventBridge()
    assert not evt.is_set()
    evt.set()
    assert evt.is_set()
    assert evt.wait(timeout=1)
    evt.clear()
    assert not evt.is_set()


def test_bridge_queues():
    """测试 bridge_queues 函数"""
    from vools.concurrent.bridges import bridge_queues
    import queue

    q1 = queue.Queue()
    q2 = queue.Queue()

    forward, backward = bridge_queues(q1, q2, direction="forward")
    q1.put("test")
    time.sleep(0.1)
    forward.stop()

    assert not q2.empty()
    assert q2.get() == "test"


def test_async_queue():
    """测试 AsyncQueue"""
    from vools.concurrent.asyncio_mod import AsyncQueue
    import asyncio

    async def test():
        q = AsyncQueue(maxsize=2)
        await q.put(1)
        await q.put(2)
        assert await q.get() == 1
        assert await q.get() == 2
        assert q.empty()

    asyncio.run(test())


def test_async_lock():
    """测试 AsyncLock"""
    from vools.concurrent.asyncio_mod import AsyncLock
    import asyncio

    async def test():
        lock = AsyncLock()
        async with lock:
            assert True

    asyncio.run(test())


def test_async_semaphore():
    """测试 AsyncSemaphore"""
    from vools.concurrent.asyncio_mod import AsyncSemaphore
    import asyncio

    async def test():
        sem = AsyncSemaphore(2)
        async with sem:
            async with sem:
                assert True

    asyncio.run(test())


def test_async_event():
    """测试 AsyncEvent"""
    from vools.concurrent.asyncio_mod import AsyncEvent
    import asyncio

    async def test():
        evt = AsyncEvent()

        async def setter():
            await asyncio.sleep(0.05)
            evt.set()

        asyncio.create_task(setter())
        await evt.wait()
        assert evt.is_set()

    asyncio.run(test())


def test_gather_async():
    """测试 gather 异步并发"""
    from vools.concurrent.asyncio_mod import gather
    import asyncio

    async def task(n):
        await asyncio.sleep(0.01)
        return n * 2

    async def test():
        results = await gather(*[task(i) for i in range(5)])
        assert results == [0, 2, 4, 6, 8]

    asyncio.run(test())


def test_to_async():
    """测试 to_async 同步转异步"""
    from vools.concurrent.asyncio_mod import to_async
    import asyncio

    def sync_add(a, b):
        return a + b

    async def test():
        result = await to_async(sync_add)(1, 2)
        assert result == 3

    asyncio.run(test())


def test_delay():
    """测试 delay 延迟执行"""
    from vools.concurrent.asyncio_mod import delay
    import asyncio

    async def test():
        async def work():
            return "done"

        start = time.time()
        result = await delay(0.05, work())
        elapsed = time.time() - start
        assert result == "done"
        assert elapsed >= 0.04

    asyncio.run(test())


def test_timeout_async():
    """测试 timeout 异步超时"""
    from vools.concurrent.asyncio_mod import timeout
    import asyncio

    async def test():
        async def long_task():
            await asyncio.sleep(10)
            return "done"

        try:
            await timeout(long_task(), 0.05)
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass

    asyncio.run(test())


def test_async_pool():
    """测试 AsyncPool"""
    from vools.concurrent.asyncio_mod import AsyncPool
    import asyncio

    async def test():
        pool = AsyncPool(max_workers=2)
        results = []

        async def task(n):
            await asyncio.sleep(0.01)
            return n ** 2

        results = await pool.gather(*[task(i) for i in range(5)])
        assert sorted(results) == [0, 1, 4, 9, 16]

    asyncio.run(test())


def test_retry_async():
    """测试 retry_async 异步重试"""
    from vools.concurrent.asyncio_mod import retry_async
    import asyncio

    call_count = [0]

    @retry_async(max_retries=3, backoff=0.01)
    async def flaky():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError("temporary error")
        return "success"

    async def test():
        result = await flaky()
        assert result == "success"
        assert call_count[0] == 3

    asyncio.run(test())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
