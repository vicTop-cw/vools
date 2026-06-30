# 装饰器模块

> **模块路径**：`vools.decorators`
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#004
> **最后更新**：2026-06-30

## 概述

`vools.decorators` 模块提供丰富的装饰器，涵盖缓存、控制流、柯里化、重载等领域。

## 导入方式

```python
from vools import (
    # 缓存
    memorize, once, persist,
    # 控制流
    repeat, retry, rerun, excepts, suppress, ignore,
    # 线程
    trd, proc,
    # 柯里化
    curry, delay_curry,
    # 重载
    overload, overcurry, overloads,
)
```

## 缓存装饰器

### @memorize - 函数结果缓存

缓存函数执行结果，支持过期时间设置。

```python
# test_memorize.py
from vools import memorize
import time

@memorize(duration=2)  # 缓存2秒
def expensive_computation(x):
    print(f"计算中: {x}")
    return x ** 2

# 第一次调用 - 会打印 "计算中: 4"
result1 = expensive_computation(4)
print(f"结果1: {result1}")  # 输出: 结果1: 16

# 第二次调用（2秒内）- 使用缓存，不会打印
result2 = expensive_computation(4)
print(f"结果2: {result2}")  # 输出: 结果2: 16

# 等待3秒后，缓存过期
time.sleep(3)

# 第三次调用 - 重新计算
result3 = expensive_computation(4)
print(f"结果3: {result3}")  # 输出: 结果3: 16
```

### @once - 单次执行

确保函数只执行一次。

```python
# test_once.py
from vools import once

call_count = 0

@once
def initialize():
    global call_count
    call_count += 1
    print("初始化完成")
    return True

# 多次调用只执行一次
initialize()  # 打印: 初始化完成
initialize()  # 不打印，使用缓存结果
initialize()  # 不打印，使用缓存结果
print(f"调用次数: {call_count}")  # 输出: 调用次数: 1
```

## 控制流装饰器

### @retry - 重试装饰器

支持多种重试条件和灵活的重试逻辑。

```python
# test_retry.py
from vools import retry
import random

# 基础用法 - 默认重试3次
@retry
def unreliable_request():
    if random.random() < 0.7:
        raise ConnectionError("网络连接失败")
    return "请求成功"

result = unreliable_request()
print(f"结果: {result}")  # 最终会返回 "请求成功"

# 带参数的重试
@retry(tries=5, delay=0.5, backoff=2)
def fragile_operation():
    """重试5次，初始延迟0.5秒，指数退避"""
    if random.random() < 0.8:
        raise ValueError("操作失败")
    return "操作成功"

result2 = fragile_operation()
print(f"结果: {result2}")
```

### @repeat - 重复执行

重复执行函数指定次数或无限循环。

```python
# test_repeat.py
from vools import repeat

@repeat(cnt=3)
def greet(name):
    return f"Hello, {name}!"

# 返回生成器
results = list(greet("Alice"))
print(f"结果: {results}")  # 输出: 结果: ['Hello, Alice!', 'Hello, Alice!', 'Hello, Alice!']

# 无限循环
counter = 0

@repeat(cnt=-1, delay=0.1)  # 无限循环，每0.1秒执行一次
def infinite_task():
    global counter
    counter += 1
    return counter

# 注意：实际使用中需要添加退出条件
# generator = infinite_task()
# for i, result in enumerate(generator):
#     if i >= 5:
#         break
```

### @suppress - 抑制异常

抑制指定类型的异常，不返回任何值。

```python
# test_suppress.py
from vools import suppress

@suppress
def risky_operation1():
    raise ValueError("错误")

result = risky_operation1()
print(f"结果: {result}")  # 输出: 结果: None

@suppress(ValueError, TypeError)
def risky_operation2():
    raise ValueError("错误")

result2 = risky_operation2()
print(f"结果2: {result2}")  # 输出: 结果2: None
```

### @excepts - 异常处理

捕获指定类型的异常并使用处理函数处理。

```python
# test_excepts.py
from vools import excepts

@excepts(ValueError, lambda e: f"捕获错误: {e}")
def might_fail():
    raise ValueError("测试错误")

result = might_fail()
print(f"结果: {result}")  # 输出: 结果: 捕获错误: 测试错误
```

## 线程装饰器

### @trd - 线程异步执行

在单独线程中异步执行函数。

```python
# test_trd.py
from vools import trd
import time

@trd
def background_task(name):
    time.sleep(1)
    return f"{name} 完成"

# 异步执行，不阻塞
future = background_task("任务1")
print("主线程继续执行...")
result = future.result()  # 等待结果
print(f"结果: {result}")  # 输出: 结果: 任务1 完成
```

## 函数扩展装饰器

### @extend - 方法扩展

为已有类添加新方法。

```python
# test_extend.py
from vools import extend

class StringHelper:
    @extend
    def shout(self):
        """为 str 类添加 shout 方法"""
        return self.upper() + "!"

# 现在所有字符串都有 shout 方法
result = "hello".shout()
print(f"结果: {result}")  # 输出: 结果: HELLO!
```

## 快捷工具装饰器

### @timeit - 计时装饰器

测量函数执行时间。

```python
# test_timeit.py
from vools import timeit
import time

@timeit
def slow_function():
    time.sleep(0.5)
    return "完成"

result = slow_function()
# 打印: slow_function 执行时间: 0.50 秒
```

### @debounce - 防抖装饰器

函数调用后等待一段时间，如果没有新调用则执行。

```python
# test_debounce.py
from vools import debounce
import time

@debounce(delay=0.5)
def on_input_change(value):
    print(f"输入值: {value}")

# 快速连续调用只会执行最后一次
on_input_change("a")
on_input_change("ab")
on_input_change("abc")  # 只会执行这个
time.sleep(1)  # 等待执行
```

### @throttle - 节流装饰器

限制函数调用频率。

```python
# test_throttle.py
from vools import throttle

call_count = 0

@throttle(delay=0.5)
def on_click():
    global call_count
    call_count += 1
    print(f"点击 {call_count}")

# 快速连续点击只会按间隔执行
on_click()  # 执行
on_click()  # 被忽略
time.sleep(0.6)
on_click()  # 执行
```

## 装饰器参数说明

| 装饰器 | 主要参数 | 说明 |
|--------|----------|------|
| `@memorize` | `duration` | 缓存有效期（秒） |
| `@retry` | `tries`, `delay`, `backoff` | 重试次数、延迟、指数退避因子 |
| `@repeat` | `cnt`, `delay` | 重复次数、延迟 |
| `@throttle` | `delay` | 节流间隔 |
| `@debounce` | `delay` | 防抖延迟 |

## 注意事项

1. **线程安全**：`memorize` 使用线程安全的 `TimedCache`
2. **可组合性**：装饰器可以叠加使用
3. **参数覆盖**：部分装饰器支持调用时覆盖参数

## 相关文档

- [缓存装饰器详细文档](./memoize.md)
- [柯里化装饰器文档](./curry.md)
- [函数重载装饰器文档](./overload.md)
