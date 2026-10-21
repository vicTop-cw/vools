"""vools.rhop.executor - 任务端业务 API（领任务/回结果）

正常情况下 daemon 自动处理；此类提供手动 API，用于调试或特殊场景。
Q2 默认决策：payload 里写 cmd 字段直接执行，也支持注册 handler。
"""

import os
from typing import Callable, Optional

from .core import Side, TaskStatus
from .envelope import Envelope
from .mirror import MirrorDB


class Executor:
    """任务端业务封装：领任务、回结果。"""

    def __init__(self, config: dict):
        self.config = config
        self.data_dir = config.get("data_dir", "./rhop-data")
        self.mirror = MirrorDB(os.path.join(self.data_dir, "mirror.db"))
        self._executor_handler = config.get("executor_handler")
        signer_cfg = config.get("signer", {})
        from .signer import FileHashSigner, NPUSigner
        if signer_cfg.get("mode") == "npu":
            self._signer = NPUSigner(marker=signer_cfg.get("npu_marker", "NPU_MARKER"))
        else:
            self._signer = FileHashSigner()

    def claim(self, worker_id: str = "manual") -> Optional[Envelope]:
        """领一个 PENDING 任务。返回 Envelope 或 None。"""
        env = self.mirror.claim_task(worker_id=worker_id)
        return env

    def execute(self, env: Envelope) -> dict:
        """执行任务并回写结果。"""
        task_id = env.task_id
        # 从 CLAIMED → RUNNING
        try:
            self.mirror.update_status(task_id, TaskStatus.RUNNING)
        except ValueError:
            # 可能不是 CLAIMED 状态（如直接调用）
            pass
        try:
            if self._executor_handler is not None:
                result = self._executor_handler(env.payload)
            else:
                result = self._default_execute(env.payload)
            sig = self._signer.sign(task_id, result)
            self.mirror.update_status(task_id, TaskStatus.DONE, result=result, signature=sig)
            return {"task_id": task_id, "status": TaskStatus.DONE.value, "result": result, "signature": sig}
        except Exception as e:
            self.mirror.update_status(task_id, TaskStatus.FAILED, error=str(e))
            raise

    def _default_execute(self, payload: dict) -> dict:
        """默认执行器：按 payload['cmd'] 执行 shell 命令。"""
        import subprocess
        cmd = payload.get("cmd")
        if not cmd:
            raise ValueError("payload 缺少 cmd 字段")
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError("cmd exited %d: %s" % (result.returncode, result.stderr[:500]))
        return {"stdout": result.stdout, "returncode": result.returncode}

    def report_result(self, task_id: str, result, signature: str = None):
        """手动报告结果。"""
        self.mirror.update_status(task_id, TaskStatus.DONE, result=result, signature=signature)

    def report_failure(self, task_id: str, error: str):
        """手动报告失败。"""
        self.mirror.update_status(task_id, TaskStatus.FAILED, error=error)

    def list_pending(self) -> list:
        """列出 PENDING 任务。"""
        return [t.to_dict() for t in self.mirror.list_tasks(status=TaskStatus.PENDING)]

    def close(self):
        self.mirror.close()
