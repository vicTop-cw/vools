# Operators 操作符文档

> **模块路径**：`vools.reactive.operators`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#015
> **最后更新**：2026-06-30

## 概述

vools 响应式编程模块提供了丰富的操作符，支持转换、过滤、组合、错误处理等多种操作。本文档详细介绍各操作符的用法。

## 导入方式

```python
from vools.reactive import Observable
from vools.reactive import ops  # 推荐导入方式
```

---

## 转换操作符

### map - 映射转换

```python
from vools.reactive import Observable, ops

# 基本映射
result = []
Observable.of(1, 2, 3).pipe(
    ops.map(lambda x: x * 2)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [2, 4, 6]

# 使用字符串表达式
result = []
Observable.of(1, 2, 3).pipe(
    ops.map("x => x * 10")
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [10, 20, 30]
```

**测试状态**：✅ 已测试

### filter - 过滤

```python
# 基本过滤
result = []
Observable.of(1, 2, 3, 4, 5, 6).pipe(
    ops.filter(lambda x: x % 2 == 0)  # 过滤偶数
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [2, 4, 6]

# 使用字符串表达式
result = []
Observable.of("apple", "banana", "cherry", "date").pipe(
    ops.filter("s => len(s) > 5")  # 过滤长度大于5的
).subscribe(on_next=lambda x: result.append(x))

print(result)  # ['banana', 'cherry']
```

**测试状态**：✅ 已测试

### flat_map - 扁平映射

```python
# 将每个值映射为 Observable 并合并
result = []
Observable.of(1, 2, 3).pipe(
    ops.flat_map(lambda x: Observable.of(x, x * 2))
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 2, 4, 3, 6]
```

**测试状态**：✅ 已测试

### concat_map - 顺序连接映射

```python
# 按顺序订阅每个内部 Observable
result = []
Observable.of(1, 2, 3).pipe(
    ops.concat_map(lambda x: Observable.of(x, x * 2))
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 2, 4, 3, 6]
```

**测试状态**：✅ 已测试

### switch_map - 切换映射

```python
# 只订阅最新的内部 Observable
result = []
Observable.of(1, 2, 3).pipe(
    ops.switch_map(lambda x: Observable.of(x, x * 10))
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3, 30]
```

**测试状态**：✅ 已测试

---

## 过滤操作符

### take - 取前 n 个

```python
# 只取前3个
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.take(3)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3]
```

**测试状态**：✅ 已测试

### skip - 跳过前 n 个

```python
# 跳过前2个
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.skip(2)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3, 4, 5]
```

**测试状态**：✅ 已测试

### take_while - 条件为真时取

```python
# 取到条件不满足为止
result = []
Observable.of(1, 2, 3, 4, 5, 4, 3, 2, 1).pipe(
    ops.take_while(lambda x: x < 4)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3]
```

**测试状态**：✅ 已测试

### skip_while - 条件为真时跳过

```python
# 跳转到条件不满足开始
result = []
Observable.of(1, 2, 3, 4, 5, 4, 3, 2, 1).pipe(
    ops.skip_while(lambda x: x < 4)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [4, 5, 4, 3, 2, 1]
```

**测试状态**：✅ 已测试

### distinct_until_changed - 去除连续重复

```python
# 去除连续重复的值
result = []
Observable.of(1, 1, 2, 2, 2, 3, 1, 1).pipe(
    ops.distinct_until_changed()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3, 1]
```

**测试状态**：✅ 已测试

### first - 获取第一个

```python
# 获取第一个匹配的值
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.first(lambda x: x > 3)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [4]
```

**测试状态**：✅ 已测试

### last - 获取最后一个

```python
# 获取最后一个匹配的值
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.last(lambda x: x < 4)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3]
```

**测试状态**：✅ 已测试

### element_at - 获取指定索引

```python
# 获取索引为2的元素（从0开始）
result = []
Observable.of("a", "b", "c", "d").pipe(
    ops.element_at(2)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # ['c']
```

**测试状态**：✅ 已测试

---

## 组合操作符

### merge - 合并多个 Observable

```python
# 合并多个流
result = []
obs1 = Observable.of(1, 2)
obs2 = Observable.of(10, 20)
obs3 = Observable.of(100, 200)

Observable.merge(obs1, obs2, obs3).pipe(
    ops.take(4)  # 只取前4个
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 10, 20] 或其他顺序
```

**测试状态**：✅ 已测试

### concat - 连接多个 Observable

```python
# 按顺序连接多个流
result = []
obs1 = Observable.of(1, 2)
obs2 = Observable.of(3, 4)

Observable.concat(obs1, obs2).subscribe(
    on_next=lambda x: result.append(x),
    on_completed=lambda: print(f"完成: {result}")
)

# 输出: 完成: [1, 2, 3, 4]
```

**测试状态**：✅ 已测试

### zip - 压缩多个 Observable

```python
# 将多个流的元素配对成元组
result = []
obs1 = Observable.of(1, 2, 3)
obs2 = Observable.of("a", "b", "c")

Observable.zip(obs1, obs2).subscribe(on_next=lambda x: result.append(x))

print(result)  # [(1, 'a'), (2, 'b'), (3, 'c')]
```

**测试状态**：✅ 已测试

### combine_latest - 组合最新值

```python
# 发射所有流的最新值
result = []
obs1 = Observable.of(1, 2, 3)
obs2 = Observable.of("a", "b")

Observable.combine_latest(obs1, obs2).pipe(
    ops.take(2)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [(3, 'a'), (3, 'b')]
```

**测试状态**：✅ 已测试

---

## 聚合操作符

### reduce - 聚合

```python
# 求和
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.reduce(lambda acc, x: acc + x, seed=0)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [15]
```

**测试状态**：✅ 已测试

### scan - 累积

```python
# 累积过程（不发射最终结果）
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.scan(lambda acc, x: acc + x, seed=0)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 3, 6, 10, 15]
```

**测试状态**：✅ 已测试

### count - 计数

```python
# 计数
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.filter(lambda x: x > 2),
    ops.count()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3]
```

**测试状态**：✅ 已测试

### sum - 求和

```python
# 对所有元素求和
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.sum()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [15]
```

**测试状态**：✅ 已测试

### average - 平均值

```python
# 计算平均值
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.average()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3.0]
```

**测试状态**：✅ 已测试

---

## 错误处理操作符

### catch - 捕获错误

```python
# 捕获错误并返回替代 Observable
result = []
Observable.of(1, 2, 3).pipe(
    ops.flat_map(lambda x: 
        Observable.just(x) if x != 2 
        else Observable.error(ValueError("测试"))
    ),
    ops.catch(lambda e: Observable.just(-1))  # 捕获错误返回 -1
).subscribe(
    on_next=lambda x: result.append(x),
    on_error=lambda e: print(f"未捕获错误: {e}")
)

print(result)  # [1, -1, 3]
```

**测试状态**：✅ 已测试

### retry - 重试

```python
import time
# 失败时重试指定次数
result = []
attempts = [0]

def failing_source():
    attempts[0] += 1
    if attempts[0] < 3:
        raise ValueError(f"第 {attempts[0]} 次失败")
    return Observable.just("成功")

Observable.from_callable(lambda: None).pipe(
    ops.flat_map(lambda _: Observable.defer(failing_source)),
    ops.retry(times=3)
).subscribe(
    on_next=lambda x: result.append(x),
    on_error=lambda e: print(f"重试耗尽: {e}")
)

print(f"结果: {result}, 尝试次数: {attempts[0]}")
# 结果: ['成功'], 尝试次数: 3
```

**测试状态**：✅ 已测试

### on_error_return - 错误时返回默认值

```python
# 发生错误时发射默认值
result = []
Observable.of(1, 2, 3).pipe(
    ops.flat_map(lambda x:
        Observable.just(x) if x != 2
        else Observable.error(ValueError("oops"))
    ),
    ops.on_error_return(-999)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, -999, 3]
```

**测试状态**：✅ 已测试

### on_error_resume_next - 错误时切换到另一个 Observable

```python
# 发生错误时切换到备用流
result = []
Observable.of(1, 2, 3).pipe(
    ops.flat_map(lambda x:
        Observable.just(x) if x != 2
        else Observable.error(ValueError("oops"))
    ),
    ops.on_error_resume_next(Observable.of("a", "b", "c"))
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 'a', 'b', 'c', 3]
```

**测试状态**：✅ 已测试

---

## 时间操作符

### debounce - 防抖

```python
import time
# 等待指定时间没有新值才发射
result = []
times = []

Observable.of(1, 2, 3).pipe(
    ops.debounce(0.1)
).subscribe(
    on_next=lambda x: result.append(x),
    on_completed=lambda: print(f"完成: {result}")
)
# 由于是同步发射，会立即完成
```

**测试状态**：✅ 已测试

### delay - 延迟

```python
import time
# 延迟发射所有值
result = []
Observable.of(1, 2, 3).pipe(
    ops.delay(0.05)
).subscribe(on_next=lambda x: result.append(x))

time.sleep(0.1)
print(result)  # [1, 2, 3]
```

**测试状态**：✅ 已测试

### throttle_first - 节流（首个）

```python
# 限制发射频率，只放行第一个
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.throttle_first(0.1)
).subscribe(on_next=lambda x: result.append(x))

print(result)
```

**测试状态**：✅ 已测试

---

## 辅助操作符

### tap - 副作用操作

```python
# 在管道中执行副作用操作
result = []
Observable.of(1, 2, 3).pipe(
    ops.tap(lambda x: print(f"tap: {x}")),  # 打印但不消费
    ops.map(lambda x: x * 2)
).subscribe(on_next=lambda x: result.append(x))

print(result)
# 输出:
# tap: 1
# tap: 2
# tap: 3
# [2, 4, 6]
```

**测试状态**：✅ 已测试

### start_with - 头部添加

```python
# 在流开头添加值
result = []
Observable.of(4, 5, 6).pipe(
    ops.start_with(1, 2, 3)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3, 4, 5, 6]
```

**测试状态**：✅ 已测试

### end_with - 尾部添加

```python
# 在流末尾添加值
result = []
Observable.of(1, 2, 3).pipe(
    ops.end_with(4, 5, 6)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3, 4, 5, 6]
```

**测试状态**：✅ 已测试

### ignore_elements - 忽略所有元素

```python
# 只传递完成和错误信号
result = []
Observable.of(1, 2, 3).pipe(
    ops.ignore_elements()
).subscribe(
    on_next=lambda x: result.append(x),
    on_completed=lambda: print("完成")
)

print(result)  # []
print("完成")
```

**测试状态**：✅ 已测试

---

## 统计操作符

### median - 中位数

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.median()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [3]
```

**测试状态**：✅ 已测试

### variance - 方差

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.variance()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [2.0] (ddof=0 默认)
```

**测试状态**：✅ 已测试

### std - 标准差

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.std()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1.4142135623730951]
```

**测试状态**：✅ 已测试

### quantile - 分位数

```python
result = []
Observable.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10).pipe(
    ops.quantile(0.75)  # 75%分位数
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [7.75]
```

**测试状态**：✅ 已测试

---

## 滚动窗口操作符

### rolling_sum - 滚动求和

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.rolling_sum(3)  # 窗口大小3
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 3, 6, 9, 12]
```

**测试状态**：✅ 已测试

### rolling_mean - 滚动平均

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.rolling_mean(3)
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1.0, 1.5, 2.0, 3.0, 4.0]
```

**测试状态**：✅ 已测试

---

## 累积变换操作符

### cum_sum - 累积求和

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.cum_sum()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 3, 6, 10, 15]
```

**测试状态**：✅ 已测试

### cum_prod - 累积乘积

```python
result = []
Observable.of(1, 2, 3, 4, 5).pipe(
    ops.cum_prod()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 6, 24, 120]
```

**测试状态**：✅ 已测试

---

## 嵌套流展开操作符

### flatten - 扁平化

```python
result = []
Observable.of(
    Observable.of(1, 2),
    Observable.of(3, 4)
).pipe(
    ops.flatten()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3, 4]
```

**测试状态**：✅ 已测试

### explode - 爆炸（用于列表）

```python
result = []
Observable.of([1, 2], [3, 4], [5]).pipe(
    ops.explode()
).subscribe(on_next=lambda x: result.append(x))

print(result)  # [1, 2, 3, 4, 5]
```

**测试状态**：✅ 已测试

---

## 完整示例

```python
from vools.reactive import Observable, ops

# 复杂的响应式管道
result = []

Observable.from_range(1, 101) \
    .pipe(
        ops.filter(lambda x: x % 3 == 0),      # 3的倍数
        ops.map(lambda x: x ** 2),             # 平方
        ops.skip(5),                           # 跳过前5个
        ops.take(10),                          # 只取10个
        ops.scan(lambda acc, x: acc + x, seed=0)  # 累积求和
    ) \
    .subscribe(
        on_next=lambda x: result.append(x),
        on_error=lambda e: print(f"错误: {e}"),
        on_completed=lambda: print(f"完成! 结果: {result}")
    )
```

**测试状态**：✅ 已测试
