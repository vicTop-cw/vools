# Task Queue - 任务队列系统

一个支持多进程/多线程处理的任务队列系统，支持任务重试、状态管理和SQLite持久化。

## 功能特性

- ✅ **多进程支持**：基于 `multiprocessing.Process` 的进程级并发
- ✅ **多线程支持**：基于 `threading.Thread` 的线程级并发
- ✅ **任务状态管理**：支持 PENDING, RUNNING, RETRYING, FAILED, SUCCESS, CANCEL
- ✅ **任务重试机制**：自动重试失败任务
- ✅ **SQLite持久化**：任务数据持久存储
- ✅ **并发安全**：原子任务领取、租约机制
- ✅ **@task装饰器**：方便地将函数转换为任务

## 安装

```bash
pip install vools
```

## 快速开始

### 基本使用

```python
from vools.task import TaskQueue, WorkerPool

def add(a: int, b: int) -> int:
    return a + b

# 创建任务队列
queue = TaskQueue("tasks.db")

# 提交任务
task_id = queue.submit(add, 2, 3)

# 启动Worker进程池
with WorkerPool(num_workers=4, db_path="tasks.db") as pool:
    # 等待任务完成
    result = queue.get_result(task_id)
    print(f"Result: {result}")  # 输出: Result: 5
```

### 使用 @task 装饰器

```python
from vools.task import task, TaskQueue, WorkerPool

@task
def multiply(x: int, y: int) -> int:
    return x * y

queue = TaskQueue("tasks.db")

# 提交任务
task_id = multiply(4, 5, queue=queue)

# 直接执行（不提交到队列）
direct_result = multiply.direct(4, 5)  # 返回: 20

# 启动Worker
with WorkerPool(num_workers=1, db_path="tasks.db") as pool:
    result = queue.get_result(task_id)  # 返回: 20
```

### 多线程模式

```python
from vools.task import TaskQueue, ThreadPool

queue = TaskQueue("tasks.db")
task_id = queue.submit(add, 1, 1)

# 使用线程池（适合IO密集型任务）
with ThreadPool(num_workers=10, db_path="tasks.db") as pool:
    result = queue.get_result(task_id)
```

## API 参考

### TaskQueue

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `submit(func, *args, **kwargs)` | 提交任务 | `func`: 函数, `priority`: 优先级, `max_retries`: 最大重试次数 | 任务ID |
| `get_task(task_id)` | 获取任务详情 | `task_id`: 任务ID | Task对象 |
| `get_task_status(task_id)` | 获取任务状态 | `task_id`: 任务ID | TaskStatus |
| `get_result(task_id, timeout)` | 获取任务结果 | `task_id`: 任务ID, `timeout`: 超时时间 | 任务结果 |
| `cancel_task(task_id)` | 取消任务 | `task_id`: 任务ID | bool |
| `retry_task(task_id)` | 重试失败任务 | `task_id`: 任务ID | bool |

### WorkerPool / ThreadPool

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `num_workers` | int | 4 | Worker数量 |
| `db_path` | str | "tasks.db" | 数据库路径 |
| `lease_seconds` | int | 300 | 任务租约时间（秒） |
| `poll_interval` | float | 0.5 | 轮询间隔（秒） |

### TaskStatus（任务状态）

| 状态 | 说明 |
|------|------|
| `PENDING` | 等待处理 |
| `RUNNING` | 正在处理 |
| `RETRYING` | 重试中 |
| `FAILED` | 失败 |
| `SUCCESS` | 成功 |
| `CANCEL` | 已取消 |

## 并发模式选择

| 模式 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **WorkerPool（多进程）** | CPU密集型任务 | 利用多核CPU，进程隔离 | 内存开销大，进程间通信开销 |
| **ThreadPool（多线程）** | IO密集型任务 | 内存开销小，共享内存 | GIL限制，不能利用多核 |

## 用于 PySpark 日期分区表回溯

```python
from vools.task import TaskQueue, WorkerPool
from datetime import datetime, timedelta

def process_partition(date_str: str):
    """处理单个日期分区"""
    from pyspark.sql import SparkSession
    
    spark = SparkSession.builder \
        .appName(f"Backfill-{date_str}") \
        .master("local[*]") \
        .getOrCreate()
    
    try:
        df = spark.read.parquet(f"/data/dt={date_str}")
        # ... 处理逻辑 ...
        df.write.mode("overwrite").parquet(f"/output/dt={date_str}")
    finally:
        spark.stop()

# 生成日期列表
dates = [
    (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range(31)
]

# 提交任务
queue = TaskQueue("spark_backfill.db")
task_ids = [queue.submit(process_partition, date) for date in dates]

# 并行处理
with WorkerPool(num_workers=4, db_path="spark_backfill.db") as pool:
    for task_id in task_ids:
        result = queue.get_result(task_id)
        print(result)
```

## 高级配置

### 任务优先级

```python
# 高优先级任务
high_priority_task = queue.submit(
    critical_task,
    priority=10,  # 数值越大优先级越高
    max_retries=5
)

# 低优先级任务
low_priority_task = queue.submit(
    background_task,
    priority=1,
    max_retries=1
)
```

### 租约机制

系统使用租约机制防止任务卡死：
- Worker领取任务时获得租约
- 任务完成或超时后租约自动释放
- 超时任务会被重新分配给其他Worker

## 测试

运行测试：

```bash
cd vools
python -m pytest tests/test_task_queue.py -v
```

## 技术实现

### 并发控制

- 使用 SQLite WAL 模式提高并发性能
- 使用 `UPDATE ... RETURNING` 实现原子任务领取
- 租约机制防止任务重复执行

### 数据模型

```python
@dataclass
class Task:
    id: int                    # 任务ID
    task_name: str             # 任务名称
    task_func: str             # 序列化的函数
    args: list                 # 位置参数
    kwargs: dict               # 关键字参数
    status: TaskStatus         # 任务状态
    priority: int              # 优先级
    retry_count: int           # 已重试次数
    max_retries: int           # 最大重试次数
    error_message: str         # 错误信息
    result: Any                # 执行结果
```

## 许可证

MIT License
