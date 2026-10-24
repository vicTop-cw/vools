"""vools.rhop.sync_folder - 目录同步守护（对标 p2 SyncFolder：生产 Share → 拉回本地）

场景：生产节点把 parquet / xlsx 写进共享目录（UNC 映射盘 / RDP tsclient / 本地目录），
本节点轮询该目录，把**新出现或内容变化**的文件拉回本地 target_dir。幂等由 manifest
（``.sync_manifest.json``，记录 sha256）保证：内容没变的文件不会重复拉取。

设计要点：

* **source 适配器协议**（v1 内置 LocalDirSource，覆盖 UNC/映射盘/本地目录）::

      source.list_files()  -> List[str]          # 相对文件名（递归可选）
      source.open_bytes(name) -> bytes           # 二进制读

* **拉取判定**（三选一即拉）：target 缺文件 / manifest 无记录 / manifest sha256 与
  源不同（源端内容更新）。
* **二进制安全**：parquet/xlsx 等一律 bytes 读写，不做文本转换。
* **守护模式**：``run_forever(stop_event)`` 按 ``poll_interval`` 轮询，``stop_event.set()``
  优雅退出；单次模式用 ``sync_once()``。
"""

from __future__ import absolute_import

import fnmatch
import hashlib
import json
import os
import threading
from typing import Any, Callable, Dict, List, Optional

#: manifest 文件名（落在 target_dir，自身永不被拉取）
MANIFEST_NAME = ".sync_manifest.json"


class LocalDirSource(object):
    """本地目录（含 UNC 映射盘）源适配器。"""

    kind = "local-dir"

    def __init__(self, path: str, recursive: bool = False):
        self.path = str(path)
        self.recursive = bool(recursive)

    def list_files(self) -> List[str]:
        """列出相对文件名（recursive=True 时返回 ``rel/sub/name`` 形态）。"""
        if not os.path.isdir(self.path):
            return []
        out: List[str] = []
        if self.recursive:
            for root, _dirs, files in os.walk(self.path):
                for f in files:
                    full = os.path.join(root, f)
                    out.append(os.path.relpath(full, self.path).replace(os.sep, "/"))
        else:
            for f in os.listdir(self.path):
                if os.path.isfile(os.path.join(self.path, f)):
                    out.append(f)
        return sorted(out)

    def open_bytes(self, name: str) -> bytes:
        with open(os.path.join(self.path, name.replace("/", os.sep)), "rb") as fh:
            return fh.read()

    def describe(self) -> Dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "recursive": self.recursive}


class SyncFolder(object):
    """单向往本地拉取的目录同步器（可单次、可守护轮询）。

    Args:
        source:        源适配器（LocalDirSource 或实现 list_files/open_bytes 协议的对象）
        target_dir:    本地落盘目录
        pattern:       文件名 glob 过滤（对 basename 匹配，缺省 "*" 全拉）
        manifest_path: manifest 落盘路径（缺省 target_dir/.sync_manifest.json）
        on_pull:       回调 on_pull(name, local_path)，每次成功拉取后触发
    """

    def __init__(self, source: Any, target_dir: str, pattern: str = "*",
                 manifest_path: Optional[str] = None,
                 on_pull: Optional[Callable[[str, str], None]] = None):
        self.source = source
        self.target_dir = str(target_dir)
        self.pattern = str(pattern or "*")
        self.manifest_path = manifest_path or os.path.join(self.target_dir, MANIFEST_NAME)
        self.on_pull = on_pull
        os.makedirs(self.target_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # manifest
    # ------------------------------------------------------------------

    def _load_manifest(self) -> Dict[str, Any]:
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.manifest_path)

    # ------------------------------------------------------------------
    # 同步
    # ------------------------------------------------------------------

    def sync_once(self) -> Dict[str, Any]:
        """单次同步：拉取新增/变化文件，返回 {"pulled", "skipped", "errors"}。"""
        manifest = self._load_manifest()
        pulled: List[str] = []
        errors: List[str] = []
        skipped = 0
        try:
            names = self.source.list_files()
        except Exception as exc:
            return {"pulled": [], "skipped": 0,
                    "errors": ["源列举失败: %s" % exc]}

        for name in names:
            base = name.rsplit("/", 1)[-1]
            if base == MANIFEST_NAME or not fnmatch.fnmatchcase(base, self.pattern):
                continue
            try:
                data = self.source.open_bytes(name)
            except Exception as exc:
                errors.append("读源失败 %s: %s" % (name, exc))
                continue
            sha = hashlib.sha256(data).hexdigest()
            local_path = os.path.join(self.target_dir, name.replace("/", os.sep))
            entry = manifest.get(name)
            # 内容未变且 target 文件仍在 → 跳过；target 被清理（文件缺失）→ 重拉
            if entry and entry.get("sha256") == sha and os.path.exists(local_path):
                skipped += 1
                continue
            parent = os.path.dirname(local_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            try:
                with open(local_path, "wb") as fh:
                    fh.write(data)
            except OSError as exc:
                errors.append("写本地失败 %s: %s" % (name, exc))
                continue
            manifest[name] = {"sha256": sha, "size": len(data)}
            pulled.append(name)
            if self.on_pull is not None:
                try:
                    self.on_pull(name, local_path)
                except Exception:
                    pass  # 回调异常不阻断同步

        if pulled:
            try:
                self._save_manifest(manifest)
            except OSError as exc:
                errors.append("manifest 写盘失败: %s" % exc)
        return {"pulled": pulled, "skipped": skipped, "errors": errors}

    def run_forever(self, poll_interval: float = 5.0,
                    stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """守护轮询：每 poll_interval 秒 sync_once 一次，直到 stop_event 置位。

        **至少跑一轮**（保证初始同步），stop_event 预先置位也执行一轮后退出。

        Returns:
            累计 {"total_pulled", "rounds", "errors"}（stop 后返回）。
        """
        stop_event = stop_event or threading.Event()
        total_pulled: List[str] = []
        errors: List[str] = []
        rounds = 0
        while True:
            result = self.sync_once()
            rounds += 1
            total_pulled.extend(result["pulled"])
            errors.extend(result["errors"])
            if stop_event.is_set():
                break
            stop_event.wait(poll_interval)
        return {"total_pulled": total_pulled, "rounds": rounds, "errors": errors}


def sync_folder_once(source_path: str, target_dir: str, pattern: str = "*",
                     recursive: bool = False) -> Dict[str, Any]:
    """便捷函数：单次把 source_path 里（匹配 pattern 的）文件拉回 target_dir。"""
    return SyncFolder(LocalDirSource(source_path, recursive=recursive),
                      target_dir, pattern=pattern).sync_once()


__all__ = ["SyncFolder", "LocalDirSource", "sync_folder_once", "MANIFEST_NAME"]
