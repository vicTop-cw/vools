"""vools.rhop.envelope - 任务信封 (.rhop 文件格式)

Py3.6 兼容：用 vools.core.dataclass_compat 的 dataclass 代替 attrs。

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

from vools.core.dataclass_compat import dataclass, field

from .core import Side, TaskStatus


@dataclass
class Envelope:
    """任务信封：镜像任务中继协议的最小传递单位。"""

    task_id: str
    status: TaskStatus
    payload: dict
    result: Optional[object] = None
    error: Optional[str] = None
    side: Side = Side.REQUESTER
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    hops_seen: List[str] = field(default_factory=list)
    signature: Optional[str] = None
    checksum: str = ""

    def __post_init__(self):
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
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            raise ValueError("envelope JSON 解析失败: %s" % exc)
        checksum = data.pop("checksum", "")
        expected = "sha256:" + hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if checksum != expected:
            raise ValueError("checksum mismatch: envelope may be corrupted")
        # 缺失必填字段时抛 ValueError（而非 KeyError），保证 IntegrityChecker 能捕获
        try:
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
        except KeyError as exc:
            raise ValueError("envelope 缺少必填字段: %s" % exc)
        except ValueError as exc:
            raise ValueError("envelope 字段值非法: %s" % exc)

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
