# vools.reactive.core — 响应式核心

Observable / Subject / Scheduler 核心实现，提供响应式编程的基础构建块。

## 核心组件

| 名称 | 说明 |
|------|------|
| `Observable` | 可观察对象 |
| `Subject` | 主题（可同时作为 Observable 和 Observer） |
| `BehaviorSubject` | 保留最新值的 Subject |
| `ReplaySubject` | 重放历史值的 Subject |
| `Scheduler` | 调度器（Immediate / CurrentThread / AsyncIO / ThreadPool / NewThread） |
| `ConnectableObservable` | 可连接 Observable |

## 使用示例

### Observable 基础用法

```python
from vools.reactive.core import Observable

# 创建 Observable
obs = Observable.of(1, 2, 3)
obs.subscribe(lambda x: print(f"Next: {x}"))
# 输出:
# Next: 1
# Next: 2
# Next: 3

# 从可迭代对象创建
obs = Observable.from_iterable([1, 2, 3, 4, 5])
obs.subscribe(
    on_next=lambda x: print(x),
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Done")
)
```

### Subject 用法

```python
from vools.reactive.core import Subject

subject = Subject()

# 订阅者 1
subject.subscribe(lambda x: print(f"Subscriber 1: {x}"))

# 订阅者 2
subject.subscribe(lambda x: print(f"Subscriber 2: {x}"))

# 发送数据
subject.on_next(1)
subject.on_next(2)
subject.on_completed()
# 输出:
# Subscriber 1: 1
# Subscriber 2: 1
# Subscriber 1: 2
# Subscriber 2: 2
```

### BehaviorSubject 用法

```python
from vools.reactive.core import BehaviorSubject

# 创建时需要初始值
subject = BehaviorSubject(0)

# 订阅者 1（会立即收到初始值 0）
subject.subscribe(lambda x: print(f"Subscriber 1: {x}"))
# 输出: Subscriber 1: 0

# 发送新值
subject.on_next(1)
# 输出: Subscriber 1: 1

# 订阅者 2（会立即收到最新值 1）
subject.subscribe(lambda x: print(f"Subscriber 2: {x}"))
# 输出: Subscriber 2: 1
```

### ReplaySubject 用法

```python
from vools.reactive.core import ReplaySubject

# 重放最近 2 个值
subject = ReplaySubject(buffer_size=2)

# 发送多个值
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)

# 订阅者会收到最近的 2 个值 (2, 3)
subject.subscribe(lambda x: print(f"Replayed: {x}"))
# 输出:
# Replayed: 2
# Replayed: 3
```

### 调度器（Scheduler）

```python
from vools.reactive.core import Observable, Scheduler
import asyncio

# 立即调度（默认）
Observable.of(1, 2, 3).subscribe_on(Scheduler.immediate()).subscribe(print)

# 线程池调度
Observable.of(1, 2, 3).subscribe_on(Scheduler.thread_pool()).subscribe(print)

# AsyncIO 调度
async def main():
    obs = Observable.of(1, 2, 3).subscribe_on(Scheduler.asyncio())
    obs.subscribe(lambda x: print(f"Async: {x}"))

asyncio.run(main())
```
