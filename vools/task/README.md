# 任务队列系统

一个支持多进程处理的任务队列系统，具有任务重试、状态管理和SQLite持久化功能。

## 功能特性

- ✅ 任务提交和执行
- ✅ 多进程并发处理
- ✅ 任务重试机制
- ✅ 任务状态管理 (PENDING, RUNNING, RETRYING, FAILED, SUCCESS, CANCEL)
- ✅ SQLite持久化存储
- ✅ 并发安全（原子任务领取、租约机制）
- ✅ 任务优先级
- ✅ `@task`装饰器，方便提交任务
- ✅ 支持任务取消和手动重试

## 快速开始

### 基本使用

```python
from vools.task import TaskQueue, WorkerPool, task

# 定义任务函数
@task
def add(a: int, b: int) -> int:
    return a + b

# 创建队列
queue = TaskQueue("tasks.db")

# 提交任务
task_id = add(2, 3, queue=queue)

# 启动Worker处理任务
pool = WorkerPool(num_workers=4, db_path="tasks.db")
pool.start()

# 等待结果
result = queue.get_result(task_id)
print(f"结果: {result}")  # 输出: 5

# 停止Worker
pool.stop()
```

### API参考

#### TaskQueue

任务队列管理器，提供任务提交和查询功能。

```python
from vools.task import TaskQueue

queue = TaskQueue(db_path="tasks.db")

# 提交任务
task_id = queue.submit(func, arg1, arg2, kwarg1=val1, priority=0, max_retries=3)

# 查询任务
task = queue.get_task(task_id)
status = queue.get_task_status(task_id)

# 等待结果
result = queue.get_result(task_id, timeout=60)
success = queue.wait_for_completion(task_id, timeout=60)

# 管理任务
queue.cancel_task(task_id)
queue.retry_task(task_id)

# 批量查询
pending = queue.get_pending_tasks()
failed = queue.get_failed_tasks()

# 清理旧任务
queue.cleanup_old_tasks(days=7)
```

#### WorkerPool

Worker进程池，用于并发处理任务。

```python
from vools.task import WorkerPool

# 创建并启动
pool = WorkerPool(
    num_workers=4,
    db_path="tasks.db",
    lease_seconds=300,  # 任务租约时间
    poll_interval=0.5   # 轮询间隔
)
pool.start()

# 使用上下文管理器
with WorkerPool(num_workers=4, db_path="tasks.db") as pool:
    # 任务会自动被处理
    result = queue.get_result(task_id)

# 停止
pool.stop()
```

#### @task装饰器

方便地将函数转换为可提交的任务。

```python
from vools.task import task

@task
def process_data(data: list) -> list:
    return [x * 2 for x in data]

# 提交任务
task_id = process_data([1, 2, 3], queue=queue)

# 直接执行（不提交队列）
result = process_data.direct([1, 2, 3])
```

#### 任务状态

```python
from vools.task.core.models import TaskStatus

# 状态枚举
TaskStatus.PENDING    # 等待处理
TaskStatus.RUNNING    # 正在处理
TaskStatus.RETRYING   # 重试中
TaskStatus.FAILED     # 失败
TaskStatus.SUCCESS    # 成功
TaskStatus.CANCEL     # 已取消
```

## 架构设计

### 并发控制

1. **原子任务领取**: 使用SQLite的UPDATE ... RETURNING语句保证原子性
2. **租约机制**: 每个任务被领取时有租约时间，超时后自动释放
3. **WAL模式**: 启用SQLite的Write-Ahead Logging提高并发性能

### 目录结构

```
vools/task/
├── __init__.py           # 包入口
├── core/
│   ├── __init__.py
│   ├── models.py         # 数据模型和状态
│   ├── storage.py        # SQLite存储层
│   ├── queue.py          # 任务队列核心逻辑
│   └── worker.py         # Worker进程
├── decorators/
│   ├── __init__.py
│   └── task_decorator.py # @task装饰器
└── utils/
    └── __init__.py
```

## 高级用法

### 任务优先级

```python
# 高优先级任务
high_priority_id = queue.submit(important_task, priority=10)

# 低优先级任务
low_priority_id = queue.submit(background_task, priority=-10)
```

### 重试控制

```python
# 设置最大重试次数
task_id = queue.submit(unreliable_func, max_retries=5)

# 手动重试失败的任务
queue.retry_task(failed_task_id)
```

### 取消任务

```python
# 取消待处理或运行中的任务
queue.cancel_task(task_id)
```

## 注意事项

1. **Windows多进程**: 任务函数需要放在可导入的模块中，不能是`__main__`模块中的函数
2. **数据库锁**: SQLite有并发限制，高负载时考虑使用其他数据库
3. **租约时间**: 根据任务执行时间调整`lease_seconds`，避免任务被重复领取
