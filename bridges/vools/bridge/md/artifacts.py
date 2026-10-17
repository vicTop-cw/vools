"""
vools.bridge.md artifacts — 产物目录/hash/增量/清理
"""


__all__ = [
    "ensure_build_dir",
    "compute_artifact_hash",
    "is_artifact_stale",
    "register_artifact",
    "clean_build",
    "guess_type",
]

import hashlib
import os
import shutil
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════
# 目录管理
# ═══════════════════════════════════════════════════════


def ensure_build_dir(build_dir: str) -> None:
    """创建 .mdbuild/ 及子目录。"""
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(os.path.join(build_dir, "artifacts"), exist_ok=True)
    os.makedirs(os.path.join(build_dir, "artifacts", "rich"), exist_ok=True)
    os.makedirs(os.path.join(build_dir, "sources"), exist_ok=True)
    os.makedirs(os.path.join(build_dir, "tmp"), exist_ok=True)


# ═══════════════════════════════════════════════════════
# 哈希计算
# ═══════════════════════════════════════════════════════


def compute_artifact_hash(path: str) -> str:
    """计算产物文件 MD5。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════
# 增量判断
# ═══════════════════════════════════════════════════════


def is_artifact_stale(
    build_dir: str,
    block_idx: int,
    block_hash: str,
    manifest: Optional[Dict] = None,
) -> bool:
    """
    判断块产物是否需要重建。

    Args:
        build_dir: 产物根目录
        block_idx: 块序号
        block_hash: 块内容哈希
        manifest: 已有清单（None 时读取）

    Returns:
        True = 需要重建
    """
    if manifest is None:
        from .manifest import read_manifest

        manifest = read_manifest(build_dir)

    if not manifest:
        return True

    blocks = manifest.get("blocks", [])
    if block_idx >= len(blocks):
        return True

    cached = blocks[block_idx]
    if cached.get("source_hash") != block_hash:
        return True

    # 检查产物文件是否存在
    artifact_path = cached.get("artifact")
    if artifact_path and os.path.exists(artifact_path):
        return False

    return True


# ═══════════════════════════════════════════════════════
# 产物注册
# ═══════════════════════════════════════════════════════


def register_artifact(
    table: Dict,
    name: str,
    path: str,
    block_idx: int,
    tag: Optional[str] = None,
) -> None:
    """
    注册产物到共享产物表。

    Args:
        table: 共享产物表 dict
        name: 产物名称
        path: 产物文件路径
        block_idx: 来源块序号
        tag: 来源块 tag
    """
    if not os.path.exists(path):
        return

    table[name] = {
        "name": name,
        "path": path,
        "hash": compute_artifact_hash(path),
        "source_block": block_idx,
        "source_tag": tag,
    }


# ═══════════════════════════════════════════════════════
# 清理
# ═══════════════════════════════════════════════════════


def clean_build(
    build_dir: str,
    stale: bool = False,
    keep: Optional[List[str]] = None,
) -> None:
    """
    清理产物目录。

    Args:
        build_dir: 产物根目录
        stale: True = 只清清单外的孤儿文件
        keep: 保留指定 tag 的产物
    """
    keep = keep or []

    if not stale:
        # 删除整个目录
        if os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        return

    # 只清 stale
    from .manifest import read_manifest

    manifest = read_manifest(build_dir)

    if manifest:
        # 从 manifest 中获取有效产物路径
        valid_paths = set()
        for block in manifest.get("blocks", []):
            if block.get("artifact") and os.path.exists(block["artifact"]):
                valid_paths.add(block["artifact"])

        # 清理 artifacts/ 下的孤儿文件
        artifacts_dir = os.path.join(build_dir, "artifacts")
        if os.path.exists(artifacts_dir):
            for fname in os.listdir(artifacts_dir):
                fpath = os.path.join(artifacts_dir, fname)
                if fpath not in valid_paths:
                    os.unlink(fpath)

    # 清理 tmp/
    tmp_dir = os.path.join(build_dir, "tmp")
    if os.path.exists(tmp_dir):
        for fname in os.listdir(tmp_dir):
            os.unlink(os.path.join(tmp_dir, fname))


# ═══════════════════════════════════════════════════════
# 产物类型感知（计划 D5）
# ═══════════════════════════════════════════════════════

#: 扩展名 → 产物类型（D5 类型集合：text/image/svg/html/json/binary）
_ARTIFACT_KIND_BY_EXT = {
    "txt": "text", "md": "text", "markdown": "text", "log": "text",
    "csv": "text", "yaml": "text", "yml": "text", "toml": "text", "ini": "text",
    "py": "text", "js": "text", "ts": "text", "java": "text", "c": "text",
    "cpp": "text", "h": "text", "rs": "text", "go": "text", "sh": "text",
    "ps1": "text", "bat": "text", "xml": "text",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "webp": "image", "bmp": "image", "tiff": "image", "ico": "image",
    "svg": "svg",
    "html": "html", "htm": "html",
    "json": "json",
}


def guess_type(path: str) -> str:
    """按扩展名判断产物类型（计划 D5；未知回退 binary）。"""
    ext = os.path.splitext(str(path))[1].lower().lstrip(".")
    return _ARTIFACT_KIND_BY_EXT.get(ext, "binary")

