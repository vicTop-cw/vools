# vools.vconcurrent — 并发工具集

> **改名说明**：物理目录从 `vools/concurrent` 更名为 `vools/vconcurrent`。
> 原目录名会 shadow 标准库 `concurrent.futures`——只要 vools 根出现在 `sys.path`
> 前面，任何 `import concurrent.futures` 都会命中 `vools/concurrent/futures.py`
> 而不是标准库，导致 `from concurrent.futures import ThreadPoolExecutor` 直接崩
> （`vools/decorators/trd.py` 首当其冲）。
>
> **兼容**：`from vools.concurrent.futures import ...` 等旧用法依然可用
> （`vools/__init__.py` 用 `sys.modules` 代理把 `vools.concurrent` 指向本目录）。
> 新代码请改用 `vools.vconcurrent.*`。

提供跨语言的并发/并行桥接能力。

## 核心模块

| 模块 | 能力 |
|------|------|
| `bridges` | 跨语言桥接（Nim/Rust/Go/Zig/TypeScript等） |
| `delegates` | 任务委托 |
| `futures` | Future/Promise 抽象 |
| `queues` | 线程安全队列 |
| `sched_mod` | 调度模块 |
| `spawns` | 进程/线程生成 |
| `threading_mod` | 线程工具 |

## 使用示例

```python
from vools.concurrent import get_manager

manager = get_manager()
```
