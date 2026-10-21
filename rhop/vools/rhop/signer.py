"""vools.rhop.signer - 真机签名

AbstractSigner       — 签名抽象
NPUSigner            — NPU 真机签名（调用 npu-smi + md5sum）
FileHashSigner       — 通用文件哈希签名（非 NPU 场景兜底）
"""

import hashlib
import json
import subprocess
from typing import Optional


class AbstractSigner(object):
    """签名抽象基类。"""

    def sign(self, task_id: str, result) -> Optional[str]:
        """对结果签名，返回签名字符串。"""
        raise NotImplementedError

    def verify(self, task_id: str, result, signature: str) -> bool:
        """验证签名。"""
        raise NotImplementedError


class FileHashSigner(AbstractSigner):
    """通用文件哈希签名（非 NPU 场景兜底）。

    签名格式: sha256:<hex>
    签名内容: json.dumps({"task_id": ..., "result": ...}, sort_keys=True)
    """

    def sign(self, task_id: str, result) -> str:
        data = json.dumps({"task_id": task_id, "result": result}, sort_keys=True)
        return "sha256:" + hashlib.sha256(data.encode("utf-8")).hexdigest()

    def verify(self, task_id: str, result, signature: str) -> bool:
        expected = self.sign(task_id, result)
        return signature == expected


class NPUSigner(AbstractSigner):
    """NPU 真机签名：调用 npu-smi + md5sum。

    签名格式: NPU_MARKER:<serial>:<md5>
    其中 serial 来自 npu-smi -q 的序列号提取。
    """

    def __init__(self, marker="NPU_MARKER"):
        self._marker = marker

    def _get_npu_serial(self) -> Optional[str]:
        """从 npu-smi -q 提取序列号。"""
        try:
            out = subprocess.check_output(
                ["npu-smi", "-q"], stderr=subprocess.DEVNULL, timeout=10
            ).decode("utf-8", errors="replace")
            for line in out.splitlines():
                lower = line.lower()
                if "serial" in lower or "sn" in lower:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return parts[-1].strip()
            return "UNKNOWN_NPU"
        except Exception:
            return None

    def sign(self, task_id: str, result) -> Optional[str]:
        serial = self._get_npu_serial()
        if serial is None:
            return None
        data = json.dumps({"task_id": task_id, "result": result}, sort_keys=True)
        md5 = hashlib.md5(data.encode("utf-8")).hexdigest()
        return "{0}:{1}:{2}".format(self._marker, serial, md5)

    def verify(self, task_id: str, result, signature: str) -> bool:
        expected = self.sign(task_id, result)
        if expected is None:
            return False
        return signature == expected
