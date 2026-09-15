# vools.concurrent — 并发工具集

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
