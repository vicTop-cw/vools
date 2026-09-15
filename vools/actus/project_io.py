"""project_io.py — 项目导入导出 (Phase M3)。

将整个 Actus 项目（动作 + 配置 + 工作流）打包为单个 .actus 文件（tar.gz），
支持导入/导出/验证/合并。
"""

import json
import os
import tarfile
import hashlib
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

PROJECT_MANIFEST_VERSION = "1.0"


def create_project_manifest(repo_root: str) -> dict:
    """创建项目清单。"""
    root = Path(repo_root)

    # 收集动作文件
    actions = []
    actions_dir = root / "actions"
    if actions_dir.exists():
        for f in actions_dir.rglob("*.actus.md"):
            rel = f.relative_to(root)
            actions.append({
                "path": str(rel),
                "size": f.stat().st_size,
                "hash": hashlib.md5(f.read_bytes()).hexdigest(),
            })

    # 收集配置文件
    configs = []
    for cfg_name in [".actus.md", "actus.config.json", "actus.yaml"]:
        cfg_path = root / cfg_name
        if cfg_path.exists():
            configs.append({
                "path": cfg_name,
                "size": cfg_path.stat().st_size,
            })

    return {
        "version": PROJECT_MANIFEST_VERSION,
        "created": datetime.now().isoformat(),
        "name": root.name,
        "actions_count": len(actions),
        "actions": actions,
        "configs": configs,
    }


def export_project(repo_root: str, output_path: str,
                   include_meta: bool = False) -> Optional[str]:
    """导出项目为 .actus 文件（tar.gz）。

    参数:
        repo_root: 项目根目录。
        output_path: 输出文件路径。
        include_meta: 是否包含 _meta 目录。

    返回:
        输出路径，失败返回 None。
    """
    root = Path(repo_root)
    if not root.exists():
        return None

    manifest = create_project_manifest(repo_root)

    try:
        with tarfile.open(output_path, "w:gz") as tar:
            # 添加清单
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            import io
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))

            # 添加动作文件
            actions_dir = root / "actions"
            if actions_dir.exists():
                for f in actions_dir.rglob("*"):
                    if f.is_file():
                        tar.add(f, f.relative_to(root))

            # 添加配置文件
            for cfg_name in [".actus.md", "actus.config.json", "actus.yaml"]:
                cfg_path = root / cfg_name
                if cfg_path.exists():
                    tar.add(cfg_path, cfg_path.relative_to(root))

            # 可选：添加元数据
            if include_meta:
                meta_dir = root / "_meta"
                if meta_dir.exists():
                    for f in meta_dir.rglob("*"):
                        if f.is_file():
                            tar.add(f, f.relative_to(root))

        logger.info(f"项目已导出: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"导出失败: {e}")
        return None


def import_project(repo_root: str, input_path: str,
                   overwrite: bool = False) -> Optional[dict]:
    """从 .actus 文件导入项目。

    参数:
        repo_root: 目标目录。
        input_path: .actus 文件路径。
        overwrite: 是否覆盖现有文件。

    返回:
        导入结果统计。
    """
    root = Path(repo_root)
    root.mkdir(parents=True, exist_ok=True)

    stats = {"imported": 0, "skipped": 0, "errors": 0}

    try:
        with tarfile.open(input_path, "r:gz") as tar:
            # 读取清单
            try:
                manifest_file = tar.getmember("manifest.json")
                manifest = json.loads(tar.extractfile(manifest_file).read())
            except (KeyError, json.JSONDecodeError):
                manifest = {}

            # 解压文件
            for member in tar.getmembers():
                if member.name == "manifest.json":
                    continue

                target = root / member.name
                if target.exists() and not overwrite:
                    stats["skipped"] += 1
                    continue

                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    stats["imported"] += 1
                except Exception:
                    stats["errors"] += 1

        logger.info(f"项目已导入: {stats}")
        return stats
    except Exception as e:
        logger.error(f"导入失败: {e}")
        return None


def validate_project(file_path: str) -> dict:
    """验证 .actus 文件完整性。

    返回:
        {valid, manifest, errors, warnings}
    """
    result = {"valid": False, "manifest": {}, "errors": [], "warnings": []}

    if not os.path.exists(file_path):
        result["errors"].append("文件不存在")
        return result

    try:
        with tarfile.open(file_path, "r:gz") as tar:
            # 检查清单
            try:
                manifest_file = tar.getmember("manifest.json")
                manifest = json.loads(tar.extractfile(manifest_file).read())
                result["manifest"] = manifest
            except KeyError:
                result["errors"].append("缺少 manifest.json")
                return result
            except json.JSONDecodeError:
                result["errors"].append("manifest.json 格式错误")
                return result

            # 验证文件完整性
            if "actions" in manifest:
                for action in manifest["actions"]:
                    action_path = action.get("path", "")
                    expected_hash = action.get("hash", "")
                    try:
                        f = tar.getmember(action_path)
                        if f:
                            data = tar.extractfile(f).read()
                            actual_hash = hashlib.md5(data).hexdigest()
                            if expected_hash and actual_hash != expected_hash:
                                result["errors"].append(f"哈希不匹配: {action_path}")
                    except KeyError:
                        result["warnings"].append(f"声明的文件不存在: {action_path}")

            result["valid"] = len(result["errors"]) == 0
    except tarfile.TarError as e:
        result["errors"].append(f"无法打开文件: {e}")

    return result


def merge_project(repo_root: str, input_path: str,
                  strategy: str = "skip_existing") -> Optional[dict]:
    """合并项目到现有目录。

    参数:
        repo_root: 目标目录。
        input_path: .actus 文件路径。
        strategy: 合并策略 (skip_existing/overwrite/rename)。

    返回:
        合并结果。
    """
    overwrite = strategy == "overwrite"
    return import_project(repo_root, input_path, overwrite=overwrite)


__all__ = [
    'PROJECT_MANIFEST_VERSION',
    'create_project_manifest',
    'export_project',
    'import_project',
    'logger',
    'merge_project',
    'validate_project'
]
