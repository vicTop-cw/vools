"""
任务队列后端（多后端抽象）。

支持：
    - pg      : PostgreSQL 持久化队列（对标 look_upon，多 Worker 竞争）
    - sqlite  : SQLite 持久化队列（vools.task 现有 TaskStorage）
    - memory  : 内存队列（测试/轻量场景）

用法：
    from vools.task.backends import create_backend
    backend = create_backend("pg", dsn="host=... dbname=...")
    backend.init_table()
    tid = backend.submit("my_task", {"cli": {"cmd": "echo hi"}})
"""

__all__ = ['create_backend', 'BackendBase']

from typing import Any, Dict, Optional


class BackendBase:
    """后端抽象基类（接口约定）。"""

    def init_table(self, drop_if_exists: bool = False):
        raise NotImplementedError

    def submit(self, task_name: str, payload: Optional[Dict[str, Any]] = None,
               **kwargs) -> int:
        raise NotImplementedError

    def acquire(self, worker_id: str, timeout_min: int = 5,
                states: Optional[list] = None) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def complete(self, task_id: int, worker_id: str, back_info: Optional[Dict[str, Any]] = None):
        raise NotImplementedError

    def fail(self, task_id: int, worker_id: str, error: str):
        raise NotImplementedError

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def close(self):
        pass


def create_backend(kind: str = "memory", **kwargs) -> BackendBase:
    """创建后端实例。"""
    kind = (kind or "memory").lower()
    if kind == "pg" or kind == "postgres" or kind == "postgresql":
        from .pg import PgTaskBackend
        return PgTaskBackend(**kwargs)
    elif kind == "sqlite":
        # 包装 vools.task 现有 TaskStorage 为 backend
        from .sqlite_backend import SqliteTaskBackend
        return SqliteTaskBackend(**kwargs)
    elif kind == "memory":
        from .memory_backend import MemoryTaskBackend
        return MemoryTaskBackend(**kwargs)
    else:
        raise ValueError("未知后端类型: %s（可用: pg / sqlite / memory）" % kind)