"""vools.rhop.envelope - 任务信封 (.rhop 文件格式)

Py3.6 基线：不用 dataclasses，用 attrs 代替。

设计要点：
  - v: 1 写在第一个字段（向前兼容）
  - version 乐观锁：镜像同步时防冲突
  - checksum 在序列化时计算，覆盖整个 payload + 元数据
  - hops_seen 审计链：每次 daemon 处理后追加自己的 side
  - 信封不含密钥——密钥在配置侧管理
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

import attr

from .core import Side, TaskStatus


@attr.s(slots=True)
class Envelope:
    """任务信封：镜像任务中继协议的最小传递单位。"""

    task_id = attr.ib(type=str)
    status = attr.ib(type=TaskStatus)
    payload = attr.ib(type=dict)                           # 任务载荷
    result = attr.ib(type=object, default=None)            # 执行结果
    error = attr.ib(type=str, default=None)                # 错误信息
    side = attr.ib(type=Side, default=Side.REQUESTER)      # 谁创建的
    version = attr.ib(type=int, default=1)                 # 乐观锁版本号
    created_at = attr.ib(type=str, default="")             # ISO 时间戳
    updated_at = attr.ib(type=str, default="")
    hops_seen = attr.ib(factory=list)                      # 审计链
    signature = attr.ib(type=str, default=None)            # 真机签名
    checksum = attr.ib(type=str, default="")               # 内容哈希

    def __attrs_post_init__(self):
        """Compute checksum on construction if not provided."""
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute sha256 checksum of envelope content (without checksum field)."""
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
            "hops_seen": list(self.hops_seen),
            "signature": self.signature,
        }
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
            "hops_seen": list(self.hops_seen),
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
        expected = "sha256:" + hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
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

    def to_dict(self):
        """转为 dict（便于序列化存储）。"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "side": self.side.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "hops_seen": list(self.hops_seen),
            "signature": self.signature,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Envelope":
        """从 dict 构造。"""
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
            checksum=data.get("checksum", ""),
        )
