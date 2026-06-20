# 响应式模块

vools.reactive 是一个功能完整的响应式编程框架，实现了 Rx 4.0 规范的所有操作符，并提供创新的自定义功能。

## 目录

- [核心类](#核心类)
  - [Observable](#observable)
  - [Subject](#subject)
  - [调度器](#调度器)
- [创建操作符](#创建操作符)
- [转换操作符](#转换操作符)
- [过滤操作符](#过滤操作符)
- [组合操作符](#组合操作符)
- [数学操作符](#数学操作符)
- [错误处理操作符](#错误处理操作符)
- [背压操作符](#背压操作符)
- [统计操作符](#统计操作符)
- [监控模块](#监控模块)
- [最佳实践](#最佳实践)

---

## 核心类

### Observable

响应式编程的核心类，代表一个可观察的数据流。

**创建方式：**

```python
from vools.reactive import Observable, of, from_iterable

# 从可迭代对象创建
obs = from_iterable([1, 2, 3])

# 创建单个值序列
obs = of(1, 2, 3)

# 创建发出单个值
obs = Observable.just(42)

# 创建空序列
obs = Observable.empty()

# 创建错误序列
obs = Observable.throw(Exception("error"))

# 创建无限序列
obs = Observable.interval(1.0)  # 每秒发射一个值

# 创建定时序列
obs = Observable.timer(0.5, 1.0)  # 0.5秒后开始，每秒发射

# 延迟创建
obs = Observable.defer(lambda: Observable.just(42))

# 创建范围序列
obs = Observable.from_range(5)      # 0, 1, 2, 3, 4
obs = Observable.from_range(2, 6)   # 2, 3, 4, 5
obs = Observable.from_range(0, 10, 2)  # 0, 2, 4, 6, 8
```

**订阅方式：**

```python
# 基本订阅
obs.subscribe(
    on_next=lambda x: print(f"Next: {x}"),
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Completed")
)

# 使用管道操作
obs.pipe(
    filter(lambda x: x > 1),
    map(lambda x: x * 2)
).subscribe(on_next=print)

# 使用 Subscription 上下文管理器
with obs.subscribe(on_next=print) as sub:
    # 自动清理
    pass
```

---

### Subject

Subject 是同时充当 Observable 和 Observer 的特殊类型。

```python
from vools.reactive import Subject, BehaviorSubject, ReplaySubject, AsyncSubject, PublishSubject

# Subject - 基础主题，发射所有后续值
subject = Subject()
subject.subscribe(on_next=print)
subject.on_next(1)  # 1
subject.on_next(2)  # 2

# BehaviorSubject - 保留最新值，新订阅者立即收到最新值
subject = BehaviorSubject(0)  # 默认值
subject.subscribe(on_next=print)  # 立即收到 0
subject.on_next(1)  # 1

# ReplaySubject - 重放历史值，新订阅者收到历史值
subject = ReplaySubject(2)  # 保留最近2个值
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)
subject.subscribe(on_next=print)  # 2, 3

# AsyncSubject - 只发射最后一个值，在完成时
subject = AsyncSubject()
subject.on_next(1)
subject.on_next(2)
subject.on_next(3)
subject.on_completed()
subject.subscribe(on_next=print)  # 3

# PublishSubject - 发射订阅后的值
subject = PublishSubject()
```

---

### 调度器

调度器控制订阅何时何地发生。

```python
from vools.reactive import (
    Scheduler, ImmediateScheduler, CurrentThreadScheduler,
    AsyncIOScheduler, ThreadPoolScheduler, NewThreadScheduler,
    immediate, current_thread, asyncio_scheduler,
    thread_pool_scheduler, new_thread_scheduler
)

# 立即调度
obs = Observable.interval(0.1).pipe(
    observe_on(immediate_scheduler)
)

# 当前线程调度
obs = Observable.interval(0.1).pipe(
    observe_on(current_thread_scheduler)
)

# 线程池调度
obs = Observable.interval(0.1).pipe(
    subscribe_on(thread_pool_scheduler)
)

# 新线程调度
obs = Observable.interval(0.1).pipe(
    subscribe_on(new_thread_scheduler)
)

# AsyncIO 调度器
obs = Observable.interval(0.1).pipe(
    subscribe_on(asyncio_scheduler)
)
```

---

## 创建操作符

```python
from vools.reactive import of, from_iterable, Observable

# 创建发出固定值
of(1, 2, 3)

# 从可迭代对象创建
from_iterable([1, 2, 3])

# 创建范围
Observable.from_range(5)      # 0, 1, 2, 3, 4
Observable.from_range(2, 6)   # 2, 3, 4, 5
Observable.from_range(0, 10, 2)  # 0, 2, 4, 6, 8

# 从 Callable 创建
from_callable(lambda: time.time())

# 从 Future 创建
from_future(some_future)

# start - 创建发出函数返回值的 Observable
start(lambda: "result")
```

---

## 转换操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable([1, 2, 3])

# map - 映射
obs.pipe(ops.map(lambda x: x * 2)).subscribe(print)  # 2, 4, 6

# flat_map / merge_map - 扁平化映射
obs.pipe(ops.flat_map(lambda x: Observable.from_iterable([x, x*10])))
# 1, 10, 2, 20, 3, 30

# concat_map - 顺序扁平化映射
obs.pipe(ops.concat_map(lambda x: Observable.from_iterable([x, x*10])))
# 按顺序发射

# switch_map - 切换到最新的内部 Observable
obs.pipe(ops.switch_map(lambda x: some_observable))

# scan - 累积扫描
obs.pipe(ops.scan(lambda acc, x: acc + x, 0)).subscribe(print)  # 1, 3, 6

# window - 窗口化
obs.pipe(ops.window(2))  # 将项目分组为 Observable 窗口

# flat_map_latest - 只处理最新的内部 Observable
obs.pipe(ops.flat_map_latest(lambda x: some_observable))
```

---

## 过滤操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable(range(10))

# filter - 过滤
obs.pipe(ops.filter(lambda x: x % 2 == 0)).subscribe(print)  # 0, 2, 4, 6, 8

# take - 取前 N 个
obs.pipe(ops.take(3)).subscribe(print)  # 0, 1, 2

# skip - 跳过前 N 个
obs.pipe(ops.skip(5)).subscribe(print)  # 5, 6, 7, 8, 9

# take_while - 条件为真时取
obs.pipe(ops.take_while(lambda x: x < 5)).subscribe(print)  # 0, 1, 2, 3, 4

# skip_while - 条件为真时跳过
obs.pipe(ops.skip_while(lambda x: x < 5)).subscribe(print)  # 5, 6, 7, 8, 9

# take_until - 直到条件满足时停止
obs.pipe(ops.take_until(lambda x: x == 5)).subscribe(print)

# skip_until - 直到条件满足时开始
obs.pipe(ops.skip_until(lambda x: x == 5)).subscribe(print)

# distinct - 去重
obs = Observable.from_iterable([1, 2, 2, 3, 3, 3])
obs.pipe(ops.distinct()).subscribe(print)  # 1, 2, 3

# distinct_until_changed - 连续重复值去重
obs = Observable.from_iterable([1, 1, 2, 2, 2, 3])
obs.pipe(ops.distinct_until_changed()).subscribe(print)  # 1, 2, 3

# debounce - 防抖
obs.pipe(ops.debounce(0.5)).subscribe(print)

# throttle_first - 节流（取第一个）
obs.pipe(ops.throttle_first(1.0)).subscribe(print)

# sample - 采样
obs.pipe(ops.sample(1.0)).subscribe(print)

# skip_last - 跳过最后 N 个
obs.pipe(ops.skip_last(2)).subscribe(print)

# take_last - 只取最后 N 个
obs.pipe(ops.take_last(2)).subscribe(print)

# first / last - 取第一个/最后一个
obs.pipe(ops.first()).subscribe(print)
obs.pipe(ops.last()).subscribe(print)

# element_at - 取指定位置元素
obs.pipe(ops.element_at(2)).subscribe(print)

# ignore_elements - 忽略所有元素
obs.pipe(ops.ignore_elements()).subscribe(print)
```

---

## 组合操作符

```python
from vools.reactive import Observable, ops

obs1 = Observable.from_iterable([1, 2, 3])
obs2 = Observable.from_iterable(['a', 'b', 'c'])

# merge - 合并多个 Observable
Observable.merge(obs1, obs2).subscribe(print)  # 1, 'a', 2, 'b', 3, 'c'

# concat - 连接多个 Observable（按顺序）
Observable.concat(obs1, obs2).subscribe(print)

# zip - 拉链组合
Observable.zip(obs1, obs2).subscribe(print)  # (1, 'a'), (2, 'b'), (3, 'c')

# combine_latest - 组合最新值
obs1.pipe(ops.combine_latest(obs2)).subscribe(print)

# with_latest_from - 获取另一个 Observable 的最新值
obs1.pipe(ops.with_latest_from(obs2)).subscribe(print)

# amb - 选择第一个发出项目的 Observable
Observable.amb(obs1, obs2).subscribe(print)

# switch - 切换到最新的 Observable
obs.pipe(ops.switch()).subscribe(print)

# race - 竞速，最快发射的 Observable 获胜
Observable.race(obs1, obs2).subscribe(print)

# pairwise - 成对发射
obs.pipe(ops.pairwise()).subscribe(print)

# partition - 分区
even, odd = obs.pipe(ops.partition(lambda x: x % 2 == 0))
```

---

## 数学操作符

```python
from vools.reactive import Observable, ops

obs = Observable.from_iterable([1, 2, 3, 4, 5])

# reduce - 聚合
obs.pipe(ops.reduce(lambda acc, x: acc + x, 0)).subscribe(print)  # 15

# count - 计数
obs.pipe(ops.count()).subscribe(print)  # 5

# sum - 求和
obs.pipe(ops.sum()).subscribe(print)  # 15

# average - 平均值
obs.pipe(ops.average()).subscribe(print)  # 3.0

# minimum / maximum - 最小/最大值
obs.pipe(ops.minimum()).subscribe(print)
obs.pipe(ops.maximum()).subscribe(print)

# all / any - 全部/任一满足条件
obs.pipe(ops.all(lambda x: x > 0)).subscribe(print)  # True
obs.pipe(ops.any(lambda x: x > 4)).subscribe(print)  # True

# contains - 是否包含
obs.pipe(ops.contains(3)).subscribe(print)  # True

# is_empty - 是否为空
obs.pipe(ops.is_empty()).subscribe(print)  # False

# to_list - 转为列表
obs.pipe(ops.to_list()).subscribe(print)  # [1, 2, 3, 4, 5]

# to_map - 转为字典
obs.pipe(ops.to_map(lambda x: (x, x*2))).subscribe(print)  # {1: 2, 2: 4, ...}

# to_set - 转为集合
obs.pipe(ops.to_set()).subscribe(print)  # {1, 2, 3, 4, 5}
```

---

## 错误处理操作符

```python
from vools.reactive import Observable, ops

# catch - 捕获错误
Observable.throw(Exception("error")).pipe(
    ops.catch(lambda e: Observable.just("recovered"))
).subscribe(on_next=print)  # "recovered"

# retry - 重试
Observable.throw(Exception("error")).pipe(
    ops.retry(3)
).subscribe(on_error=lambda e: print(f"Failed after 3 retries"))

# retry_with_backoff - 带退避的重试（创新功能）
Observable.throw(Exception('err')).pipe(
    ops.retry_with_backoff(max_retries=5, initial_delay=1.0, multiplier=2.0)
).subscribe(on_error=lambda e: print(f'Failed: {e}'))

# on_error_return - 错误时返回默认值
Observable.throw(Exception("error")).pipe(
    ops.on_error_return("default")
).subscribe(print)  # "default"

# on_error_resume_next - 错误时切换到另一个 Observable
Observable.throw(Exception("error")).pipe(
    ops.on_error_resume_next(Observable.just("fallback"))
).subscribe(print)  # "fallback"

# retry_when - 条件重试
```

---

## 背压操作符

背压操作符用于处理数据流过快的情况。

```python
from vools.reactive import Observable, ops

# backpressure_buffer - 缓冲
obs.pipe(ops.backpressure_buffer(max_size=100)).subscribe(print)

# backpressure_drop - 丢弃
obs.pipe(ops.backpressure_drop()).subscribe(print)

# backpressure_error - 超限时错误
obs.pipe(ops.backpressure_error(max_size=10)).subscribe(print)

# backpressure_latest - 只保留最新
obs.pipe(ops.backpressure_latest()).subscribe(print)

# circuit_breaker - 断路器模式（创新功能）
Observable.from_iterable(data).pipe(
    ops.circuit_breaker(threshold=5, reset_timeout=60.0)
).subscribe(on_next=process)
```

---

## 统计操作符

提供丰富的统计聚合和数据分析操作符。

### 统计聚合

```python
from vools.reactive import Observable

# 中位数
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    median()
).subscribe(print)  # 3.0

# 方差
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    variance()
).subscribe(print)

# 标准差
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    std()
).subscribe(print)

# 分位数
Observable.from_iterable(range(1, 11)).pipe(
    quantile(0.5)
).subscribe(print)  # 5.5

# 最小值索引
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    arg_min()
).subscribe(print)  # 3

# 最大值索引
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    arg_max()
).subscribe(print)  # 4

# 唯一值计数
Observable.from_iterable([1, 2, 2, 3, 3, 3]).pipe(
    n_unique()
).subscribe(print)  # 3
```

### 滚动窗口

```python
# 滚动求和（窗口大小为3）
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    rolling_sum(3)
).subscribe(print)  # 1, 3, 6, 9, 12

# 滚动最小值
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    rolling_min(3)
).subscribe(print)  # 5, 3, 3, 1, 1

# 滚动最大值
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    rolling_max(3)
).subscribe(print)  # 5, 5, 8, 8, 9

# 滚动均值
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    rolling_mean(3)
).subscribe(print)  # 1.0, 1.5, 2.0, 3.0, 4.0
```

### 累积变换

```python
# 累积求和
Observable.from_iterable([1, 2, 3, 4]).pipe(
    cum_sum()
).subscribe(print)  # 1, 3, 6, 10

# 累积最小值
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    cum_min()
).subscribe(print)  # 5, 3, 3, 1, 1

# 累积最大值
Observable.from_iterable([5, 3, 8, 1, 9]).pipe(
    cum_max()
).subscribe(print)  # 5, 5, 8, 8, 9

# 累积均值
Observable.from_iterable([1, 2, 3, 4]).pipe(
    cum_mean()
).subscribe(print)  # 1.0, 1.5, 2.0, 2.5

# 累积乘积
Observable.from_iterable([1, 2, 3, 4]).pipe(
    cum_prod()
).subscribe(print)  # 1, 2, 6, 24
```

### 排序 Top-N

```python
# 排序
Observable.from_iterable([3, 1, 4, 2]).pipe(
    sort()
).subscribe(print)  # 1, 2, 3, 4

# 降序排序
Observable.from_iterable([3, 1, 4, 2]).pipe(
    sort(reverse=True)
).subscribe(print)  # 4, 3, 2, 1

# Top-K（最大 k 个）
Observable.from_iterable([5, 3, 8, 1, 9, 2]).pipe(
    top_k(3)
).subscribe(print)  # 9, 8, 5

# Bottom-K（最小 k 个）
Observable.from_iterable([5, 3, 8, 1, 9, 2]).pipe(
    bottom_k(3)
).subscribe(print)  # 1, 2, 3
```

### 其他工具

```python
# 过滤 None 值
Observable.from_iterable([1, None, 2, None, 3]).pipe(
    drop_none()
).subscribe(print)  # 1, 2, 3

# 填充 None 值
Observable.from_iterable([1, None, 2, None, 3]).pipe(
    fill_none(0)
).subscribe(print)  # 1, 0, 2, 0, 3

# 绝对值
Observable.from_iterable([-1, 2, -3, 4]).pipe(
    abs()
).subscribe(print)  # 1.0, 2.0, 3.0, 4.0

# 值域限制
Observable.from_iterable([-1, 2, 5, 8]).pipe(
    clamp(0, 5)
).subscribe(print)  # 0.0, 2.0, 5.0, 5.0

# 展开嵌套列表
Observable.from_iterable([[1, 2], [3, 4], [5]]).pipe(
    explode()
).subscribe(print)  # 1, 2, 3, 4, 5
```

---

## 监控模块

vools.reactive 提供了完整的系统监控能力。

### 键盘监控

```python
from vools.reactive import KeySubject, KeyObserver, from_keyboard

# 创建键盘监控
obs, disp = from_keyboard(backend="polling")

# 使用 KeySubject
with KeySubject(backend="polling") as ks:
    received = []
    ks.subscribe(on_next=lambda kd: received.append(kd))

# 使用 KeyObserver 按事件类型路由
ko = KeyObserver(
    on_press=lambda kd: print(f"Press: {kd.key_name}"),
    on_release=lambda kd: print(f"Release: {kd.key_name}"),
)
ko.attach(ks)
```

### 鼠标监控

```python
from vools.reactive import MouseSubject, MouseObserver, from_mouse

# 创建鼠标监控
obs, disp = from_mouse(backend="polling")

# 使用 MouseSubject
with MouseSubject(backend="polling") as ms:
    ms.subscribe(on_next=lambda md: print(f"Mouse: {md.x}, {md.y}"))

# 使用 MouseObserver 路由
mo = MouseObserver(
    on_move=lambda md: print(f"Move: {md.x}, {md.y}"),
    on_click=lambda md: print(f"Click: {md.button}"),
    on_scroll=lambda md: print(f"Scroll: {md.delta}"),
)
mo.attach(ms)
```

### 剪贴板监控

```python
from vools.reactive import ClipSubject, ClipObserver, from_clipboard, write_to_clipboard

# 创建剪贴板监控
obs, disp = from_clipboard()

# 使用 ClipSubject
with ClipSubject(backend="polling") as cs:
    cs.subscribe(on_next=lambda cd: print(f"Clipboard: {cd.content}"))

# 使用 ClipObserver 按内容类型路由
co = ClipObserver(
    on_text=lambda cd: print(f"Text: {cd.content}"),
    on_files=lambda cd: print(f"Files: {cd.files}"),
    on_image=lambda cd: print(f"Image: {len(cd.content)} bytes"),
)
co.attach(cs)

# 写入剪贴板
write_to_clipboard("Hello World")
```

### 文件系统监控

```python
from vools.reactive import FileSubject, FileObserver, from_filesystem, write_to_filesystem

# 创建文件监控
obs, disp = from_filesystem(paths=["/path/to/watch"], backend="polling")

# 使用 FileSubject
with FileSubject(paths=["/path"], backend="polling") as fs:
    fs.subscribe(on_next=lambda fd: print(f"File: {fd.path} {fd.change_type}"))

# 使用 FileObserver 按变更类型路由
fo = FileObserver(
    on_created=lambda fd: print(f"Created: {fd.path}"),
    on_modified=lambda fd: print(f"Modified: {fd.path}"),
    on_deleted=lambda fd: print(f"Deleted: {fd.path}"),
    on_renamed=lambda fd: print(f"Renamed: {fd.old_path} -> {fd.path}"),
)
fo.attach(fs)
```

### 目录监控

```python
from vools.reactive import FolderSubject, FolderObserver, from_foldersystem

# 创建目录监控
obs, disp = from_foldersystem(paths=["/path/to/watch"], backend="polling")

# 使用 FolderSubject
with FolderSubject(paths=["/path"], backend="polling") as fs:
    fs.subscribe(on_next=lambda fd: print(f"Folder: {fd.path}"))

# 使用 FolderObserver 路由
fo = FolderObserver(
    on_folder_created=lambda fd: print(f"Folder created: {fd.path}"),
    on_folder_deleted=lambda fd: print(f"Folder deleted: {fd.path}"),
)
fo.attach(fs)
```

---

## 最佳实践

### 1. 及时取消订阅

```python
# 使用 Subscription 取消订阅
sub = obs.subscribe(on_next=print)
sub.unsubscribe()

# 使用上下文管理器自动清理
with obs.subscribe(on_next=print) as sub:
    # 操作完成后自动取消订阅
    pass
```

### 2. 使用管道操作符组合

```python
# 推荐：使用管道组合操作符
obs.pipe(
    ops.filter(lambda x: x > 0),
    ops.map(lambda x: x * 2),
    ops.take(10)
).subscribe(on_next=print)

# 不推荐：链式调用（某些场景下仍可用）
obs.pipe(ops.filter("_ > 0")).pipe(ops.map("x * 2"))
```

### 3. 错误处理

```python
# 始终添加错误处理
obs.subscribe(
    on_next=print,
    on_error=lambda e: print(f"Error: {e}"),
    on_completed=lambda: print("Done")
)

# 使用错误处理操作符
obs.pipe(
    ops.retry(3),
    ops.on_error_return("fallback")
).subscribe(
    on_next=print,
    on_error=lambda e: print(f"Final error: {e}")
)
```

### 4. 背压处理

```python
# 高频数据源使用背压操作符
high_freq_obs.pipe(
    ops.backpressure_drop()  # 或 backpressure_buffer, backpressure_latest
).subscribe(on_next=process)
```

### 5. 资源管理

```python
# 监控模块使用上下文管理器
with KeySubject(backend="polling") as ks:
    ks.subscribe(on_next=handle_key)
    # 自动清理资源
    pass
```

### 6. 性能优化

```python
# 使用 cache 操作符缓存发射值
obs.pipe(
    ops.cache(duration=5.0, max_size=100)
).subscribe(on_next=print)

# 使用 parallel 操作符并行处理
obs.pipe(
    ops.parallel(max_concurrent=4)
).subscribe(on_next=heavy_process)
```
