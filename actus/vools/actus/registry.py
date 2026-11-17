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
from bisect import bisect_left
from typing import Dict, List, Optional, Tuple
from vools.core.dataclass_compat import dataclass, asdict
from .constants import is_action_file
from .semantic import SemanticScorer, try_load_embedder
from .fuzzy import (
    edit_similarity,
    edit_suggestions,
    fuzzy_match,
    has_pinyin_support,
    levenshtein_distance,
    pinyin_prefix,
    pinyin_prefix_match,
    pinyin_suggestions,
)
from .tokenizer import tokenize

#: 安装清单目录可用环境变量覆盖（嵌入式/测试隔离；默认仍 `~/.actus/installed`）。
INSTALLED_DIR_ENV = "ACTUS_INSTALLED_DIR"

#: P4 检索复杂度优化（提升计划 P4）：倒排/前缀索引的最小 term 长度。
#: 与 `_score_entry_ex` 词级 `len(word) < 2` 跳过对齐；更短查询由
#: 「词零命中回退线性」兜底保证正确性。
_INVERTED_MIN_TERM = 2

#: P4 倒排候选上界：候选 id 数超过该值时回退线性全量打分，限制扫描上界
#: （防止倒排命中集合过大时 set 并集/打分成为新的瓶颈）。
_INVERTED_MAX_SCAN = 1024

#: F1 语义检索（提升计划 F1）：语义分融合权重（关键词分 1-w + 语义分 w）。
#: 默认 0.4 即「关键词 0.6 + 向量/语义 0.4」；可通过 SearchParams.semantic_weight
#: 或 search()/recommend() 的同名参数覆盖。
_SEMANTIC_WEIGHT = 0.4

#: F1 语义检索：纯语义召回阈值。仅当语义开关开启且权重 > 0 时，关键词分
#: 为 0 但语义分 ≥ 该值的条目才允许进入结果（提升跨义词召回；权重为 0 时
#: 完全不收纯语义条目，保证回退关键词基线）。
_SEM_CUTOFF = 0.2

#: SearchParams.filtered_args() 视为过滤约束的字段
#: （语义打分参数 semantic_weight/semantic_cutoff 与索引开关
#: use_inverted/semantic 不算过滤约束）。
_FILTER_FIELDS = ("query", "category", "author", "tags", "kind", "purpose",
                  "industry", "languages", "trust", "exclude_tags",
                  "tags_mode", "name", "md5", "limit", "offset")

#: P4 短字段（id/name/tag/usage）连续子串索引的最大子串长度。
#: 线性打分中「词 ∈ 字段」对短字段以子串判定，故短字段建受限全子串
#: 索引（≤ 该长度全覆盖）以保持与线性结果等价；超长子串（>12）罕见，
#: 由「词零命中回退线性」兜底。description 长字段仅建 token 级索引。
_INVERTED_MAX_SUBSTR = 12

#: F2 模糊匹配与拼写纠错（提升计划 F2）：编辑距离容错上限（≤2）。
#: 对查询词与索引 term（id/name/desc/tag/usage 的 token）匹配。
_FUZZY_MAX_DIST = 2

#: F2 did-you-mean 相似度阈值：similarity = 1 - dist/max(len)，低于该值
#: 的候选不进入纠错建议（避免"距离 2 但长得完全不像"的噪音）。
_FUZZY_CUTOFF = 0.5

#: F2 模糊命中降权分（模糊是兜底纠错，权重低于精确关键词命中）。
_FUZZY_WHOLE_SCORE = 0.3
_FUZZY_TOKEN_SCORE = 0.25
_FUZZY_TAG_SCORE = 0.2
_FUZZY_PINYIN_SCORE = 0.25
_FUZZY_DESC_SCORE = 0.15

# E4 排序：trust 模式的信任级别次序（trusted 最高，缺省按 community 处理）
_TRUST_RANK = {'trusted': 0, 'community': 1, 'unverified': 2}


@dataclass
class SearchParams:
    """统一检索参数（提升计划 E1：三入口共用同一检索内核）。

    registry.search / MCP actus_search / CLI search 全部收敛到
    `ActionRegistry.search_params`，本对象是唯一的参数载体。
    """

    query: Optional[str] = None       # 关键词（空串/None → 按 limit 返回最近注册动作）
    category: Optional[str] = None    # 注册表分类过滤（RegistryEntry.category）
    author: Optional[str] = None      # 作者过滤
    tags: Optional[List[str]] = None  # 标签过滤（匹配任意一个）
    kind: Optional[str] = None        # v2.0 动作类别（exec/demo/template…）
    purpose: Optional[str] = None     # v2.0 用途维度（多值中命中任一）
    industry: Optional[str] = None    # v2.0 行业维度（多值中命中任一）
    languages: Optional[List[str]] = None  # T0r14 语言维度（多值中命中任一）
    trust: Optional[str] = None       # T0r14 信任级别过滤（trusted/community/unverified，单值）
    exclude_tags: Optional[List[str]] = None  # T0r14 排除标签（与任一相交即排除）
    tags_mode: Optional[str] = None   # T0r14 多 tag 语义（"and"=全部命中；None/"or"=任一命中，保持既有行为）
    name: Optional[str] = None        # P1 名称维度（命中 by_name 反向索引预过滤）
    md5: Optional[str] = None         # P1 内容指纹维度（命中 by_md5 反向索引预过滤）
    limit: int = 50                   # 最大返回数（空查询语义也按此截断）
    offset: int = 0                   # 分页偏移
    semantic: bool = False            # F1：是否启用语义分融合排序（默认关闭=回退关键词基线）
    semantic_weight: float = _SEMANTIC_WEIGHT  # F1：语义分权重 w（关键词分占 1-w）
    semantic_cutoff: float = _SEM_CUTOFF      # F1：纯语义召回阈值（语义分≥此值且关键词 0 分时允许召回）
    use_inverted: bool = True         # P4：是否启用倒排/前缀索引候选加速
                                      #（False 走线性全量打分，等价基准/调试用）
    fuzzy: bool = False               # F2：编辑距离容错开关（默认关闭=回退关键词基线）
    fuzzy_max_dist: int = _FUZZY_MAX_DIST  # F2：最大编辑距离（≤2）
    fuzzy_cutoff: float = _FUZZY_CUTOFF    # F2：模糊命中相似度阈值
    pinyin: bool = False              # F2：拼音前缀容错开关（可选 pypinyin，
                                      #     缺失时优雅降级为无命中，不崩溃）
    sort: Optional[str] = None        # E4：结果排序（trust|name|recent；
                                      #     None=默认相关度排序，不回归）

    def filtered_args(self) -> dict:
        """非空过滤参数（供日志/调试与下游理解本次检索约束）。

        布尔开关（semantic）与打分参数（semantic_weight/semantic_cutoff）
        及索引开关（use_inverted）不算过滤约束，不列出。
        """
        data = asdict(self)
        return {k: data[k] for k in _FILTER_FIELDS
                if data[k] not in (None, [], "")}


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
    # v2.0 分类维度（E1 统一检索新增；.actus.registry.json 旧条目缺省 None）：
    # kind 单值；purpose / industry 多值列表（索引 brief 来源）。
    kind: Optional[str] = None
    purpose: Optional[List[str]] = None
    industry: Optional[List[str]] = None
    # T0r14 语言维度（索引 brief 的 languages 字段，代码块语言提取；空列表无命中）
    languages: Optional[List[str]] = None
    # E3 推荐/联想新增：用法说明（索引 brief 的 usage 字段，reason 链来源之一）
    usage: Optional[str] = None

    def __post_init__(self) -> None:
        """初始化后处理：将 None 字段归一为空列表，保证下游可迭代。"""
        if self.permissions is None:
            self.permissions = []
        if self.dependencies is None:
            self.dependencies = []
        if self.purpose is None:
            self.purpose = []
        if self.industry is None:
            self.industry = []
        if self.languages is None:
            self.languages = []
        if self.usage is None:
            self.usage = ""

    @classmethod
    def from_brief(cls, action_id: str, brief: dict) -> "RegistryEntry":
        """从 indexer 的 actions.index.json 条目（brief）构造条目。

        E1 统一检索入口：MCP/CLI 从 `_meta/actions.index.json` 加载统一内核，
        需要把 indexer 的 brief 映射为 RegistryEntry。索引文件本身不被修改。
        """
        tags = brief.get("tags") or []
        if not isinstance(tags, list):
            tags = [t for t in str(tags).split(",") if t.strip()]
        kind = brief.get("kind") or "exec"
        purpose = brief.get("purpose") or ["utility"]
        if not isinstance(purpose, list):
            purpose = [str(purpose)]
        industry = brief.get("industry") or ["general"]
        if not isinstance(industry, list):
            industry = [str(industry)]
        languages = brief.get("languages") or []
        if not isinstance(languages, list):
            languages = [str(languages)]
        languages = [str(l).strip().lower() for l in languages if str(l).strip()]
        return cls(
            id=action_id,
            name=brief.get("name") or action_id,
            version=brief.get("version") or "",
            description=brief.get("description") or "",
            category=brief.get("category") or kind,
            path=brief.get("path") or "",
            author=brief.get("author") or "",
            tags=tags,
            checksum=brief.get("md5") or brief.get("sha256") or "",
            signature=None,
            permissions=[],
            dependencies=[],
            trust_level=brief.get("trust") or "community",
            kind=kind,
            purpose=purpose,
            industry=industry,
            languages=languages,
            usage=brief.get("usage") or "",
        )

    def to_dict(self) -> dict:
        """转为普通 dict（dataclass asdict）。"""
        return asdict(self)

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
        # P1：by_* 反向索引复用（提升计划 P0/P1）。
        # `load_from_index` 从 actions.index.json 提取 by_kind/by_purpose/
        # by_industry/by_name/by_md5；`search_params` 命中维度时先按索引求
        # 候选集再做评分/切片，替代对 `actions` 全量的线性扫描。
        # 旧索引缺某维度键 → 该维度回退全量扫描（等价性由测试锁定）。
        self._inv: Dict[str, Dict[str, object]] = {}
        #: 无反向索引时的等价回退映射（与索引同源，均来自 brief，见
        #: indexer.build_index 建键规则）：name 键 = brief.name 小写
        #: （缺 name 不入键）；md5 键 = brief.md5 32hex 小写（仅 32 位收录）。
        self._name_key_of: Dict[str, str] = {}
        self._id_md5: Dict[str, str] = {}
        #: P4 内存倒排/前缀索引（惰性构建）：None = 未构建或失效。
        #: `_entries` 变更入口（build_from_directory / load_from_file /
        #: load_from_index）重置为 None，下次搜索按需重建。
        self._inverted: Optional[dict] = None
        #: F1 语义打分器（惰性构建）：None = 未构建或失效。
        #: 与 `_inverted` 同生命周期——entries 变更即失效，下次语义检索
        #: 按需重建（TF-IDF 模型随条目变化自动重算）。
        self._semantic_scorer: Optional[SemanticScorer] = None
        #: F1 可选嵌入器注入点（默认 None = 内置 TF-IDF 路径）。
        #: 可赋 `try_load_embedder()` 返回的 Sentence-Transformer 实例；
        #: 模型缺失/加载失败时为 None，语义检索自动降级 TF-IDF，不崩溃。
        self.semantic_embedder: Optional[object] = None

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

        # P4：条目集合已变，倒排/前缀索引失效（惰性重建）
        self._inverted = None
        self._semantic_scorer = None

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
        # P4：条目集合已变，倒排/前缀索引失效（惰性重建）
        self._inverted = None
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

    def load_from_index(self, index: dict) -> None:
        """从 indexer 的 actions.index.json（brief）填充注册表条目。

        E1 统一检索入口：MCP actus_search / CLI search 用同一份
        `_meta/actions.index.json` 作为数据源，保证检索口径一致。
        P1 反向索引复用：同时提取 by_kind/by_purpose/by_industry/by_name/
        by_md5 到 `self._inv`，供 `search_params` 预过滤。索引结构
        （schema v2.0.0）不在此处改动；`_invalid:` 前缀条目跳过。
        """
        self._entries.clear()
        self._inv.clear()
        self._name_key_of.clear()
        self._id_md5.clear()
        # P4：条目集合已变，倒排/前缀索引失效（惰性重建）
        self._inverted = None
        self._semantic_scorer = None
        raw_actions = index.get("actions") or {}
        for aid, raw in raw_actions.items():
            if not isinstance(aid, str) or aid.startswith("_invalid:"):
                continue
            if not isinstance(raw, dict):
                continue
            entry = RegistryEntry.from_brief(aid, raw)
            if entry:
                self._entries[entry.id] = entry
            # P1 回退映射（与 indexer.build_index 建键规则保持一致）：
            # by_name 只收录 brief.name 非空者；by_md5 只收录 32 位 hex。
            name_raw = str(raw.get("name") or "").strip().lower()
            if name_raw:
                self._name_key_of[aid] = name_raw
            md5_raw = str(raw.get("md5") or "").strip().lower()
            if md5_raw and len(md5_raw) == 32:
                self._id_md5[aid] = md5_raw
        # P1：提取反向索引。缺失的维度（旧索引/自定义索引无 by_* 键，
        # 或索引为空 dict —— 空索引无预过滤价值，同样回退全量扫描）
        # → 该维度回退全量扫描，保证与旧索引向后兼容。
        # T0r14：新增 languages/trust 维度（by_languages/by_trust）。
        for dim in ("kind", "purpose", "industry", "name", "md5",
                    "languages", "trust"):
            idx = index.get("by_" + dim)
            if isinstance(idx, dict) and idx:
                self._inv[dim] = idx

    def search(self, query: str = None, category: str = None,
               author: str = None, tags: List[str] = None,
               limit: int = 50, semantic: bool = False,
               kind: str = None, purpose: str = None,
               industry: str = None, offset: int = 0,
               languages: List[str] = None, trust: str = None,
               exclude_tags: List[str] = None, tags_mode: str = None,
               name: str = None, md5: str = None,
               semantic_weight: float = _SEMANTIC_WEIGHT,
               semantic_cutoff: float = _SEM_CUTOFF,
               fuzzy: bool = False, pinyin: bool = False,
               fuzzy_max_dist: int = _FUZZY_MAX_DIST,
               fuzzy_cutoff: float = _FUZZY_CUTOFF,
               sort: str = None) -> List[RegistryEntry]:
        """搜索注册表条目（**委托统一检索内核** `search_params`）。

        参数:
            query: 关键词（匹配 id/name/description/tags）。
                   空串/None → 按 limit 返回**最近注册**动作（统一空查询语义）。
            category: 分类过滤（RegistryEntry.category）。
            author: 作者过滤。
            tags: 标签过滤（匹配任意一个）。
            limit: 最大返回数。
            semantic: 是否启用语义分融合排序（默认关闭 = 完全回退关键词打分）。
            kind: v2.0 动作类别过滤（exec/demo/template…）。
            purpose: v2.0 用途维度过滤（多值中命中任一）。
            industry: v2.0 行业维度过滤（多值中命中任一）。
            languages: T0r14 语言维度过滤（代码块语言，多值中命中任一）。
            trust: T0r14 信任级别过滤（trusted/community/unverified，单值）。
            exclude_tags: T0r14 排除标签（与任一相交即排除；tags 中的
                          "-tag" 前缀写法也会被拆分为排除语义）。
            tags_mode: T0r14 多 tag 语义（"and"=全部标签命中；
                       None/"or"=任一标签命中，保持既有行为）。
            offset: 分页偏移。
            name: 名称精确维度（命中 by_name 反向索引预过滤）。
            md5: 内容指纹维度（命中 by_md5 反向索引预过滤）。
            semantic_weight: 语义分权重 w（关键词分占 1-w；默认 0.4）。
            semantic_cutoff: 纯语义召回阈值（仅 semantic=True 且权重>0 生效）。
            fuzzy: F2 编辑距离容错开关（默认关闭 = 回退关键词基线；开启后
                   仅在关键词零命中时兜底纠错召回）。
            pinyin: F2 拼音前缀容错开关（可选 pypinyin；缺失时优雅降级
                   为无命中，不崩溃）。
            fuzzy_max_dist: F2 最大编辑距离（≤2）。
            fuzzy_cutoff: F2 模糊命中相似度阈值。
            sort: E4 结果排序（trust=信任度优先/name=名称字典序/
                   recent=最近注册优先；None=默认相关度排序）。

        返回:
            匹配的 RegistryEntry 列表（按相关度排序；空查询按注册序逆序）。

        使用示例:
            ```python
            from vools.actus import ActionRegistry

            reg = ActionRegistry()
            reg.load_from_repo("./my-repo")          # 实时构建（不落盘）
            hits = reg.search("计算", limit=5)       # → List[RegistryEntry]
            for e in hits:
                print(e.id, e.trust_level)
            ```
        """
        params = SearchParams(
            query=query, category=category, author=author, tags=tags,
            limit=limit, semantic=semantic, kind=kind,
            purpose=purpose, industry=industry, offset=offset,
            languages=languages, trust=trust,
            exclude_tags=exclude_tags, tags_mode=tags_mode,
            name=name, md5=md5,
            semantic_weight=semantic_weight,
            semantic_cutoff=semantic_cutoff,
            fuzzy=fuzzy, pinyin=pinyin,
            fuzzy_max_dist=fuzzy_max_dist,
            fuzzy_cutoff=fuzzy_cutoff,
            sort=sort)
        return self.search_params(params)

    def search_params(self, params: SearchParams) -> List[RegistryEntry]:
        """**统一检索内核**（提升计划 E1/P1）：唯一实现过滤 + 打分逻辑。

        MCP `actus_search` 与 CLI `search` 全部委托此处，不再各自实现
        过滤/打分。行为契约：
        - P1：结构化维度（kind/purpose/industry/name/md5）命中反向索引
          `by_*` 时，**先按索引求交集得到候选集**，替代对 `actions` 全量
          线性扫描；category/author/tags 无反向索引，仍由 `_filter_entry`
          兜底过滤。索引缺失的维度自动回退全量等价过滤（旧索引兼容）。
        - 候选集仍过 `_filter_entry`（等价性锚点）→ 索引预过滤结果与
          原有全量扫描结果**完全一致**（由 `test_inverted_index_reuse.py` 锁定）；
        - query 为空（None/''）→ 过滤结果按**注册序逆序**（最近注册在前），
          截断 `offset:offset+limit`；
        - query 非空 → 语义评分（`_score_entry`）>0 者按分降序，
          截断 `offset:offset+limit`；
        - E4：`SearchParams.sort`（trust|name|recent）覆盖默认排序；
          分页 + 真实总数经 `search_params_with_total` 对外暴露。
        """
        full, _total = self._search_params_full(params)
        return full[params.offset: params.offset + params.limit]

    def search_params_with_total(self, params: SearchParams):
        """E4：统一检索内核分页变体——返回 `(分页结果, 实际匹配总数 total)`。

        total 为过滤 + 打分后、截断前的完整命中数（空查询/纯过滤场景
        = 过滤后池大小），供 CLI/MCP 返回真实 total 而不只是本页条数。
        排序/分页语义与 `search_params` 完全一致。
        """
        full, total = self._search_params_full(params)
        return (full[params.offset: params.offset + params.limit], total)

    def _search_params_full(self, params: SearchParams):
        """E4 重构：统一检索内核完整实现，返回 `(完整排序列表, total)`。"""
        q = (params.query or "").strip()

        # ── T0r14 多 tag 语义预处理 ──
        # 支持排除语义：tags 中 "-tag" 前缀写法拆为排除项；exclude_tags
        # 显式排除合并去重。tags_mode="and" 要求全部标签命中，否则保持
        # 既有"任一命中"（OR）行为（向后兼容）。
        tags = [str(t).strip() for t in (params.tags or [])]
        tags = [t for t in tags if t]
        exclude_tags = [str(t).strip() for t in (params.exclude_tags or [])]
        pos_tags, neg_tags = [], []
        for t in tags:
            if t.startswith("-") and len(t) > 1:
                neg_tags.append(t[1:])
            else:
                pos_tags.append(t)
        exclude_tags = list(dict.fromkeys([t for t in exclude_tags + neg_tags if t]))
        tags = list(dict.fromkeys(pos_tags))
        tags_mode = (params.tags_mode or "").strip().lower() or None

        # ── P1 反向索引预过滤：命中维度 → 候选集（交集） ──
        # 与 indexer.build_index 建键一致：查询值 strip+lower 归一。
        # 候选集不保证顺序，最终按 `_entries` 插入序重排（空查询"最近注册
        # 在前"依赖该序）。
        candidates: Optional[set] = None
        for dim, val in (("kind", params.kind), ("purpose", params.purpose),
                         ("industry", params.industry), ("name", params.name),
                         ("md5", params.md5),
                         ("languages", params.languages), ("trust", params.trust)):
            if not val:
                continue
            values = [str(v).strip().lower() for v in
                      (val if isinstance(val, list) else [val])]
            idx = self._inv.get(dim)
            hit: Optional[set] = None
            if idx is not None:
                ids: set = set()
                for v in values:
                    got = idx.get(v)
                    if got is None:
                        continue
                    ids.update(got if isinstance(got, list) else [got])
                hit = ids
            elif dim == "name":
                # 回退：线性扫 by_name 同源映射（缺 name 不入键，与索引一致）
                hit = {aid for aid, nk in self._name_key_of.items()
                       if nk in values}
            elif dim == "md5":
                # 回退：线性扫 by_md5 同源映射（仅 32hex 入映射，与索引一致）
                hit = {aid for aid, m in self._id_md5.items() if m in values}
            # kind/purpose/industry 无索引时无需特殊处理：`_filter_entry`
            # 即全量等价基准，候选集保持 None 即全量扫描。
            if hit is not None:
                candidates = hit if candidates is None else (candidates & hit)

        if candidates is None:
            pool = [e for e in self._entries.values()
                    if self._filter_entry(
                        e, params.category, params.author, tags,
                        params.kind, params.purpose, params.industry,
                        languages=params.languages, trust=params.trust,
                        exclude_tags=exclude_tags, tags_mode=tags_mode)]
        else:
            # 候选集保持注册序；`_filter_entry` 兜底（等价性锚点）。
            pool = [e for e in self._entries.values()
                    if e.id in candidates and self._filter_entry(
                        e, params.category, params.author, tags,
                        params.kind, params.purpose, params.industry,
                        languages=params.languages, trust=params.trust,
                        exclude_tags=exclude_tags, tags_mode=tags_mode)]

        if not q:
            # 空查询统一语义：最近注册动作（插入序逆序 = 最后注册在前）；
            # 排序统一交给 `_order_results`（sort 缺省时维持注册逆序契约）。
            scored = [(0.0, e) for e in pool]
        else:
            query_lower = q.lower()
            query_words = set(tokenize(query_lower, expand_ngram=False))

            # ── P4 倒排/前缀索引候选加速（提升计划 P4） ──
            # 默认启用：先取倒排命中并集（term→action_ids），再对候选集合
            # 打分，把 O(N×字段) 降为 O(候选×字段)。
            # 安全回退（等价性锚点，任一成立走原线性全量打分，结果与倒排
            # 路径完全一致）：
            #   * `use_inverted=False`（等价基准/调试）；
            #   * 倒排未构建（惰性构建失败）；
            #   * 候选无法安全覆盖：存在 ≥2 字符词在倒排/前缀中零命中
            #     （词仅靠字段中段子串命中时倒排会漏检 → 回退线性保正确）；
            #   * 候选超过 `_INVERTED_MAX_SCAN` 上界（限制扫描上界，防止
            #     命中集合过大时 set 并集/打分成为新的瓶颈）。
            cand_ids: Optional[set] = None
            if params.use_inverted:
                self._ensure_inverted()
                cand_ids = self._inverted_candidates(query_lower, query_words)
                if cand_ids is not None and len(cand_ids) > _INVERTED_MAX_SCAN:
                    cand_ids = None

            scored = []
            if params.semantic:
                # ── F1 语义融合排序 ──
                # 对过滤后 pool 全量计算「关键词分 + 语义分」，融合分 =
                # (1-w)*kw + w*sem。收录条件：关键词命中（kw>0）或纯语义召回
                # （权重>0 且语义分 ≥ cutoff）。w=0 时纯语义条目不收，结果与
                # 关键词基线一致（回退语义）；语义分缺失（打分器不可用）时
                # 融合退化为关键词分，行为与基线一致。
                sem_scores = self._semantic_scores(query_lower)
                w = max(0.0, min(1.0, float(params.semantic_weight)))
                cutoff = float(params.semantic_cutoff)
                for entry in pool:
                    kw = self._score_entry(entry, query_lower, query_words)
                    sem = (sem_scores or {}).get(entry.id, 0.0)
                    if kw > 0 or (w > 0 and sem >= cutoff):
                        fused = self._fuse_scores(kw, sem, w)
                        scored.append((fused, entry))
            elif cand_ids is not None:
                for entry in pool:
                    if entry.id not in cand_ids:
                        continue
                    score = self._score_entry(entry, query_lower, query_words)
                    if score > 0:
                        scored.append((score, entry))
            else:
                for entry in pool:
                    score = self._score_entry(entry, query_lower, query_words)
                    if score > 0:
                        scored.append((score, entry))

            # ── F2 模糊匹配与拼写纠错兜底 ──
            # 仅在**关键词零命中**时启用（fuzzy/pinyin 为纠错，不改变已有
            # 命中的排序，保证开关开启时精确路径行为不回归）。对 pool 内
            # 条目做编辑距离容错打分（`_fuzzy_score_entry`），分数 >0 者
            # 进入结果。拼音开关 pypinyin 缺失时 `has_pinyin_support()` 为
            # False，该路自动退化为纯编辑距离，不抛异常。
            if not scored and (params.fuzzy or params.pinyin):
                fuzzy_max_dist = max(0, int(getattr(params, "fuzzy_max_dist",
                                                    _FUZZY_MAX_DIST)))
                for entry in pool:
                    fscore = self._fuzzy_score_entry(
                        entry, query_lower, query_words,
                        max_dist=fuzzy_max_dist,
                        use_pinyin=bool(params.pinyin))
                    if fscore > 0:
                        scored.append((fscore, entry))

        # E4 排序：默认相关度（分降序、同分注册序）；sort 覆盖为
        # trust/name/recent。预建 id→注册序映射，避免每次比较都 O(N)
        # 重建 keys 列表——P4 大库性能优化，行为等价。
        order = {aid: i for i, aid in enumerate(self._entries)}
        full = self._order_results(params, scored, order, empty_query=not q)
        return full, len(full)

    def _order_results(self, params, scored, order, empty_query=False):
        """E4：按 `params.sort` 对 `(score, entry)` 列表排序，返回条目列表。

        - sort=None → 默认相关度（分降序、同分注册序；空查询 = 注册序逆序
          「最近注册在前」，维持既有契约）；
        - trust → 信任级别优先（trusted > community > unverified），
          同级按相关度（分降序、同分注册序）；
        - name → 名称字典序优先（大小写不敏感），同级按相关度；
        - recent → 最近注册优先（注册序逆序），同级按相关度；
        未知 sort 值回退默认相关度（不抛异常、不回归）。
        """
        sort = (params.sort or "").strip().lower() or None
        if sort == "trust":
            scored.sort(key=lambda x: (_TRUST_RANK.get(
                getattr(x[1], "trust_level", None) or "community", 1),
                -x[0], order[x[1].id]))
        elif sort == "name":
            scored.sort(key=lambda x: (
                (x[1].name or x[1].id).lower(), -x[0], order[x[1].id]))
        elif sort == "recent":
            scored.sort(key=lambda x: (-order[x[1].id], -x[0]))
        elif empty_query:
            # 既有空查询语义：最近注册在前（注册序逆序）
            scored.sort(key=lambda x: (-order[x[1].id], -x[0]))
        else:
            scored.sort(key=lambda x: (-x[0], order[x[1].id]))
        return [entry for _, entry in scored]

    def search_explain(self, query: str = None, category: str = None,
                       author: str = None, tags: List[str] = None,
                       limit: int = 50, semantic: bool = False,
                       kind: str = None, purpose: str = None,
                       industry: str = None, offset: int = 0,
                       languages: List[str] = None, trust: str = None,
                       exclude_tags: List[str] = None, tags_mode: str = None,
                       name: str = None, md5: str = None,
                       semantic_weight: float = _SEMANTIC_WEIGHT,
                       semantic_cutoff: float = _SEM_CUTOFF,
                       fuzzy: bool = False, pinyin: bool = False,
                       fuzzy_max_dist: int = _FUZZY_MAX_DIST,
                       fuzzy_cutoff: float = _FUZZY_CUTOFF,
                       sort: str = None) -> List[dict]:
        """搜索并附带匹配解释（提升计划 E2 结果可读性）。

        与 `search` 共用 `search_params` 内核——结果集与排序完全一致，
        每条额外附带：
        - entry: RegistryEntry
        - score: float（0-1，round 3）
        - match_fields: List[str]（命中字段标识，如 ['name', 'tag=record']）
        - reason: str（人类可读理由，如"命中 name、命中 tag=record"）

        空查询（无关键词打分）时 score=0.0、match_fields=[]、reason=''。

        F1 语义开启时：结果排序按融合分，但 `score` 字段仍报告关键词分
        （既有契约，E2 解释链不变；语义分可通过 `entry` 的排序位置观察）。
        F2 模糊开启时（关键词零命中、模糊纠错召回）：`score` 报告模糊
        容错分，`match_fields` 含 `fuzzy=...` / `pinyin=...` 标注，
        `reason` 含"拼写近似"/"拼音近似"说明。
        E4：`sort`（trust|name|recent）覆盖默认排序，语义同 `search`。
        """
        params = SearchParams(
            query=query, category=category, author=author, tags=tags,
            limit=limit, semantic=semantic, kind=kind,
            purpose=purpose, industry=industry, offset=offset,
            languages=languages, trust=trust,
            exclude_tags=exclude_tags, tags_mode=tags_mode,
            name=name, md5=md5,
            semantic_weight=semantic_weight,
            semantic_cutoff=semantic_cutoff,
            fuzzy=fuzzy, pinyin=pinyin,
            fuzzy_max_dist=fuzzy_max_dist,
            fuzzy_cutoff=fuzzy_cutoff,
            sort=sort)
        return self.search_explain_params(params)

    def search_explain_params(self, params: SearchParams) -> List[dict]:
        """search_explain 的 SearchParams 版本（MCP/CLI 统一入口）。"""
        out, _total = self.search_explain_params_with_total(params)
        return out

    def search_explain_params_with_total(self, params: SearchParams):
        """E4：解释版分页变体——返回 `(解释列表, 实际匹配总数 total)`。

        解释内容与 `search_explain_params` 完全一致；total 语义同
        `search_params_with_total`（过滤+打分后、截断前的完整命中数），
        供 MCP/CLI 在带分页时返回真实总数。
        """
        entries, total = self.search_params_with_total(params)
        return (self._build_explanations(params, entries), total)

    def _build_explanations(self, params: SearchParams,
                            entries: List[RegistryEntry]) -> List[dict]:
        """为分页后的条目逐条构建匹配解释（E2 契约，E4 提取复用）。"""
        q = (params.query or "").strip()
        if not q:
            return [{'entry': e, 'score': 0.0, 'match_fields': [],
                     'reason': ''} for e in entries]
        query_lower = q.lower()
        query_words = set(tokenize(query_lower, expand_ngram=False))
        w = max(0.0, min(1.0, float(getattr(params, 'semantic_weight', _SEMANTIC_WEIGHT))))
        cutoff = float(getattr(params, 'semantic_cutoff', _SEM_CUTOFF))
        sem_scores = self._semantic_scores(query_lower) if getattr(params, 'semantic', False) else {}
        # F2：模糊兜底开启（关键词零命中时 `search_params` 可能返回模糊纠错
        # 条目）。这类条目关键词分为 0，需要报告模糊容错分与标注。
        use_fuzzy = bool(getattr(params, "fuzzy", False) or getattr(params, "pinyin", False))
        fuzzy_max_dist = max(0, int(getattr(params, "fuzzy_max_dist", _FUZZY_MAX_DIST)))
        out = []
        for e in entries:
            score, fields = self._score_entry_ex(e, query_lower, query_words)
            if not fields and use_fuzzy:
                fscore, ffields = self._fuzzy_score_entry_ex(
                    e, query_lower, query_words,
                    max_dist=fuzzy_max_dist,
                    use_pinyin=bool(getattr(params, "pinyin", False)))
                if fscore > 0:
                    score, fields = fscore, ffields
            if fields:
                reason = self._reason_from_fields(fields)
            elif sem_scores and sem_scores.get(e.id, 0.0) >= cutoff and w > 0:
                reason = '语义相近'
            else:
                reason = ''
            out.append({'entry': e, 'score': round(score, 3),
                        'match_fields': fields, 'reason': reason})
        return out

    @staticmethod
    def _filter_entry(entry, category: str = None, author: str = None,
                      tags: List[str] = None, kind: str = None,
                      purpose: str = None, industry: str = None,
                      languages: List[str] = None, trust: str = None,
                      exclude_tags: List[str] = None,
                      tags_mode: str = None) -> bool:
        """硬过滤：category / author / tags / kind / purpose / industry /
        languages / trust 任一不满足即排除。

        T0r14 语义：
        - tags：默认任一命中（OR，保持既有行为）；tags_mode="and" 时要求
          全部命中；exclude_tags（或 tags 中 "-tag" 拆分而来）与任一相交
          即排除。
        - languages：多值命中任一（与索引建键一致，大小写不敏感）。
        - trust：单值精确匹配（大小写不敏感，缺省按 community 处理）。
        """
        if category and entry.category != category:
            return False
        if author and entry.author != author:
            return False
        if tags:
            if (tags_mode or "").strip().lower() == "and":
                if not all(t in entry.tags for t in tags):
                    return False
            elif not any(t in entry.tags for t in tags):
                return False
        if exclude_tags and any(t in entry.tags for t in exclude_tags):
            return False
        if kind:
            ekind = getattr(entry, "kind", None) or entry.category
            if ekind != kind:
                return False
        if purpose:
            epurpose = getattr(entry, "purpose", None) or []
            if not any(p in epurpose for p in (purpose if isinstance(purpose, list) else [purpose])):
                return False
        if industry:
            eindustry = getattr(entry, "industry", None) or []
            if not any(i in eindustry for i in (industry if isinstance(industry, list) else [industry])):
                return False
        if languages:
            elangs = [str(x).strip().lower() for x in
                      (getattr(entry, "languages", None) or [])]
            wanted = [str(x).strip().lower() for x in
                      (languages if isinstance(languages, list) else [languages])]
            if not any(l in elangs for l in wanted):
                return False
        if trust:
            etrust = (getattr(entry, "trust_level", None) or "community")
            if str(etrust).strip().lower() != str(trust).strip().lower():
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

    # ──────────────────────────── P4 倒排/前缀索引 ────────────────────────────
    # 提升计划 P4「检索复杂度优化」：把 `search_params` 的非空 query 打分
    # 从全量线性 O(N×字段) 降为 O(候选×字段)。
    #   * 倒排表：term(token/前缀/短字段整串) → {action_id, ...}；
    #   * 前缀索引：id / name 小写排序数组，查询词 `bisect` 前缀范围；
    #   * 查询 = 各词精确命中 ∪ 前缀命中 的并集 → 候选集合；
    #   * 候选无法安全覆盖 / 候选过多时回退线性（等价性锚点）。

    def build_inverted_index(self) -> dict:
        """构建内存倒排表与前缀索引（P4），返回索引结构供测试/统计。

        倒排 term 覆盖规则（与 `_score_entry_ex` 命中判定对齐）：
        - **精确 token**：id/name/description/usage/tags 按空白分词（小写）
          后的每个 token（覆盖词级精确命中 + 整串 query∈字段 的 token 级
          情形，如 'monitor' → desc token）；
        - **token 前缀链**：每个 token 的 ≥`_INVERTED_MIN_TERM` 字符前缀
          （覆盖「词是字段 token 前缀」的词级子串命中与前缀查询，如
          'cal' → 'calculator'）；
        - **短字段连续子串**：id/name/tag/usage 的全部长度 ≤
          `_INVERTED_MAX_SUBSTR` 连续子串（覆盖「query/词 ∈ 短字段」的
          中段/后缀子串命中，如 '记录' ∈ usage '测试记录'、
          'finance.tax' ∈ id 'calc.finance.tax'）；
        - **前缀索引**：id / name 小写排序数组（`bisect` 前缀范围），
          加速 id/name 前缀查询（如 'bench.action'）。

        近似说明（已知且被兜底）：description 为长字段，仅建 token 级
        索引（中段子串如 'lcul' ∈ 'calculator' 不建）——这类词级命中仅
        +0.08 且实际查询罕见；当任一查询词在倒排/前缀中零命中时
        `search_params` 自动回退线性全量打分，保证与线性结果一致
        （等价性测试锁定）。
        """
        terms: Dict[str, set] = {}
        id_keys: List[str] = []
        id_by_lower: Dict[str, str] = {}
        name_keys: List[Tuple[str, str]] = []

        def _add(t: str, aid: str) -> None:
            terms.setdefault(t, set()).add(aid)

        def _add_substrings(text: str, aid: str) -> None:
            """短字段受限全子串索引（含整串与全部前缀/中段/后缀）。"""
            n = len(text)
            for start in range(n):
                hi = min(n, start + _INVERTED_MAX_SUBSTR) + 1
                for end in range(start + _INVERTED_MIN_TERM, hi):
                    _add(text[start:end], aid)

        def _add_token_prefixes(text: str, aid: str) -> None:
            """长字段 token 级（精确 token + 前缀链）。"""
            for tok in text.split():
                _add(tok, aid)
                for i in range(_INVERTED_MIN_TERM, len(tok) + 1):
                    _add(tok[:i], aid)

        for aid, e in self._entries.items():
            eid_l = (e.id or "").lower()
            name_l = (e.name or "").lower()
            desc_l = (e.description or "").lower()
            usage_l = (e.usage or "").lower()
            if eid_l:
                id_keys.append(eid_l)
                id_by_lower.setdefault(eid_l, aid)
            if name_l:
                name_keys.append((name_l, aid))
            # description：长字段，仅 token 级（精确 + 前缀链）
            _add_token_prefixes(desc_l, aid)
            # usage / id / name / tags：短字段，token 级 + 受限全子串
            for text in (usage_l, eid_l, name_l):
                if not text:
                    continue
                _add_token_prefixes(text, aid)
                _add_substrings(text, aid)
            for tag in e.tags or []:
                tag_l = str(tag).lower()
                if not tag_l:
                    continue
                _add_token_prefixes(tag_l, aid)
                _add_substrings(tag_l, aid)

        inv = {
            "terms": terms,
            "id_keys": sorted(set(id_keys)),
            "id_by_lower": id_by_lower,
            "name_keys": sorted(name_keys, key=lambda kv: kv[0]),
            "entry_count": len(self._entries),
        }
        self._inverted = inv
        return inv

    def _ensure_inverted(self) -> Optional[dict]:
        """惰性构建倒排/前缀索引（entries 变更入口已重置 `self._inverted`）。"""
        if self._inverted is None:
            return self.build_inverted_index()
        return self._inverted

    # ── F1 语义检索（提升计划 F1） ──

    def _semantic_docs(self) -> Dict[str, str]:
        """语义文档归一化文本：id + name + tags + description + usage。

        语义模型对"跨义词"的召回靠多字段叠加词袋：同一动作的 id/name/
        tags/description/usage 各自贡献 token，查询与任一字段语义相近即可
        获得非零余弦分。
        """
        docs: Dict[str, str] = {}
        for aid, e in self._entries.items():
            parts = [aid, e.name or "",
                     " ".join(t for t in (e.tags or []) if t),
                     e.description or "", e.usage or ""]
            docs[aid] = " ".join(p for p in parts if p)
        return docs

    def _ensure_semantic(self) -> Optional[SemanticScorer]:
        """惰性构建语义打分器（entries 变更入口已重置 `self._semantic_scorer`）。

        embedder 注入后仍可能编码失败——`SemanticScorer` 内部自动降级
        TF-IDF；此处永不抛异常，失败返回 None（调用方按关键词路径回退）。
        """
        if self._semantic_scorer is None:
            try:
                self._semantic_scorer = SemanticScorer(
                    embedder=self.semantic_embedder
                ).build(self._semantic_docs())
            except Exception:
                self._semantic_scorer = None
        return self._semantic_scorer

    def _semantic_scores(self, query_lower: str) -> Dict[str, float]:
        """查询语义分 {action_id: 0~1}；打分器不可用时返回 {}。"""
        scorer = self._ensure_semantic()
        if scorer is None:
            return {}
        try:
            return scorer.scores(query_lower)
        except Exception:
            return {}

    @staticmethod
    def _fuse_scores(kw: float, sem: float, weight: float) -> float:
        """关键词分与语义分加权融合：final = (1-w)*kw + w*sem。

        权重越界自动钳制到 [0,1]；w=0 时恒等于关键词分（回退基线）。
        """
        w = max(0.0, min(1.0, float(weight)))
        return (1.0 - w) * kw + w * sem

    @staticmethod
    def _prefix_ids(inv: dict, word: str) -> set:
        """前缀索引命中（id 前缀 + name 前缀，bisect 前缀范围）。"""
        hits: set = set()
        id_keys = inv["id_keys"]
        id_by_lower = inv["id_by_lower"]
        lo = bisect_left(id_keys, word)
        i = lo
        while i < len(id_keys) and id_keys[i].startswith(word):
            hits.add(id_by_lower[id_keys[i]])
            i += 1
        name_keys = inv["name_keys"]
        lo = bisect_left(name_keys, (word, ""))
        i = lo
        while i < len(name_keys) and name_keys[i][0].startswith(word):
            hits.add(name_keys[i][1])
            i += 1
        return hits

    def _inverted_candidates(self, query_lower: str,
                             query_words: set) -> Optional[set]:
        """倒排/前缀索引召回候选 id 集合；返回 None 表示回退线性。

        快路径条件（全部满足才走倒排，否则回退线性保证与线性打分结果
        等价）：
        - 倒排已构建；
        - `query_words` 中每个 ≥2 字符的词都至少在精确 token / 前缀数组
          中有一个命中（杜绝「词仅靠字段中段子串命中」导致的候选漏检）；
        - `query_lower` 整串也查一次精确命中（覆盖单 token 整串
          query∈字段 与跨词整串的前缀命中场景）。
        """
        inv = self._inverted
        if inv is None:
            return None
        terms = inv["terms"]
        cand: Optional[set] = None
        missing = False
        for word in query_words:
            if len(word) < _INVERTED_MIN_TERM:
                continue
            hits = set(terms.get(word, ()))
            hits.update(self._prefix_ids(inv, word))
            if not hits:
                missing = True
            if cand is None:
                cand = hits
            else:
                cand.update(hits)
        whole = terms.get(query_lower)
        if whole:
            if cand is None:
                cand = set(whole)
            else:
                cand.update(whole)
        if missing:
            return None
        return cand if cand else None

    def _score_entry(self, entry: RegistryEntry,
                     query_lower: str, query_words: set) -> float:
        """计算条目的相关度分数（0-1）。

        委托 `_score_entry_ex` 取分（E2 结果可读性）：分数与 match_fields
        同源生成，杜绝打分逻辑两处漂移。
        """
        score, _ = self._score_entry_ex(entry, query_lower, query_words)
        return score

    @staticmethod
    def _score_entry_ex(entry: RegistryEntry,
                        query_lower: str, query_words: set):
        """计算相关度分数并收集命中字段（E2 结果可读性）。

        返回 `(score, match_fields)`：
        - score 与 `_score_entry` 完全一致（0-1，cap 1.0）；
        - match_fields 为命中字段标识列表（如 ['id', 'name',
          'tag=record', 'word=monitor']），供 CLI/MCP 展示 match reason。
        """
        score = 0.0
        fields: List[str] = []

        def _add(field: str) -> None:
            if field not in fields:
                fields.append(field)

        # 精确 id 匹配（最高分）
        if query_lower == entry.id.lower():
            score += 1.0
            _add('id')
        elif query_lower in entry.id.lower():
            score += 0.6
            _add('id')

        # 名称匹配
        if query_lower in entry.name.lower():
            score += 0.5
            _add('name')

        # 描述匹配
        if query_lower in entry.description.lower():
            score += 0.3
            _add('description')

        # 用法匹配（E3 推荐 reason 链：命中 usage 也计入置信度）
        if entry.usage and query_lower in entry.usage.lower():
            score += 0.25
            _add('usage')

        # 标签精确匹配
        for tag in entry.tags:
            if tag.lower() == query_lower:
                score += 0.4
                _add(f'tag={tag}')
            elif tag.lower() in query_lower:
                score += 0.2
                _add(f'tag={tag}')

        # 关键词匹配（每个词加分）
        for word in query_words:
            if len(word) < 2:
                continue
            if word in entry.id.lower():
                score += 0.15
                _add(f'word={word}')
            if word in entry.name.lower():
                score += 0.1
                _add(f'word={word}')
            if word in entry.description.lower():
                score += 0.08
                _add(f'word={word}')
            if entry.usage and word in entry.usage.lower():
                score += 0.1
                _add('usage')
            for tag in entry.tags:
                if word in tag.lower():
                    score += 0.12
                    _add(f'tag={tag}')

        return min(score, 1.0), fields

    # ── F2 模糊匹配与拼写纠错（提升计划 F2） ──

    def _fuzzy_score_entry(self, entry: RegistryEntry,
                           query_lower: str, query_words: set,
                           max_dist: int = _FUZZY_MAX_DIST,
                           use_pinyin: bool = False) -> float:
        """计算条目的模糊容错分（0-1；关键词零命中时的纠错兜底路径）。

        委托 `_fuzzy_score_entry_ex` 取分与命中标注（与 `_score_entry`
        同源原则）。无任何模糊命中返回 0.0。
        """
        score, _ = self._fuzzy_score_entry_ex(
            entry, query_lower, query_words,
            max_dist=max_dist, use_pinyin=use_pinyin)
        return score

    @classmethod
    def _fuzzy_score_entry_ex(cls, entry: RegistryEntry,
                              query_lower: str, query_words: set,
                              max_dist: int = _FUZZY_MAX_DIST,
                              use_pinyin: bool = False):
        """计算模糊容错分并收集命中标注（F2 纠错路径）。

        返回 `(score, match_fields)`：score 与 `_fuzzy_score_entry`
        完全一致（0-1，cap 1.0）。命中判定：
        - 编辑距离：`fuzzy_match(word, term, max_dist)`（小写归一，
          距离 ≤ max_dist）；覆盖 id/name/tags/description/usage；
        - 拼音前缀：`pinyin_prefix_match`（可选 pypinyin，缺失自动
          降级无命中，不抛异常）；仅 use_pinyin=True 时启用；
        - 每字段至多计一次分（多个查询词命中同一字段不重复叠加）。

        权重：整串命中 id/name +0.3；词级命中 id/name +0.25；tag +0.2；
        description/usage +0.15；拼音命中同字段再 +0.25/+0.2/+0.15
        （按字段对齐，避免拼音分叠加出越界）。
        """
        score = 0.0
        fields: List[str] = []

        def _add(field: str, weight: float) -> None:
            nonlocal score
            if field in fields:
                return
            score += weight
            fields.append(field)

        id_l = (entry.id or "").lower()
        name_l = (entry.name or "").lower()
        desc_l = (entry.description or "").lower()
        usage_l = (entry.usage or "").lower()
        id_tokens = [t for t in id_l.replace('.', ' ').split() if len(t) >= 2]
        name_tokens = [t for t in name_l.split() if len(t) >= 2]
        desc_tokens = [t for t in desc_l.split() if len(t) >= 2]
        usage_tokens = [t for t in usage_l.split() if len(t) >= 2]
        tag_lowers = [str(t).lower() for t in (entry.tags or []) if t]

        def _fuzzy_any(word: str, terms) -> bool:
            return any(fuzzy_match(word, t, max_dist) for t in terms if t)

        # 整串模糊命中（query 与整字段）
        if fuzzy_match(query_lower, id_l, max_dist):
            _add('fuzzy=id', _FUZZY_WHOLE_SCORE)
        if fuzzy_match(query_lower, name_l, max_dist):
            _add('fuzzy=name', _FUZZY_WHOLE_SCORE)
        if any(fuzzy_match(query_lower, t, max_dist) for t in tag_lowers):
            _add('fuzzy=tag', _FUZZY_TAG_SCORE)

        # 词级模糊命中（每个查询词 vs 字段 token）
        for word in query_words:
            if len(word) < 2:
                continue
            if _fuzzy_any(word, id_tokens):
                _add('fuzzy=id', _FUZZY_TOKEN_SCORE)
            if _fuzzy_any(word, name_tokens):
                _add('fuzzy=name', _FUZZY_TOKEN_SCORE)
            if _fuzzy_any(word, tag_lowers):
                _add('fuzzy=tag', _FUZZY_TAG_SCORE)
            if _fuzzy_any(word, desc_tokens):
                _add('fuzzy=description', _FUZZY_DESC_SCORE)
            if _fuzzy_any(word, usage_tokens):
                _add('fuzzy=usage', _FUZZY_DESC_SCORE)

        # 拼音前缀容错（可选 pypinyin，缺失优雅降级）
        if use_pinyin and has_pinyin_support():
            def _pinyin_any(word: str, terms) -> bool:
                return any(pinyin_prefix_match(word, t, max_dist)
                           for t in terms if t)
            for word in [query_lower] + sorted(query_words):
                if len(word) < 2:
                    continue
                if _pinyin_any(word, id_tokens):
                    _add('pinyin=id', _FUZZY_PINYIN_SCORE)
                if _pinyin_any(word, name_tokens):
                    _add('pinyin=name', _FUZZY_PINYIN_SCORE)
                if _pinyin_any(word, tag_lowers):
                    _add('pinyin=tag', _FUZZY_TAG_SCORE)
                if _pinyin_any(word, desc_tokens):
                    _add('pinyin=description', _FUZZY_DESC_SCORE)
                if _pinyin_any(word, usage_tokens):
                    _add('pinyin=usage', _FUZZY_DESC_SCORE)

        return min(score, 1.0), fields

    def suggest(self, query: str = None, limit: int = 3,
                max_dist: int = _FUZZY_MAX_DIST,
                cutoff: float = _FUZZY_CUTOFF,
                use_pinyin: bool = True) -> List[dict]:
        """查询无命中时给出纠错建议（did you mean）。

        对注册表内 id/name/tags/usage/description 的候选 term 计算
        编辑距离（`edit_suggestions`）与拼音前缀（`pinyin_suggestions`，
        可选 pypinyin，缺失自动降级为纯编辑距离），返回距离最近且
        相似度 ≥ cutoff 的候选词与所属动作。

        返回:
            [{term, distance, similarity, action_id, kind}]：
            - term: 候选词（原大小写）；
            - distance: 与查询的编辑距离；
            - similarity: 归一化相似度（1-dist/max_len）；
            - action_id: 候选词所属动作 id；
            - kind: 'edit' 编辑距离纠错 / 'pinyin' 拼音纠错。
        """
        q = (query or "").strip()
        if not q:
            return []
        q_lower = q.lower()
        # 候选 term 收集（id/name/tag 全量；usage/description 仅 token，
        # 与打分字段口径一致，避免超长描述整串误建议）
        terms: Dict[str, str] = {}
        for aid, e in self._entries.items():
            for t in (e.id or "", e.name or ""):
                if t:
                    terms.setdefault(t, aid)
            for t in (e.tags or []):
                if t:
                    terms.setdefault(str(t), aid)
            for t in ((e.usage or "").split() + (e.description or "").split()):
                if len(t) >= 2:
                    terms.setdefault(t, aid)
        if not terms:
            return []

        # 排除已精确/包含命中的 term（纠错只服务真正无命中场景）
        skipped = [t for t in terms
                   if q_lower == t.lower() or q_lower in t.lower()
                   or t.lower() in q_lower]
        pool = [t for t in terms if t not in skipped]

        suggestions: List[dict] = []
        for t in pool:
            t_l = t.lower()
            for cand in edit_suggestions(q_lower, [t_l], max_dist=max_dist,
                                         cutoff=cutoff, top_n=1):
                suggestions.append({'term': t, 'action_id': terms[t],
                                    'distance': cand['distance'],
                                    'similarity': cand['similarity'],
                                    'kind': 'edit'})
            if use_pinyin and has_pinyin_support():
                for cand in pinyin_suggestions(q_lower, [t_l], max_dist=max_dist,
                                               cutoff=cutoff, top_n=1):
                    suggestions.append({'term': t, 'action_id': terms[t],
                                        'distance': cand['distance'],
                                        'similarity': cand['similarity'],
                                        'kind': 'pinyin'})

        # 距离升序 → 相似度降序 → term 字典序（稳定可测）
        suggestions.sort(key=lambda s: (s['distance'], -s['similarity'],
                                        s['term'].lower()))
        # 同 (action_id, term, kind) 去重
        seen = set()
        out: List[dict] = []
        for s in suggestions:
            key = (s['action_id'], s['term'], s['kind'])
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _reason_from_fields(match_fields: List[str]) -> str:
        """match_fields → 人类可读匹配理由（如"命中 name、命中 tag=record"）。"""
        if not match_fields:
            return ''
        return '命中 ' + '、命中 '.join(match_fields[:6])

    def recommend(self, description: str, limit: int = 5,
                  semantic: bool = False,
                  semantic_weight: float = _SEMANTIC_WEIGHT,
                  semantic_cutoff: float = _SEM_CUTOFF) -> List[dict]:
        """根据自然语言描述推荐动作（E3 推荐/联想 + F1 语义融合）。

        参数:
            description: 任务描述（如 "监控文件夹变化"）；为空时返回热门兜底列表。
            limit: 最大推荐数。
            semantic: 是否启用语义分融合排序（默认关闭 = 关键词打分现状）。
            semantic_weight: 语义分权重 w（关键词分占 1-w；默认 0.4）。
            semantic_cutoff: 纯语义召回阈值（仅 semantic=True 且权重>0 生效）。

        返回:
            推荐列表 [{entry, score, confidence, reason, match_fields}]。
            - reason: 命中链（id/name/description/tag/usage/关键词）；纯语义
              召回时 reason='语义相近'；
            - confidence: 置信度（0-1，等于融合分）；
            - semantic=False 时无任何关键词命中返回 []（保持既有语义）；
            - 有命中但不足 limit 时，用「相关动作联想 + 热门兜底」补足。

        使用示例:
            ```python
            from vools.actus import ActionRegistry

            reg = ActionRegistry()
            reg.load_from_repo("./my-repo")
            recs = reg.recommend("监控文件夹变化", limit=3)  # → List[dict]
            for rec in recs:      # 每项含 entry/score/confidence/reason/match_fields
                print(rec["entry"]["id"], rec["confidence"], rec["reason"])
            ```
        """
        description = (description or "").strip()
        if not description:
            return self._fallback_recommendations(limit)

        description_lower = description.lower()
        description_words = set(description_lower.split())

        sem_scores: Dict[str, float] = {}
        w = 0.0
        if semantic:
            sem_scores = self._semantic_scores(description_lower)
            w = max(0.0, min(1.0, float(semantic_weight)))
        cutoff = float(semantic_cutoff)

        scored = []
        for entry in self._entries.values():
            score, match_fields = self._score_entry_ex(
                entry, description_lower, description_words)
            sem = (sem_scores or {}).get(entry.id, 0.0)
            if score > 0.1 or (w > 0 and sem >= cutoff):
                fused = self._fuse_scores(score, sem, w)
                reason = self._explain_match(entry, description_lower,
                                             description_words)
                if not reason and not match_fields and sem > 0:
                    reason = '语义相近'
                scored.append({
                    'entry': entry.to_dict(),
                    'score': round(fused, 3),
                    'confidence': round(fused, 3),
                    'reason': reason or self._reason_from_fields(match_fields),
                    'match_fields': match_fields,
                })

        scored.sort(key=lambda x: x['score'], reverse=True)
        if not scored:
            # 无任何打分命中：保持既有"无关描述返回空列表"语义，不做兜底污染。
            return []
        return self._fill_to_limit(scored, limit)[:limit]

    def related(self, action_id: str, limit: int = 5) -> List[dict]:
        """「相关动作」联想：按共享 tag/purpose/industry 维度找邻近推荐项。

        参数:
            action_id: 目标动作 ID（必须已注册，否则返回空列表）。
            limit: 最大联想数。

        返回:
            [{entry, score, confidence, reason, match_fields}]，仅收录与目标
            至少共享 1 个维度（tag/purpose/industry）的条目，按共享度降序。
        """
        target = self._entries.get(action_id)
        if target is None:
            return []

        target_tags = set(t.lower() for t in (target.tags or []))
        target_purposes = set(p.lower() for p in (target.purpose or []))
        target_industries = set(i.lower() for i in (target.industry or []))

        related_items = []
        for entry in self._entries.values():
            if entry.id == action_id:
                continue
            fields = []
            score = 0.0
            for tag in (entry.tags or []):
                if tag.lower() in target_tags:
                    score += 0.4
                    fields.append(f'共享标签: {tag}')
            for purpose in (entry.purpose or []):
                if purpose.lower() in target_purposes:
                    score += 0.3
                    fields.append(f'共享用途: {purpose}')
            for industry in (entry.industry or []):
                if industry.lower() in target_industries:
                    score += 0.2
                    fields.append(f'共享行业: {industry}')
            if score > 0:
                related_items.append({
                    'entry': entry.to_dict(),
                    'score': round(min(score, 1.0), 3),
                    'confidence': round(min(score, 1.0), 3),
                    'reason': self._reason_from_fields(fields) or '相关动作',
                    'match_fields': fields,
                })

        related_items.sort(key=lambda x: x['score'], reverse=True)
        return related_items[:limit]

    def _fallback_recommendations(self, limit: int) -> List[dict]:
        """空 description 兜底：返回热门/最近使用动作列表（不崩溃）。

        无真实使用统计时，用信任等级（trusted/verified 优先）与 exec 类型
        代理"热门"语义，注册序在后视为"最近"，稳定排序保证确定性。
        """
        if limit <= 0:
            return []
        trust_rank = {'trusted': 0, 'verified': 1, 'community': 2,
                      'sandbox': 3, 'unverified': 4, 'internal': 5}
        ranked = sorted(
            self._entries.values(),
            key=lambda e: (
                trust_rank.get((e.trust_level or '').lower(), 9),
                0 if (e.kind or '').lower() == 'exec' else 1,
                e.id,
            ))
        items = []
        for entry in ranked[:limit]:
            items.append({
                'entry': entry.to_dict(),
                'score': 0.1,
                'confidence': 0.1,
                'reason': '热门兜底: 高信任动作优先',
                'match_fields': [],
            })
        return items

    def _fill_to_limit(self, scored: List[dict], limit: int) -> List[dict]:
        """主命中不足 limit 时补足：先按共享维度联想，再热门兜底。

        补足项排除已收录条目；联想只针对主命中 top 条目做邻近推荐，
        保证联想与目标动作至少共享 1 个维度。
        """
        if limit <= 0 or len(scored) >= limit:
            return scored
        seen = {item['entry']['id'] for item in scored}
        filled = list(scored)
        if filled:
            top_id = filled[0]['entry']['id']
            for item in self.related(top_id, limit=limit):
                if len(filled) >= limit:
                    break
                if item['entry']['id'] not in seen:
                    filled.append(item)
                    seen.add(item['entry']['id'])
        if len(filled) < limit:
            for item in self._fallback_recommendations(limit):
                if len(filled) >= limit:
                    break
                if item['entry']['id'] not in seen:
                    filled.append(item)
                    seen.add(item['entry']['id'])
        return filled

    def _explain_match(self, entry: RegistryEntry,
                       query: str, query_words: set) -> str:
        """生成匹配解释（E3：reason 链含 id/name/description/tag/usage/关键词）。"""
        reasons = []
        if query in entry.id.lower():
            reasons.append('id 匹配')
        if query in entry.name.lower():
            reasons.append('名称匹配')
        if query in entry.description.lower():
            reasons.append('描述匹配')
        if entry.usage:
            usage_lower = entry.usage.lower()
            if query in usage_lower or any(
                    len(w) > 2 and w in usage_lower for w in query_words):
                reasons.append('用法匹配')
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
    """便捷函数：搜索注册表（委托 `ActionRegistry.search`）。

    F5（T0r15）：包公开 API 入口（`from vools.actus import search_registry`）。

    参数:
        repo_dir: 本地仓库根目录（含 actions/）。
        query: 搜索关键词（匹配 id/name/description/tags）。
        category: 分类过滤。
        limit: 最大返回数。

    返回:
        List[RegistryEntry]，按相关度排序。

    使用示例:
        ```python
        from vools.actus import search_registry

        hits = search_registry("./my-repo", "计算", limit=5)
        print([e.id for e in hits])
        ```
    """
    registry = ActionRegistry()
    registry.load_from_repo(repo_dir)
    return registry.search(query=query, category=category, limit=limit)


def recommend_registry(repo_dir: str, description: str, limit: int = 5,
                       semantic: bool = False) -> List[dict]:
    """便捷函数：按自然语言描述推荐动作（委托 `ActionRegistry.recommend`）。

    F5（T0r15）：包公开 API 入口（`from vools.actus import recommend_registry`），
    与 `ActionRegistry.recommend` 输出契约一致（含 reason 命中链与 confidence
    置信度）。

    参数:
        repo_dir: 本地仓库根目录（含 actions/）。
        description: 任务描述（如 "监控文件夹变化"）；为空时返回热门兜底。
        limit: 最大推荐数。
        semantic: 是否启用语义分融合排序。

    返回:
        [{entry, score, confidence, reason, match_fields}]，按分降序。

    使用示例:
        ```python
        from vools.actus import recommend_registry

        recs = recommend_registry("./my-repo", "监控文件夹变化", limit=3)
        for rec in recs:
            print(rec["entry"]["id"], rec["confidence"], rec["reason"])
        ```
    """
    registry = ActionRegistry()
    registry.load_from_repo(repo_dir)
    return registry.recommend(description, limit=limit, semantic=semantic)


__all__ = [
    'ActionRegistry',
    'RegistryEntry',
    'build_registry',
    'search_registry',
    'recommend_registry'
]
