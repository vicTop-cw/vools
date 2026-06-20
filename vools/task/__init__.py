"""
任务队列系统 - 支持多进程处理、重试机制、状态管理、DAG编排

核心功能：
- 任务提交与执行
- 多进程并行处理
- 多线程并行处理
- 任务重试机制
- DAG 依赖编排（depends_on）
- 规则引擎（装饰器 + JSON配置双模式）
- 状态管理 (PENDING, READY, RUNNING, RETRYING, FAILED, SUCCESS, SKIPPED, CANCEL)
- SQLite存储（含并发控制）

示例：
```python
from vools.task import task, TaskQueue, WorkerPool, DagScheduler

@task
def add(a, b):
    return a + b

# DAG 依赖编排
queue = TaskQueue()
dag = DagScheduler(queue, mode="thread")
t1 = queue.submit(add, 1, 2)
t2 = queue.submit(add, 3, 4, depends_on={t1})
dag.register_tasks(t1, t2)
dag.start()
dag.await_completion()

# 规则引擎
from vools.task.rules import rule, RuleEngine

@rule(name="check")
def my_rule(ctx):
    return ctx.get("valid", False)
```
"""

from .core.queue import TaskQueue
from .core.worker import WorkerPool, ThreadPool
from .decorators.task_decorator import task, batch_execute
from .core.models import TaskStatus, Task, DagValidationError

# 延迟导入 rules 子包
from .rules import Rule, RuleSet, RuleEngine, rule, RuleStatus, DagScheduler

__all__ = [
    'TaskQueue', 'WorkerPool', 'ThreadPool',
    'task', 'batch_execute',
    'TaskStatus', 'Task', 'DagValidationError',
    'Rule', 'RuleSet', 'RuleEngine', 'rule', 'RuleStatus',
    'DagScheduler',
]
