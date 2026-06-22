# vools.task.utils — 任务队列工具模块

提供任务处理常用的辅助函数和工具类，包括函数式工具、任务辅助、异步工具和 Result 类型。

## 主要功能

### 函数式工具

| 名称 | 说明 | 示例 |
|------|------|------|
| `identity` | 恒等函数 | `identity(42)` → 42 |
| `const` | 常量函数 | `const(5)(1,2)` → 5 |
| `compose` | 函数组合（从右到左） | `compose(f, g)(x)` → `f(g(x))` |
| `pipe` | 函数管道（从左到右） | `pipe(f, g)(x)` → `g(f(x))` |
| `partial` | 偏函数 | `partial(add, 1)(2)` → 3 |

### 任务辅助

| 名称 | 说明 | 示例 |
|------|------|------|
| `retry` | 重试执行 | `retry(func, times=3)` |
| `timeout` | 超时限制 | `timeout(func, 5.0)` |
| `catch` | 捕获异常 | `catch(int, "42", default=0)` |
| `finally_fn` | 确保清理执行 | 确保资源释放 |

### 装饰器

| 名称 | 说明 | 示例 |
|------|------|------|
| `@with_timeout(seconds)` | 超时装饰器 | `@with_timeout(5.0)` |
| `@with_retry(times, delay)` | 重试装饰器 | `@with_retry(times=3)` |
| `@with_logging(logger)` | 日志装饰器 | `@with_logging()` |

### Result 类型

| 名称 | 说明 |
|------|------|
| `Result.success(value)` | 创建成功结果 |
| `Result.failure(error)` | 创建失败结果 |
| `result.is_success` | 检查是否成功 |
| `result.value` | 获取成功值 |
| `result.error` | 获取错误信息 |
| `result.get_or(default)` | 获取值或默认值 |
| `result.map(func)` | 映射成功值 |
| `result.flat_map(func)` | 扁平化映射 |

## 使用示例

### 函数式工具

```python
from vools.task.utils import identity, const, compose, pipe, partial

# 恒等函数
result = identity(42)  # 42

# 常量函数
f = const(5)
result = f(1, 2, 3)  # 5

# 函数组合
f = compose(lambda x: x + 1, lambda x: x * 2)
result = f(3)  # (3 * 2) + 1 = 7

# 函数管道
f = pipe(lambda x: x * 2, lambda x: x + 1)
result = f(3)  # (3 * 2) + 1 = 7

# 偏函数
add = partial(lambda a, b: a + b, 1)
result = add(2)  # 3
```

### 任务辅助

```python
from vools.task.utils import retry, timeout, catch

# 重试
def fetch_data():
    return requests.get(url)

result = retry(fetch_data, times=3, delay=1.0)

# 超时
@timeout(func, 5.0)
def long_running():
    pass

# 捕获异常
result = catch(lambda: int("not a number"), default=0)  # 0
```

### 装饰器

```python
from vools.task.utils import with_timeout, with_retry, with_logging

@with_timeout(5.0)
def timed_task():
    pass

@with_retry(times=3, delay=1.0)
def retried_task():
    pass

@with_logging()
def logged_task():
    pass
```

### Result 类型

```python
from vools.task.utils import Result

# 创建结果
success = Result.success(42)
failure = Result.failure("error message")

# 检查状态
if success.is_success:
    print(success.value)  # 42

# 获取值或默认值
result = failure.get_or(0)  # 0

# 映射
mapped = success.map(lambda x: x * 2)  # Result.success(84)

# 链式调用
result = (
    Result.success(5)
    .map(lambda x: x + 1)
    .map(lambda x: x * 2)
)  # Result.success(12)
```

## 与 TaskQueue 配合使用

```python
from vools.task import TaskQueue, WorkerPool
from vools.task.utils import retry, with_logging, Result

@with_logging()
def process_data(data):
    return transform(data)

queue = TaskQueue("tasks.db")
task_id = queue.submit(retry(lambda: process_data(data), times=3))

with WorkerPool(num_workers=4, db_path="tasks.db") as pool:
    result = queue.get_result(task_id)
```

## 异步支持

```python
from vools.task.utils import async_retry, async_timeout

async def fetch_data():
    return await api.get()

# 异步重试
result = await async_retry(fetch_data, times=3)

# 异步超时
result = await async_timeout(coro, seconds=5.0)
```
