"""
vools.concurrent - 并发与并行编程工具集

对 Python 标准库的并发模块进行高级封装，提供更易用、更安全的 API。

子模块：
    threading_mod    - 线程管理（线程、锁、事件、信号量）
    multiprocessing_mod - 进程管理（进程、共享内存、管道）
    futures          - concurrent.futures 封装
    subprocess_mod   - 子进程管理
    spawns           - 进程派生工具
    contextvars_mod  - 上下文变量
    sched_mod        - 事件调度器
    queues           - 队列工具
    delegates        - 委托模式
    bridges          - 跨模块桥接通信
    asyncio_mod      - 异步编程工具
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
]
