"""vools.rhop.task.sync - 「双方各自持库」模式的加密同步层

当共享介质无法承载"同一个 SQLite 文件被双方同时读写"时（跨机网络盘、SFTP/Git
形态、或就是不想让两个人同时写一个文件），改用 ``store.kind = sqlite-local``：
两边各持一个本地库，靠本模块把两边收敛成"同样的库"。

同步协议刻意做得极简、无冲突：

* 两个**单向文档**，各自只由一方写、另一方读，天然不会互相覆盖：
      ``<name>.a2b.rhop``  A 写（任务定义 + 取消请求）→ B 读
      ``<name>.b2a.rhop``  B 写（任务状态 + 结果）      → A 读
* 文档整体用 rhop 密钥加密（共享介质上只出现密文）；
* 合并规则按 ``task_name`` 幂等 + ``version`` 单调：旧版本整条丢弃
  （与 ``mirror.py`` 的乐观锁语义一致），因此重复同步、乱序同步都安全；
* 重置意图走专门的 ``resets`` 通道（``request_reset``）：A 端只登记意图、不改本地状态，
  B 端据此重跑并回推 —— 这样双方的版本算术始终对齐，不会出现「A 端本地改状态后把对端
  较新的状态永久挡在版本门外」的发散（BUG-280）。
* 不做目录枚举，只读写这两个固定文件名，所以 SFTP / Git 形态的介质也能用。

注意：A→B 的任务定义会带上 ``payload_enc``（本身就是密文），文档再整体加密一次，
属于"密文套密文"，任何一方拿到介质文件都读不出明文。
"""

from __future__ import absolute_import

import logging
from typing import Any, Dict, List, Optional

from ..session import Role
from .errors import RhopTaskError
from .models import TaskRecord, TaskState, utcnow_iso

log = logging.getLogger("vools.rhop.task.sync")

#: 同步文档版本
SYNC_VERSION = 1

#: 任务定义同步字段（与 TaskRecord 对齐）
TASK_SYNC_FIELDS = (
    "task_name", "task_type", "value", "deps", "priority", "timeout_min",
    "retry_delay_min", "max_retries", "scheduled_at", "payload_enc", "payload_sha",
    "tags", "queue", "owner", "team", "group_name", "extra_desc", "version",
    "created_at", "state",
)

#: 状态同步字段
STATE_SYNC_FIELDS = (
    "task_name", "state", "version", "back_info", "last_err", "worker_id",
    "lock_time", "start_time", "end_time", "expire_time", "retry_count",
    "scheduled_at", "cancel_requested",
)


class TaskSync(object):
    """本地库模式的加密双向同步（两个单向文档）。"""

    def __init__(self, store: Any, crypto: Any, role: str,
                 shared: Any = None, name: str = "rhop",
                 a2b_file: Optional[str] = None, b2a_file: Optional[str] = None,
                 limit: int = 5000):
        self.store = store
        self.crypto = crypto
        self.role = role
        self.shared = shared
        self.name = str(name or "rhop")
        self.a2b_file = a2b_file or "%s.a2b.rhop" % self.name
        self.b2a_file = b2a_file or "%s.b2a.rhop" % self.name
        self.limit = int(limit or 5000)
        self.last_pull = None  # type: Optional[Dict[str, Any]]
        self.last_push = None  # type: Optional[Dict[str, Any]]
        #: 待下发的重置意图 {task_name: A 端请求时的 version}
        #: A 端 requeue/retry_failed 只登记意图、不改本地状态（否则本地 version+1 会把 B 的
        #: 较新状态永久挡在 apply_state 的单调版本门之外，造成双方永久发散——BUG-280 的根因）。
        self._resets = {}  # type: Dict[str, int]

    # ------------------------------------------------------------------
    # 文档读写（加密）
    # ------------------------------------------------------------------

    def _require(self) -> Any:
        if self.shared is None:
            raise RhopTaskError(
                "本地库模式（sqlite-local）需要 shared path 才能同步："
                "请在配置里补 shared.write/shared.read 指向双方共同可达的介质。")
        if self.crypto is None:
            raise RhopTaskError("同步需要密钥：请在配置里提供 key。")
        return self.shared

    def _write_doc(self, filename: str, doc: Dict[str, Any]) -> str:
        shared = self._require()
        text = self.crypto.encrypt_json(doc)
        return shared.write_text(filename, text)

    def _read_doc(self, filename: str) -> Optional[Dict[str, Any]]:
        shared = self._require()
        try:
            text = shared.read_text(filename)
        except FileNotFoundError:
            return None
        except Exception as exc:
            log.warning("读取同步文档 %s 失败: %s", filename, exc)
            return None
        if not text or not text.strip():
            return None
        result = self.crypto.decrypt_verify(text)
        if not result.ok:
            log.warning("同步文档 %s 解密失败: %s（密钥是否一致？）", filename, result.reason)
            return None
        return result.payload if isinstance(result.payload, dict) else None

    # ------------------------------------------------------------------
    # A → B：任务定义 + 取消请求
    # ------------------------------------------------------------------

    def push_tasks(self, records: Optional[List[TaskRecord]] = None) -> Dict[str, Any]:
        """A 侧：把任务定义（可增量）合并进 a2b 文档并落盘。"""
        if records is None:
            records = self.store.list_tasks(limit=self.limit)
        incoming = {}
        for rec in records:
            if rec is None:
                continue
            # deps/tags 在 record 上是 VList（非 list 子类，json 不认），序列化边界转 plain list
            incoming[rec.task_name] = {
                k: (list(v) if k in ("deps", "tags") and v is not None else v)
                for k, v in ((fk, getattr(rec, fk, None)) for fk in TASK_SYNC_FIELDS)
            }

        existing = self._read_doc(self.a2b_file) or {}
        merged = {}
        for item in existing.get("tasks") or []:
            if isinstance(item, dict) and item.get("task_name"):
                merged[str(item["task_name"])] = item
        merged.update(incoming)

        cancels = sorted({name for name, rec in self.store_map().items()
                          if rec.cancel_requested or rec.state == TaskState.CANCELLED})
        doc = {
            "v": SYNC_VERSION,
            "kind": "tasks",
            "from": "A",
            "sent_at": utcnow_iso(),
            "tasks": [merged[k] for k in sorted(merged.keys())],
            "cancels": cancels,
            # 重置意图：B 端据此重跑并回推，A 端据此收敛（见 request_reset 注释）
            "resets": [{"task_name": k, "at_version": v} for k, v in sorted(self._resets.items())],
        }
        path = self._write_doc(self.a2b_file, doc)
        self.last_push = {"pushed": len(incoming), "total": len(merged),
                          "cancels": len(cancels), "resets": len(self._resets),
                          "file": self.a2b_file, "path": path}
        return self.last_push

    # ------------------------------------------------------------------
    # A → B：重置意图（requeue / retry_failed 的本地库模式专用通道）
    # ------------------------------------------------------------------

    def request_reset(self, task_name: str, at_version: Optional[int] = None) -> Dict[str, Any]:
        """登记一次重置意图（A 侧）。**不改本端状态**，只把它写进 a2b 文档交 B 执行。

        Args:
            task_name:    任务名
            at_version:   请求时的本端版本（缺省取当前版本）；B 端据此做幂等判定：
                          只有版本仍停在 at_version 的任务才真正重跑。

        Returns:
            {"task_name", "ok", "at_version"}（任务不存在时 ok=False）

        为什么不能由 A 直接把状态改成 PENDING：本地库模式下 A 这么一改，A 的版本就比 B 大了，
        B 之后的状态回推会被 apply_state 的『版本必须严格递增』永久丢弃 → 双方发散（BUG-280）。
        正确姿势是让对端把「重置 → 重跑 → 回推」做完，A 再收敛到对端的版本。
        """
        rec = self.store.get_task(task_name)
        if rec is None:
            return {"task_name": task_name, "ok": False,
                    "reason": "任务不存在（或尚未同步到本端）"}
        version = int(at_version if at_version is not None else rec.version)
        self._resets[str(task_name)] = version
        self.push_tasks()          # 立即落盘，不等下一轮 push
        return {"task_name": str(task_name), "ok": True, "at_version": version}

    # ------------------------------------------------------------------
    # B → A：任务状态 + 结果
    # ------------------------------------------------------------------

    def push_states(self) -> Dict[str, Any]:
        """B 侧：把当前状态快照写进 b2a 文档。"""
        states = []
        records = self.store.list_tasks(limit=self.limit)
        for rec in records:
            states.append({k: getattr(rec, k, None) for k in STATE_SYNC_FIELDS})
        doc = {
            "v": SYNC_VERSION,
            "kind": "states",
            "from": "B",
            "sent_at": utcnow_iso(),
            "states": states,
        }
        path = self._write_doc(self.b2a_file, doc)
        self.last_push = {"pushed": len(states), "file": self.b2a_file, "path": path}
        return self.last_push

    def store_map(self) -> Dict[str, TaskRecord]:
        """当前库里的任务（按 task_name）。"""
        return {rec.task_name: rec for rec in self.store.list_tasks(limit=self.limit)}

    # ------------------------------------------------------------------
    # 拉取并应用
    # ------------------------------------------------------------------

    def pull(self) -> Dict[str, Any]:
        """读对端文档并应用（按本端方向决定读哪个文件）。

        Returns:
            {"applied": n, "inserted": n, "updated": n, "stale": n, "missing": n,
             "cancels": n, "file": ..., "skipped": bool}
        """
        stats = {"applied": 0, "inserted": 0, "updated": 0, "stale": 0,
                 "missing": 0, "cancels": 0, "resets": 0, "file": None, "skipped": False}
        if self.role == Role.SEND:      # A 读 B 的状态
            doc = self._read_doc(self.b2a_file)
            stats["file"] = self.b2a_file
            if doc is None:
                stats["skipped"] = True
                self.last_pull = stats
                return stats
            for item in doc.get("states") or []:
                if not isinstance(item, dict) or not item.get("task_name"):
                    continue
                try:
                    outcome = self.store.apply_state(item)
                except Exception as exc:
                    log.warning("应用状态 %s 失败: %s", item.get("task_name"), exc)
                    continue
                stats[outcome] = stats.get(outcome, 0) + 1
                if outcome == "updated":
                    stats["applied"] += 1
            # A 侧：对端版本已推进过重置请求 → 该重置被消费，撤销意图
            for name in list(self._resets.keys()):
                rec = self.store.get_task(name)
                if rec is not None and rec.version > self._resets[name]:
                    del self._resets[name]
        elif self.role == Role.RECV:    # B 读 A 的任务定义
            doc = self._read_doc(self.a2b_file)
            stats["file"] = self.a2b_file
            if doc is None:
                stats["skipped"] = True
                self.last_pull = stats
                return stats
            for item in doc.get("tasks") or []:
                if not isinstance(item, dict) or not item.get("task_name"):
                    continue
                try:
                    outcome = self.store.apply_task(TaskRecord.from_dict(item))
                except Exception as exc:
                    log.warning("应用任务 %s 失败: %s", item.get("task_name"), exc)
                    continue
                stats[outcome] = stats.get(outcome, 0) + 1
                if outcome != "stale":
                    stats["applied"] += 1
            for name in doc.get("cancels") or []:
                try:
                    if self.store.set_cancel_requested(str(name), True):
                        stats["cancels"] += 1
                except Exception as exc:
                    log.warning("应用取消请求 %s 失败: %s", name, exc)
            # 重置意图：B 端真正重跑（版本+1 → PENDING），后续执行与状态回推即可让 A 收敛
            for item in doc.get("resets") or []:
                if isinstance(item, dict):
                    name, at_version = item.get("task_name"), int(item.get("at_version") or 0)
                else:
                    name, at_version = item, 0
                if not name:
                    continue
                name = str(name)
                rec = self.store.get_task(name)
                if rec is None:
                    continue
                if rec.version > at_version:      # 已推进过 ⇒ 幂等跳过，不重复重置
                    continue
                try:
                    if self.store.requeue(name):
                        stats["resets"] += 1
                except Exception as exc:
                    log.warning("应用重置请求 %s 失败: %s", name, exc)
        self.last_pull = stats
        return stats

    def describe(self) -> Dict[str, Any]:
        """自描述。"""
        return {
            "mode": "sqlite-local",
            "role": self.role,
            "a2b_file": self.a2b_file,
            "b2a_file": self.b2a_file,
            "has_shared": self.shared is not None,
            "pending_resets": sorted(self._resets),
            "last_push": self.last_push,
            "last_pull": self.last_pull,
        }


__all__ = ["TaskSync", "TASK_SYNC_FIELDS", "STATE_SYNC_FIELDS", "SYNC_VERSION"]