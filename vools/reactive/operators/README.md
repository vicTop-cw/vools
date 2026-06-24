# vools.reactive.operators — 操作符集合

响应式操作符，包括标准操作符、扩展操作符和统计操作符，用于转换、过滤、组合和处理 Observable 流。

## 操作符分类

### 标准操作符

`map`, `filter`, `flat_map`, `take`, `skip`, `debounce`, `throttle_first`, `merge`, `concat`, `zip`, `combine_latest`, `reduce`, `scan`, `distinct_until_changed`

### 扩展操作符

`from_range`, `from_callable`, `window`, `switch`, `cache`, `parallel`, `retry_with_backoff`, `circuit_breaker`, `buffer`, `group_by`, `tap`

### 统计操作符

`median`, `variance`, `std`, `quantile`, `rolling_sum`, `rolling_mean`, `cum_sum`, `top_k`, `bottom_k`, `sort`, `arg_min`, `arg_max`

### 监控操作符

连接 `vools.reactive.monitoring` 的桥接操作符。

## 使用示例

### 基础操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import map, filter, take

# 链式调用操作符
result = []
Observable.from_iterable(range(10)).pipe(
    filter(lambda x: x % 2 == 0),
    map(lambda x: x * 2),
    take(3)
).subscribe(lambda x: result.append(x))
# result: [0, 4, 8]
```

### 组合操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import merge, zip, combine_latest

# merge - 合并多个 Observable
obs1 = Observable.of(1, 2, 3)
obs2 = Observable.of(4, 5, 6)
merged = obs1.pipe(merge(obs2))
# 输出: 1, 2, 3, 4, 5, 6 （顺序取决于发射时机）

# zip - 配对组合
obs1 = Observable.of(1, 2, 3)
obs2 = Observable.of('a', 'b', 'c')
zipped = obs1.pipe(zip(obs2))
# 输出: (1, 'a'), (2, 'b'), (3, 'c')
```

### 聚合操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import reduce, scan, sum, average

# reduce - 归约
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    reduce(lambda acc, x: acc + x, 0)
).subscribe(lambda x: result.append(x))
# result: [15]

# scan - 扫描（每次累积都发射）
result = []
Observable.from_iterable([1, 2, 3, 4, 5]).pipe(
    scan(lambda acc, x: acc + x, 0)
).subscribe(lambda x: result.append(x))
# result: [1, 3, 6, 10, 15]
```

### 过滤操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import filter, take, skip, distinct_until_changed, first

# filter - 过滤
Observable.from_iterable(range(10)).pipe(
    filter(lambda x: x > 5)
).subscribe(print)
# 输出: 6, 7, 8, 9

# take/skip - 截取
Observable.from_iterable(range(10)).pipe(
    skip(3),
    take(4)
).subscribe(print)
# 输出: 3, 4, 5, 6

# distinct_until_changed - 去重（相邻相同）
Observable.of(1, 1, 2, 2, 3, 1).pipe(
    distinct_until_changed()
).subscribe(print)
# 输出: 1, 2, 3, 1
```

### 统计操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import median, variance, std, top_k, rolling_mean

# 统计操作符
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# 中位数
Observable.from_iterable(data).pipe(
    median()
).subscribe(lambda x: print(f"Median: {x}"))
# 输出: Median: 5.5

# 标准差
Observable.from_iterable(data).pipe(
    std()
).subscribe(lambda x: print(f"Std: {x}"))

# Top K
Observable.from_iterable(data).pipe(
    top_k(3)
).subscribe(lambda x: print(f"Top 3: {x}"))
# 输出: Top 3: [10, 9, 8]
```

### 错误处理操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import catch, retry, retry_with_backoff, on_error_return

# catch - 捕获错误
Observable.throw_error(ValueError("oops")).pipe(
    catch(lambda e: Observable.of("recovered"))
).subscribe(print)
# 输出: recovered

# retry - 重试
Observable.create(lambda observer: ...).pipe(
    retry(3)  # 最多重试 3 次
).subscribe(print)

# on_error_return - 出错时返回默认值
Observable.throw_error(RuntimeError("fail")).pipe(
    on_error_return("default")
).subscribe(print)
# 输出: default
```

### 工具操作符

```python
from vools.reactive import Observable
from vools.reactive.operators import tap, delay, buffer, to_list

# tap - 副作用（不改变流）
Observable.of(1, 2, 3).pipe(
    tap(lambda x: print(f"Logging: {x}")),
    map(lambda x: x * 2)
).subscribe()
# 输出:
# Logging: 1
# Logging: 2
# Logging: 3

# to_list - 收集为列表
result = []
Observable.from_iterable(range(5)).pipe(
    to_list()
).subscribe(lambda x: result.append(x))
# result: [[0, 1, 2, 3, 4]]
```
