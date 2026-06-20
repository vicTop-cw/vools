"""
SQLite存储层 - 处理任务持久化和并发控制
"""

__all__ = ['TaskStorage']

import sqlite3
import uuid
import json
from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timedelta
from contextlib import contextmanager

from .models import Task, TaskStatus


class TaskStorage:
    """任务存储管理器（线程安全）"""

    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """获取新的数据库连接（每次都创建新连接）"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # 启用WAL模式提高并发
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _transaction(self, immediate: bool = False):
        """事务上下文管理器"""
        conn = self._get_connection()
        try:
            if immediate:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute("BEGIN TRANSACTION")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        """初始化数据库表结构"""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    task_func TEXT NOT NULL,
                    args TEXT,
                    kwargs TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    priority INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    worker_id TEXT,
                    lease_timeout TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_priority
                ON tasks (status, priority DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_worker_lease
                ON tasks (worker_id, lease_timeout)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id INTEGER NOT NULL,
                    depends_on_id INTEGER NOT NULL,
                    PRIMARY KEY (task_id, depends_on_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY (depends_on_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dep_task
                ON task_dependencies (task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dep_depends
                ON task_dependencies (depends_on_id)
            """)

    def insert_task(self, task: Task) -> int:
        """插入新任务"""
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO tasks
                (task_name, task_func, args, kwargs, status, priority, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_name,
                task.task_func,
                json.dumps(task.args),
                json.dumps(task.kwargs),
                task.status.value,
                task.priority,
                task.max_retries,
            ))
            task_id = cursor.lastrowid
            for dep_id in task.dependencies:
                conn.execute("""
                    INSERT OR IGNORE INTO task_dependencies (task_id, depends_on_id)
                    VALUES (?, ?)
                """, (task_id, dep_id))
            return task_id

    def claim_task(self, worker_id: str, lease_seconds: int = 300) -> Optional[Task]:
        """
        原子领取任务（关键并发控制）

        使用UPDATE ... RETURNING确保原子性，同时处理过期租约的任务
        """
        lease_timeout = (datetime.now() + timedelta(seconds=lease_seconds)).isoformat()
        now = datetime.now().isoformat()

        with self._transaction(immediate=True) as conn:
            # 先处理过期租约的任务
            conn.execute("""
                UPDATE tasks
                SET status = 'PENDING',
                    worker_id = NULL,
                    lease_timeout = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE status IN ('RUNNING', 'RETRYING')
                AND lease_timeout < ?
            """, (now,))

            # 原子领取可用任务
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'RUNNING',
                    worker_id = ?,
                    lease_timeout = ?,
                    started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM tasks
                    WHERE status = 'PENDING'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                )
                RETURNING *
            """, (worker_id, lease_timeout))

            row = cursor.fetchone()
            if row:
                return self._row_to_task(row)
            return None

    def update_task_status(self, task_id: int, status: TaskStatus,
                          error_message: Optional[str] = None,
                          result: Any = None,
                          worker_id: Optional[str] = None) -> bool:
        """更新任务状态"""
        now = datetime.now().isoformat()
        with self._transaction(immediate=True) as conn:
            # 构建更新语句
            updates = {
                "status": status.value,
                "updated_at": now,
            }

            if worker_id is not None:
                updates["worker_id"] = worker_id

            if status == TaskStatus.SUCCESS:
                updates["completed_at"] = now
                updates["lease_timeout"] = None
                if result is not None:
                    updates["result"] = json.dumps(result)
            elif status == TaskStatus.FAILED:
                updates["completed_at"] = now
                updates["lease_timeout"] = None
                if error_message:
                    updates["error_message"] = error_message
            elif status == TaskStatus.RETRYING:
                updates["retry_count"] = self._get_retry_count(conn, task_id) + 1

            # 构建SQL
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            params = list(updates.values()) + [task_id]

            # 只允许更新属于该worker的任务或未分配任务
            if worker_id:
                cursor = conn.execute(f"""
                    UPDATE tasks
                    SET {set_clause}
                    WHERE id = ? AND (worker_id = ? OR worker_id IS NULL)
                """, params + [worker_id])
            else:
                cursor = conn.execute(f"""
                    UPDATE tasks
                    SET {set_clause}
                    WHERE id = ?
                """, params)

            return cursor.rowcount > 0

    def _get_retry_count(self, conn: sqlite3.Connection, task_id: int) -> int:
        """获取当前重试次数"""
        cursor = conn.execute("SELECT retry_count FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_task(self, task_id: int) -> Optional[Task]:
        """获取任务详情"""
        with self._transaction() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return self._row_to_task(row) if row else None

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """按状态获取任务列表"""
        with self._transaction() as conn:
            cursor = conn.execute("""
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY priority DESC, created_at ASC
            """, (status.value,))
            return [self._row_to_task(row) for row in cursor.fetchall()]

    def cancel_task(self, task_id: int) -> bool:
        """取消任务"""
        with self._transaction(immediate=True) as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'CANCEL',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('PENDING', 'RUNNING', 'RETRYING')
            """, (task_id,))
            return cursor.rowcount > 0

    def retry_task(self, task_id: int) -> bool:
        """手动重试失败任务"""
        with self._transaction(immediate=True) as conn:
            cursor = conn.execute("""
                UPDATE tasks
                SET status = 'PENDING',
                    worker_id = NULL,
                    lease_timeout = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'FAILED'
            """, (task_id,))
            return cursor.rowcount > 0

    def cleanup_old_tasks(self, days: int = 7) -> int:
        """清理旧任务"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._transaction(immediate=True) as conn:
            cursor = conn.execute("""
                DELETE FROM tasks
                WHERE completed_at < ?
            """, (cutoff,))
            return cursor.rowcount

    def generate_worker_id(self) -> str:
        """生成唯一Worker ID"""
        return str(uuid.uuid4())

    def _row_to_task(self, row: tuple) -> Task:
        """将数据库行转换为Task对象"""
        # 获取列名
        columns = [
            "id", "task_name", "task_func", "args", "kwargs", "status",
            "priority", "retry_count", "max_retries", "error_message", "result",
            "created_at", "updated_at", "started_at", "completed_at",
            "worker_id", "lease_timeout"
        ]
        data = dict(zip(columns, row))
        return Task.from_dict(data)
