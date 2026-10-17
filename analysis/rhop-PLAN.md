# vools-rhop — 双方对等镜像任务中继协议

> **设计规划文档 v2** (2026-10-15，按需求重新设计)
> 前置阅读: `c:\users\victo\tmp\temp.txt`
> 核心约束: **只有两方**（需求端 / 任务端），不是多跳；双方各跑常驻 daemon；Py3.6 基线
> 状态: 设计评审中，未开始编码

---

## 一、定位（v2 修正）

### 1.1 模型：两方对等镜像

```
┌─────────────────┐                         ┌─────────────────┐
│   需求端 (A)     │                         │   任务端 (B)     │
│                 │   ┌─────────────────┐   │                 │
│  RequestDaemon  │◄──┤  传输通道       ├──►│  ExecuteDaemon  │
│  Mirror DB      │   │  (Git/SFTP/...) │   │  Mirror DB      │
│  inbox/ outbox/ │   └─────────────────┘   │  inbox/ outbox/ │
└─────────────────┘                         └─────────────────┘
```

- **需求端**：提交任务，等结果回来
- **任务端**：收到任务，执行，把结果放回去
- **双方对等**：没有"控制端"，两边都是常驻 daemon，互相监控对方目录
- **镜像数据库**：两边各有一份本地 SQLite，内容一致（daemon 负责同步）

### 1.2 命名

| 项 | 值 |
|---|---|
| 包名 | `vools-rhop` |
| 命名空间 | `vools.rhop` |
| RHOP 全称 | **R**elay **H**op **O**rchestration **P**rotocol |
| 核心模块 | `vools.rhop.mirror`（镜像协议）+ `vools.rhop.daemon`（常驻进程） |
| 版本策略 | 独立演进，Py3.6 基线 |

### 1.3 与 v1 设计的区别

| 维度 | v1（多跳中继，已废弃） | v2（两方镜像，当前） |
|---|---|---|
| 拓扑 | p0→p1→p2→p3 多跳链 | 需求端 ↔ 任务端，两方对等 |
| 中间节点 | 跳板 p1/p2 只做转发 | 无中间节点，双方直接通信 |
| 状态管理 | 各节点各自管 | 双方各持一份镜像 DB，daemon 同步 |
| 传输 | 固定 SFTP/RDP 盘 | 自适应：Git / SFTP / TextDP / 本地 |
| 执行 | 跳板可执行 + 终点执行 | 只有任务端执行，需求端只提交/收结果 |
| 常驻进程 | 无（每次 dispatch 一次） | 双方都跑 daemon，持续监控 |

---

## 二、约束回顾

| # | 约束 | 设计影响 |
|---|---|---|
| C1 | 只有两方（需求端 / 任务端） | 不做多跳，不做跳板路由 |
| C2 | 双方各跑一个常驻 daemon | daemon 是核心，不是 dispatch 一次就走 |
| C3 | 双方各有一个镜像数据库 | SQLite 本地持久化，daemon 负责同步 |
| C4 | 联网时 → Git 仓库中继（或 TextDP） | Git transport 是首选在线方案 |
| C5 | 不联网时 → SFTP 账密镜像文件夹 | SFTP transport 是离线兜底 |
| C6 | Py3.6 基线（首版即 Py3.6） | 不用 dataclasses / f-string= / walrus / match |
| C7 | 通用性优先 | 传输层抽象，后端可插拔 |

---

## 三、架构总览

### 3.1 分层

```
┌──────────────────────────────────────────────────────────────┐
│  vools.rhop.daemon       — 常驻进程（双方各跑一个）           │
├──────────────────────────────────────────────────────────────┤
│  vools.rhop.requester    — 需求端业务 API（提交任务/查结果） │
│  vools.rhop.executor     — 任务端业务 API（领任务/回结果）    │
├──────────────────────────────────────────────────────────────┤
│  vools.rhop.mirror       — 镜像数据库（SQLite，双方共享 schema）│
│  vools.rhop.envelope     — 任务信封（.rhop 文件格式）         │
├──────────────────────────────────────────────────────────────┤
│  vools.rhop.transport    — 自适应传输层（可插拔后端）         │
│    ├── git.py            (在线首选：Git 仓库中继)            │
│    ├── sftp.py           (离线兜底：SFTP 账密镜像文件夹)     │
│    ├── textdp.py         (第三方：TextDP 中继)               │
│    └── local.py          (测试用：本地文件系统直连)          │
├──────────────────────────────────────────────────────────────┤
│  vools.rhop.integrity    — 文件完整性校验                     │
│  vools.rhop.signer       — 真机签名（NPU_MARKER 抽象）       │
│  vools.rhop.config       — 配置管理（环境变量 / 配置文件）   │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
vools-rhop/
├── pyproject.toml
├── README.md
├── docs/
│   └── ARCHITECTURE.md
├── vools/
│   └── rhop/
│       ├── __init__.py          # 懒加载入口
│       ├── core.py              # Side 枚举 + 基础数据结构
│       ├── envelope.py          # 任务信封 (.rhop)
│       ├── mirror.py            # ★ 镜像数据库 (SQLite)
│       ├── daemon.py            # ★ 常驻 daemon（双方共用）
│       ├── requester.py         # 需求端业务封装
│       ├── executor.py          # 任务端业务封装
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── base.py          # AbstractTransport
│       │   ├── git.py           # Git 仓库中继
│       │   ├── sftp.py          # SFTP 账密镜像
│       │   ├── textdp.py        # TextDP 第三方中继
│       │   └── local.py         # 本地直连（测试）
│       ├── integrity.py         # 文件完整性校验
│       ├── signer.py            # 真机签名
│       ├── config.py            # 配置管理
│       └── _compat.py           # Py3.6 兼容工具
├── examples/
│   ├── git_relay.py             # 在线 Git 中继示例
│   ├── sftp_mirror.py           # 离线 SFTP 镜像示例
│   ├── requester_only.py        # 需求端单独使用
│   └── executor_only.py         # 任务端单独使用
├── tests/
│   ├── test_envelope.py
│   ├── test_mirror.py
│   ├── test_daemon.py
│   ├── test_transport_git.py
│   ├── test_transport_sftp.py
│   ├── test_transport_local.py
│   ├── test_integrity.py
│   └── test_py36_compat.py
└── bin/
    └── rhop-daemon              # 可执行入口（双方各跑一个）
```

---

## 四、核心数据模型

### 4.1 Side 枚举（只有两方）

```python
# vools/rhop/core.py
# Py3.6: 不用 dataclasses，用枚举 + attrs

from enum import Enum

class Side(Enum):
    REQUESTER = "requester"   # 需求端：提交任务，等结果
    EXECUTOR = "executor"     # 任务端：领任务，执行，回结果
```

### 4.2 TaskStatus 状态机

```python
class TaskStatus(Enum):
    PENDING = "pending"       # 需求端已提交，任务端未领
    CLAIMED = "claimed"       # 任务端已领，准备执行
    RUNNING = "running"       # 任务端正在执行
    DONE = "done"             # 任务端执行完成，结果已写回
    FAILED = "failed"         # 任务端执行失败
    CANCELLED = "cancelled"   # 需求端取消
```

**状态流转**：
```
PENDING ──► CLAIMED ──► RUNNING ──► DONE
   │            │            │
   │            │            └──► FAILED
   │            │
   └────────────┴──► CANCELLED (仅 PENDING 可取消)
```

### 4.3 Envelope（任务信封）

```python
# vools/rhop/envelope.py
# Py3.6: 用 attrs 代替 dataclasses

import attr
import json
import hashlib

@attr.s(slots=True)
class Envelope:
    task_id = attr.ib(type=str)
    status = attr.ib(type=TaskStatus)
    payload = attr.ib(type=dict)           # 任务载荷
    result = attr.ib(type=object, default=None)  # 执行结果
    error = attr.ib(type=str, default=None)      # 错误信息
    side = attr.ib(type=Side, default=Side.REQUESTER)  # 谁创建的
    version = attr.ib(type=int, default=1)        # 乐观锁版本号
    created_at = attr.ib(type=str, default="")    # ISO 时间戳
    updated_at = attr.ib(type=str, default="")
    hops_seen = attr.ib(factory=list)             # 审计链
    signature = attr.ib(type=str, default=None)   # 真机签名
    checksum = attr.ib(type=str, default="")      # 内容哈希

    def to_rhop_bytes(self):
        """序列化为 .rhop 文件字节。"""
        data = {
            "v": 1,
            "task_id": self.task_id,
            "status": self.status.value,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "side": self.side.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "hops_seen": self.hops_seen,
            "signature": self.signature,
        }
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
        checksum = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
        data["checksum"] = checksum
        return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")

    @classmethod
    def from_rhop_bytes(cls, raw):
        """从 .rhop 字节反序列化 + 校验。"""
        data = json.loads(raw.decode("utf-8"))
        checksum = data.pop("checksum", "")
        expected = "sha256:" + hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        if checksum != expected:
            raise ValueError("checksum mismatch: envelope may be corrupted")
        return cls(
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            payload=data["payload"],
            result=data.get("result"),
            error=data.get("error"),
            side=Side(data.get("side", "requester")),
            version=data.get("version", 1),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            hops_seen=data.get("hops_seen", []),
            signature=data.get("signature"),
            checksum=checksum,
        )
```

**设计要点**：
- `v: 1` 版本号写在第一个字段，向前兼容
- `version` 乐观锁：镜像同步时防冲突（后写覆盖，但版本号递增可追踪）
- `checksum` 在序列化时计算，覆盖整个 payload + 元数据
- `hops_seen` 审计链：每次 daemon 处理后追加自己的 side 标识
- **信封不含密钥**——密钥在配置侧管理

### 4.4 .rhop 文件格式

```json
{
  "v": 1,
  "task_id": "job-2026-10-15-001",
  "status": "pending",
  "payload": {
    "cmd": "spark-submit --master yarn myjob.jar",
    "lang": "scala",
    "data_tables": ["table1", "table2"]
  },
  "result": null,
  "error": null,
  "side": "requester",
  "version": 1,
  "created_at": "2026-10-15T10:30:00Z",
  "updated_at": "2026-10-15T10:30:00Z",
  "hops_seen": ["requester"],
  "signature": null,
  "checksum": "sha256:abc123..."
}
```

---

## 五、镜像数据库（Mirror DB）

### 5.1 Schema（双方共享，完全一致）

```sql
-- vools.rhop.mirror.SCHEMA

CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    side        TEXT NOT NULL,
    payload     TEXT,
    result      TEXT,
    error       TEXT,
    signature   TEXT,
    version     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    checksum    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    old_status   TEXT,
    new_status   TEXT,
    detail       TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    direction    TEXT NOT NULL,   -- push | pull
    transport    TEXT NOT NULL,   -- git | sftp | textdp | local
    task_id      TEXT,
    success      INTEGER NOT NULL,
    error        TEXT,
    bytes_xfer   INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);
```

### 5.2 MirrorDB 类

```python
# vools/rhop/mirror.py

import sqlite3
import os
import time

class MirrorDB:
    """镜像数据库：双方各持一份，schema 完全一致。

    daemon 负责同步——本类只提供本地读写，不做网络操作。
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """初始化 schema（幂等）。"""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    # ── 任务 CRUD ──

    def upsert_task(self, env):
        """写入/更新任务（乐观锁：version 必须递增）。"""
        now = _now_iso()
        cur = self._conn.execute(
            "SELECT version FROM tasks WHERE task_id = ?", (env.task_id,)
        )
        row = cur.fetchone()
        if row:
            if env.version <= row["version"]:
                raise StaleVersionError(
                    "task %s: local version %d, incoming %d" % (
                        env.task_id, row["version"], env.version))
        self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, status, side, payload, result, error, signature,
                version, created_at, updated_at, checksum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (env.task_id, env.status.value, env.side.value,
             json.dumps(env.payload), json.dumps(env.result), env.error,
             env.signature, env.version, env.created_at, now, env.checksum)
        )
        self._conn.execute(
            "INSERT INTO events (task_id, event_type, old_status, new_status, created_at) VALUES (?, 'updated', NULL, ?, ?)",
            (env.task_id, env.status.value, now)
        )
        self._conn.commit()

    def get_task(self, task_id):
        """读取单个任务。"""
        ...

    def list_tasks(self, status=None, limit=50):
        """列出任务，可按状态过滤。"""
        ...

    def update_status(self, task_id, new_status, result=None, error=None, signature=None):
        """更新任务状态（version + 1）。"""
        ...

    def claim_task(self, worker_id, lock_timeout_sec=300):
        """任务端领任务：PENDING → CLAIMED，带租约。"""
        ...

    # ── 同步日志 ──

    def log_sync(self, direction, transport, task_id, success, error=None, bytes_xfer=0):
        """记录同步日志。"""
        ...

    def pending_sync(self, since=None):
        """列出待同步的事件（用于 push 到对端）。"""
        ...

    def close(self):
        self._conn.close()
```

### 5.3 同步协议

daemon 每轮迭代做两件事：

**Pull（拉取对端变化）**：
```
1. 通过 transport.pull() 拉取对端 inbox/ 的最新信封
2. 对每个信封：校验 checksum → 写入本地 mirror DB（upsert）
3. 记录 sync_log
```

**Push（推送本地变化）**：
```
1. 从 mirror DB 读取待同步事件（pending_sync）
2. 通过 transport.push() 推送给对端 outbox/
3. 标记事件已同步
```

**冲突处理**：
- `version` 乐观锁：后写覆盖，但版本号必须递增
- 如果本地 version > 对端 version → 本地赢
- 如果对端 version > 本地 version → 对端赢，本地被覆盖
- 同步日志记录冲突，便于事后审计

### 5.4 目录结构（双方一致）

```
<data_dir>/
├── mirror.db           # SQLite 镜像数据库
├── inbox/              # 待处理的信封（daemon 监控这里）
│   ├── job-001.rhop
│   └── job-002.rhop
├── outbox/             # 已处理完的信封（只增不删）
│   └── job-001.rhop
├── processing/         # 正在处理的信封（daemon 工作区）
├── failed/             # 处理失败的信封（需人工介入）
└── tmp/                # 临时文件（原子写中转）
```

---

## 六、传输层（Transport）

### 6.1 抽象接口

```python
# vools/rhop/transport/base.py

class TransportError(Exception):
    pass

class TransportUnavailable(TransportError):
    """传输通道不可用（网络断 / 认证失败）。"""
    pass

class AbstractTransport(object):
    """传输层抽象：把信封从一个 side 推到另一个 side。

    注意：传输层只管"文件搬运"，不管"任务语义"。
    语义由 daemon + mirror 处理。
    """

    def __init__(self, config):
        self.config = config

    def check(self):
        """检查通道是否可用。返回 (bool, error_msg)。"""
        raise NotImplementedError

    def push(self, env, dest_dir):
        """推送信封到对端目录。
        返回 TransportResult。
        """
        raise NotImplementedError

    def pull(self, src_dir):
        """从对端目录拉取最新信封。
        返回 (envelope_or_None, transport_result)。
        """
        raise NotImplementedError

    def list_remote(self, dir_path):
        """列出对端目录中的信封文件。"""
        raise NotImplementedError

    def sync_folder(self, local_dir, remote_dir):
        """双向同步文件夹（SFTP 镜像模式用）。"""
        raise NotImplementedError

    def close(self):
        """释放资源。"""
        raise NotImplementedError
```

### 6.2 Git Transport（在线首选）

```python
# vools/rhop/transport/git.py

class GitTransport(AbstractTransport):
    """Git 仓库中继：双方 push 到同一个远程仓库。

    适用场景：双方都能联网，有 Git 仓库（GitHub / GitCode / 自建 GitLab）。
    优势：双方都可在 NAT 后面，只要能 push/pull 就行。
    劣势：有 Git 仓库的速率限制；push 有延迟。

    目录约定（在 Git 仓库里）：
      <repo>/
      ├── inbox/<side>/       # 各 side 自己的 inbox
      ├── outbox/<side>/      # 各 side 自己的 outbox
      └── mirror/             # 镜像 DB 的快照（可选）
    """

    def __init__(self, config):
        # config: {repo_url, branch, token, local_path, side}
        self.repo_url = config["repo_url"]
        self.branch = config.get("branch", "main")
        self.token = config.get("token", "")
        self.local_path = config.get("local_path", "./rhop-git")
        self.side = config["side"]
        self._inited = False

    def check(self):
        """git ls-remote 检查仓库可达。"""
        ...

    def _ensure_repo(self):
        """确保本地有 repo 的 clone。"""
        if not os.path.isdir(os.path.join(self.local_path, ".git")):
            # git clone <repo_url> <local_path> --branch <branch>
            subprocess.check_call(["git", "clone", ...])
        self._inited = True

    def push(self, env, dest_dir):
        """把信封写入本地 repo → git add → git commit → git push。"""
        self._ensure_repo()
        # 1. 写 inbox/<side>/<task_id>.rhop
        # 2. git add
        # 3. git commit -m "rhop: push <task_id>"
        # 4. git push origin <branch>
        ...

    def pull(self, src_dir):
        """git pull → 读对端 inbox/<other_side>/ 最新文件。"""
        self._ensure_repo()
        subprocess.check_call(["git", "pull", ...])
        # 读对端目录里最新的 .rhop 文件
        ...

    def sync_folder(self, local_dir, remote_dir):
        """Git 模式下不需要文件夹同步——push/pull 就是同步。"""
        return TransportResult(ok=True, note="git push/pull is the sync mechanism")
```

### 6.3 SFTP Transport（离线兜底）

```python
# vools/rhop/transport/sftp.py

class SFTPTransport(AbstractTransport):
    """SFTP 账密镜像：通过 SSH/SFTP 在双方文件夹间镜像。

    适用场景：双方至少一方有 SFTP 可达（端口 22 或其他）。
    优势：不依赖公网，只要有 SSH 端口可达就行。
    劣势：需要配置 SSH 密钥或密码；SFTP 服务器要可达。

    目录约定：
      需求端本地: <data_dir>/inbox/  <data_dir>/outbox/
      任务端 SFTP: /sftp/inbox/      /sftp/outbox/
      （daemon 把需求端 inbox/ 推到任务端 outbox/，反之亦然）
    """

    def __init__(self, config):
        # config: {host, port, user, password, key_path, chroot_prefix, side}
        ...

    def check(self):
        """尝试 SSH 连接，检查可达。"""
        ...

    def push(self, env, dest_dir):
        """SFTP put: 本地 .rhop → 远端 inbox/。"""
        # 用 paramiko (复用 vools-actus.jump 或独立实现)
        ...

    def pull(self, src_dir):
        """SFTP get: 远端 inbox/ → 本地 outbox/。"""
        ...

    def sync_folder(self, local_dir, remote_dir):
        """双向镜像：本地 ↔ 远端文件夹，只增不删。"""
        # 复用 vools-actus.jump.sync 或直接 paramiko
        ...
```

**SFTP 镜像逻辑**（双向文件夹同步）：
```
每轮 daemon 迭代:
  1. 列远端 inbox/ 里的 .rhop 文件
  2. 对每个新文件: SFTP get → 写入本地 outbox/
  3. 列本地 outbox/ 里的 .rhop 文件
  4. 对每个新文件: SFTP put → 写入远端 inbox/
  5. 处理完成后: 移动到 failed/ 或 done/
```

### 6.4 TextDP Transport（第三方中继）

```python
# vools/rhop/transport/textdp.py

class TextDPTransport(AbstractTransport):
    """TextDP 第三方中继。

    具体实现待确认——目前是抽象骨架。
    用户需提供 TextDP 的 API / SDK 后补全。
    """

    def __init__(self, config):
        # config: {endpoint, api_key, ...}
        ...

    def check(self):
        raise NotImplementedError("TextDP transport not yet implemented")

    def push(self, env, dest_dir):
        raise NotImplementedError("TextDP transport not yet implemented")

    def pull(self, src_dir):
        raise NotImplementedError("TextDP transport not yet implemented")
```

### 6.5 Local Transport（测试用）

```python
# vools/rhop/transport/local.py

class LocalTransport(AbstractTransport):
    """本地文件系统直连：两个 data_dir 在同一文件系统上。

    仅用于单元测试和开发测试，不用于生产。
    """

    def __init__(self, config):
        # config: {local_dir_a, local_dir_b}
        ...

    def push(self, env, dest_dir):
        # 直接把 .rhop 文件复制到 dest_dir
        ...

    def pull(self, src_dir):
        # 从 src_dir 读最新 .rhop
        ...
```

### 6.6 传输选择策略

```python
# vools/rhop/transport/__init__.py

def create_transport(config):
    """根据配置创建传输后端。

    config['transport'] 可以是:
      - "git"      → GitTransport
      - "sftp"     → SFTPTransport
      - "textdp"   → TextDPTransport
      - "local"    → LocalTransport
      - "auto"     → 自动探测，按优先级选第一个可用的
    """
    mode = config.get("transport", "auto")

    if mode == "auto":
        # 按优先级探测
        for backend in ("git", "sftp", "textdp"):
            t = create_transport(dict(config, transport=backend))
            if t.check()[0]:
                return t
        raise TransportUnavailable("no transport available")

    return _TRANSPORT_REGISTRY[mode](config)
```

---

## 七、常驻 Daemon

### 7.1 设计原则

- **双方共用同一个 daemon 类**，通过 `side` 参数区分行为
- **轮询模式**：每 N 秒检查一次 inbox/ 和同步状态
- **幂等**：同一信封重复处理不会产生副作用
- **可中断**：收到 SIGINT/SIGTERM 后优雅退出

### 7.2 核心循环

```python
# vools/rhop/daemon.py

class RelayDaemon:
    """常驻 daemon：双方各跑一个，通过 side 参数区分行为。"""

    def __init__(self, config):
        self.config = config
        self.side = Side(config["side"])
        self.data_dir = config["data_dir"]
        self.poll_interval = config.get("poll_interval", 10)  # 秒
        self.transport = create_transport(config)
        self.mirror = MirrorDB(os.path.join(self.data_dir, "mirror.db"))
        self._running = False

    def start(self):
        """启动 daemon（阻塞）。"""
        self._running = True
        self._ensure_dirs()
        self._log("daemon started, side=%s, transport=%s" % (self.side.value, type(self.transport).__name__))
        while self._running:
            try:
                self._run_once()
            except Exception as e:
                self._log("error in run_once: %s" % e)
            time.sleep(self.poll_interval)

    def stop(self, signum=None, frame=None):
        """优雅停止。"""
        self._log("daemon stopping...")
        self._running = False
        self.transport.close()
        self.mirror.close()

    def _run_once(self):
        """单次迭代：拉取 → 处理 → 推送 → 同步。"""
        # 1. 拉取对端新信封
        self._pull_remote()

        # 2. 处理本地 inbox/ 里的信封
        self._process_inbox()

        # 3. 推送本地变化给对端
        self._push_local()

        # 4. 清理过期任务
        self._cleanup()

    def _pull_remote(self):
        """从传输层拉取对端的新信封。"""
        other_side = self._other_side()
        remote_dir = "inbox/%s" % other_side.value
        env, result = self.transport.pull(remote_dir)
        if env:
            # 校验 + 写入本地 mirror DB
            try:
                self.mirror.upsert_task(env)
                self._log("pulled task %s from %s" % (env.task_id, other_side.value))
            except StaleVersionError:
                self._log("skipped stale task %s" % env.task_id)
            self.mirror.log_sync("pull", type(self.transport).__name__, env.task_id, True)

    def _process_inbox(self):
        """处理本地 inbox/ 里的信封。"""
        inbox = os.path.join(self.data_dir, "inbox")
        for fpath in sorted(os.listdir(inbox)):
            if not fpath.endswith(".rhop"):
                continue
            full_path = os.path.join(inbox, fpath)
            env = self._read_envelope(full_path)
            if not env:
                continue
            if self.side == Side.REQUESTER:
                self._process_as_requester(env)
            else:
                self._process_as_executor(env)

    def _process_as_executor(self, env):
        """任务端处理：领任务 → 执行 → 写结果。"""
        if env.status != TaskStatus.PENDING:
            return
        # 1. 标记 CLAIMED
        self.mirror.update_status(env.task_id, TaskStatus.CLAIMED)
        # 2. 标记 RUNNING
        self.mirror.update_status(env.task_id, TaskStatus.RUNNING)
        # 3. 执行任务
        try:
            result = self._execute_task(env.payload)
            # 4. 写结果
            self.mirror.update_status(env.task_id, TaskStatus.DONE, result=result)
            self._log("task %s done" % env.task_id)
        except Exception as e:
            # 5. 写错误
            self.mirror.update_status(env.task_id, TaskStatus.FAILED, error=str(e))
            self._log("task %s failed: %s" % (env.task_id, e))
        # 6. 移动信封到 outbox/
        self._move_envelope(env.task_id, "outbox")

    def _execute_task(self, payload):
        """执行任务（子类可覆盖）。"""
        # 默认实现：根据 payload['cmd'] 执行 shell 命令
        # 或通过 payload['lang'] 选择执行器
        ...

    def _push_local(self):
        """推送本地变化给对端。"""
        other_side = self._other_side()
        remote_dir = "outbox/%s" % other_side.value
        # 从 mirror DB 读待推送的事件
        pending = self.mirror.pending_sync()
        for event in pending:
            env = self.mirror.get_task(event["task_id"])
            if env:
                result = self.transport.push(env, remote_dir)
                self.mirror.log_sync("push", type(self.transport).__name__, env.task_id, result.ok)

    def _other_side(self):
        return Side.EXECUTOR if self.side == Side.REQUESTER else Side.REQUESTER

    def _ensure_dirs(self):
        for d in ("inbox", "outbox", "processing", "failed", "tmp"):
            os.makedirs(os.path.join(self.data_dir, d), exist_ok=True)

    def _log(self, msg):
        print("[%s] [%s] %s" % (_now_iso(), self.side.value, msg))
```

### 7.3 CLI 入口

```python
# vools/rhop/daemon.py (续)

def main():
    """CLI 入口：rhop-daemon --config <path>"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="配置文件路径")
    args = parser.parse_args()
    config = load_config(args.config)
    daemon = RelayDaemon(config)
    # 注册信号处理
    import signal
    signal.signal(signal.SIGINT, daemon.stop)
    signal.signal(signal.SIGTERM, daemon.stop)
    daemon.start()

if __name__ == "__main__":
    main()
```

### 7.4 配置文件格式

```json
{
  "side": "requester",
  "data_dir": "/data/rhop",
  "poll_interval": 10,
  "transport": "auto",
  "git": {
    "repo_url": "https://github.com/user/rhop-relay.git",
    "branch": "main",
    "token": "$GITHUB_TOKEN"
  },
  "sftp": {
    "host": "10.0.0.1",
    "port": 22,
    "user": "relay",
    "password": "$SFTP_PASSWORD",
    "chroot_prefix": "/sftp"
  },
  "executor": {
    "command_template": "bash {cmd}",
    "timeout_sec": 3600
  }
}
```

---

## 八、业务 API（请求端 / 执行端）

### 8.1 Requester（需求端）

```python
# vools/rhop/requester.py

class Requester:
    """需求端业务封装：提交任务、查结果。"""

    def __init__(self, config):
        self.config = config
        self.mirror = MirrorDB(os.path.join(config["data_dir"], "mirror.db"))
        self.transport = create_transport(config)

    def submit(self, payload, *, task_id=None, priority=10):
        """提交任务。返回 task_id。"""
        if not task_id:
            task_id = "job-%s" % _now_iso().replace(":", "-").replace("-", "").replace("T", "-").replace("Z", "")
        env = Envelope(
            task_id=task_id,
            status=TaskStatus.PENDING,
            payload=payload,
            side=Side.REQUESTER,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        # 写本地 inbox
        self._write_inbox(env)
        # 写入 mirror DB
        self.mirror.upsert_task(env)
        # 立即尝试推送（daemon 也会定期推送，这里只是加速）
        try:
            other_side = Side.EXECUTOR
            self.transport.push(env, "outbox/%s" % other_side.value)
        except TransportUnavailable:
            pass  # daemon 会重试
        return task_id

    def get_result(self, task_id, *, timeout=600):
        """查询任务结果（轮询等待）。"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            env = self.mirror.get_task(task_id)
            if env and env.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return {"task_id": task_id, "status": env.status.value, "result": env.result, "error": env.error, "signature": env.signature}
            time.sleep(2)
        raise TimeoutError("task %s not done within %d sec" % (task_id, timeout))

    def list_tasks(self, *, status=None):
        """列出任务。"""
        return self.mirror.list_tasks(status=status)
```

### 8.2 Executor（任务端）

```python
# vools/rhop/executor.py

class Executor:
    """任务端业务封装：领任务、回结果。

    注意：正常情况下，daemon 自动处理。
    Executor 类提供手动 API，用于调试或特殊场景。
    """

    def __init__(self, config):
        self.config = config
        self.mirror = MirrorDB(os.path.join(config["data_dir"], "mirror.db"))

    def claim(self):
        """领一个 PENDING 任务。返回 Envelope 或 None。"""
        env = self.mirror.claim_task(worker_id="manual")
        if env:
            self._execute(env)
        return env

    def _execute(self, env):
        """执行任务（可子类覆盖）。"""
        ...

    def report_result(self, task_id, result, signature=None):
        """手动报告结果。"""
        self.mirror.update_status(task_id, TaskStatus.DONE, result=result, signature=signature)

    def report_failure(self, task_id, error):
        """手动报告失败。"""
        self.mirror.update_status(task_id, TaskStatus.FAILED, error=error)
```

---

## 九、完整性校验

```python
# vools/rhop/integrity.py

class IntegrityChecker:
    """信封完整性校验：checksum 比对 + 文件大小校验。"""

    @staticmethod
    def verify(env, raw_bytes):
        """校验信封字节是否完整。
        返回 (bool, error_msg)。
        """
        try:
            restored = Envelope.from_rhop_bytes(raw_bytes)
            return True, None
        except ValueError as e:
            return False, str(e)
```

---

## 十、真机签名

```python
# vools/rhop/signer.py

class AbstractSigner(object):
    def sign(self, task_id, result):
        raise NotImplementedError

    def verify(self, task_id, result, signature):
        raise NotImplementedError

class NPUSigner(AbstractSigner):
    """NPU 真机签名：调用 npu-smi + md5sum。"""

    def sign(self, task_id, result):
        # subprocess 调 npu-smi -q → 提取序列号
        # md5sum(json.dumps(result)) → 拼接 NPU_MARKER
        ...

    def verify(self, task_id, result, signature):
        # 解析 NPU_MARKER → 重算 md5 → 比对
        ...

class FileHashSigner(AbstractSigner):
    """通用文件哈希签名（非 NPU 场景兜底）。"""

    def sign(self, task_id, result):
        data = json.dumps({"task_id": task_id, "result": result}, sort_keys=True)
        return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()

    def verify(self, task_id, result, signature):
        expected = self.sign(task_id, result)
        return signature == expected
```

---

## 十一、Py3.6 基线

### 11.1 不使用

| 特性 | 最低版本 | 替代方案 |
|---|---|---|
| `@dataclass` | 3.7 | `@attr.s` (attrs) |
| `from __future__ import annotations` | 3.7 | 不用，用 `typing` 模块 |
| `f"{x=}"` | 3.8 | `"x=%r" % x` |
| `:=` (walrus) | 3.8 | 赋值 + 条件拆开写 |
| `match` | 3.10 | `if/elif` |
| `str.removeprefix()` | 3.9 | `s[2:]` 或 `re.sub` |
| `dict \| dict` | 3.9 | `dict1.update(dict2)` |
| `list[str]` / `dict[str, int]` | 3.9 | `List[str]` / `Dict[str, int]` |
| `typing.Literal` | 3.8 | `typing.Union[str, int]` + 文档 |
| `asyncio.run()` | 3.7 | `loop.run_until_complete()` |

### 11.2 使用

```python
from __future__ import absolute_import  # 安全，所有版本可用

from typing import Dict, List, Optional, Union, Any, Callable, Tuple
from enum import Enum
import attr
import json
import os
import sys
import sqlite3
import hashlib
import time
import subprocess
import signal
import argparse
```

### 11.3 测试矩阵

```
CI:
  Python 3.6  (基线，必须全绿)
  Python 3.10 (开发环境)
  Python 3.13 (最新)
```

---

## 十二、复用现有 vools 能力

| 能力 | 复用自 | 说明 |
|---|---|---|
| SFTP push/pull/sync | `vools-actus.jump` | paramiko 已写好，直接调用 |
| 加密 | `vools.pyk.configs` | Fernet + `PYK_SECRET_KEY`，可选 |
| 数据类 | `attrs` | Py3.6 兼容，vools 已有依赖 |
| 日志 | `vools.core` | 可选，保持轻量 |

**rhop 不依赖 pyspark、不依赖 paramiko（可选）、不依赖 psycopg2（可选）**。核心协议是纯 Python + SQLite + stdlib。

### 12.1 依赖声明

```toml
# vools-rhop/pyproject.toml
[project]
requires-python = ">=3.6"
dependencies = [
    "attrs>=20.3,<23; python_version < '3.7'",
]

[project.optional-dependencies]
sftp = ["paramiko>=2.12"]       # SFTP 传输
git = []                        # Git 用 subprocess 调系统 git，无需额外依赖
crypto = ["cryptography>=41.0"] # Fernet 加密
dev = ["pytest>=7.4", "pytest-cov>=4.1", "responses>=0.20"]
all = ["vools-rhop[sftp,crypto,dev]"]
```

---

## 十三、分阶段落地

### Phase 0 — 核心协议（1 周）

- [ ] `core.py` — Side 枚举 + TaskStatus + 基础数据结构
- [ ] `envelope.py` — .rhop 格式 + 序列化/反序列化 + checksum
- [ ] `mirror.py` — SQLite 镜像数据库 + schema + CRUD
- [ ] `config.py` — 配置文件加载（JSON / 环境变量）
- [ ] `integrity.py` — 完整性校验
- [ ] `tests/test_envelope.py` + `tests/test_mirror.py`
- [ ] **里程碑**：本地构造信封、写入 mirror DB、校验通过

### Phase 1 — 传输层（1 周）

- [ ] `transport/base.py` — AbstractTransport
- [ ] `transport/local.py` — 本地直连（测试用）
- [ ] `transport/git.py` — Git 仓库中继
- [ ] `transport/sftp.py` — SFTP 账密镜像（复用 actus.jump）
- [ ] `transport/textdp.py` — TextDP 骨架（待补全）
- [ ] `tests/test_transport_local.py` + `tests/test_transport_git.py`
- [ ] **里程碑**：本地 Git 仓库双方 push/pull 跑通

### Phase 2 — Daemon（1 周）

- [ ] `daemon.py` — 常驻 daemon + 核心循环
- [ ] `bin/rhop-daemon` — CLI 入口 + 信号处理
- [ ] `tests/test_daemon.py` — 本地 transport 下端到端测试
- [ ] **里程碑**：两个 daemon 进程在本地跑起来，任务从 A 到 B 自动执行并回结果

### Phase 3 — 业务 API（1 周）

- [ ] `requester.py` — 需求端 API（submit / get_result / list_tasks）
- [ ] `executor.py` — 任务端 API（claim / report_result / report_failure）
- [ ] `signer.py` — 真机签名（NPU_MARKER + 通用哈希）
- [ ] `examples/requester_only.py` + `examples/executor_only.py`
- [ ] **里程碑**：需求端 submit → daemon 自动推 → 任务端 daemon 自动执行 → 结果自动回 → 需求端 get_result 拿到

### Phase 4 — 硬化 + 发布（1 周）

- [ ] `tests/test_py36_compat.py` — Py3.6 全模块导入 + 运行
- [ ] `README.md` + `docs/ARCHITECTURE.md`
- [ ] `examples/git_relay.py` + `examples/sftp_mirror.py`
- [ ] CI 矩阵 (Py3.6/3.10/3.13)
- [ ] PyPI 发布 v0.1.0
- [ ] **里程碑**：Py3.6 全绿，真机 SFTP 端到端跑通

---

## 十四、测试策略

### 14.1 关键测试用例

```python
# tests/test_mirror.py
def test_upsert_task_version_conflict():
    """version 不递增时拒绝写入。"""
    ...

def test_mirror_sync_log():
    """sync_log 记录 push/pull 结果。"""
    ...

# tests/test_daemon.py
def test_daemon_pull_push_local():
    """LocalTransport 下：A submit → A daemon push → B daemon pull → B execute → B push result → A pull result。"""
    ...

def test_daemon_idempotent():
    """同一信封重复处理不产生副作用。"""
    ...

def test_daemon_graceful_stop():
    """SIGTERM 后优雅退出，不丢任务。"""
    ...

# tests/test_transport_git.py
def test_git_push_pull_roundtrip():
    """git push → 另一侧 git pull → 读到同一个信封。"""
    ...

# tests/test_py36_compat.py
def test_all_modules_import():
    """Py3.6 下所有模块可导入。"""
    ...
```

### 14.2 故障注入

```python
def test_inject_transport_unavailable():
    """传输层不可用时，daemon 不崩溃，持续重试。"""
    ...

def test_inject_checksum_corruption():
    """信封被篡改（checksum 不匹配），daemon 丢弃并记录。"""
    ...

def test_inject_partial_transfer():
    """SFTP 传输中断（文件不完整），integrity 检出。"""
    ...
```

---

## 十五、风险与开放问题

### 15.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| Git 仓库速率限制 | 高频 push 被限 | 批量 push + 指数退避重试 |
| SFTP 服务器不可达 | 离线传输失败 | 降级到 local（手动搬运）+ 持续重试 |
| 镜像 DB 版本冲突 | 数据覆盖 | 乐观锁 + 冲突日志 |
| daemon 被杀死未恢复 | 任务卡住 | 启动时恢复 processing/ 里的任务 |
| Py3.6 无 dataclasses | 数据类不可用 | attrs (vools 已有依赖) |

### 15.2 开放问题（待你确认）

1. **Q1: TextDP 具体是什么？** 是某个工具？某个协议？还是需要我设计一个文本数据平面？目前只搭了骨架。
2. **Q2: 执行器怎么注册？** 任务端收到 payload 后，怎么知道用什么命令执行？是 payload 里写 `cmd` 字段直接执行？还是注册 handler？
3. **Q3: 需求端是否需要"撤回"能力？** 任务提交后能不能取消？目前状态机支持 PENDING → CANCELLED，但 daemon 推送后对端可能已领走。
4. **Q4: 信封 payload 大小限制？** SFTP 和 Git 都有文件大小限制。大文件走独立通道？
5. **Q5: 多工作地/多仓库？** 如果需求端要同时和多个任务端通信（不同 Git 仓库），怎么配置？目前只支持一对一边。

---

## 十六、一句话总结

> vools-rhop 是一个**两方对等镜像任务中继协议**：需求端和任务端各跑一个常驻 daemon，各持一份 SQLite 镜像数据库，通过自适应传输层（Git / SFTP / TextDP）交换任务信封，daemon 自动拉取、处理、推送、同步。Py3.6 基线，核心零外部依赖，SFTP/Git 可选。

---

## 附录 A：关键术语

| 术语 | 定义 |
|---|---|
| 需求端 (Requester) | 提交任务、等结果的一方 |
| 任务端 (Executor) | 领任务、执行、回结果的一方 |
| 镜像数据库 (Mirror DB) | 双方各持一份的 SQLite，schema 一致，daemon 负责同步 |
| 信封 (Envelope) | `.rhop` 文件，任务的最小传递单位 |
| Daemon | 常驻进程，轮询监控 inbox/，自动 push/pull/处理 |
| Transport | 传输后端（Git / SFTP / TextDP / Local），可插拔 |
| 乐观锁 | 用 `version` 字段防并发写入冲突 |

## 附录 B：与 temp.txt 建议的对照

| temp.txt 建议 | rhop v2 实现 |
|---|---|
| 文件作为任务载体 | envelope (.rhop 文件) |
| 两方传递信息 | daemon push/pull + transport |
| 镜像数据库 | MirrorDB (SQLite，双方共享 schema) |
| 联网用 Git 中继 | GitTransport (push/pull 到共享仓库) |
| 不联网用 SFTP | SFTPTransport (账密镜像文件夹) |
| 双方常驻程序 | RelayDaemon (双方共用，side 参数区分) |
| 监控新文件 | daemon 轮询 inbox/ + transport.pull() |
| Py3.6 基线 | attrs + stdlib + subprocess，零现代 Python 特性 |
| 通用性 | 传输层抽象，后端可插拔 |
