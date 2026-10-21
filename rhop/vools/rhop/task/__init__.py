"""vools.rhop.task - 通用任务队列（A 提交加密 JSON 指令 → B 解密执行）

对齐 ``vools.pyk.look_upon`` 的表结构与状态流转，去掉 P0..P3 跳板角色：
只按配置里的「方向（A/B/C）+ 介质 + 存储后端」运行；任务身份用 ``task_name``，
依赖用 ``task_name`` 列表表达。

快速上手::

    from vools.rhop.task import TaskConfig, TaskDaemon

    cfg = TaskConfig.from_file("rhop-A.json")     # role=A 提交方
    TaskDaemon(cfg).run_sender(tasks=[{"task_name": "hello",
                                       "cli": {"cmd": "echo hi"}}])

    cfgB = TaskConfig.from_file("rhop-B.json")    # role=B 执行方
    TaskDaemon(cfgB).run_executor()               # 常驻：心跳 + 领取 + 执行

命令行::

    python -m vools.rhop.task --config rhop-B.json serve
    python -m vools.rhop.task --config rhop-A.json submit --file tasks.json --wait

数据库抽象：``queue.store.kind`` 默认 ``sqlite-shared``（双方读写同一个库文件）；
介质无法同时读写时用 ``sqlite-local``（双方各持一个库 + 加密同步收敛）；
接入 PostgreSQL 等后端只需 ``register_store(kind, factory)``。
"""

from __future__ import absolute_import

# 基础模型与异常
from .errors import (  # noqa: F401
    DagValidationError,
    ExecDenied,
    HeartbeatError,
    PayloadError,
    PlaintextSecretError,
    RhopTaskError,
    SecretError,
    StoreError,
    StoreUnavailable,
    TaskNotFound,
)
from .models import (  # noqa: F401
    TaskRecord,
    TaskState,
    iso_add_seconds,
    parse_iso,
    utcnow,
    utcnow_iso,
)

# 配置 / 敏感信息
from .config import TaskConfig, load_task_config, normalize_role  # noqa: F401
from .secrets import (  # noqa: F401
    SECRET_ENC_COMMAND,
    find_secret_fields,
    mask_value,
    resolve_config_secrets,
)

# 存储抽象（可换后端）
from .store import (  # noqa: F401
    DEFAULT_STORE_KIND,
    SqliteTaskStore,
    TaskStore,
    available_store_kinds,
    create_store,
    register_store,
)

# 心跳 / 执行 / 队列 / 同步 / 常驻
from .heartbeat import Heartbeat, HeartbeatPump  # noqa: F401
from .exec import (  # noqa: F401
    ExecPolicy,
    cli_execute,
    get_handler,
    register_handler,
    run_payload,
)
from .queue import TaskQueue  # noqa: F401
from .sync import TaskSync  # noqa: F401
from .daemon import TaskDaemon, build_queue  # noqa: F401

__all__ = [
    # 异常
    "RhopTaskError", "DagValidationError", "TaskNotFound", "StoreUnavailable",
    "StoreError", "PayloadError", "ExecDenied", "HeartbeatError", "SecretError",
    "PlaintextSecretError",
    # 模型
    "TaskState", "TaskRecord", "utcnow", "utcnow_iso", "iso_add_seconds", "parse_iso",
    # 配置
    "TaskConfig", "load_task_config", "normalize_role",
    "resolve_config_secrets", "find_secret_fields", "mask_value", "SECRET_ENC_COMMAND",
    # 存储
    "TaskStore", "SqliteTaskStore", "create_store", "register_store",
    "available_store_kinds", "DEFAULT_STORE_KIND",
    # 心跳
    "Heartbeat", "HeartbeatPump",
    # 执行
    "ExecPolicy", "run_payload", "cli_execute", "register_handler", "get_handler",
    # 队列 / 同步 / 常驻
    "TaskQueue", "TaskSync", "TaskDaemon", "build_queue",
]