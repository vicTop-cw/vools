# vools.task.decorators — 任务装饰器

提供便捷的装饰器，将普通函数转换为可提交到任务队列的任务函数。

## 核心组件

| 名称 | 说明 |
|------|------|
| `@task` | 将函数标记为可提交队列的任务 |
| `@batch_execute` | 批量执行装饰器 |

## 使用示例

### @task 装饰器基本使用

```python
from vools.task.decorators import task
from vools.task.core import TaskQueue, WorkerPool

# 使用装饰器标记任务函数
@task
def add(a: int, b: int) -> int:
    return a + b

# 方式 1: 直接调用（不经过队列）
result = add.direct(2, 3)
print(f"直接调用: {result}")  # 5

# 方式 2: 提交到队列
queue = TaskQueue("tasks.db")
task_id = add(2, 3, queue=queue)
print(f"任务ID: {task_id}")

# 启动 Worker 并获取结果
with WorkerPool(num_workers=2, db_path="tasks.db") as pool:
    result = queue.get_result(task_id)
    print(f"队列执行结果: {result}")  # 5
```

### @task 带自定义配置

```python
from vools.task.decorators import task

@task(priority=10, max_retries=3)
def important_task(data: str) -> str:
    """重要任务，高优先级，失败自动重试"""
    return f"processed: {data}"

# 提交时使用默认配置
queue = TaskQueue("tasks.db")
task_id = important_task("test data", queue=queue)

# 也可以提交时覆盖配置
task_id = important_task(
    "urgent data",
    queue=queue,
    priority=100,  # 覆盖默认优先级
    max_retries=5   # 覆盖默认重试次数
)
```

### 任务函数的属性

```python
from vools.task.decorators import task

@task
def my_func(x: int) -> int:
    return x * 2

# 被装饰的函数保留原有功能
print(my_func.direct(5))  # 10

# 可以访问原始函数
print(my_func.__wrapped__(5))  # 10

# 函数名和文档字符串保留
print(my_func.__name__)  # my_func
```

### 结合 TaskQueue 使用

```python
from vools.task.decorators import task
from vools.task.core import TaskQueue, WorkerPool

@task
def fetch_data(url: str) -> dict:
    import requests
    resp = requests.get(url)
    return resp.json()

@task
def process_data(data: dict) -> dict:
    data['processed'] = True
    return data

queue = TaskQueue("workflow.db")

# 提交任务链
task1_id = fetch_data("https://api.example.com/data", queue=queue)
# 可以基于 task1 的结果继续处理（实际应用中可结合 DAG）

with WorkerPool(num_workers=4, db_path="workflow.db") as pool:
    result1 = queue.get_result(task1_id)
    task2_id = process_data(result1, queue=queue)
    result2 = queue.get_result(task2_id)
    print(f"最终结果: {result2}")
```

### @batch_execute 批量执行

```python
from vools.task.decorators import batch_execute

# 批量执行装饰器（如果支持）
@batch_execute
def process_items(items: list) -> list:
    return [item * 2 for item in items]

result = process_items([1, 2, 3, 4, 5])
print(f"批量处理结果: {result}")
```

### 在类中使用

```python
from vools.task.decorators import task

class DataProcessor:
    @task
    def process(self, data: str) -> str:
        return f"processed: {data}"
    
    @staticmethod
    @task
    def static_process(data: str) -> str:
        return f"static: {data}"

# 实例方法
processor = DataProcessor()
queue = TaskQueue("tasks.db")

# 注意：实例方法需要确保实例可序列化
# 建议使用静态方法或模块级函数作为任务函数
task_id = DataProcessor.static_process("test", queue=queue)
```

## 注意事项

- 任务函数必须可以被 pickle 序列化（多进程模式下）
- 建议使用模块级函数，避免实例方法的序列化问题
- `direct()` 方法直接在当前进程执行，不经过队列
- 被装饰函数保留原始函数，可以通过 `__wrapped__` 访问
- 任务优先级数值越大，优先级越高
- 合理设置 max_retries，避免无限重试
