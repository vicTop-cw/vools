# vools.task.core — 任务队列核心

数据模型、SQLite 存储、队列管理和 Worker 实现，是任务队列系统的核心基础设施。

## 核心组件

| 名称 | 说明 |
|------|------|
| `Task` | 任务数据模型（含 dependencies 支持 DAG） |
| `TaskStatus` | 任务状态枚举（PENDING, READY, RUNNING, SUCCESS, FAILED, SKIPPED, CANCEL） |
| `TaskStorage` | SQLite 存储层（含 DAG 依赖表） |
| `TaskQueue` | 任务队列管理器（提交、状态查询、结果获取） |
| `Worker` | 单 Worker 执行器 |
| `WorkerPool` | 多进程 Worker 池 |
| `ThreadPool` | 多线程 Worker 池 |

## 使用示例

### TaskQueue 基本使用

```python
from vools.task.core import TaskQueue, WorkerPool, TaskStatus

# 创建任务队列
queue = TaskQueue("tasks.db")

# 定义任务函数
def add(a: int, b: int) -> int:
    return a + b

# 提交任务
task_id = queue.submit(add, 2, 3)
print(f"任务ID: {task_id}")

# 获取任务状态
status = queue.get_task_status(task_id)
print(f"任务状态: {status}")

# 启动 Worker 池并等待结果
with WorkerPool(num_workers=4, db_path="tasks.db") as pool:
    result = queue.get_result(task_id, timeout=10)
    print(f"任务结果: {result}")
```

### 任务状态管理

```python
from vools.task.core import TaskQueue, TaskStatus

queue = TaskQueue("tasks.db")

def my_task():
    return "done"

# 提交任务
task_id = queue.submit(my_task)

# 查询任务状态
task = queue.get_task(task_id)
print(f"状态: {task.status}")
print(f"重试次数: {task.retry_count}")

# 取消任务
cancelled = queue.cancel_task(task_id)
print(f"已取消: {cancelled}")

# 重试失败任务
retried = queue.retry_task(task_id)
print(f"已重试: {retried}")
```

### 使用 Worker 池（多进程）

```python
from vools.task.core import TaskQueue, WorkerPool

queue = TaskQueue("tasks.db")

def compute(n: int) -> int:
    return n * n

# 批量提交任务
task_ids = [queue.submit(compute, i) for i in range(10)]

# 启动多进程 Worker 池
with WorkerPool(num_workers=4, db_path="tasks.db") as pool:
    # 获取所有结果
    results = [queue.get_result(tid) for tid in task_ids]
    print(f"结果: {results}")
```

### 使用线程池

```python
from vools.task.core import TaskQueue, ThreadPool
import time

queue = TaskQueue("tasks.db")

def io_task(url: str) -> str:
    time.sleep(0.1)  # 模拟 IO 操作
    return f"fetched: {url}"

# IO 密集型任务适合用线程池
urls = ["http://example.com/1", "http://example.com/2", "http://example.com/3"]
task_ids = [queue.submit(io_task, url) for url in urls]

with ThreadPool(num_workers=10, db_path="tasks.db") as pool:
    results = [queue.get_result(tid) for tid in task_ids]
    print(f"结果: {results}")
```

### TaskStorage 直接使用

```python
from vools.task.core import TaskStorage, Task, TaskStatus

# 创建存储
storage = TaskStorage("tasks.db")
storage.init_db()

# 添加任务
task = Task(
    task_name="my_task",
    task_func="module.my_function",
    args=[1, 2],
    kwargs={},
    status=TaskStatus.PENDING,
    priority=5,
    max_retries=3,
)
task_id = storage.add_task(task)

# 领取任务（原子操作）
leased_task = storage.lease_task(worker_id="worker-1", lease_seconds=300)
if leased_task:
    print(f"领取任务: {leased_task.id}")

# 完成任务
storage.complete_task(task_id, result="success")
```

### 任务重试机制

```python
from vools.task.core import TaskQueue, WorkerPool

queue = TaskQueue("tasks.db")

def flaky_task() -> str:
    import random
    if random.random() < 0.5:
        raise ValueError("随机失败")
    return "success"

# 提交带重试的任务
task_id = queue.submit(flaky_task, max_retries=3)

with WorkerPool(num_workers=2, db_path="tasks.db") as pool:
    try:
        result = queue.get_result(task_id, timeout=30)
        print(f"成功: {result}")
    except Exception as e:
        task = queue.get_task(task_id)
        print(f"失败，重试了 {task.retry_count} 次: {e}")
```

### Worker 直接使用

```python
from vools.task.core import Worker, TaskStorage

storage = TaskStorage("tasks.db")

# 创建单个 Worker
worker = Worker(storage=storage, worker_id="worker-1")

# 运行单个任务
worker.run_once()

# 持续运行直到队列为空
worker.run_until_empty()
```

## 任务状态流转

```
PENDING → READY → RUNNING → SUCCESS
              ↓         ↓
            CANCEL    FAILED → RETRYING → READY
```

## 注意事项

- SQLite 存储适合中小规模任务，大规模建议使用专业消息队列
- 多进程模式下，任务函数必须可被 pickle 序列化
- 注意设置合理的租约时间，避免任务卡死
- 大数据结果建议存储到外部系统，不要直接存在任务表中
