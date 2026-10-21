"""vools.rhop - 双方对等镜像任务中继协议（MVP + 配置驱动地基 + v2 镜像 DB / 状态机 / 业务 API + 通用任务队列）。"""

__version__ = "0.2.0"

from . import actions, config, crypto, core, interact, session  # noqa: F401

# v2 镜像 daemon / 业务 API
from .core import Side, TaskStatus  # noqa: F401
from .envelope import Envelope  # noqa: F401
from .mirror import MirrorDB, StaleVersionError  # noqa: F401
from .integrity import IntegrityChecker  # noqa: F401
from .daemon import RelayDaemon  # noqa: F401
from .requester import Requester  # noqa: F401
from .executor import Executor  # noqa: F401
from .signer import AbstractSigner, FileHashSigner, NPUSigner  # noqa: F401

# 通用任务队列（A 提交加密 JSON 指令 → B 解密执行；SQLite 管依赖/状态；存储可换后端）
from . import task  # noqa: F401
from .task import (  # noqa: F401
    TaskConfig,
    TaskDaemon,
    TaskQueue,
    TaskRecord,
    TaskState,
    TaskStore,
    create_store,
    register_store,
)
