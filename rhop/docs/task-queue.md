# rhop 通用任务队列（A 提交加密 JSON 指令 → B 解密执行）

> **模块路径**：`vools.rhop.task`（存储抽象 `vools.rhop.task.store`，密文工具 `vools.rhop.secret`）
> **状态**：已实现并验证（2026-10-21，`rhop/tests` 456 passed）
> **参照**：表结构与流转对齐 `vools.pyk.look_upon`；**去掉了 P0..P3 跳板角色**，改为配置驱动的方向 A/B/C。

---

## 1. 定位与拓扑

一句话：**A[host] 把加密 JSON 指令交给 B[server]，B 解密后按指示执行；多任务与依赖由 SQLite 管理。**

```
A[提交方 role=A]                        共享介质（文件系统可达）                 B[执行方 role=B]
────────────────                      ─────────────────────                   ────────────────
TaskQueue.submit()  ──写行(载荷加密)──▶  tasks.db  ──原子领取(依赖门控)──▶  TaskQueue.run_resident()
  · DAG 校验 / 幂等                       │  双方同一份库时状态天然可见            · 解密 JSON → 白名单派发
status()/watch() ◀──直接读同一份库────────┘                                       · 执行 action / cli / handler
Heartbeat.read() ──────────────────▶ xxxx.heartbeat ◀──每 5s 写时间戳────────────   · 回写结果(可加密) / 重试
                                     （一直不动=挂了；写入 closed=停机）
```

角色只有三种，**没有 P0/P1/P2/P3 跳板链**：

| 方向 | 含义 | 典型命令 |
|---|---|---|
| `A` | 提交方（写任务、看状态、判活、停机） | `submit` / `status` / `check-heartbeat` / `close` |
| `B` | 执行方（常驻、心跳、领取、执行、回写） | `serve` / `once` |
| `C` | 中转（仅介质能力，不消费队列） | — |

A/B 反向传递只需把配置里的 `role` 互换（介质、密钥、队列原样复用）。

---

## 2. 快速开始

### 2.1 两份配置（只差方向）

```jsonc
// rhop-A.json —— A 提交方
{
  "name": "rhop-link",
  "role": "A",
  "key": {"env": "RHOP_KEY"},
  "shared": {"write": "D:\\share\\rhop"},
  "queue": {"store": {"kind": "sqlite-shared"}},
  "exec": {"allow": ["action:*", "handler:*"]}
}
```

```jsonc
// rhop-B.json —— B 执行方（同一介质；若要各自持库则把 kind 改成 sqlite-local）
{
  "name": "rhop-link",
  "role": "B",
  "key": {"env": "RHOP_KEY"},
  "shared": {"write": "/mnt/share/rhop"},
  "queue": {
    "store": {"kind": "sqlite-shared"},
    "heartbeat": {"file": "rhop-link.heartbeat", "interval_sec": 5, "stale_after_sec": 15},
    "poll_interval_sec": 2,
    "max_retries": 3, "retry_delay_min": 5, "timeout_min": 60,
    "encrypt_result": true
  },
  "exec": {"allow": ["action:*", "handler:*", "cli:python"], "timeout_sec": 3600}
}
```

配置文件推荐用静态页面生成：[`rhop/tools/config_generator.html`](../tools/config_generator.html)
（见 §12）。

### 2.2 三步跑起来

```bash
# 1) B 端常驻（心跳 + 领取 + 执行 + 回写）
python -m vools.rhop.task --config rhop-B.json serve

# 2) A 端提交（支持数组或 {"tasks": [...]}）
python -m vools.rhop.task --config rhop-A.json submit --file tasks.json

# 3) A 端看状态 / 判活 / 停机
python -m vools.rhop.task --config rhop-A.json status
python -m vools.rhop.task --config rhop-A.json check-heartbeat   # alive=0 stale=1 missing=2
python -m vools.rhop.task --config rhop-A.json close             # 让 B 优雅停机
```

任务文件示例（依赖用任务名表达）：

```json
[
  {"task_name": "extract", "cli": {"cmd": "python etl.py --ds 2026-10-21"}},
  {"task_name": "load", "deps": ["extract"], "cli": {"lang": "python", "script": "print('load')"}},
  {"task_name": "notify", "action": "jump.push", "payload": {"local": "out.csv", "remote": "out.csv"},
   "deps": ["load"], "max_retries": 5, "retry_delay_min": 1}
]
```

### 2.3 代码内嵌

```python
from vools.rhop.task import TaskConfig, TaskDaemon

TaskDaemon(TaskConfig.from_file("rhop-A.json")).run_sender(
    tasks=[{"task_name": "hello", "cli": {"cmd": "echo hi"}}], wait=True)

TaskDaemon(TaskConfig.from_file("rhop-B.json")).run_executor()   # 常驻，直到 closed/SIGTERM
```

---

## 3. 配置 schema

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `name` | str | `rhop-link` | 会话名；用于心跳文件名/worker_id 默认值/同步文档名 |
| `role` | str | — | **方向**：`A`/`B`/`C`；也接受 `SEND`/`RECV`/`RELAY`、`requester`/`executor` |
| `direction` | str | — | `role` 的别名（二者给一个即可） |
| `key` | str \| dict | — | 主密钥（解其它密文的那把钥匙）：`{plain/cipher/env/path}`，见 §11 |
| `shared.write` / `shared.read` | str | — | 共同可达介质；两种形态不同时（A 本地目录 / B UNC 或 mount）分别填 |
| `online[]` | list | `[]` | 在线通道（sftp/git/relay），供信封链路使用 |
| `relay` | dict | — | A/B 不可直连时的中转地址与 token |
| `base_dir` | str | 配置文件所在目录 | `sqlite-local` 默认库文件与路径模板 `{base_dir}` 的基准 |
| `queue.store.kind` | str | `sqlite-shared` | 存储后端：`sqlite-shared` / `sqlite-local` / 已注册的自定义后端 |
| `queue.store.path` | str | 见 §4 | 库文件路径，支持 `{shared}` `{base_dir}` `{name}` `{role}` 模板 |
| `queue.store.journal_mode` / `synchronous` | str | 拓扑默认 | 共享库 `DELETE/FULL`，本地库 `WAL/NORMAL`；可覆盖 |
| `queue.store.busy_timeout_sec` | float | 15 | SQLite 忙等 |
| `queue.store.lock_ttl_sec` | float | 900 | 领取任务的锁有效期（与任务 `timeout_min` 取大者） |
| `queue.heartbeat.file` | str | `<name>.heartbeat` | 心跳文件名 |
| `queue.heartbeat.interval_sec` | float | 5 | B 写时间戳间隔 |
| `queue.heartbeat.stale_after_sec` | float | 15 | A 判死阈值（建议 ≥3×写间隔） |
| `queue.heartbeat.closed_token` | str | `closed` | 停机哨兵文本 |
| `queue.worker_id` | str | `<name>-<role>` | worker 标识（写进任务行，便于排查） |
| `queue.poll_interval_sec` | float | 2 | 空闲轮询间隔 |
| `queue.max_retries` | int | 3 | 默认最大重试次数（任务可覆盖） |
| `queue.retry_delay_min` | float | 5 | 默认重试间隔（分钟，可小数；`0`=立即重排） |
| `queue.timeout_min` | float | 60 | 默认单任务超时（分钟） |
| `queue.encrypt_result` | bool | true | 结果落库是否加密 |
| `queue.result_max_bytes` | int | 65536 | 结果超过则截断并给出提示 |
| `exec.allow` | list | `["action:*","handler:*"]` | 执行白名单（见 §10） |
| `exec.allow_any` | bool | false | 放开任意命令（自担风险） |
| `exec.workdir` / `exec.env` / `exec.timeout_sec` | — | "" / {} / 3600 | 默认工作目录 / 追加环境变量 / 执行超时 |

`config` 子命令可校验并打印已解析配置（敏感值打码、明文告警走 stderr）：

```bash
python -m vools.rhop.task --config rhop-B.json config --check-store
```

---

## 4. 数据库抽象与两种拓扑（重点）

队列层**只依赖 `TaskStore` 抽象**，不写任何 SQL，因此拓扑可配置、后端可更换。

| 拓扑 | `queue.store.kind` | 数据一致性来源 | 适用场景 |
|---|---|---|---|
| **单一共享库**（默认） | `sqlite-shared` | 双方打开同一个库文件 | 双方能同时读写同一份文件系统介质（同机、SMB/NFS 挂载、共享盘） |
| **各自持库** | `sqlite-local` | `TaskSync` 加密包收敛（§14） | 介质无法承载并发读写，或不想让两人同时写一个文件 |
| **网络数据库** | 自定义（如 `postgres`） | 由数据库自身保证 | 双方都能连到一个 DB 服务 |

### 4.1 默认路径

```jsonc
{"queue": {"store": {"kind": "sqlite-shared"}}}
// → <shared_read_root>/rhop-<name>.db

{"queue": {"store": {"kind": "sqlite-local"}}}
// → <base_dir>/rhop-<role>.db   (A 端 rhop-a.db / B 端 rhop-b.db)
```

### 4.2 介质校验（重要）

只有**文件系统形态**的 `shared`（本地目录 / UNC / 盘符 / `file://`）才能承载 SQLite：

- `http(s)://` 形态：`shared_read_root()` 返回 `None`，`sqlite-shared` 会**明确报错**并建议改用 `sqlite-local`
  （不会把 URL 当相对路径静默建成一个奇怪目录）。
- 只有 SFTP/Git 在线通道、没有共享文件系统：同样只能选 `sqlite-local`。

### 4.3 共享盘的并发策略

`sqlite-shared` 刻意使用 **回滚日志（`journal_mode=DELETE`）+ `synchronous=FULL` + `busy_timeout` + 写重试退避**：
WAL 依赖可靠的共享内存与文件锁，在网络盘上不可靠，故共享场景禁用（本地库仍用 WAL）。
写路径一律 `BEGIN IMMEDIATE` 显式事务；`claim_next` 在事务内选行 + 带状态守卫的 `UPDATE`（校验 rowcount），
多 worker / 跨机并发下不会领到同一条任务。

> 诚实提示：跨主机共享 SQLite 是**尽力而为**。生产建议把库放在 B 侧或双方都能稳定挂载的介质；
> 若观察到频繁 `database is locked`，请降并发、调大 `busy_timeout_sec`，或切 `sqlite-local`。

### 4.4 接入 PostgreSQL 等后端

新增后端只需注册一个工厂，队列代码零改动。**仓库里已落地 PostgreSQL 后端**（`task/store/pg_store.py`），
形态如下：

```python
from .base import TaskStore

class PgTaskStore(TaskStore):
    # init_schema / insert_tasks（INSERT ON CONFLICT DO NOTHING 幂等）/
    # claim_next（状态守卫 UPDATE，原子）/ set_state（乐观锁）/
    # apply_task / apply_state（版本单调门）/ ...
    ...

def _build_postgres(spec: dict, ctx: dict) -> TaskStore:
    """PostgreSQL 后端工厂：从 spec 读取连接参数。"""
    return PgTaskStore(spec, ctx)

register_store("postgres", _build_postgres)   # 之后配置里 kind 填 "postgres" 即可
```

启用方式：

- 宿主依赖 `psycopg2`：`pip install psycopg2-binary`（运行期才 import；未安装时 `create_store`
  抛可读的 `StoreUnavailable`，不会静默失败）；
- 配置 `"queue": {"store": {"kind": "postgres", ...}}` + 一台可达的 PostgreSQL 服务；
- 该后端自己的 38 条用例（`tests/test_pg_store.py`）需要真实 PG，故默认从全量回归里排除
  （见 §16）。

`TaskStore` 契约（`task/store/base.py`）：`init_schema` / `insert_tasks`（幂等）/ `claim_next`（原子、依赖门控）/
`set_state` / `update_fields` / `clean_stale_locks` / `reset_failed` / `requeue` / `set_cancel_requested` /
`apply_task` / `apply_state` / `get_task` / `list_tasks` / `all_task_names` / `count_by_state` / `close` / `describe`。

**契约是强制的，不只是注释**：`TaskStore` 继承 `abc.ABC`（`ABCMeta` 生效），上表前 16 个方法都是
`@abc.abstractmethod`。因此——

- 缺实现的子类**在构造期**就抛 `TypeError`，报错里点名缺哪几个方法，不会拖到运行期某个调用点才炸；
- `create_store` 把工厂构造时的 `TypeError` 转成可读的 `StoreUnavailable`（含后端 kind 与缺失方法名），
  让"接了不完整后端"在配置期暴露；
- 回归测试 `tests/test_task_store.py::TestAbstractContract` 锁定了这份契约面（多一个/少一个方法都会红）。

> 历史缺陷 BUG-279：早期写作 `class TaskStore(object)`，`@abc.abstractmethod` 完全惰性（`__abstractmethods__` 为空），
> 裸 `TaskStore()` 与零实现子类都能实例化，`create_store` 的 `isinstance` 校验形同虚设。已按上述方式收口。

未知 kind 会报错并列出已注册后端。

---

## 5. 任务表 schema

表名默认 `tasks`（`store.table` 可改），`PRAGMA user_version = 1` 供将来迁移。

| 列 | 类型 | 说明 |
|---|---|---|
| `task_id` | INTEGER PK AUTOINCREMENT | 内部主键 |
| `task_name` | TEXT NOT NULL UNIQUE | **对外身份**（幂等键、依赖引用、同步合并键） |
| `task_type` | TEXT NOT NULL DEFAULT 'CLI' | 自由字符串（无枚举限制；`CLI/action` 等只是提示） |
| `value` | TEXT | 任务原始参数（**TEXT 语义**，对齐 look_upon 的 `VARCHAR(200)`） |
| `deps` | TEXT NOT NULL DEFAULT '[]' | **JSON 数组，元素为 task_name** |
| `state` | TEXT NOT NULL CHECK(...) | 见 §6 |
| `priority` | INTEGER NOT NULL DEFAULT 0 | 越大越先领取 |
| `timeout_min` / `retry_delay_min` / `retry_count` / `max_retries` | REAL / INTEGER | 超时与重试策略 |
| `scheduled_at` | TEXT | 计划执行时间（UTC ISO；未到不领取） |
| `worker_id` / `lock_time` / `expire_time` / `start_time` / `end_time` | TEXT | 竞争锁与时间线 |
| `cancel_requested` | INTEGER NOT NULL DEFAULT 0 | 取消请求 |
| `version` | INTEGER NOT NULL DEFAULT 1 | 乐观锁 / 同步单调版本 |
| `payload_enc` | TEXT | **加密 JSON 指令**（Fernet 信封文本） |
| `payload_sha` | TEXT | 明文载荷的 sha256（解密后校验完整性） |
| `back_info` | TEXT | 结果 JSON（`encrypt_result=true` 时为密文） |
| `last_err` | TEXT | 最近错误（失败原因） |
| `tags` / `queue` / `owner` / `team` / `group_name` / `extra_desc` | TEXT | 通用可选标签（保留 look_upon 的路由能力） |
| `created_at` / `updated_at` | TEXT NOT NULL | UTC ISO |

索引：`state` / `priority` / `lock_time` / `scheduled_at` / `worker_id` / `task_type` / `queue`。

### 与 look_upon 的差异（有意为之）

| 维度 | look_upon（PG） | 本模块（SQLite，通用化） |
|---|---|---|
| 依赖标识 | `INTEGER[]`（自增 task_id） | **task_name 列表**（跨库/同步/PG 都成立） |
| 表名 | 固定单表 | 可配（`store.table`） |
| 存储 | 只支持 PG | **抽象**：sqlite-shared / sqlite-local / 可注册 PG |
| 角色 | vq 侧 p0..p3 跳板链 | **A/B/C 方向**，无跳板角色 |
| 语言枚举 | 无（VARCHAR(32)） | 无（保持一致） |
| 结果 | `back_info` JSONB | `back_info` TEXT，**可加密**、可截断 |

---

## 6. 状态机

```
PENDING ──claim──▶ LOCKED ──start──▶ RUNNING ──ok──▶ COMPLETED
   ▲                  │                 │
   │              释放/超时              ├─retry（retry_count<max）─▶ RETRY_PENDING ─▶ (回到 LOCKED)
   └──────────────────┘                 └─retry 超限 / 确定性错误─▶ FAILED
PENDING/LOCKED/RETRY_PENDING ──cancel──▶ CANCELLED
RUNNING ──cancel──▶ （打 cancel_requested，收尾后 CANCELLED）
```

- `ACTIVE = PENDING/LOCKED/RUNNING/RETRY_PENDING`；`COMPLETED/FAILED/CANCELLED` 为终态。
- 非法流转被拒（`StoreError`）；运维重跑用 `force=True`（`requeue` / `retry_failed`）。
- **重试**：失败且 `retry_count < max_retries` → `RETRY_PENDING` + `scheduled_at = now + retry_delay_min*60`；
  否则 `FAILED`。`retry_delay_min = 0` 表示立即重排（`run_until_done` 会立刻再领）。
- **不可重试的确定性失败**：载荷解密失败、白名单拒绝、无法识别指令、workdir 不存在等，直接 `FAILED`（重试没意义）。
- **失效锁回收**（worker 崩溃不丢任务）：`clean_stale_locks` 优先按每行自己的 `expire_time` 判定
  （`LOCKED → PENDING`、`RUNNING → RETRY_PENDING`），`expire_time` 为空时退回 `lock_time < now - lock_ttl_sec`。
  领取时 `expire_time = now + max(store.lock_ttl_sec, 任务 timeout_min*60)`，避免长任务被别的 worker 误判为失效。

---

## 7. 依赖与 DAG

- `deps` 是 **task_name 列表**；`claim_next` 只领取「所有 deps 均 COMPLETED」的任务（存储层保守兜底：
  依赖不存在的任务永远不会被领取）。
- `submit` 做 DAG 校验：依赖必须已提交或同批出现；自依赖与成环一律抛 `DagValidationError`（含环路径）。
  校验覆盖「已有任务 + 本批新任务」，因此跨批次成环也能拦住。
- 幂等：同 `task_name` 重复提交不会产生新行（`INSERT OR IGNORE`），已存在的行**保持不变**、
  并计入 `submit` 返回的 `skipped`（BUG-291 收口：早期文档把这里写成"幂等 upsert"，
  容易被读成"后到覆盖"，已统一口径）。要更新已存在任务请 `cancel` 后重新提交。
- 优先级：`priority DESC, task_id ASC`；`scheduled_at` 未到不领取。

---

## 8. 加密载荷与结果

- **提交时**：`payload`（或内联的 `action`/`cli`/`handler`/`args`）用主密钥加密成 Fernet 信封文本写入
  `payload_enc`，并对明文算 `payload_sha`（sha256，稳定 JSON 序列化）。
  介质与库里**只有密文**——第三方拿到库文件也读不出指令内容。
- **执行时**：B 解密 → 校验 `payload_sha` → 注入任务上下文（`value` / `task_name` / `task_type`，
  与 look_upon 的 `ctx` 语义对齐）→ 派发执行。
- **结果**：`back_info` 默认也加密（`encrypt_result=false` 可关）。`result_max_bytes` 是**落库文本的硬上限**
  （BUG-283 收口）：先裁 `stdout`/`stderr`，仍超限就退化为紧凑摘要
  （`truncated` + `result_kind` + `result_chars` + `result_head` + 提示），
  库行/同步包不再无界膨胀；加密路径会预留约 600B 的 Fernet 信封开销。
- **大载荷文件通道**（advance 轮新增，默认关闭）：`queue.file_channel.enabled=true` 时，
  结果超过 `file_channel.max_bytes` 就**把完整结果落文件**，信封里只回 `file_ref`
  （`path` + `sha256` + `bytes`），B 端 `decode_result` 按引用读回；引用失效（文件被清理/丢失/
  sha 不匹配）返回可区分的标记（`__file_missing__` / `__file_sha_mismatch__` …），不会抛错。
  落点 `file_channel.dir`（缺省 `<base_dir>/rhop-files`）**需双方共享**；
  **路径校验**：dir 会先相对 `base_dir` 解析为绝对路径并 realpath 归一，必须落在
  `base_dir` 或 shared 路径之内，否则抛 `SecretError` 拒绝开启文件通道（BUG-295 收口）。
  `keep_days` 控制 `rhop-task file-clean` 的清理保留期，**清理只删本通道写出的结果文件**
  （文件名匹配 `<UTC时间戳>-<sha8>.json`，BUG-296 收口），同目录的其它文件一律不碰。
  这条通道正是把"大结果请写文件并用引用路径回传"从文档建议变成可执行的机制。
- **载荷侧同样支持落文件**（advance 轮扩展，默认关闭）：`file_channel.payload_max_bytes > 0` 时，
  A 侧提交的载荷超过阈值就把**已加密的载荷**写进同一目录，`payload_enc` 只存引用信封
  `{"kind": "rhop-payload-file", "file_ref": {...}}`；B 端 `decrypt_payload` 按引用读回再解密，
  引用失效（文件缺失/不可读/sha 不匹配）抛可读的 `PayloadError`。文件里存的是密文，
  共享目录不会泄露明文；`payload_sha` 仍对明文载荷做完整性校验。
  这样 A 侧的大指令不会整条进队列与同步文档。
- 解密失败原因区分：`MALFORMED`（信封不合法）/ `BAD_TOKEN`（密钥不符或被篡改）/ `NOT_JSON`；
  `payload_sha` 不匹配单独报「完整性校验失败」。

---

## 9. 心跳协议 `xxxx.heartbeat`

| 场景 | 行为 |
|---|---|
| **B 运行中** | 每 `interval_sec`（默认 5 秒）把 UTC 时间戳原子写入 `<shared>/<name>.heartbeat` |
| **文件一直不动** | A 判定执行服务挂了：`stale`（超过 `stale_after_sec`，默认 15 秒） |
| **文件内容 = `closed`** | 停机指令：B 停止领取新任务、收尾当前任务后退出 |
| **B 优雅停机** | 自己把该文件写成 `closed`（A 一眼区分"主动关的"还是"崩了"） |
| **从未启动 / 文件被删** | `missing` |

- 写入是**后台线程**（`HeartbeatPump`）：**与任务执行解耦**。B 正在跑一个 10 分钟的长任务时，
  心跳照样每 5 秒更新（否则 A 会误判成挂了）。线程看到 `closed` 就停止写盘（不覆盖运维写下的哨兵）。
- 读数是四态：`alive` / `stale` / `closed` / `missing`（内容不合法时为 `unknown` 并给出原因）；
  内容可带 worker 标识（`include_worker`）。
- `check-heartbeat` 退出码：`alive→0`、`closed→0`（主动停机不算故障）、`stale→1`、`missing→2`。
- 时间戳为**微秒级** ISO（`TIMESTAMP_FORMAT`）。早期用秒精度时，A 读到的 age 会多出最多约 1s 的截断误差
  （写入在 .900、读取紧随其后时读到 age≈0.9s 而真实只有 5ms），阈值小于 1s 就会把刚写完心跳的 B 判成死了
  （BUG-282）。配置层另加一道校验：`stale_after_sec ≥ interval_sec + 1s`，不合规直接报错，双保险。

---

## 10. 执行通道与白名单

B 端按顺序派发（默认**白名单**，任意命令必须显式放行）：

1. `{"action": "jump.push", "payload": {...}}` → `vools.rhop.actions` 注册动作（Ω-gate 解包）；
2. `{"cli": {"lang"|"cmd"|"args"|"script"|"script_path"|"workdir"|"env"|"stdin"|"timeout_sec"|"shell"|"check"}}`
   → `subprocess`（字段与 `vools.pyk.look_upon.cli_execute` 完全一致，无语言枚举限制）；
3. `{"handler": "name"}` 或 `task_type` 命中 `register_handler` 注册的 Python 函数。

白名单规则：

| 写法 | 含义 |
|---|---|
| `action:*` / `action:jump.push` | 放行动作（默认放行全部动作） |
| `handler:*` / `handler:etl` | 放行处理器（默认放行全部处理器） |
| `cli:python` / `cli:bash` / `cli:git` | 放行对应可执行名（`cli:python` 同时匹配 `python.exe`） |
| `cli:*` / `*` | 放行任意命令行（等价于 `allow_any`，慎用） |
| `exec.allow_any: true` | 整体放开（自担风险） |

- 默认 `exec.allow = ["action:*", "handler:*"]`：**只放行代码内注册的封闭集合**，命令行一律拒绝。
- 被拒绝时抛 `ExecDenied` → 任务落 `FAILED`（不重试），`last_err` 写明需要加哪条白名单。
- `shell=true` 需要额外放行 `cli:shell`（或 `allow_any`）；默认 `shell=false`。
- **审计**（BUG-281 收口）：cli 通道在**执行前**打一条审计行（logger `vools.rhop.task.exec`，级别 INFO）：
  `rhop cli 审计: task=<任务名> channel=cli name=<可执行名> allow_hit=<命中的 allow 条目>
  allow_any=<bool> shell=<bool> cmd=<实际命令，或 lang/script/script_path>`。
  审计必须写在执行前：放在执行后补记，遇到超时、被杀、子进程异常就漏了。
- **分级建议**（放行 cli 之前逐条确认）：
  1. 能只放行动作/处理器（封闭集合）就别放 `cli:*`；
  2. `cli:<解释器>` **等于把该解释器可执行的任意代码权交给 A**——确认 A 侧身份可信、
     B 侧执行环境可信，且没有更细的命令模板约束需求；
  3. 需要细粒度控制时优先用 `register_handler` 注册的 Python 处理器（可读、可测、可评审），
     而不是给 `cli:*` 开绿灯；
  4. 开启 `allow_any` 前确认 `exec` 段来自受信任的配置来源（可配 `--strict-secrets` 卡口）。

---

## 11. 敏感信息：明文 / 密文双支持

两种写法，优先级统一为 **非空明文 > 密文（解密）> path（读文件）> env（读环境变量）> 空串**：

```jsonc
// 写法 A：兄弟键（最通用）
{"sftp_password_plain": "my-password", "sftp_password_cipher": "RHOP-ENC:..."}
// → 解析出 sftp_password

// 写法 B：秘密节点（含 plain 或 cipher 键才算）
{"key": {"plain": "", "cipher": "RHOP-ENC:...", "env": "RHOP_KEY", "path": ""},
 "relay": {"token_plain": "", "token_cipher": "RHOP-ENC:..."}}
```

- **只要用了明文就告警**（stderr + logging），并打印确切命令与操作步骤：

  ```
  ⚠ 配置字段 'sftp.password' 使用了明文。
        生成密文：python -m vools.rhop.secret enc "<你的明文>"
        然后把输出填到 'sftp.password_cipher'（密文区），并清空 'sftp.password_plain'（明文区）。
  ```

- `--strict-secrets`（或 `TaskConfig(..., strict_secrets=True)`）把明文从警告升级为**报错**，供 CI/生产卡口。
- 主密钥本身也支持密文：`{"cipher": "RHOP-ENC:...", "env": "RHOP_KEY"}` ——
  外层密钥由 `env`/`path` 提供（避免"自己解自己"）；外键不对时报错指出 `key.cipher`。
- 密文格式：`RHOP-ENC:` + Fernet token（PBKDF2-HMAC-SHA256，salt `vools.rhop.mvp.crypto.v1`，
  100k 迭代，32 字节 → urlsafe base64）。密钥只从 `RHOP_KEY` 环境变量 / `--key` / `--key-file` 读取，代码不留明文。
- 日志/`config --print`/HTML 回显一律打码（`***`），绝不回显明文。

```bash
python -m vools.rhop.secret keygen                    # 生成密钥（写进环境变量，勿入库）
python -m vools.rhop.secret enc "my-password"         # → RHOP-ENC:...
python -m vools.rhop.secret dec "RHOP-ENC:..."        # 反解核对
```

> 本模块只支持 rhop 自带密文方案（用户确认）。vq 现网的 `E:` 前缀（vools core `VText` XOR）**不兼容**，
> 迁移时用上面命令重新生成即可。

---

## 12. 静态 HTML 配置生成器

[`rhop/tools/config_generator.html`](../tools/config_generator.html) —— **单文件、内联 JS/CSS、不联网、不起服务**，
双击用浏览器打开（`file://`）即可用。

- 表单覆盖 §3 全部字段；「方向」是第一个选项（只有 A/B/C）；
- 敏感字段成对（明文区 + 密文区 + 「生成密文」按钮）：点击后**在浏览器内**用纯 JS 实现 Fernet
  （PBKDF2-HMAC-SHA256 + AES-128-CBC + HMAC-SHA256，PKCS7）生成密文，**自动填入密文区并清空明文区**，
  同时给出等价的 `python -m vools.rhop.secret enc` 命令作为备用；
- 实时生成 JSON、校验（共享库缺 `shared`、心跳阈值小于间隔等）、明文残留红色告警、下载 / 复制；
- 页内「派生密钥文本」只用于本地计算，不上传、不落盘、**不会写进生成的配置**；
- 互通性由测试保证：`tests/test_html_fernet.py` 把内联脚本抽出来交给 Node，做
  **JS 加密 → Python 解密** 与 **Python 加密 → JS 解密** 双向验证，并校验派生密钥与 Python 逐字节一致
  （无 node 时该用例跳过并说明原因）。

---

## 13. CLI 参考

```
python -m vools.rhop.task --config <cfg.json> [--json] [--strict-secrets] [--no-warn-plaintext] <子命令>
```

| 子命令 | 说明 | 退出码 |
|---|---|---|
| `submit --file tasks.json` / `--task NAME [--cmd --lang --dep --priority] [--wait]` | A：提交（载荷加密、DAG 校验、幂等） | 0；`--wait` 判死/超时 → 1 |
| `serve [--once] [--max-iterations N] [--no-closed-on-exit]` | B：心跳 + 常驻消费 | 0 |
| `once` | B：只跑一轮（cron/调试） | 0 |
| `status [--state S] [--limit N] [--watch] [--show-payload]` | 看状态（本地库模式会先拉同步） | 0 |
| `watch [--timeout S] [--dead-grace N]` | A：盯完成 + 判 B 心跳 | 0；判死/超时 → 1 |
| `check-heartbeat [--max-age S]` | 判活 | alive/closed → 0，stale → 1，missing → 2 |
| `close` | 写 `closed` 停机指令 | 0 |
| `cancel --task X` / `requeue --task X` / `retry-failed` | 运维 | requeue 失败 → 1 |
| `sync --direction push\|pull\|both` | 本地库模式强制同步 | 非本地库模式 → 2 |
| `config [--check-store]` | 校验并打印已解析配置（打码） | 0 |
| `file-clean` | 清理过期的结果文件（大载荷文件通道，按 `file_channel.keep_days`） | 0 |

`--json` 时 stdout 是**纯 JSON**（提示/告警走 stderr），可直接 `json.loads`。

---

## 14. 同步协议（`sqlite-local`）

两边各持一个本地库时，用**两个单向文档**收敛（各自只由一方写、另一方读，天然无冲突）：

| 文档 | 写方 | 内容 | 读方 |
|---|---|---|---|
| `<name>.a2b.rhop` | A | 任务定义（含 `payload_enc`）+ 取消请求 | B |
| `<name>.b2a.rhop` | B | 任务状态 + 结果 + 版本 | A |

- 文档整体再用主密钥加密一次（"密文套密文"）——介质上只有密文。
- 合并规则：按 `task_name` 幂等合并（**已存在的行保持不变**，与 §10 的 `INSERT OR IGNORE` 口径一致）；
  `version` 不递增的整条丢弃（乐观锁，语义同 `mirror.py`），
  因此**重复同步、乱序同步、旧包追不上新状态**都安全。

- **同 `task_name` 已存在时不会被覆盖**：`submit` 对已存在任务计入 `skipped`（不产生新行、不推版本）。
  要更新已存在任务请 `cancel` 后重新提交（或先删除）；`resets` 通道的重置意图优先于取消（见上）。
- 触发点：A 的 `submit` 自动 `push_tasks`；B 的 `run_once` 先 `pull`（拿任务/取消）再 `push`（回状态）；
  `cancel` 会带上取消请求；也可手动 `sync --direction`。
- **重置意图走 `resets` 通道**（BUG-280 收口）：`a2b.rhop` 文档里带 `resets: [{task_name, at_version}]`，
  A 端 `requeue` / `retry_failed` 只登记意图、不改本地状态；B 端 `pull` 时对版本仍停在
  `at_version` 的任务执行 `requeue`（幂等），重跑后的状态回推会让 A 端收敛并撤销该意图。
  这样双方版本始终对齐，不会出现"A 本地重置后把 B 的较新状态永久挡在版本门外"的发散。

- **控制意图的优先级（BUG-290 收口）**：`cancels` 与 `resets` 都是控制意图，B 端 `pull` 里
  **先应用 cancels 再应用 resets**，因此**重置优先于取消**：

  - `cancel` 只作用于尚未结束的任务（`PENDING`/`LOCKED`/`RETRY_PENDING` → 直接 `CANCELLED`；
    `RUNNING` → 打 `cancel_requested` 等 worker 收尾）；对**已终态**的任务是幂等 no-op，
    且会打一条 warning 留痕（避免"看起来取消了、实际没变"）；
  - 因此对已完成任务「先取消后重置」与「先重置后取消」都会收敛到**重置后的状态**（`PENDING`，待重跑）。
    需要真正阻止重跑时，请在 B 端执行 `cancel`（或让重置意图先于取消下发）；
  - 回归锁定：`tests/test_task_sync.py::TestControlIntentPrecedence`（两种顺序各跑一遍）
    与语料 `tests/boundary/r10_concurrency_sync.py` 的 P8。
- 不做目录枚举，只读写这两个固定文件名，所以 SFTP / Git 形态的介质也能用。
- `status` 前会自动 `pull` 一次，保证 A 看到的是最新状态（本地库模式有一拍延迟，共享库模式为零延迟）。

---

## 15. 边界与已知限制

| 事项 | 说明 |
|---|---|
| 跨主机共享 SQLite | 尽力而为（见 §4.3）；频繁 locked 请降并发或切 `sqlite-local` |
| `value` 是 TEXT | 数字/布尔写进去再读出来是文本（对齐 look_upon）；结构化参数放 `payload` |
| 本地库模式的运维操作 | `requeue` / `retry_failed` 在 A 端**只登记重置意图**（`TaskSync.resets` 通道），由 B 端真正重跑并回推状态，双方版本始终对齐——不会发散（BUG-280 已修复，回归用例见 `tests/test_task_sync.py::TestRequeueConvergence`） |
| 长任务与锁 | `expire_time` 按任务自己的 `timeout_min` 取大者；仍建议 `timeout_min` 与真实耗时匹配 |
| 结果大小 | `result_max_bytes` 是**落库文本硬上限**（BUG-283 已修）：先裁 `stdout`/`stderr`，仍超限退化为紧凑摘要（`result_chars`/`result_head`），加密路径预留约 600B 信封开销；大结果请写文件并用引用路径回传 |
| 任务租约与续期 | 领取后任务是 `LOCKED`（先锁后置 `RUNNING`），租约 = `max(lock_ttl_sec, timeout_min×60)`。**默认不续期**：租约到期后 `clean_stale_locks` 会回收重跑（`LOCKED→PENDING`、`RUNNING→RETRY_PENDING`），因此**任务实际执行时长必须短于租约**，否则会被重复执行（BUG-289）。长任务请显式开 `queue.renew_lock=true`（执行期间后台线程按 `renew_interval_sec` 刷新 `lock_time`/`expire_time`，默认关闭以保持零回归），或给该任务设置足够的 `timeout_min`。**`timeout_min` 同时是命令执行的硬超时**（BUG-324 收口）：`run_once` 把它换算成 `timeout_sec` 传给执行器，超时命令被截断并归为 `RETRY_PENDING`（可重试）——否则会出现「租约按 `timeout_min` 算、命令却跑到 `exec.timeout_sec`（默认 1 小时）」的错配，导致租约先过期、命令还在跑、被重复领取执行 |
| 双方共享介质 | `shared.write` 指向**双方共同可达**的介质（本地目录 / UNC / 盘符 / `file://`；`http(s)` 与只有 SFTP/Git 在线通道时请改用 `sqlite-local`）。**相对 `store.path` 一律相对共享根解析**，落点必须在共享根之内（越界抛 `StoreUnavailable`，BUG-302 收口）；显式绝对路径无需 shared 配置 |
| 大载荷文件 | `file_channel` 默认关闭。开启后结果超阈值会落文件、信封只回 `file_ref`；**落点目录需双方共享**（否则 B 端按引用读不到），且会校验落点必须落在 `base_dir`/shared 之内（越界直接 `SecretError` 拒绝开启，BUG-295）；`keep_days` 过期由 `rhop-task file-clean` 清理，**只删本通道写出的结果文件**（BUG-296），引用失效时返回可区分标记而非抛错 |
| 时钟偏差 | 心跳判死与 `scheduled_at` 都依赖系统时间；跨机请对时。心跳为微秒级时间戳（BUG-282 已修），且配置层校验 `stale_after_sec ≥ interval_sec + 1s`，不合规直接报错 |
| 白名单强度 | `exec.allow` 里的 `cli:<解释器>` **等于放行该解释器可执行的任意代码**（设计性质，非缺陷）：现已审计（§10 审计行）+ 分级建议（§10），放行前请按该节逐条确认 |
| 已知风险清单 | `rhop/tests/boundary/README.md` 的 P2 仍被语料判为 CONFIRMED——因为它验证的是"放行解释器即放行代码"这一**设计性质**（不会因加审计而消失），本节 §10 已把它的处置方式写清楚 |
| 加密算法 | Fernet（AES-128-CBC + HMAC-SHA256，PBKDF2 派生）：足够应付"介质被第三方看到"的场景；如需更强密钥管理可换后端自行替换 `RhopCrypto` |
| 会话方向 | 一个进程一个方向；反向传递改配置 `role` 即可（介质/密钥/队列复用） |

---

## 16. 测试与验证

```bash
cd rhop && python -m pytest -q
        # 598 passed（600 collected；2 failed 来自并行开发中的 clipboard / watch 测试）
```

> 全量 598 条**包含** `test_pg_store.py` 的 38 条（PostgreSQL 后端）。
> 本机 PG 在 **WSL Ubuntu 22.04** 里运行，Windows 侧通过 `127.0.0.1:5432` 可达，
> 连接串 `postgres / 123456`（与测试里硬编码一致），因此默认命令**不再需要**排除它。
> 早先写的「需真实 PG 服务、故默认排除」是**没去连**得出的结论，已更正。
> 下表的计数**以实测为准**，可用稽核仪器随时自校：
> `cd rhop && python tests/audit_api_doc.py <实测 passed 数>`（退出码 = 不一致条数，0 表示文档与实现一致）。

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| `test_task_store.py` | 53 | schema/索引、幂等写入、状态机、乐观锁、优先级、依赖门控、计划时间、取消标记、跨连接原子领取、失效锁回收、版本同步、后端注册与未知 kind、**TaskStore 真 ABC 契约面（含契约面与文档逐字一致）、租约续期 touch_lock（BUG-289）、共享库落点校验（BUG-302）** |
| `test_task_config.py` | 45 | 方向归一（含拒绝 P0..P3）、默认值、`exec` 默认拒绝任意命令、存储 kind、路径模板、介质校验（http 不当目录）、主密钥四种来源、明文告警、严格模式、掩码、**心跳判死阈值必须 ≥ 写间隔 + 1s（BUG-282）** |
| `test_task_secrets.py` | 31 | 明文优先、密文解密、秘密节点、path/env 取值、告警文案含命令与回填指引、严格模式、字段发现、打码 |
| `test_task_exec.py` | 60 | 白名单（默认拒绝 cli、`.exe` 归一、shell 闸门、allow_any）、语言映射、CLI 执行（stdin/env/workdir/timeout/check/退出码）、处理器注册与派发、通道识别、**命中条目读回（matched_pattern）与 cli 审计行（BUG-281，含执行失败/超时也留痕）** |
| `test_heartbeat.py` | 22 | 四态判定、节流/强制写、`closed` 不被覆盖、原子写、**后台线程在任务耗时期间照跳**、运维写 closed 触发退出、瞬时写失败自愈、**微秒级时间戳 + 秒边界不误判死（BUG-282）** |
| `test_task_queue.py` | 74 | 归一/幂等/依赖参数、DAG（缺失/自依赖/成环/跨批次成环）、载荷加解密与完整性、执行成功/失败、**显式 0 重试与 0 延迟**、白名单拒绝终态、取消语义、**取消终态任务留痕（BUG-290）**、运行循环、结果加密/截断/解码、**`result_max_bytes` 落库硬上限（明文与加密两条路径，BUG-283）、租约续期 renew_lock（BUG-289）、大载荷文件通道（结果与载荷两侧落文件 / 引用读回 / 引用失效 / 清理，默认关闭；BUG-295 路径校验、BUG-296 清理只认结果文件）、任务级超时约束命令执行时长 + 超时归为可重试（BUG-324）** |
| `test_task_sync.py` | 22 | 两库收敛、幂等拉取、依赖顺序、状态回流、取消传播、旧定义不覆盖新状态、介质上只有密文、坏密钥降级、缺 shared 报错、**A 端 `requeue`/`retry_failed` 走 resets 通道后双方收敛（BUG-280）、cancel/reset 意图裁决：两种顺序都收敛到重置后的状态（BUG-290）** |
| `test_task_cli.py` | 28 | 各子命令与退出码、纯 JSON stdout、全局选项前后位置、严格模式卡口、本地库全流程 |
| `test_task_e2e.py` | 16 | A 提交→B 执行→A 看状态（两种拓扑）、长任务期间心跳照跳、运维 `closed` 停机、优雅停机、判死与从未启动、崩溃回收重跑、接线与角色分派 |
| `test_html_fernet.py` | 15 | 页面结构/离线自包含/无跳板角色选项、JS↔Python 双向密文互通、派生密钥一致、错密钥失败、页面密文直接喂给 `TaskConfig` 与 `secret` CLI |

任务队列之外的 15 个测试文件合计 151 条：`test_actions.py` 19、`test_mirror.py` 15、`test_endpoint.py` 16、
`test_transport.py` 18、`test_session.py` 12、`test_interact.py` 12、`test_crypto.py` 10、`test_envelope.py` 9、
`test_daemon_e2e.py` 7、`test_signer.py` 7、`test_core.py` 8、`test_relay.py` 8、`test_integrity.py` 5、
`test_sftp_live.py` 3、`test_watch.py` 2。

> 历史漂移记录：本表的计数曾因历次修复只改实现未回写而过期（文档曾写 458 / 表内 313，实测 488 / 337），
> 已按实测回写并改用稽核仪器自校（BUG-287）。

端到端手工联调记录（CLI 全链路，2026-10-21）：

```
submit --file tasks.json          → 已提交 2 条
once (B) × 2                      → job1 completed（依赖先跑）→ job2 completed
status (A，共享库)                 → COMPLETED=2，A 端无需任何同步
check-heartbeat                   → missing（B 未启动）exit 2
close → check-heartbeat           → closed，exit 0
serve --max-iterations 5          → reason=stop-requested（读到 closed 后退出）
```

---

## 17. 与 look_upon 的对应关系

| look_upon | 本模块 |
|---|---|
| `LookUpon(task_function, dbtable, ...)` | `TaskQueue(TaskConfig)`（`TaskDaemon` 为常驻封装） |
| `add_tasks(tasks, deps=...)` | `submit(tasks, deps=...)`（额外做载荷加密） |
| `_init_table()`（`CREATE TABLE IF NOT EXISTS`） | `TaskStore.init_schema()`（+ `PRAGMA user_version`） |
| `_acquire_task`（`FOR UPDATE SKIP LOCKED`） | `claim_next()`（`BEGIN IMMEDIATE` + 状态守卫 UPDATE） |
| `execute_task`（`do` / `cli` / `task_function`） | 白名单派发：`action` / `cli` / `handler` |
| `run_until_done` / `run_until_done_resident` | `run_until_done` / `run_resident` |
| `clean_stale_locks` / `update_failed_to_pending` | `clean_stale_locks` / `reset_failed` / `requeue` |
| `deps`（`INTEGER[]`） | `deps`（task_name JSON 数组） |
| `state` CHECK 约束 | `TaskState` 常量 + 表级 CHECK + Python 流转校验 |
| `payload` / `back_info`（JSONB） | `payload_enc`（加密）/ `back_info`（JSON 或密文） |
| 口令/密钥不走代码 | 明文/密文双区 + `RHOP-ENC` + 告警与 `secret` CLI |