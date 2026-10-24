"""vools.rhop.requester - 需求端业务 API（提交任务/查结果）

需求端封装：submit / get_result / list_tasks
"""

import os
import time
from typing import Dict, List, Optional

from .core import Side, TaskStatus
from .envelope import Envelope
from .mirror import MirrorDB


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Requester:
    """需求端业务封装：提交任务、查结果。"""

    def __init__(self, config: dict):
        self.config = config
        self.data_dir = config.get("data_dir", "./rhop-data")
        self.mirror = MirrorDB(os.path.join(self.data_dir, "mirror.db"))
        self._ensure_dirs()

    def submit(self, payload: dict, *, task_id: str = None, priority: int = 10) -> str:
        """提交任务。返回 task_id。"""
        if not task_id:
            task_id = "job-%s" % _now_iso().replace(":", "").replace("-", "").replace("T", "-")
        env = Envelope(
            task_id=task_id,
            status=TaskStatus.PENDING,
            payload=payload,
            side=Side.REQUESTER,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        # 写本地 inbox
        inbox_path = os.path.join(self.data_dir, "inbox", "%s.rhop" % task_id)
        with open(inbox_path, "wb") as fh:
            fh.write(env.to_rhop_bytes())
        # 写入 mirror DB
        self.mirror.upsert_task(env)
        return task_id

    def get_result(self, task_id: str, *, timeout: int = 600) -> Optional[dict]:
        """查询任务结果（轮询等待）。

        dict: {"task_id", "status", "result", "error", "signature"}
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            env = self.mirror.get_task(task_id)
            if env and env.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return {
                    "task_id": task_id,
                    "status": env.status.value,
                    "result": env.result,
                    "error": env.error,
                    "signature": env.signature,
                }
            time.sleep(2)
        return None

    def list_tasks(self, *, status: str = None) -> List[dict]:
        """列出任务。"""
        ts = TaskStatus(status) if status else None
        tasks = self.mirror.list_tasks(status=ts)
        return [t.to_dict() for t in tasks]

    def cancel(self, task_id: str) -> bool:
        """取消任务（仅 PENDING 状态可取消）。

        Q3 默认决策：推送后对端可能已领走，取消尽力而为。
        """
        try:
            self.mirror.update_status(task_id, TaskStatus.CANCELLED)
            return True
        except ValueError:
            return False

    def _ensure_dirs(self):
        for d in ("inbox", "outbox", "processing", "failed", "tmp"):
            os.makedirs(os.path.join(self.data_dir, d), exist_ok=True)

    def close(self):
        self.mirror.close()
