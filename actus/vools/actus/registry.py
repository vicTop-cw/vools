"""registry.py —— 动作注册表（docs/20 §M2）。

动作注册表索引构建、搜索、验证和缓存管理。
支持本地仓库和远程 Git 仓库的索引发现。

审计口径（第 10 轮）：
- **写语义**只有 `write_index` / `build_from_directory(write=True)` /
  `cache_remote_index` / `record_installation` / `invalidate_cache` /
  `remove_installation`；`load_*` / `search` / `list_*` / `verify_*` 一律不落盘。
- 索引写盘必须**原子**（tmp + `os.replace`）；索引损坏时 `load_from_file` 返回
  带 `problems` 信号的空索引，`load_from_repo` 回退到内存重建（`write=False`）。
"""

import json
import hashlib
import os
import re
import tempfile
import time
from typing import Dict, List, Optional, Tuple
from vools.core.dataclass_compat import dataclass, asdict
from .constants import is_action_file

#: 安装清单目录可用环境变量覆盖（嵌入式/测试隔离；默认仍 `~/.actus/installed`）。
INSTALLED_DIR_ENV = "ACTUS_INSTALLED_DIR"


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

    def __post_init__(self) -> None:
        """初始化后处理：将 None 字段归一为空列表，保证下游可迭代。"""
        if self.permissions is None:
            self.permissions = []
        if self.dependencies is None:
            self.dependencies = []

    def to_dict(self) -> dict:
        """转为普通 dict（dataclass asdict）。"""
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

    def __init__(self, cache_dir: str = None, manifest_dir: str = None) -> None:
        """
        参数:
            cache_dir: 远程索引缓存目录（默认 ~/.actus/cache）。
            manifest_dir: 安装清单目录（默认 `~/.actus/installed`；
                可用环境变量 ACTUS_INSTALLED_DIR 覆盖，嵌入式/测试用）。

        注意：**构造不写盘**。改前这里无条件 `os.makedirs(cache_dir)` ——
        只读查询（`actus search`/`registry info`）也会在 HOME 下建目录；
        现在缓存目录在首次真正写缓存时才创建。
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser("~"), ".actus", "cache")
        self._cache_dir = cache_dir
        self._manifest_dir = (manifest_dir
                              or os.environ.get(INSTALLED_DIR_ENV)
                              or os.path.join(os.path.expanduser("~"), ".actus", "installed"))
        self._entries: Dict[str, RegistryEntry] = {}
        #: 读路径上的非致命问题（索引损坏回退、跳过坏 manifest、path 越界…）。
        #: 只做诊断，不改变返回值语义。
        self.warnings: List[str] = []

    @property
    def cache_dir(self) -> str:
        """缓存目录路径。"""
        return self._cache_dir

    @property
    def manifest_dir(self) -> str:
        """安装清单目录路径。"""
        return self._manifest_dir

    # ── 索引构建 ──

    def write_index(self, index: dict, repo_dir: str) -> str:
        """把索引字典落盘到 `<repo_dir>/.actus.registry.json`，返回写入路径。

        从 `build_from_directory` 里抽出来做单一真源：需要「先构建、成功后才落盘」
        的调用方（publish 要先签名，签名失败不能留下半成品）可以把构建与写盘拆开。

        审计修复（P1 非原子）：改前 `open(...,"w")` 先截断原文件再 dump —— 磁盘满/
        进程被杀会把**原本有效的索引**清成空/半截，而 load 侧又不会重建，于是
        `search`/`install` 永久坏掉（只能手删文件）。现在写临时文件 + `os.replace`
        （同目录，原子替换）：失败时旧索引原样保留，临时文件清理干净。
        """
        registry_path = os.path.join(repo_dir, ".actus.registry.json")
        fd, tmp_path = tempfile.mkstemp(prefix=".actus.registry.", suffix=".tmp",
                                        dir=repo_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, registry_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return registry_path

    def build_from_directory(self, repo_dir: str, write: bool = True) -> dict:
        """从本地仓库目录构建索引。

        扫描 repo_dir/actions/ 下所有 .actus.md 文件，
        提取元数据生成 .actus.registry.json。

        参数:
            repo_dir: 仓库根目录。
            write: 是否把索引**落盘**到 `<repo_dir>/.actus.registry.json`。
                   默认 True（保持既有调用方行为）；传 False 时只在内存里构建，
                   一个字节都不写 —— `publish --dry-run` 这类预检路径必须传 False，
                   否则「干跑」会在校验阶段就改掉仓库状态（假 dry-run）。

        返回:
            索引字典（write=True 时已写入 .actus.registry.json）。
        """
        actions_dir = os.path.join(repo_dir, "actions")
        if not os.path.isdir(actions_dir):
            return self._empty_index(repo_dir)

        entries = []
        for root, dirs, files in os.walk(actions_dir):
            for fname in files:
                if not is_action_file(fname):
                    continue
                fpath = os.path.join(root, fname)
                entry = self._parse_action_file(fpath, repo_dir)
                if entry:
                    entries.append(entry)

        index = self._empty_index(repo_dir)
        index["actions"] = [e.to_dict() for e in entries]

        # 写入注册表文件（write=False 时跳过：预检/干跑不该改仓库状态）
        if write:
            self.write_index(index, repo_dir)

        # 缓存到内存
        for entry in entries:
            self._entries[entry.id] = entry

        return index

    def load_from_file(self, registry_path: str) -> dict:
        """从 .actus.registry.json 加载索引。

        参数:
            registry_path: 索引文件路径。

        返回:
            索引字典。损坏时返回 **空索引 + 明确信号**（`corrupt` / `problems`），
            不再抛 `JSONDecodeError`（调用方应按"索引不可用"处理，如回退重建）。
        """
        if not os.path.isfile(registry_path):
            return {"actions": []}

        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (OSError, ValueError) as exc:
            problem = "index corrupt: %s: %s" % (type(exc).__name__, exc)
            self.warnings.append("%s（%s）" % (problem, registry_path))
            return {"actions": [], "corrupt": True,
                    "problems": {registry_path: problem}}
        if not isinstance(index, dict):
            problem = "index corrupt: 顶层不是对象（%s）" % type(index).__name__
            self.warnings.append("%s（%s）" % (problem, registry_path))
            return {"actions": [], "corrupt": True,
                    "problems": {registry_path: problem}}

        repo_root = os.path.dirname(os.path.abspath(registry_path))
        problems = dict(index.get("problems") or {})

        # 加载条目到内存
        # py3.6 下 dataclass_compat 用 attrs 实现，类没有 __dataclass_fields__
        # 属性，需回退到 __attrs_attrs__（attrs 的字段描述符）。
        _entry_fields = getattr(RegistryEntry, '__dataclass_fields__', None)
        if _entry_fields is None:
            _entry_fields = {a.name: a for a in getattr(RegistryEntry, '__attrs_attrs__', ())}
        for raw in index.get("actions", []) or []:
            if not isinstance(raw, dict):
                problems["?%d" % len(problems)] = "条目不是对象: %r" % (raw,)
                continue
            rel_path = raw.get("path", "")
            if self._resolve_entry_path(repo_root, rel_path) is None:
                # 索引里的 path 越界（绝对路径/../）→ 拒绝加载，绝不读仓库外文件
                problems[raw.get("id", "?")] = "path 越界/非法: %r" % (rel_path,)
                continue
            try:
                entry = RegistryEntry(**{
                    k: v for k, v in raw.items()
                    if k in _entry_fields
                })
            except TypeError as exc:
                problems[raw.get("id", "?")] = "条目字段缺失/非法: %s" % exc
                continue
            self._entries[entry.id] = entry

        if problems:
            index["problems"] = problems
            self.warnings.append("索引有条目被跳过（%d 条）: %s"
                                 % (len(problems), registry_path))
        return index

    def _resolve_entry_path(self, repo_root: str, rel_path: str) -> Optional[str]:
        """索引条目 path → 仓库内绝对路径；绝对路径 / `..` / 越界一律返回 None。

        审计修复（P1 越界读）：改前 `_entry_to_action`/`verify_checksum` 直接
        `os.path.join(repo_dir, entry.path)` —— `os.path.join` 遇到绝对路径会**丢弃**
        repo_dir，于是恶意/损坏索引可让质量分级读取仓库外任意文件（实测读到 HOME 下
        文件）。现在统一走 `errors.ensure_within` 的 realpath 包含性检查。
        """
        if not rel_path or not isinstance(rel_path, str):
            return None
        if os.path.isabs(rel_path) or rel_path.startswith(("/", "\\")):
            return None
        candidate = os.path.join(repo_root, rel_path)
        try:
            from .errors import ensure_within
            return ensure_within(repo_root, candidate, what="索引条目路径")
        except Exception:
            return None

    def _index_is_stale(self, index: dict, registry_path: str, repo_dir: str) -> bool:
        """索引是否与磁盘不一致（条目文件缺失/比索引新/索引空但磁盘有动作）。"""
        try:
            index_mtime = os.path.getmtime(registry_path)
        except OSError:
            return True
        entries = index.get("actions") or []
        for raw in entries:
            rel_path = raw.get("path") if isinstance(raw, dict) else None
            fpath = self._resolve_entry_path(repo_dir, rel_path) if rel_path else None
            if fpath is None or not os.path.isfile(fpath):
                return True
            try:
                if os.path.getmtime(fpath) > index_mtime + 1e-6:
                    return True
            except OSError:
                return True
        if not entries:
            actions_dir = os.path.join(repo_dir, "actions")
            if os.path.isdir(actions_dir):
                for _root, _dirs, files in os.walk(actions_dir):
                    if any(is_action_file(fname) for fname in files):
                        return True
        return False

    def load_from_repo(self, repo_dir: str) -> dict:
        """从仓库目录加载索引（优先 .actus.registry.json，否则实时构建）。

        实时构建时**不落盘**（write=False）：本方法是**读**语义，不该因为
        「仓库里还没有索引文件」就顺手创建 `.actus.registry.json`。
        改前 `actus search`（纯只读命令）跑完会在用户仓库里留下这个文件 ——
        与 `publish --dry-run` 假干跑同族（界面是查询，实际改了仓库状态）。
        需要持久化的调用方仍然显式走 `build_from_directory(write=True)`
        （`registry build` / `publish` / installer 都是这样）。

        审计修复（P1 损坏不设防 + P2 陈旧索引）：
          * 索引损坏 / 有条目非法 → **回退内存重建**（仍不落盘）+ `warnings` 记录；
          * 索引与磁盘不一致（动作文件缺失/被改/索引空但磁盘有）→ 同样内存重建，
            返回体带 `stale_index=True`，不再"无声信索引"返回幽灵条目。
        """
        registry_path = os.path.join(repo_dir, ".actus.registry.json")
        if not os.path.isfile(registry_path):
            return self.build_from_directory(repo_dir, write=False)

        index = self.load_from_file(registry_path)
        if index.get("corrupt") or index.get("problems"):
            rebuilt = self.build_from_directory(repo_dir, write=False)
            rebuilt.setdefault("problems", {}).update(index.get("problems") or {})
            rebuilt["rebuilt_from_memory"] = True
            self.warnings.append("索引损坏/有条目非法，已回退内存重建（未落盘）: %s"
                                 % registry_path)
            return rebuilt
        if self._index_is_stale(index, registry_path, repo_dir):
            rebuilt = self.build_from_directory(repo_dir, write=False)
            rebuilt["stale_index"] = True
            self.warnings.append("索引与磁盘不一致，已回退内存重建（未落盘）: %s"
                                 % registry_path)
            return rebuilt
        return index

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
        # query 未指定（None）→ 仅按过滤参数筛选（空串 '' 仍走评分路径，
        # 所有条目得 0 分 → 无匹配；旧实现 `not query` 把纯过滤调用短路成全量返回，
        # 使 search(tags=[...]) 等纯过滤参数失效）
        if query is None:
            results = [e for e in self._entries.values()
                       if self._filter_entry(e, category, author, tags)]
            return results[:limit]

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for entry in self._entries.values():
            # 硬过滤
            if not self._filter_entry(entry, category, author, tags):
                continue

            score = self._score_entry(entry, query_lower, query_words)
            if score > 0:
                scored.append((score, entry))

        # 按分数降序
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in scored[:limit]]
        return results

    @staticmethod
    def _filter_entry(entry, category: str = None, author: str = None,
                      tags: List[str] = None) -> bool:
        """硬过滤：category / author / tags（tags 匹配任意一个）任一不满足即排除。"""
        if category and entry.category != category:
            return False
        if author and entry.author != author:
            return False
        if tags and not any(t in entry.tags for t in tags):
            return False
        return True

    def filter_by_quality(self, level: str = None, limit: int = 50,
                          repo_dir: str = None) -> List[dict]:
        """按质量分级过滤（docs/03 §5.3，借鉴 HA Quality Scale）。

        质量分级从真实数据计算（签名/Omega/执行指标/维护活跃度），非手工申报——
        杜绝自写自测恒绿。数据源不可用时降级 bronze，绝不虚报更高等级。

        参数:
            level: 目标等级（platinum/gold/silver/bronze/internal）；
                   None 时返回全部（每条带 computed quality 字段）。
            limit: 最大返回数。
            repo_dir: 仓库根（**必填**：动作文件定位与越界校验的基准）。

        返回:
            [{entry, quality, evidence}] 按质量等级降序。

        审计修复（"查不到"伪装成"没有"）：改前 repo_dir 缺省时用
        `cache_dir` 上一级当仓库根（默认值是 `~`，几乎永远错）→ 所有条目解析失败
        → 静默返回 []，调用方以为"没有高质量动作"。现在缺 repo_dir 直接报错，
        不再给假空结果。
        """
        from .quality import quality_scale, QUALITY_LEVELS, _LEVEL_RANK

        if level is not None and level not in QUALITY_LEVELS:
            raise ValueError(f'未知质量等级: {level!r}（支持 {QUALITY_LEVELS}）')
        if not repo_dir:
            raise ValueError(
                'filter_by_quality() 需要 repo_dir（动作文件所在仓库根）；'
                '缺省会静默返回空列表，把"查不到"伪装成"没有"')

        results: List[dict] = []
        for entry in self._entries.values():
            action = self._entry_to_action(entry, repo_dir)
            if action is None:
                self.warnings.append('质量分级跳过条目 %s：动作文件不可解析' % entry.id)
                continue
            q = quality_scale(action)
            if level is not None and q['quality'] != level:
                continue
            results.append({'entry': entry, 'quality': q['quality'],
                            'evidence': q['evidence']})

        results.sort(key=lambda r: (-_LEVEL_RANK.get(r['quality'], 0), r['entry'].id))
        return results[:limit]

    def _entry_to_action(self, entry, repo_dir: str = None):
        """RegistryEntry → Action（质量计算用；解析失败/路径越界返回 None）。"""
        from .model import parse_cfg_from_file
        root = repo_dir
        if not root:
            return None
        fpath = self._resolve_entry_path(root, entry.path)
        if fpath is None or not os.path.isfile(fpath):
            return None
        try:
            return parse_cfg_from_file(fpath)
        except Exception:
            return None

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
            校验是否通过。path 越界（绝对路径/`..`）→ False（不读仓库外文件）。
        """
        fpath = self._resolve_entry_path(repo_dir, entry.path)
        if fpath is None or not os.path.isfile(fpath):
            return False

        actual_checksum = self._compute_checksum(fpath)
        expected = entry.checksum or ""
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

        sig_path = self._resolve_entry_path(repo_dir, entry.signature)
        if sig_path is None or not os.path.isfile(sig_path):
            return False

        fpath = self._resolve_entry_path(repo_dir, entry.path)
        if fpath is None or not os.path.isfile(fpath):
            return False

        # 尝试 Ed25519 验证
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey
            )
            from cryptography.hazmat.primitives import serialization
            import base64

            # 加载公钥
            if public_key is None:
                # 从注册表索引的 author 字段推断（author 来自索引 → 必须防路径逃逸：
                # 形如 '../../x' 的 author 会让 key_path 跳出 ~/.actus/keys 读任意文件）
                author = str(entry.author or "")
                if not re.match(r'^[A-Za-z0-9][A-Za-z0-9._-]*$', author) or ".." in author:
                    self.warnings.append(
                        "拒绝对 author=%r 推断公钥路径（非法字符/可能越界）" % (author,))
                    return False
                keys_dir = os.path.join(os.path.expanduser("~"), ".actus", "keys")
                try:
                    from .errors import ensure_within
                    key_path = ensure_within(keys_dir,
                                             os.path.join(keys_dir, author + ".pub"),
                                             what="公钥路径")
                except Exception:
                    return False
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
            # 审计修复（P2 假通过）：改前这里退化到 `_verify_signature_fallback`
            # 做"sig.message == entry.checksum"的伪验签 —— checksum 就写在索引里、
            # sig 文件也可写，等于任何人都能伪造"验签通过"。没有密码学能力时
            # **必须 fail-closed**：拒绝该签名（并记录原因，便于排查）。
            self.warnings.append(
                "未安装 cryptography，无法验证签名（fail-closed，拒绝 %s）"
                % entry.id)
            return False

    def validate_entry(self, entry: RegistryEntry, repo_dir: str) -> Tuple[bool, str]:
        """完整校验条目（格式 + 校验和 + 签名）。

        返回:
            (是否有效, 错误信息)。CLI `registry validate` 用本函数（真校验），
            不再只数 id 个数。
        """
        # 逐项收集全部问题（不只报第一个）：CLI `registry validate` 因此能"点名每项"
        problems: List[str] = []
        if not re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', entry.id):
            problems.append("Invalid action ID format: %s" % entry.id)
        if not re.match(r'^\d+\.\d+\.\d+$', entry.version):
            problems.append("Invalid version format: %s" % entry.version)
        # 文件存在性 + 路径越界（绝对不能读仓库外文件）
        fpath = self._resolve_entry_path(repo_dir, entry.path)
        if fpath is None:
            problems.append("Action path 越界/非法: %s" % entry.path)
        elif not os.path.isfile(fpath):
            problems.append("Action file not found: %s" % entry.path)
        elif entry.checksum and not self.verify_checksum(entry, repo_dir):
            problems.append("Checksum mismatch for %s" % entry.id)
        if entry.signature and not self.verify_signature(entry, repo_dir):
            problems.append("Signature verification failed for %s" % entry.id)
        if problems:
            return False, "; ".join(problems)
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
        os.makedirs(self._cache_dir, exist_ok=True)   # 懒创建：只读构造不再建目录
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

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except (OSError, ValueError):
            # 审计修复（零风险）：缓存是**可重建的副本**，损坏等价于"没有缓存"。
            # 改前 json.load 直接抛 JSONDecodeError 穿透到 CLI（`install --cached` 崩）；
            # 现在按 cache miss 处理（返回 None → 调用方重新拉取）。
            return None
        if not isinstance(cache_data, dict):
            return None

        # 检查过期
        cached_at = cache_data.get("cached_at", 0)
        if time.time() - cached_at > max_age_seconds:
            return None

        return cache_data.get("index")

    def invalidate_cache(self, repo_url: str = None) -> None:
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
            # 清除全部缓存（**只删本模块写的 .json**）
            # 审计修复（零风险）：改前删除 cache_dir 里**所有文件**——实测把用户
            # 放进缓存目录的 USER_DATA.txt 也删了。cache_dir 可由调用方传入任意路径，
            # 误删面过大；现在只清 `*.json` 缓存文件，目录不存在时直接返回（懒创建后
            # 可能从未建过）。
            if not os.path.isdir(self._cache_dir):
                return
            for fname in os.listdir(self._cache_dir):
                fpath = os.path.join(self._cache_dir, fname)
                if os.path.isfile(fpath) and fname.endswith(".json"):
                    os.remove(fpath)

    # ── 安装清单 ──

    def record_installation(self, repo_url: str, repo_dir: str,
                            branch: str = "main", tag: str = None,
                            commit: str = None) -> dict:
        """记录安装信息到安装清单。

        审计修复（P2 无视 cache_dir）：改前固定拼 `~/.actus/installed` —— 嵌入式/
        测试里传了隔离 cache_dir 也会污染真实 HOME。现在清单目录可配置：
        显式 `manifest_dir=`（构造参数）或环境变量 ACTUS_INSTALLED_DIR，默认仍是
        `~/.actus/installed`（保持既有契约，有测试钉住该默认值）。

        清单写盘也用 tmp + `os.replace`（避免半截清单，与索引同一口径）。
        """
        manifest_dir = self._manifest_dir
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
            if isinstance(e, dict)
        ]

        fd, tmp_path = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp",
                                        dir=manifest_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, manifest_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return manifest

    def load_manifest(self, repo_url: str) -> Optional[dict]:
        """加载安装清单（损坏 → None + warning，不抛）。"""
        manifest_dir = self._manifest_dir
        cache_key = self._url_to_cache_key(repo_url)
        manifest_path = os.path.join(manifest_dir, f"{cache_key}.json")

        if not os.path.isfile(manifest_path):
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError) as exc:
            self.warnings.append("安装清单损坏（%s），按缺失处理: %s"
                                 % (exc, manifest_path))
            return None

    def list_installed(self) -> List[dict]:
        """列出所有已安装的仓库。

        审计修复（P3）：改前任一清单损坏（半截 JSON）→ 整个列表抛异常，
        `actus install list` 全崩。现在逐个跳过坏文件并记 `warnings`。
        """
        manifest_dir = self._manifest_dir
        if not os.path.isdir(manifest_dir):
            return []

        manifests = []
        for fname in os.listdir(manifest_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(manifest_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as exc:
                self.warnings.append("跳过损坏的安装清单（%s）: %s" % (exc, fpath))
                continue
            if isinstance(data, dict):
                manifests.append(data)
            else:
                self.warnings.append("跳过非对象安装清单: %s" % fpath)
        return manifests

    def remove_installation(self, repo_url: str) -> None:
        """移除安装清单。"""
        manifest_dir = self._manifest_dir
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
            try:
                from vools.encoding import read_text as _fc_read_text
                content = _fc_read_text(fpath)
            except Exception:
                # vools.encoding 不可用时退化为 utf-8（动作文件约定 utf-8）
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
        """签名验证退化方案（无 cryptography 库时使用）——**已改为 fail-closed**。

        审计修复（P2 假通过）：改前这里用 `sig.message == entry.checksum` 冒充验签：
        checksum 写在索引里、sig 文件可随意写，手写
        `{"message": "<公开 checksum>", "signature": "ZmFrZQ=="}` 就能"验签通过"。
        没有密码学能力时**不能假装验过**：签名条目一律 False；只有"无签名"条目
        按主路径同款判据（仅 community）放行。`verify_signature()` 的 ImportError
        分支已直接 fail-closed，本方法保留给外部调用方/历史兼容。
        """
        if not entry.signature:
            return entry.trust_level == "community"
        self.warnings.append(
            "未安装 cryptography，跳过签名校验并判为未通过（fail-closed）: %s"
            % getattr(entry, "id", "?"))
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
