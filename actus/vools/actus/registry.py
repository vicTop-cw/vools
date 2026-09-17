"""registry.py —— 动作注册表（docs/20 §M2）。

动作注册表索引构建、搜索、验证和缓存管理。
支持本地仓库和远程 Git 仓库的索引发现。
"""

import json
import hashlib
import os
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class RegistryEntry:
    """注册表条目（对应 .actus.registry.json 中的一项）。"""
    id: str
    name: str
    version: str
    description: str
    category: str
    path: str
    author: str
    tags: List[str]
    checksum: str
    signature: Optional[str] = None
    permissions: List[str] = None
    dependencies: List[str] = None
    trust_level: str = "community"  # trusted / community / unverified

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []
        if self.dependencies is None:
            self.dependencies = []

    def to_dict(self) -> dict:
        return asdict(self)


class ActionRegistry:
    """动作注册表。

    职责：
    - 构建本地仓库的索引
    - 从 Git 远程发现动作
    - 搜索和过滤动作
    - 验证签名和完整性
    - 缓存远程索引
    """

    def __init__(self, cache_dir: str = None):
        """
        参数:
            cache_dir: 远程索引缓存目录（默认 ~/.actus/cache）
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser("~"), ".actus", "cache")
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._entries: Dict[str, RegistryEntry] = {}

    @property
    def cache_dir(self) -> str:
        return self._cache_dir

    # ── 索引构建 ──

    def build_from_directory(self, repo_dir: str) -> dict:
        """从本地仓库目录构建索引。

        扫描 repo_dir/actions/ 下所有 .actus.md 文件，
        提取元数据生成 .actus.registry.json。

        参数:
            repo_dir: 仓库根目录。

        返回:
            索引字典（已写入 .actus.registry.json）。
        """
        actions_dir = os.path.join(repo_dir, "actions")
        if not os.path.isdir(actions_dir):
            return self._empty_index(repo_dir)

        entries = []
        for root, dirs, files in os.walk(actions_dir):
            for fname in files:
                if not fname.endswith(".actus.md"):
                    continue
                fpath = os.path.join(root, fname)
                entry = self._parse_action_file(fpath, repo_dir)
                if entry:
                    entries.append(entry)

        index = self._empty_index(repo_dir)
        index["actions"] = [e.to_dict() for e in entries]

        # 写入注册表文件
        registry_path = os.path.join(repo_dir, ".actus.registry.json")
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        # 缓存到内存
        for entry in entries:
            self._entries[entry.id] = entry

        return index

    def load_from_file(self, registry_path: str) -> dict:
        """从 .actus.registry.json 加载索引。

        参数:
            registry_path: 索引文件路径。

        返回:
            索引字典。
        """
        if not os.path.isfile(registry_path):
            return {"actions": []}

        with open(registry_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        # 加载条目到内存
        for raw in index.get("actions", []):
            entry = RegistryEntry(**{
                k: v for k, v in raw.items()
                if k in RegistryEntry.__dataclass_fields__
            })
            self._entries[entry.id] = entry

        return index

    def load_from_repo(self, repo_dir: str) -> dict:
        """从仓库目录加载索引（优先 .actus.registry.json，否则实时构建）。"""
        registry_path = os.path.join(repo_dir, ".actus.registry.json")
        if os.path.isfile(registry_path):
            return self.load_from_file(registry_path)
        return self.build_from_directory(repo_dir)

    # ── 搜索与查询 ──

    def search(self, query: str = None, category: str = None,
               author: str = None, tags: List[str] = None,
               limit: int = 50, semantic: bool = True) -> List[RegistryEntry]:
        """搜索注册表条目。

        参数:
            query: 关键词（匹配 id/name/description/usage）。
            category: 分类过滤。
            author: 作者过滤。
            tags: 标签过滤（匹配任意一个）。
            limit: 最大返回数。
            semantic: 是否启用语义评分排序。

        返回:
            匹配的 RegistryEntry 列表（按相关度排序）。
        """
        if not query:
            results = list(self._entries.values())
            return results[:limit]

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for entry in self._entries.values():
            # 硬过滤
            if category and entry.category != category:
                continue
            if author and entry.author != author:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue

            score = self._score_entry(entry, query_lower, query_words)
            if score > 0:
                scored.append((score, entry))

        # 按分数降序
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in scored[:limit]]
        return results

    def _score_entry(self, entry: RegistryEntry,
                     query_lower: str, query_words: set) -> float:
        """计算条目的相关度分数（0-1）。"""
        score = 0.0

        # 精确 id 匹配（最高分）
        if query_lower == entry.id.lower():
            score += 1.0
        elif query_lower in entry.id.lower():
            score += 0.6

        # 名称匹配
        if query_lower in entry.name.lower():
            score += 0.5

        # 描述匹配
        if query_lower in entry.description.lower():
            score += 0.3

        # 标签精确匹配
        for tag in entry.tags:
            if tag.lower() == query_lower:
                score += 0.4
            elif tag.lower() in query_lower:
                score += 0.2

        # 关键词匹配（每个词加分）
        for word in query_words:
            if len(word) < 2:
                continue
            if word in entry.id.lower():
                score += 0.15
            if word in entry.name.lower():
                score += 0.1
            if word in entry.description.lower():
                score += 0.08
            for tag in entry.tags:
                if word in tag.lower():
                    score += 0.12

        return min(score, 1.0)

    def recommend(self, description: str, limit: int = 5) -> List[dict]:
        """根据自然语言描述推荐动作。

        参数:
            description: 任务描述（如 "监控文件夹变化"）。
            limit: 最大推荐数。

        返回:
            推荐列表 [{entry, score, reason}]。
        """
        description_lower = description.lower()
        description_words = set(description_lower.split())

        scored = []
        for entry in self._entries.values():
            score = self._score_entry(entry, description_lower, description_words)
            if score > 0.1:
                reason = self._explain_match(entry, description_lower, description_words)
                scored.append({
                    'entry': entry.to_dict(),
                    'score': round(score, 3),
                    'reason': reason,
                })

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]

    def _explain_match(self, entry: RegistryEntry,
                       query: str, query_words: set) -> str:
        """生成匹配解释。"""
        reasons = []
        if query in entry.id.lower():
            reasons.append('id 匹配')
        if query in entry.name.lower():
            reasons.append('名称匹配')
        if query in entry.description.lower():
            reasons.append('描述匹配')
        for tag in entry.tags:
            if tag.lower() in query:
                reasons.append(f'标签: {tag}')
                break
        for word in query_words:
            if len(word) > 2 and word in entry.id.lower():
                reasons.append(f'关键词: {word}')
                break
        return ', '.join(reasons) if reasons else '相关度高'

    def get(self, action_id: str) -> Optional[RegistryEntry]:
        """获取指定 ID 的注册表条目。"""
        return self._entries.get(action_id)

    def list_all(self) -> List[RegistryEntry]:
        """列出所有条目。"""
        return list(self._entries.values())

    def list_categories(self) -> List[str]:
        """列出所有分类。"""
        return list(set(e.category for e in self._entries.values()))

    def list_authors(self) -> List[str]:
        """列出所有作者。"""
        return list(set(e.author for e in self._entries.values()))

    # ── 验证 ──

    def verify_checksum(self, entry: RegistryEntry, repo_dir: str) -> bool:
        """验证动作文件的 SHA256 校验和。

        参数:
            entry: 注册表条目。
            repo_dir: 仓库根目录。

        返回:
            校验是否通过。
        """
        fpath = os.path.join(repo_dir, entry.path)
        if not os.path.isfile(fpath):
            return False

        actual_checksum = self._compute_checksum(fpath)
        expected = entry.checksum
        if expected.startswith("sha256:"):
            expected = expected[7:]

        return actual_checksum == expected

    def verify_signature(self, entry: RegistryEntry, repo_dir: str,
                         public_key: str = None) -> bool:
        """验证动作文件的数字签名。

        参数:
            entry: 注册表条目。
            repo_dir: 仓库根目录。
            public_key: 公钥内容（PEM 格式），None 则尝试从 .actus/keys/ 加载。

        返回:
            签名验证是否通过。
        """
        if not entry.signature:
            # 无签名视为 community 级别
            return entry.trust_level == "community"

        sig_path = os.path.join(repo_dir, entry.signature)
        if not os.path.isfile(sig_path):
            return False

        fpath = os.path.join(repo_dir, entry.path)
        if not os.path.isfile(fpath):
            return False

        # 尝试 Ed25519 验证
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey, Ed25519PrivateKey
            )
            from cryptography.hazmat.primitives import serialization
            import base64

            # 加载公钥
            if public_key is None:
                # 从注册表索引的 author 字段推断
                key_path = os.path.join(
                    os.path.expanduser("~"), ".actus", "keys",
                    f"{entry.author}.pub"
                )
                if not os.path.isfile(key_path):
                    return False
                with open(key_path, "rb") as f:
                    public_key = f.read()

            # 加载签名
            with open(sig_path, "rb") as f:
                sig_data = json.load(f)
            sig_bytes = base64.b64decode(sig_data["signature"])
            message = sig_data.get("message", "").encode("utf-8")

            # 验证
            if isinstance(public_key, str):
                public_key = public_key.encode("utf-8")

            try:
                # 尝试 PEM 格式
                pub = serialization.load_pem_public_key(public_key)
                pub.verify(sig_bytes, message)
                return True
            except Exception:
                # 尝试裸 32 字节公钥
                if len(public_key) == 32:
                    pub = Ed25519PublicKey.from_public_bytes(public_key)
                    pub.verify(sig_bytes, message)
                    return True
                return False

        except ImportError:
            # cryptography 库不可用，退化到简单哈希验证
            return self._verify_signature_fallback(entry, repo_dir)

    def validate_entry(self, entry: RegistryEntry, repo_dir: str) -> Tuple[bool, str]:
        """完整校验条目（格式 + 校验和 + 签名）。

        返回:
            (是否有效, 错误信息)
        """
        # 格式校验
        if not re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', entry.id):
            return False, f"Invalid action ID format: {entry.id}"

        if not re.match(r'^\d+\.\d+\.\d+$', entry.version):
            return False, f"Invalid version format: {entry.version}"

        # 文件存在性
        fpath = os.path.join(repo_dir, entry.path)
        if not os.path.isfile(fpath):
            return False, f"Action file not found: {entry.path}"

        # 校验和验证
        if entry.checksum and not self.verify_checksum(entry, repo_dir):
            return False, f"Checksum mismatch for {entry.id}"

        # 签名验证
        if entry.signature and not self.verify_signature(entry, repo_dir):
            return False, f"Signature verification failed for {entry.id}"

        return True, "ok"

    # ── 缓存管理 ──

    def cache_remote_index(self, repo_url: str, index: dict) -> str:
        """缓存远程索引到本地。

        参数:
            repo_url: 仓库 URL。
            index: 索引字典。

        返回:
            缓存文件路径。
        """
        cache_key = self._url_to_cache_key(repo_url)
        cache_path = os.path.join(self._cache_dir, f"{cache_key}.json")

        cache_data = {
            "url": repo_url,
            "cached_at": time.time(),
            "index": index
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return cache_path

    def load_cached_index(self, repo_url: str, max_age_seconds: int = 3600) -> Optional[dict]:
        """加载缓存的远程索引。

        参数:
            repo_url: 仓库 URL。
            max_age_seconds: 最大缓存年龄（秒）。

        返回:
            缓存的索引字典，过期或不存在返回 None。
        """
        cache_key = self._url_to_cache_key(repo_url)
        cache_path = os.path.join(self._cache_dir, f"{cache_key}.json")

        if not os.path.isfile(cache_path):
            return None

        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 检查过期
        cached_at = cache_data.get("cached_at", 0)
        if time.time() - cached_at > max_age_seconds:
            return None

        return cache_data.get("index")

    def invalidate_cache(self, repo_url: str = None):
        """使缓存失效。

        参数:
            repo_url: 指定仓库，None 则清除全部缓存。
        """
        if repo_url:
            cache_key = self._url_to_cache_key(repo_url)
            cache_path = os.path.join(self._cache_dir, f"{cache_key}.json")
            if os.path.isfile(cache_path):
                os.remove(cache_path)
        else:
            # 清除全部缓存
            for fname in os.listdir(self._cache_dir):
                fpath = os.path.join(self._cache_dir, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)

    # ── 安装清单 ──

    def record_installation(self, repo_url: str, repo_dir: str,
                            branch: str = "main", tag: str = None,
                            commit: str = None) -> dict:
        """记录安装信息到安装清单。

        返回:
            安装清单条目。
        """
        manifest_dir = os.path.join(os.path.expanduser("~"), ".actus", "installed")
        os.makedirs(manifest_dir, exist_ok=True)

        cache_key = self._url_to_cache_key(repo_url)
        manifest_path = os.path.join(manifest_dir, f"{cache_key}.json")

        manifest = {
            "url": repo_url,
            "cache_key": cache_key,
            "installed_at": time.time(),
            "branch": branch,
            "tag": tag,
            "commit": commit,
            "local_path": repo_dir,
            "actions": []
        }

        # 加载已安装的索引
        index = self.load_from_repo(repo_dir)
        manifest["actions"] = [
            {"id": e["id"], "version": e["version"], "checksum": e.get("checksum", "")}
            for e in index.get("actions", [])
        ]

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return manifest

    def load_manifest(self, repo_url: str) -> Optional[dict]:
        """加载安装清单。"""
        manifest_dir = os.path.join(os.path.expanduser("~"), ".actus", "installed")
        cache_key = self._url_to_cache_key(repo_url)
        manifest_path = os.path.join(manifest_dir, f"{cache_key}.json")

        if not os.path.isfile(manifest_path):
            return None

        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_installed(self) -> List[dict]:
        """列出所有已安装的仓库。"""
        manifest_dir = os.path.join(os.path.expanduser("~"), ".actus", "installed")
        if not os.path.isdir(manifest_dir):
            return []

        manifests = []
        for fname in os.listdir(manifest_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(manifest_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                manifests.append(json.load(f))
        return manifests

    def remove_installation(self, repo_url: str):
        """移除安装清单。"""
        manifest_dir = os.path.join(os.path.expanduser("~"), ".actus", "installed")
        cache_key = self._url_to_cache_key(repo_url)
        manifest_path = os.path.join(manifest_dir, f"{cache_key}.json")

        if os.path.isfile(manifest_path):
            os.remove(manifest_path)

    # ── 私有方法 ──

    def _empty_index(self, repo_dir: str) -> dict:
        """生成空索引骨架。"""
        name = os.path.basename(os.path.abspath(repo_dir))
        return {
            "name": name,
            "version": "1.0.0",
            "description": "",
            "author": "unknown",
            "license": "MIT",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "actions": []
        }

    def _parse_action_file(self, fpath: str, repo_dir: str) -> Optional[RegistryEntry]:
        """从动作文件解析元数据。

        提取 #!cfg 块中的 id/version/description 等字段，
        计算文件校验和，推断分类和作者。
        """
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        # 提取 #!cfg 块
        cfg_match = re.search(
            r'```json\s*#!cfg\s*\n(.*?)\n```',
            content, re.DOTALL
        )
        if not cfg_match:
            return None

        try:
            cfg = json.loads(cfg_match.group(1))
        except json.JSONDecodeError:
            return None

        # 必需字段
        action_id = cfg.get("id", "")
        name = cfg.get("name", "")
        if not action_id or not name:
            return None

        # 推断分类（从路径）
        rel_path = os.path.relpath(fpath, repo_dir)
        parts = rel_path.split(os.sep)
        category = parts[1] if len(parts) > 2 else "uncategorized"

        # 推断作者（从 ID 前缀）
        author = action_id.split(".")[0] if "." in action_id else "unknown"

        # 计算校验和
        checksum = self._compute_checksum(fpath)

        return RegistryEntry(
            id=action_id,
            name=name,
            version=cfg.get("version", "1.0.0"),
            description=cfg.get("description", ""),
            category=category,
            path=rel_path,
            author=author,
            tags=cfg.get("tags", []),
            checksum=f"sha256:{checksum}",
            signature=cfg.get("signature"),
            permissions=cfg.get("permissions", []),
            dependencies=cfg.get("deps", []),
            trust_level=cfg.get("trust_level", "community")
        )

    @staticmethod
    def _compute_checksum(fpath: str) -> str:
        """计算文件 SHA256 校验和。"""
        h = hashlib.sha256()
        with open(fpath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _url_to_cache_key(url: str) -> str:
        """URL 转缓存 key。"""
        # 移除协议前缀和特殊字符
        key = re.sub(r'[^a-zA-Z0-9_-]', '_', url)
        # 限制长度
        return key[:64]

    def _verify_signature_fallback(self, entry: RegistryEntry, repo_dir: str) -> bool:
        """签名验证退化方案（无 cryptography 库时使用）。

        退化到校验和验证（无加密签名）。
        """
        if not entry.signature:
            return entry.trust_level in ("community", "trusted")

        sig_path = os.path.join(repo_dir, entry.signature)
        if not os.path.isfile(sig_path):
            return False

        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig_data = json.load(f)

            # 退化：只验证消息与文件校验和匹配
            expected_message = sig_data.get("message", "")
            return expected_message == entry.checksum
        except (OSError, json.JSONDecodeError):
            return False


# ── 便捷函数 ──

def build_registry(repo_dir: str) -> dict:
    """便捷函数：构建仓库索引。"""
    registry = ActionRegistry()
    return registry.build_from_directory(repo_dir)


def search_registry(repo_dir: str, query: str = None,
                    category: str = None, limit: int = 50) -> List[RegistryEntry]:
    """便捷函数：搜索注册表。"""
    registry = ActionRegistry()
    registry.load_from_repo(repo_dir)
    return registry.search(query=query, category=category, limit=limit)


__all__ = [
    'ActionRegistry',
    'RegistryEntry',
    'build_registry',
    'search_registry'
]
