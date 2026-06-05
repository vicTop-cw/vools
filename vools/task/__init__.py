"""
任务队列系统 - 支持多进程处理、重试机制、状态管理

核心功能：
- 任务提交与执行
- 多进程并行处理
- 任务重试机制
- 状态管理 (PENDING, RUNNING, RETRYING, FAILED, SUCCESS, CANCEL)
- SQLite存储（含并发控制）

示例：
```python
from vools.task import task, TaskQueue, WorkerPool

@task
def add(a, b):
    return a + b

# 提交任务
queue = TaskQueue()
task_id = queue.submit(add, 1, 2)

# 启动Worker处理
pool = WorkerPool(num_workers=4)
pool.start()

# 等待任务完成
result = queue.get_result(task_id)
```
"""

from .core.queue import TaskQueue
from .core.worker import WorkerPool, ThreadPool
from .decorators.task_decorator import task
from .core.models import TaskStatus, Task

__all__ = ['TaskQueue', 'WorkerPool', 'ThreadPool', 'task', 'TaskStatus', 'Task']
