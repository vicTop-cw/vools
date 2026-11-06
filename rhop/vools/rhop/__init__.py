"""vools.rhop - 双方对等镜像任务中继协议（MVP + 配置驱动地基 + v2 镜像 DB / 状态机 / 业务 API + 通用任务队列）。"""

__version__ = "0.9.0"

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
from .task.local_runner import (  # noqa: F401
    mark_local_result,
    run_local_task,
    should_run_local,
)

# 节点侧能力：目录同步守护 + 剪贴板共享（对标 p2 SyncFolder / p0-p1 monitorclip）
from .sync_folder import (  # noqa: F401
    LocalDirSource,
    SyncFolder,
    sync_folder_once,
)
from .clipboard import (  # noqa: F401
    ClipboardFileSync,
    get_clipboard_backend,
    read_clipboard,
    write_clipboard,
)

# 压缩/解压能力（clone 自 clip/Jump/common/universal_compress.py，2026-11-06 增强）
from . import compress  # noqa: F401
from .compress import (  # noqa: F401
    ALGO_DEFAULT,
    compress,
    compress_bytes,
    compress_bytes_auto,
    compress_file,
    compress_many,
    csv_bytes_to_rows,
    decompress_bytes,
    detect_algo,
    pack_bytes,
    pack_dict,
    restore,
    restore_bytes,
    restore_bytes_to_bytes,
    restore_file,
    restore_many,
    rows_to_csv_bytes,
    unpack_dict,
    unpack_files,
    unpack_files_multi,
)
