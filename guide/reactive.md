# vools 响应式编程（v0.1.18）

`vools.reactive` 是一个功能完整的响应式编程框架，提供 `Observable`、`Subject`、丰富的操作符，以及对键盘、鼠标、剪贴板、文件系统的响应式监控。

> Python 3.9+ 支持

---

## 模块结构

`vools.reactive` 采用模块化设计，分为三个子包：

```
vools/reactive/
├── core/          # 基础核心：Observable、Subject、BehaviorSubject、ReplaySubject
├── monitoring/    # 监控类：KeySubject、MouseSubject、ClipSubject、FileSubject、FolderSubject
└── operators/     # 操作符：ops 命名空间
```

所有符号通过 `vools.reactive` 统一导出，保持 API 兼容性。

---

## 1. 基本用法

### Observable

`Observable` 是响应式流的核心：数据源通过 `on_next` 发射事件，通过 `on_error` 报告错误，通过 `on_completed` 标志结束。

```python
from vools.reactive import Observable, ops

# 从可迭代对象创建
obs = Observable.from_iterable([1, 2, 3])

# 订阅
obs.subscribe(
    on_next=lambda x: print(f"Next: {x}"),
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Completed"),
)
# Next: 1
# Next: 2
# Next: 3
# Completed
```

### 创建操作符

```python
# 从可迭代对象创建
obs = Observable.from_iterable([1, 2, 3])

# 单个值
obs = Observable.just(42)

# 多个值
obs = Observable.of(1, 2, 3)

# 空序列
obs = Observable.empty()

# 无限序列：每秒发射一个递增整数
obs = Observable.interval(1.0)

# 延迟创建
obs = Observable.defer(lambda: Observable.just(42))
```

### 管道操作

`pipe` 允许将多个操作符按顺序组合：

```python
from vools.reactive import Observable, ops

result = []
Observable.from_iterable(range(10)) \
    .pipe(
        ops.filter(lambda x: x > 5),
        ops.map(lambda x: x * 10),
    ) \
    .subscribe(on_next=result.append)
print(result)   # [60, 70, 80, 90]
```

---

## 2. 转换操作符

### map

```python
result = []
Observable.from_iterable([1, 2, 3]) \
    .pipe(ops.map(lambda x: x * 2)) \
    .subscribe(on_next=result.append)
# result: [2, 4, 6]
```

### flat_map

`flat_map` 会把每个元素转换为新的 `Observable`，然后把所有流合并：

```python
result = []
Observable.from_iterable([1, 2, 3]) \
    .pipe(ops.flat_map(lambda x: Observable.from_iterable([x, x * 10]))) \
    .subscribe(on_next=result.append)
# result: [1, 10, 2, 20, 3, 30]
```

### scan

`scan` 累积每一步的中间结果：

```python
result = []
Observable.from_iterable([1, 2, 3]) \
    .pipe(ops.scan(lambda acc, x: acc + x, 0)) \
    .subscribe(on_next=result.append)
# result: [1, 3, 6]
```

---

## 3. 过滤操作符

```python
# filter
Observable.from_iterable(range(10)) \
    .pipe(ops.filter(lambda x: x % 2 == 0)) \
    .subscribe(on_next=print)
# 0 2 4 6 8

# take — 取前 n 个
Observable.from_iterable(range(10)) \
    .pipe(ops.take(3)) \
    .subscribe(on_next=print)
# 0 1 2

# skip — 跳过前 n 个
Observable.from_iterable(range(10)) \
    .pipe(ops.skip(7)) \
    .subscribe(on_next=print)
# 7 8 9

# distinct — 去重
Observable.from_iterable([1, 2, 2, 3, 3, 3]) \
    .pipe(ops.distinct()) \
    .subscribe(on_next=print)
# 1 2 3
```

---

## 4. 组合操作符

```python
from vools.reactive import Observable, ops

obs1 = Observable.from_iterable([1, 2, 3])
obs2 = Observable.from_iterable(["a", "b", "c"])

# zip — 按位置配对
result = []
Observable.zip(obs1, obs2).subscribe(on_next=result.append)
# result: [(1, 'a'), (2, 'b'), (3, 'c')]

# merge — 按时间合并
result = []
Observable.merge(obs1, obs2).subscribe(on_next=result.append)
# result: [1, 'a', 2, 'b', 3, 'c']
```

---

## 5. Subject

`Subject` 既是 `Observable`（可以被订阅）也是观察者（可以手动发射事件），常用于跨模块的事件总线。

```python
from vools.reactive import Subject, BehaviorSubject, ReplaySubject

# 基础 Subject
subject = Subject()
subject.subscribe(on_next=lambda x: print(f"sub1: {x}"))
subject.on_next(1)   # sub1: 1
subject.on_next(2)   # sub1: 2

# BehaviorSubject — 保留最新值，新订阅者立即收到
bs = BehaviorSubject(0)
bs.subscribe(on_next=lambda x: print(f"bs1: {x}"))  # bs1: 0
bs.on_next(1)                                         # bs1: 1
bs.on_next(2)                                         # bs1: 2
bs.subscribe(on_next=lambda x: print(f"bs2: {x}"))  # bs2: 2

# ReplaySubject — 重放最近 n 个事件
rs = ReplaySubject(2)
rs.on_next(1)
rs.on_next(2)
rs.on_next(3)
rs.subscribe(on_next=lambda x: print(f"rs: {x}"))
# rs: 2
# rs: 3
```

---

## 6. 错误处理

```python
# catch — 捕获错误，切换到备用流
result = []
Observable.throw(ValueError("oops")) \
    .pipe(ops.catch(lambda e: Observable.just("recovered"))) \
    .subscribe(on_next=result.append)
# result: ['recovered']

# retry — 失败后重试
result = []
Observable.throw(ValueError("oops")) \
    .pipe(ops.retry(3)) \
    .subscribe(on_next=result.append, on_error=lambda e: print(f"finally: {e}"))
```

---

## 7. 响应式监控模块（Windows）

`vools.reactive` 提供对键盘、鼠标、剪贴板、文件系统的监控支持，所有监控模块都是 `Subject` 的子类，可直接用操作符组合。

> 监控类模块当前只在 **Windows** 下可用。

### 键盘监控

```python
from vools.reactive import KeySubject

with KeySubject(backend="polling") as ks:
    ks.subscribe(on_next=lambda kd: print(f"key: {kd}"))
    # 持续监控键盘事件
```

### 鼠标监控

```python
from vools.reactive import MouseSubject

with MouseSubject(backend="polling") as ms:
    ms.subscribe(on_next=lambda md: print(f"mouse: {md.x}, {md.y}"))
```

### 剪贴板监控

```python
from vools.reactive import ClipSubject

with ClipSubject(filter_self=True) as cs:
    cs.subscribe(on_next=lambda cd: print(f"clipboard: {cd.content}"))
    # filter_self=True 时自动忽略本进程写入剪贴板的内容
```

### 文件系统监控

```python
from vools.reactive import FileSubject

with FileSubject(paths=["./watch_dir"], backend="polling") as fs:
    fs.subscribe(on_next=lambda fd: print(f"{fd.path} {fd.change_type}"))
    # change_type 可能是 created / modified / deleted / renamed
```

### 目录监控

```python
from vools.reactive import FolderSubject

with FolderSubject(paths=["./watch_dir"], backend="polling") as f:
    f.subscribe(on_next=lambda fd: print(f"folder: {fd.path}"))
```

---

## 8. 导入位置速查

| 名称 | 导入位置 | 说明 |
|------|----------|------|
| `Observable` | `from vools.reactive import Observable` | 基础可观察序列 |
| `Subject` | `from vools.reactive import Subject` | 基础主题（事件总线） |
| `BehaviorSubject` | `from vools.reactive import BehaviorSubject` | 保留最新值 |
| `ReplaySubject` | `from vools.reactive import ReplaySubject` | 重放历史值 |
| `ops` | `from vools.reactive import ops` | 操作符命名空间 |
| `KeySubject` | `from vools.reactive import KeySubject` | 键盘监控（Windows） |
| `MouseSubject` | `from vools.reactive import MouseSubject` | 鼠标监控（Windows） |
| `ClipSubject` | `from vools.reactive import ClipSubject` | 剪贴板监控（Windows） |
| `FileSubject` | `from vools.reactive import FileSubject` | 文件监控（Windows） |
| `FolderSubject` | `from vools.reactive import FolderSubject` | 目录监控（Windows） |
