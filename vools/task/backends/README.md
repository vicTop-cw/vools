# vools.task.backends — 任务队列多后端抽象

`vools.task.backends` 把任务队列的持久化/竞争语义抽象为统一接口 `BackendBase`，
支持三种后端（`pg` / `sqlite` / `memory`），由 `create_backend()` 工厂按名字创建。

## 核心类 / 函数

| 名称 | 类型 | 说明 |
|---|---|---|
| `BackendBase` | 抽象基类 | 定义 `init_table / submit / acquire / complete / fail / get / close` 七方法契约 |
| `create_backend(kind, **kwargs)` | 工厂函数 | `kind` ∈ `pg` / `sqlite` / `memory`，返回具体后端实例 |
| `PgTaskBackend` | 类 | PostgreSQL 持久化队列（对标 look_upon，多 Worker 竞争） |
| `SqliteTaskBackend` | 类 | SQLite 持久化队列（包装 vools.task 现有 `TaskStorage`） |
| `MemoryTaskBackend` | 类 | 内存队列（测试 / 轻量场景，进程退出即丢） |
| `_dag.py` | 模块 | 内部 DAG 依赖辅助（不对外公开） |

## 使用示例

```python
from vools.task.backends import create_backend

# 创建一个 PostgreSQL 后端
backend = create_backend("pg", dsn="host=localhost dbname=tasks")
backend.init_table()
tid = backend.submit("my_task", {"cli": {"cmd": "echo hi"}})

# Worker 竞争取任务
task = backend.acquire("worker-1")
if task:
    backend.complete(task["id"], "worker-1", {"result": "ok"})
backend.close()
```

## 规则与约定

- 各具体后端必须实现 `BackendBase` 的全部抽象方法，缺一即 `TypeError`。
- `kind` 大小写不敏感；`pg` 接受 `postgres` / `postgresql` 别名。
- 未知 `kind` 抛 `ValueError`，不静默回退。
- 模块级 `__all__` 只暴露 `create_backend` 与 `BackendBase`；具体后端类
  由工厂按需惰性导入（避免未装 `psycopg2` 时整包 import 失败）。
