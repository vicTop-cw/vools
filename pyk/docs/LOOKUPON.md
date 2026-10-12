# LookUpon — 任务调度（PostgreSQL 队列）

`vools.pyk.look_upon` 是 vools-pyk 的 **PostgreSQL 任务队列**。
支持 DAG 依赖、跨表依赖、可配置重试、worker 竞争锁、超时回滚、取消请求、优先级调度。

> 文档即实现：本文档中的 Schema、状态机、API 即为本模块的**权威契约**。
> 代码以文档为准实现；任何与本文不符的代码视为 BUG。

---

## 1. 表 Schema（32 列）

LookUpon 使用单张 PostgreSQL 表承载任务队列。表结构在 `LookUpon.__init__` 时通过
`CREATE TABLE IF NOT EXISTS` **一次性建好**（无 ALTER 补列）。

| # | 列名 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| 1 | `task_id` | `SERIAL PRIMARY KEY` | — | 自增主键 |
| 2 | `task_name` | `VARCHAR(256) NOT NULL UNIQUE` | — | 任务名（唯一） |
| 3 | `value` | `VARCHAR(200)` | `NULL` | 任务参数（原始字符串） |
| 4 | `task_type` | `VARCHAR(32) NOT NULL` | `'SQL'` | 任务类型（SQL / PY / SHELL …） |
| 5 | `team` | `VARCHAR(128) NOT NULL` | `''` | 所属团队 |
| 6 | `group_name` | `VARCHAR(128) NOT NULL` | `''` | 所属分组 |
| 7 | `owner` | `VARCHAR(64) NOT NULL` | `''` | 责任人 |
| 8 | `queue` | `VARCHAR(64) NOT NULL` | `''` | 队列名（可多 worker 隔离） |
| 9 | `tags` | `JSONB NOT NULL` | `'[]'` | 标签数组 |
| 10 | `state` | `VARCHAR(20) NOT NULL` | `'PENDING'` | 状态（见 §2） |
| 11 | `deps` | `INTEGER[]` | `NULL` | 依赖的 `task_id` 数组（同表依赖） |
| 12 | `deps_task_tables` | `JSONB` | `NULL` | **跨表依赖**映射（见 §5） |
| 13 | `priority` | `INT NOT NULL` | `0` | 优先级（数值越大越优先） |
| 14 | `timeout_min` | `INT NOT NULL` | `60` | 单次执行超时（分钟） |
| 15 | `retry_delay_min` | `INT NOT NULL` | `5` | 重试间隔（分钟） |
| 16 | `retry_count` | `INT NOT NULL` | `0` | 当前已重试次数 |
| 17 | `max_retries` | `INT NOT NULL` | `{self.max_retries}` | 最大重试次数 |
| 18 | `worker_id` | `VARCHAR(50)` | `NULL` | 当前持有锁的 worker |
| 19 | `lock_time` | `TIMESTAMP` | `NULL` | 加锁时间 |
| 20 | `start_time` | `TIMESTAMP` | `NULL` | 实际开始时间 |
| 21 | `end_time` | `TIMESTAMP` | `NULL` | 结束时间 |
| 22 | `scheduled_at` | `TIMESTAMP` | `NULL` | 计划执行时间 |
| 23 | `expire_time` | `TIMESTAMP` | `NULL` | 锁过期时间 |
| 24 | `cancel_requested` | `BOOLEAN NOT NULL` | `FALSE` | 是否请求取消 |
| 25 | `version` | `INT NOT NULL` | `1` | 乐观锁版本号 |
| 26 | `last_err` | `TEXT` | `NULL` | 最近一次错误 |
| 27 | `back_info` | `JSONB` | `NULL` | 回退信息（push_back 用） |
| 28 | `payload` | `JSONB` | `NULL` | 任务数据（JSONB，灵活传参） |
| 29 | `extra_desc` | `TEXT` | `NULL` | 扩展描述 |
| 30 | `push_back_at` | `TIMESTAMP` | `NULL` | 回退时间（push_back 后置时间戳） |
| 31 | `created_at` | `TIMESTAMP NOT NULL` | `CURRENT_TIMESTAMP` | 创建时间 |
| 32 | `updated_at` | `TIMESTAMP NOT NULL` | `CURRENT_TIMESTAMP` | 更新时间 |

### 索引

LookUpon 建表同时创建以下索引：

| 索引 | 目的 |
|---|---|
| `idx_state (state)` | 按状态扫描待办 |
| `idx_lock_time (lock_time)` | 清理过期锁 |
| `idx_task_name (task_name)` | 按名查找 |
| `idx_deps USING GIN (deps)` | 依赖数组查询 |
| `idx_deps_task_tables USING GIN (deps_task_tables)` | 跨表依赖 JSONB 查询 |
| `idx_task_type (task_type)` | 按类型扫描 |
| `idx_team (team)` | 按团队扫描 |
| `idx_group_name (group_name)` | 按分组扫描 |
| `idx_owner (owner)` | 按责任人扫描 |
| `idx_queue (queue)` | 按队列扫描 |
| `idx_priority (priority)` | 按优先级取任务 |
| `idx_expire_time (expire_time)` | 清理过期任务 |
| `idx_scheduled_at (scheduled_at)` | 按计划时间取任务 |
| `idx_cancel_requested (cancel_requested)` **部分索引** | 只对 `cancel_requested = true` 建索引 |

---

## 2. 状态机

LookUpon 任务的 `state` 取值集合（**硬约束**，DB CHECK 约束）：

```
PENDING ──acquire──▶ LOCKED ──start──▶ RUNNING ──success──▶ COMPLETED
   ▲                    │                   │
   │                    │                   ├──retry──▶ RETRY_PENDING
   │                    │                   │              │
   │                    │                   │              └──acquire──▶ LOCKED（回到上面）
   │                    │                   └──fail(超限)──▶ FAILED
   │                    │
   └────────release──────┘
```

| 状态 | 含义 | 可迁移到 |
|---|---|---|
| `PENDING` | 待领取 | `LOCKED`, `RETRY_PENDING`（回退） |
| `LOCKED` | 已加锁（被某 worker 抢到） | `RUNNING`, `PENDING`（释放锁） |
| `RUNNING` | 执行中 | `COMPLETED`, `RETRY_PENDING`, `FAILED` |
| `COMPLETED` | 完成（终态） | — |
| `FAILED` | 失败（终态） | — |
| `RETRY_PENDING` | 等待重试 | `LOCKED`（下次 acquire） |

终态：`COMPLETED` / `FAILED`。终态任务不可再被领取。

---

## 3. 快速开始

```python
from vools.pyk.look_upon import LookUpon

def my_task(task_name: str):
    # 执行你的业务逻辑
    print(f"running {task_name}")
    return "ok"

lu = LookUpon(
    task_function=my_task,
    dbtable="public.look_upon",
    dbName="mydb",
    user="postgres",
    password="****",
    host="127.0.0.1",
    port=5432,
)

# 1) 添加任务（支持同表 deps 与跨表 deps_task_tables）
lu.add_tasks(
    tasks=["task_a", "task_b"],
    deps={"task_b": [1]},          # task_b 依赖 task_a (task_id=1)
)

# 2) 运行到完成（阻塞）
lu.run_until_done(worker_id="w1")

# 3) 查看结果
print(lu.is_all_done())
lu.close()
```

---

## 4. DAG 依赖

### 4.1 同表依赖（`deps`）

`deps` 是 `INTEGER[]`，存**同表**其他任务的 `task_id`。

```python
lu.add_tasks(
    tasks=["A", "B", "C"],
    deps={"B": [1], "C": [1, 2]},   # B 依赖 A(id=1)；C 依赖 A(id=1) 和 B(id=2)
)
```

- 只有 `deps` 里所有任务都 `COMPLETED`，本任务才可 `acquire`。
- 自动 DAG 校验：`add_tasks` 内部会调用 `_validate_deps_dag` 检测环，有环即报错。

### 4.2 跨表依赖（`deps_task_tables`）

`deps_task_tables` 是 `JSONB`，支持依赖**另一张 LookUpon 表**里的任务。

```python
lu.add_tasks(
    tasks=["my_task"],
    deps_task_tables={
        "other_table": ["other_task_1", "other_task_2"],   # 依赖另一张表的任务
    },
)
```

跨表依赖满足的条件（`_cross_deps_satisfied`）：
1. 另一张表存在且**可读**；
2. 被依赖的任务**全部**处于 `COMPLETED`；
3. 若依赖表不可用（不存在 / 不可连接），视为**不满足**（保守不执行）。

---

## 5. Worker 竞争锁

多个 worker 可并行运行同一队列。LookUpon 使用**事务 + 乐观锁**保证同一任务
同一时刻只被一个 worker 领取：

```python
lu.run_until_done(worker_id="worker-A", timeout_min=5, interval=10)
```

- `timeout_min`：单任务执行超时（分钟），超时视为失败（可按重试策略重试）。
- `interval`：poll 间隔（秒）。
- `_acquire_task` 内部使用 `UPDATE ... WHERE state='PENDING' AND ... RETURNING`
  原子抢占，并写入 `worker_id` / `lock_time` / `expire_time`。

### 锁回收

`clean_stale_locks(timeout_min=10)`：把 `lock_time` 早于 `now - timeout_min` 的
`LOCKED` 任务释放回 `PENDING`，防 worker 崩溃后死锁。

---

## 6. 重试策略

| 参数 | 说明 |
|---|---|
| `max_retries` | 最大重试次数（构造函数传入，默认 3） |
| `retry_delay_min` | 每次重试前等待分钟数 |
| `retry_count` | 当前已重试次数（表内列） |

失败后：
- `retry_count < max_retries` → 任务转 `RETRY_PENDING`，`scheduled_at = now + retry_delay_min`
- `retry_count >= max_retries` → 任务转 `FAILED`（终态）

---

## 7. Payload & 结果

LookUpon 支持 `payload` JSONB 列，把复杂数据塞进任务：

```python
lu.add_tasks(
    tasks=["task_with_payload"],
    payload={"task_with_payload": {"run_date": "2026-10-12", "param": 42}},
)
# 在 task_function 里用 lu.set_payload / lu._get_payload 读写
lu.execute_task_with_result("task_with_payload", "w1")
```

`task_function` 收到的是 `task_name`；如需 payload，调用方通过 `LookUpon` 实例
或 `set_payload(task_name, payload)` 写入，再在任务函数里 `lu._get_payload(task_name)` 取出。

---

## 8. CLI 执行通道（无语言枚举限制）

**`task_type` 是 `VARCHAR(32)`，且没有 CHECK 枚举约束**（只有 `state` 有 CHECK），
所以 Scala / Java / R / Go / Node / Shell / SQL / Python ... **都可以自由填**。
LookUpon 提供两条执行路径处理跨语言任务：

### 8.1 通过 payload['cli'] 触发 CLI 执行

当任务 payload 里带 `cli` 子 dict 时，`execute_task` 自动走 **Python subprocess**
调用外部 CLI，不再经过 `self.task_function`：

```python
lu.add_tasks(
    tasks=["scala_job", "java_job", "sql_job", "shell_job"],
    payload={
        "scala_job":  {"cli": {"lang": "scala",  "args": ["--master", "local[*]"]}},
        "java_job":   {"cli": {"cmd": "java -cp lib/app.jar MainClass", "args": ["--run_date", "2026-10-12"]}},
        "sql_job":    {"cli": {"lang": "psql",  "script": "SELECT 1;", "env": {"PGDATABASE": "mydb"}}},
        "shell_job":  {"cli": {"cmd": "bash deploy.sh", "workdir": "/app", "timeout_sec": 600}},
    },
)
lu.run_until_done(worker_id="w1")
```

### 8.2 支持的 payload['cli'] 字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `lang` | str | 无 | 语言名（`python` / `scala` / `java` / `shell` / `sql` / `r` / `node` / `go` / `julia` / `ruby` / `perl` / `php` / `spark-submit` …），用于推断默认命令前缀 |
| `cmd` | str | 无 | **完整命令字符串**（给了它就跳过 lang 推断），如 `"python run.py --x 1"` |
| `args` | list | `[]` | 追加在 cmd 后的参数列表 |
| `script` | str | 无 | 内联脚本内容，写入临时文件后执行 |
| `script_path` | str | 无 | 已有脚本路径（与 `script` 二选一） |
| `workdir` | str | 当前 cwd | 工作目录 |
| `env` | dict | 继承当前环境 | 附加环境变量 |
| `stdin` | str | 无 | stdin 输入文本 |
| `stdin_from_value` | bool | `True` | 把顶层 `value` 作为 stdin 传入 |
| `timeout_sec` | int | 无 | 超时（秒） |
| `capture` | bool | `True` | 是否捕获 stdout/stderr |
| `shell` | bool | `False` | 是否用 shell 解释命令（默认 False，安全） |
| `check` | bool | `False` | 退出码非 0 是否抛 `CalledProcessError`（默认只记录 `ok=False`） |

顶层 `task_type` 会作为语言提示（若 `lang` 未显式给），大小写不敏感，
支持别名：`SCALA`→scala、`SQL`→sql、`PY`→python、`SHELL`→shell、`JAVA`→java。

### 8.3 语言默认命令映射

| lang / task_type | 默认命令前缀 |
|---|---|
| `python` / `py` / `PY` | `python`（Windows 自动找 `python.exe` / `python3`） |
| `scala` / `sc` | `scala` |
| `java` | `java` |
| `javac` | `javac` |
| `shell` / `bash` / `sh` / `zsh` | `bash`（`sh`/`zsh` 同理） |
| `sql` / `psql` | `psql` |
| `r` / `rscript` | `Rscript` |
| `node` / `js` / `javascript` | `node` |
| `go` / `golang` | `go run` |
| `julia` | `julia` |
| `ruby` | `ruby` |
| `perl` | `perl` |
| `php` | `php` |
| `dotnet` | `dotnet` |
| `spark-submit` | `spark-submit` |
| `spark_sql` / `sparksql` | `spark-sql` |

找不到解释器时 **明确报错**（不静默跳过），要求用户用 `cli.cmd` 显式指定完整命令。

### 8.4 返回值

`cli_execute` 返回结构化 dict，写入 `back_info`：

```python
{
    "ok": True,
    "exit_code": 0,
    "stdout": "...",          # 捕获的 stdout
    "stderr": "...",          # 捕获的 stderr
    "cmd": "python run.py --x 1",  # 实际执行的命令
    "duration_ms": 123.45,
    "error": None,
    "task_type": "scala",
}
```

### 8.5 直接调用（不依赖 LookUpon 实例）

```python
from vools.pyk.look_upon import cli_execute

r = cli_execute({
    "task_type": "SCALA",
    "cli": {"args": ["-version"]},
})
print(r["ok"], r["stdout"])
```

---

## 9. 模块级辅助函数

LookUpon 同时提供模块级函数，方便快速上手：

| 函数 | 说明 |
|---|---|
| `add_tasks(dbtable, tasks, deps, ...)` | 免实例化加任务 |
| `query_tasks(dbtable, where_cond)` | 用 Spark 读取 LookUpon 表为 DataFrame |
| `init_tasks(dbtable, tasks, drop_if_exists)` | 初始化表并插入初始任务 |
| `run_until_done(task_function, dbtable, worker_id, ...)` | 免实例化运行到完成 |
| `reset_tasks(tasks)` | 把 tasks 重置回 PENDING |
| `update_failed_to_pending(dbtable)` | 把 FAILED 任务重置回 PENDING |
| `run_doneEx(dbtable, **kwargs)` | 高级 `run_done` 变体 |
| `get_replaced_sql(ds, replace_func, spark)` | 用 replace_func 替换 SQL 里的变量 |
| `cli_execute(payload, timeout_sec, capture)` | **CLI 执行通道**（模块级，脱离 LookUpon 可用） |

---

## 10. 典型使用模式

### 10.1 单 worker 串行

```python
lu = LookUpon(task_fn, dbtable, **cfg)
lu.add_tasks(["a", "b", "c"], deps={"b": [1], "c": [2]})
lu.run_until_done(worker_id="w1")
```

### 10.2 多 worker 并行

```python
import threading

def worker(wid):
    lu.run_until_done(worker_id=wid, timeout_min=10, interval=5)

threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(3)]
[t.start() for t in threads]
[t.join() for t in threads]
```

### 10.3 常驻进程

```python
lu.run_until_done_resident(worker_id="resident", interval=30)
# 常驻：没有任务时 sleep，有任务就取；被 cancel_requested 可安全退出
```

### 10.4 取消请求

```python
# 外部（或 worker 内部）标记取消
lu.execute_sql(
    "UPDATE public.look_upon SET cancel_requested = true WHERE task_name = %s",
    ["long_task"],
)
# worker 在执行时检查 cancel_requested，可安全退出
```

---

## 11. 异常

| 异常 | 触发场景 |
|---|---|
| `TaskFunctionError` | 任务函数自身抛错 |
| `TaskAlreadyLocked` | 尝试领取已被锁定的任务 |
| `MaxRetriesExceeded` | 重试次数超限 |

---

## 12. 完整方法一览（`LookUpon` 类）

### 生命周期

| 方法 | 说明 |
|---|---|
| `__init__(task_function, dbtable, **cfg)` | 构造；`cfg` 包含 db/user/password/host/port/max_retries |
| `add_tasks(tasks, deps, deps_task_tables, ...)` | 批量添加任务（自动 DAG 校验） |
| `execute_task(task_name, worker_id, skip_states)` | 手动领取并执行单个任务；payload 含 `cli` 时走 CLI 通道 |
| `execute_task_with_result(task_name, worker_id)` | 执行并返回 payload 结果 |
| `run_until_done(worker_id, timeout_min, interval, states)` | 阻塞式跑到全部完成 |
| `run_until_done_resident(worker_id, ...)` | 常驻运行 |
| `is_all_done()` | 是否全部完成 |
| `clean_stale_locks(timeout_min)` | 回收过期锁 |
| `close()` | 关闭连接 |

### 查询 / 数据

| 方法 | 说明 |
|---|---|
| `query(sql)` | 执行查询 |
| `execute_sql(sql, params)` | 执行写操作 |
| `properties()` | 返回连接属性 |
| `set_payload(task_name, payload)` | 写入 payload |
| `_get_payload(task_name)` | 读取 payload |
| `drop()` | 删除 LookUpon 表 |

### CLI 执行通道

| 符号 | 说明 |
|---|---|
| `cli_execute(payload, timeout_sec, capture)` | 模块级 CLI 执行函数（脱离 LookUpon 可用） |
| `LANGUAGE_DEFAULT_CMD` | `dict`：语言 → 默认命令前缀 |
| `LANGUAGE_EXTENSIONS` | `dict`：语言 → 脚本扩展名 |
| `_detect_language(task_type)` | 把 `task_type` 归一化为语言 key |
| `_find_executable(prefix)` | 在 PATH 上查找解释器（Windows 自动补 `.exe`/`.bat`/`.cmd`） |

### 装饰器

| 方法 | 说明 |
|---|---|
| `LookUpon.register_do(name)` | 注册 `do_<name>` 处理器 |
| `LookUpon.builtin_do(name)` | 声明内置 `do_<name>` 处理器 |

