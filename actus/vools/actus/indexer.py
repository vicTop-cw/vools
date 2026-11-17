"""动作发现与索引（docs/08 §1/§2）：扫描 actions/ → 校验 → _meta/actions.index.json。

分类体系 v2.0（docs/03 §2.6）：索引含 by_kind/by_purpose/by_industry 反向索引，
filter_by_dimension 按维度过滤。
"""

__all__ = ['scan_actions', 'build_index', 'load_index', 'get_action',
           'filter_by_dimension', 'action_roots',
           'BackgroundIndexRebuilder', 'rebuild_index_background',
           'get_load_cache_stats', 'reset_load_cache']

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from .errors import ActionError
from .model import parse_cfg_from_file, Action
from .validate import (
    validate_action, validate_graph, analyze_graph,
    resolve_test_binding, governance_notices,
    split_validation,
)
from .paths import repo_root
from .constants import is_testish_id, is_action_file, ACTION_SUFFIXES

_TZ = timezone(timedelta(hours=8))
# 动作文件后缀真源在 constants（单一真源，docs/08 §1）：
# - .actus.md         旧格式（#!cfg JSON 元数据，形式 A）
# - .actus.schema.md  新格式（YAML front-matter 元数据，形式 B）
# 存量缺陷：此前只认 .actus.md，导致 basics/ 下 4 个 .actus.schema.md
# 从未进过引擎索引（扫不到 → 索引缺 → MCP 工具目录也没有）。
ACTION_SUFFIX = '.actus.md'  # 向后兼容别名（外部代码可能引用）

# 本模块内的判定别名（历史名 _is_action_file，保留防外部引用）
_is_action_file = is_action_file


# ---------------------------------------------------------------------------
# 索引自动失效（REFACTOR_COMPLETION §六.4）：解析器指纹
#
# 问题：格式解析逻辑（格式检测 / 元数据解析 / 块提取）变更后，旧索引缓存
# 继续被 load_index 使用 ⇒「解析逻辑改了、旧索引继续用」的静默错配
# （此前唯一手段是手工删 _meta/ 重建）。
# 方案：build_index 落盘时写入 parser_fingerprint —— 格式解析链关键模块
# 源码内容的 sha256（前 16 hex，命名键分隔）；load_index 读回比对，不匹配
# ⇒ 索引过期 ⇒ 自动重建（结果附 rebuild_reason + logging.info，不静默）。
# 指纹只依赖源码文本字节（无 mtime/时钟因素），同码同值、跨机器可复现；
# 全部指纹源不可读时退化为空输入 hash，同样恒定，不会引发重建风暴。
# ---------------------------------------------------------------------------

#: 索引缓存里解析器指纹的键名（indexer 自身扩展字段，schema_version 不动）。
INDEX_FINGERPRINT_KEY = 'parser_fingerprint'

# ---------------------------------------------------------------------------
# T0r13（P5 加载与缓存优化）：进程级 load_index 结果缓存 + 重字段懒加载
#
# 目标：
#   * 同进程二次 load_index 命中进程级缓存 —— 0 次磁盘读 / 0 次反序列化
#     （缓存命中仅做一次 os.stat 元数据校验：mtime_ns + size 与首读一致即
#     视为未变更；解析器指纹变化/文件变更时自动失效并重建）。
#   * actions 立即可用；by_* 反向索引与 dependency_graph 等重字段按需懒加载
#     （首读时只解析轻量标量 + actions，重字段保留原始 JSON 子串，首次访问
#     才解析，解析结果在缓存条目内共享）。
#   * 返回结构契约不变：返回体仍是普通 dict，顶层键与既有 load_index 完全
#     一致；重字段值为 dict 子类 _LazyField（isinstance(x, dict) 通过），
#     首次访问（len/get/迭代/比较等）自动解析，内容与全量解析逐字段相等。
#   * 命中统计：get_load_cache_stats() 返回 hits/misses/cached_entries，
#     供验收打点；reset_load_cache() 清空缓存（测试隔离用）。
# ---------------------------------------------------------------------------

#: 需要懒加载的「重字段」：反向索引 + 依赖图（冷启动不解析，首次访问才解析）。
_LAZY_HEAVY_FIELDS = ('by_kind', 'by_purpose', 'by_industry', 'by_name',
                      'by_md5', 'by_languages', 'by_trust',
                      'dependency_graph')

#: 进程级 load_index 缓存（key=actions.index.json 绝对路径）。
_LOAD_CACHE_LOCK = threading.RLock()
_LOAD_CACHE: Dict[str, '_IndexCacheEntry'] = {}
#: 命中/未命中计数（验收打点）。
_LOAD_STATS = {'hits': 0, 'misses': 0}


class _IndexCacheEntry:
    """load_index 的进程级缓存条目。

    - light：轻量顶层标量（schema_version / classification_version /
      generated_at / parser_fingerprint 等，已解析）；
    - actions：动作 brief 字典（已解析，立即可用）；
    - heavy_raw：重字段的原始 JSON 子串（未解析，懒加载原料）；
    - heavy_resolved：已懒解析的重字段缓存（同进程只解析一次，多返回体共享）。
    """

    __slots__ = ('path', 'mtime_ns', 'size', 'fingerprint',
                 'light', 'actions', 'heavy_raw', 'heavy_resolved')

    def __init__(self, path, mtime_ns, size, fingerprint,
                 light, actions, heavy_raw, heavy_resolved=None):
        self.path = path
        self.mtime_ns = mtime_ns
        self.size = size
        self.fingerprint = fingerprint
        self.light = light
        self.actions = actions
        self.heavy_raw = heavy_raw
        self.heavy_resolved = heavy_resolved or {}

    def make_index(self) -> dict:
        """组装返回体（每次新 dict；actions 浅拷贝；重字段懒包装或已解析拷贝）。"""
        index = dict(self.light)
        index['actions'] = dict(self.actions)
        for field in _LAZY_HEAVY_FIELDS:
            if field in self.heavy_raw:
                if field in self.heavy_resolved:
                    index[field] = dict(self.heavy_resolved[field])
                else:
                    index[field] = _LazyField(self, field)
            elif field in self.heavy_resolved:
                index[field] = dict(self.heavy_resolved[field])
        return index


class _LazyField(dict):
    """惰性重字段包装（dict 子类）：首次访问才从缓存条目解析。

    与普通 dict 契约一致：isinstance(x, dict) 为 True；所有读操作
    （len/get/items/迭代/比较/bool）都会先触发 _ensure() 解析。
    """

    def __init__(self, entry: _IndexCacheEntry, field: str) -> None:
        super().__init__()
        self._entry = entry
        self._field = field
        self._resolved = False

    def _ensure(self) -> None:
        if self._resolved:
            return
        entry = self._entry
        field = self._field
        with _LOAD_CACHE_LOCK:
            data = entry.heavy_resolved.get(field)
            if data is None:
                raw = entry.heavy_raw.get(field)
                try:
                    data = json.loads(raw) if raw else {}
                except ValueError:
                    data = {}
                entry.heavy_resolved[field] = data
        dict.update(self, data)
        self._resolved = True

    def __getitem__(self, key):
        self._ensure()
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        self._ensure()
        return dict.__contains__(self, key)

    def __iter__(self):
        self._ensure()
        return dict.__iter__(self)

    def __len__(self):
        self._ensure()
        return dict.__len__(self)

    def __bool__(self):
        self._ensure()
        return dict.__len__(self) > 0

    def keys(self):
        self._ensure()
        return dict.keys(self)

    def values(self):
        self._ensure()
        return dict.values(self)

    def items(self):
        self._ensure()
        return dict.items(self)

    def get(self, key, default=None):
        self._ensure()
        return dict.get(self, key, default)

    def copy(self):
        self._ensure()
        return dict.copy(self)

    def __repr__(self):
        self._ensure()
        return dict.__repr__(self)

    def __str__(self):
        self._ensure()
        return dict.__str__(self)

    def __eq__(self, other):
        self._ensure()
        if isinstance(other, dict):
            if isinstance(other, _LazyField):
                # 对侧未解析时 C 层 dict 比较会直接读内部键表（绕过
                # __getitem__），导致内容缺失误判不等 —— 先解析对侧。
                other._ensure()
            return dict.__eq__(self, other)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return None


def _skip_ws(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i] in ' \t\n\r':
        i += 1
    return i


def _json_value_end(text: str, i: int) -> int:
    """返回从 i 开始 JSON 值（跳过字符串/嵌套容器）的结束下标（不含）。

    不做真实解析，只做括号深度 + 字符串转义扫描 —— O(n) 且不构建对象。
    """
    n = len(text)
    if i >= n:
        return i
    c = text[i]
    if c == '"':
        i += 1
        while i < n:
            ch = text[i]
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                return i + 1
            i += 1
        return n
    if c in '[{':
        depth = 0
        while i < n:
            ch = text[i]
            if ch == '"':
                i += 1
                while i < n:
                    cc = text[i]
                    if cc == '\\':
                        i += 2
                        continue
                    if cc == '"':
                        break
                    i += 1
            elif ch in '[{':
                depth += 1
            elif ch in ']}':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n
    # 标量（数字 / true / false / null）：扫到逗号或右花括号
    while i < n and text[i] not in ',}':
        i += 1
    return i


def _split_top_level(text: str) -> Dict[str, tuple]:
    """遍历顶层 JSON 键，返回 {key: (start, end)}（值子串下标，end 不含）。

    不解析任何值；actions 等需要解析的字段由调用方按子串 json.loads。
    失败时返回空 dict（调用方回退全量 json.load，行为与旧实现一致）。
    """
    start = text.find('{')
    if start < 0:
        return {}
    i = start + 1
    n = len(text)
    fields: Dict[str, tuple] = {}
    while True:
        i = _skip_ws(text, i)
        if i >= n or text[i] == '}':
            break
        if text[i] != '"':
            return {}
        # 顶层键名（ASCII，无转义；键名由本引擎生成）
        key_end = text.find('"', i + 1)
        if key_end < 0:
            return {}
        key = text[i + 1:key_end]
        i = _skip_ws(text, key_end + 1)
        if i >= n or text[i] != ':':
            return {}
        i = _skip_ws(text, i + 1)
        if i >= n:
            return {}
        value_end = _json_value_end(text, i)
        if value_end <= i:
            return {}
        fields[key] = (i, value_end)
        i = _skip_ws(text, value_end)
        if i < n and text[i] == ',':
            i += 1
    return fields


def _fingerprint_source_texts() -> Dict[str, str]:
    """指纹源：格式解析链关键模块的源码文本（键名稳定，便于测试替换）。

    覆盖解析链两层（缺文件则跳过该层，指纹退化为剩余层的 hash）：
      * model.py       —— 格式检测（后缀 + _has_yaml_frontmatter）与双格式
                          解析入口 parse_cfg_from_file/_parse_schema_md_action
      * frontmatter.py —— YAML front-matter 元数据解析（形式 B）
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    sources = (('model', 'model.py'), ('frontmatter', 'frontmatter.py'))
    texts = {}
    for key, rel in sources:
        try:
            with open(os.path.join(pkg_dir, rel), 'r', encoding='utf-8') as f:
                texts[key] = f.read()
        except OSError:
            continue
    return texts


def _parser_fingerprint() -> str:
    """解析器指纹：_fingerprint_source_texts() 内容的 sha256 前 16 hex。"""
    texts = _fingerprint_source_texts()
    digest = hashlib.sha256()
    for key in sorted(texts):
        digest.update(key.encode('utf-8'))
        digest.update(b'\x00')
        digest.update(texts[key].encode('utf-8'))
    return digest.hexdigest()[:16]


def _inject_cached_path(rel: str, roots: List[str]) -> str:
    """缓存命中时恢复动作绝对路径（rel 形如 r0/actions/x.actus.md）。"""
    parts = rel.split('/')
    idx = parts[0][1:] if len(parts) > 1 and parts[0].startswith('r') else '0'
    root = roots[int(idx)] if idx.isdigit() and int(idx) < len(roots) else roots[0]
    return os.path.join(root, *parts[1:])


def _repo_root() -> str:
    """仓库根。可被 ACTUS_REPO_ROOT 环境变量覆盖（测试/多仓库场景）。

    真源：`paths.repo_root()`（不设 env / 设 ACTUS_REPO_ROOT 两种情况下都与本函数
    改前的行为逐字相同，迁移时已用两种状态做对照验证）。本函数保留为兼容别名 ——
    全仓有大量模块 import 它。
    """
    return repo_root()


def _seed_actions_dir() -> str:
    """包内种子动作目录（vools/actus/actions/，随 wheel 分发）。

    三层动作边界（docs/08 §1）：
      1. 基座自带种子动作：vools/actus/actions/（wheel 内，pip 装上就有）
      2. 用户项目动作：<ACTUS_REPO_ROOT>/actions/（Git 仓，优先）
      3. 社区仓动作：default_repos.json 指向的远程仓（curator 发现）
    缺目录（源码树异常形态）时返回空串，调用方跳过。
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'actions')


def _action_roots(actions_dir: str = None) -> List[str]:
    """汇总全部动作扫描根（去重、保序：用户项目优先于包内种子）。"""
    roots: List[str] = []
    if actions_dir:
        roots.append(actions_dir)
    else:
        roots.append(os.path.join(_repo_root(), 'actions'))
        seed = _seed_actions_dir()
        if os.path.isdir(seed) and seed not in roots:
            roots.append(seed)
    # 去重保序
    seen = set()
    out = []
    for r in roots:
        norm = os.path.normpath(r)
        if norm not in seen:
            seen.add(norm)
            out.append(r)
    return out


# 公开别名（外部/测试查询扫描根用）
action_roots = _action_roots


_MTIMES_CACHE = 'actions.mtimes.json'  # mtime 缓存（_meta/ 下）

# P3（T0r7）：动作解析结果缓存（_meta/ 下）。mtime 命中时从该文件恢复
# Action 对象，**不再调用 parse_cfg_from_file**（修复 V-17 命中仍全量重解析）。
# 键与 actions.mtimes.json 一致（root 路径 hash 前缀的 rel）；值=序列化 Action
# （排除运行时注入的 meta['_path']，命中恢复时由 _inject_cached_path 重新注入）。
_PARSE_CACHE = 'actions.parse.json'


def _serialize_action(action: Action) -> dict:
    """序列化 Action 供解析结果缓存（meta 剔除运行时注入的 '_path'）。"""
    meta = dict(action.meta)
    meta.pop('_path', None)
    return {
        'meta': meta,
        'path': action.path,
        'sha256': action.sha256,
        'md5': action.md5,
        'raw': action.raw,
        'body': action.body,
        'blocks': action.blocks,
        'file_directives': action.file_directives,
    }


def _action_from_cache_entry(entry: dict) -> Action:
    """从解析结果缓存条目反序列化 Action（字段不全时按缺省构造）。"""
    meta = dict(entry.get('meta') or {})
    return Action(
        meta=meta,
        path=str(entry.get('path') or ''),
        sha256=str(entry.get('sha256') or ''),
        md5=str(entry.get('md5') or ''),
        raw=str(entry.get('raw') or ''),
        body=str(entry.get('body') or ''),
        blocks=list(entry.get('blocks') or []),
        file_directives=dict(entry.get('file_directives') or {}),
    )


def _atomic_write_json(path: str, obj: dict) -> None:
    """原子写 JSON：先写 tmp（带 pid 防多进程碰撞），再 os.replace 替换。

    P3（T0r7）：mtime / 解析结果 / 索引落盘统一走原子替换，保证并发读
    （后台重建期间 load_index 读盘）永远看到完整文件，不会读到半截 JSON。
    """
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _try_load_json(path: str) -> Optional[dict]:
    """读 JSON 文件，不存在/损坏时返回 None（不抛错）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_index_file(meta_dir: str, index: dict, atomic_write: bool = False) -> None:
    """索引落盘：默认直接写（历史行为）；atomic_write=True 走 tmp + os.replace
    原子替换（P3 后台重建：重建期间读盘永远看到完整旧索引，完成后瞬间切换）。"""
    path = os.path.join(meta_dir, 'actions.index.json')
    if atomic_write:
        _atomic_write_json(path, index)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

def scan_actions(actions_dir: str = None, validate: bool = True,
                 use_cache: bool = True, write_cache: bool = True) -> Dict[str, Action]:
    """递归扫描动作根下所有 .actus.md / .actus.schema.md，生成动作清单。

    - 文件后缀双轨：.actus.md（形式 A #!cfg JSON）+ .actus.schema.md（形式 B YAML）；
    - 扫描根多层：<ACTUS_REPO_ROOT>/actions/（用户项目）+ vools/actus/actions/（包内种子）；
    - id 重复或解析失败的动作记入 problems（附着在函数属性上，供索引展示），
      不中断其余动作的发现；
    - validate=True 时逐个做契约校验（失败标记 invalid 而非中断扫描）。
    - use_cache=True（默认）：mtime 缓存（_meta/actions.mtimes.json）判定
      "文件是否变更"——变更文件重解析，未变更文件走缓存分支；
      V-17（寻虫 2026-10-22）：缓存分支当前仍调用 parse_cfg_from_file 全量
      重解析（缓存只决定是否登记 problems，不省解析开销）。docstring 此前
      写"仅重解析变更文件、冷启动 2.4s→0.3s"与实现不符——此处措辞对齐实现。
      真实现"命中免解析"需序列化 Action 元数据，且会激活 V-18 跨根污染
      （缓存键无 actions_dir 身份），故暂不实现，只对齐文档。
    """
    roots = _action_roots(actions_dir)
    actions: Dict[str, Action] = {}
    problems = {}

    # ── 加载 mtime 缓存 ──
    mtimes_cache: Dict[str, float] = {}
    # P3（T0r7）：解析结果缓存（rel → 序列化 Action）。mtime 命中且该文件
    # 存在缓存条目时直接反序列化恢复，不调用 parse_cfg_from_file（V-17 修复）。
    parse_cache: Dict[str, dict] = {}
    if use_cache:
        # 审计修（`_meta` 手写 → paths.meta_dir()）：缓存是**运行时数据**，
        # 之前硬编码 `_repo_root()/_meta`，于是设了 ACTUS_META_DIR 也不隔离
        # （test_demo_indexing 里记着这个老毛病：不显式传 meta_dir 就会把缓存
        # 写进真实仓库）。现在跟随 paths.meta_dir()（ACTUS_META_DIR > repo_root()/_meta）。
        from .paths import meta_dir as _paths_meta_dir
        meta_dir = _paths_meta_dir()
        cache_path = os.path.join(meta_dir, _MTIMES_CACHE)
        loaded = _try_load_json(cache_path)
        if isinstance(loaded, dict):
            mtimes_cache = loaded
        parse_path = os.path.join(meta_dir, _PARSE_CACHE)
        loaded_parse = _try_load_json(parse_path)
        if isinstance(loaded_parse, dict):
            parse_cache = loaded_parse

    new_mtimes: Dict[str, float] = {}
    # P3（T0r7）：本次扫描解析成功的新/变更文件的序列化 Action（与 new_mtimes
    # 同源），保存时整份替换 parse 缓存——文件被删除后条目自然清理。
    new_parse_cache: Dict[str, dict] = {}
    # 命中免解析计数（观测/测试用，不参与逻辑）。
    parse_hits = 0
    cached_actions: Dict[str, Action] = {}
    changed_files = []
    # P2（推荐缓存与增量注册）：与 changed_files 同源收集"变更且解析成功"的
    # 动作 id，供上层增量注册使用（intent.get_router_with_cache）。挂属性而非
    # 改返回签名，保持 scan_actions 的既有 API 逐字兼容。
    changed_ids = []

    # V-18（寻虫 2026-10-22）：缓存键 r{root_idx} 用枚举序号，
    # 不同 actions_dir 的相同序号根会共享同一缓存键——A/B 两仓同相对
    # 路径文件 mtime 相等时互相覆盖（当前被"命中仍重解析"掩盖，一旦
    # 兑现免解析即踩）。改为 root 路径 hash，不同目录身份必不同。
    root_ids: Dict[int, str] = {}
    for root_idx, root in enumerate(roots):
        root_ids[root_idx] = hashlib.md5(
            os.path.normpath(root).encode('utf-8')).hexdigest()[:8]

    for root_idx, root in enumerate(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                if not _is_action_file(fn):
                    continue
                full = os.path.join(dirpath, fn)
                # rel 带 root 路径 hash 前缀（V-18）：保证多扫描根下
                # 不碰撞且不同目录身份必不同——旧实现用枚举序号 r{root_idx}，
                # 两个 actions_dir 的相同序号根会共享同一缓存键互相覆盖
                rel = f'r{root_ids[root_idx]}/' + os.path.relpath(full, root).replace(os.sep, '/')
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                new_mtimes[rel] = mtime

                # 缓存命中：mtime 未变 → 跳过解析（V-17 修复）
                # P3（T0r7）：优先从解析结果缓存直接恢复 Action，完全不调用
                # parse_cfg_from_file；缓存条目缺失/损坏时回退到旧解析路径
                # （与历史行为一致），保证老缓存（只有 actions.mtimes.json、
                # 没有 actions.parse.json）升级后首扫仍能正常兜底。
                if use_cache and rel in mtimes_cache and mtimes_cache[rel] == mtime:
                    entry = parse_cache.get(rel) if parse_cache else None
                    if entry is not None:
                        try:
                            action = _action_from_cache_entry(entry)
                            cached_actions[rel] = action
                            parse_hits += 1
                            continue
                        except Exception:
                            pass  # 缓存条目损坏 → 回退解析
                    try:
                        action = parse_cfg_from_file(full)
                        cached_actions[rel] = action
                        continue
                    except Exception:
                        pass  # 缓存损坏，重新解析

                # 解析（新文件或变更文件）
                try:
                    action = parse_cfg_from_file(full)
                except ActionError as e:
                    # `.demo.` 文档页的两种情形必须区分：
                    # - **没有 front-matter** → 纯教学资产，无 #!cfg 块属正常，跳过；
                    # - **有 front-matter 却解析失败** → 就是坏动作文件，必须上报。
                    # 此前一律跳过，实测「有 front-matter 的坏 demo」被完全静默
                    # 忽略（不在 actions、也不在 invalid），用户毫无提示。
                    if '.demo.' in fn:
                        from .model import _has_yaml_frontmatter
                        try:
                            with open(full, encoding='utf-8') as fh:
                                raw_text = fh.read()
                        except OSError:
                            raw_text = ''
                        if not _has_yaml_frontmatter(raw_text):
                            continue
                    problems[rel] = f'parse: {e.message}'
                    continue
                aid = action.meta.get('id')
                if not aid:
                    problems[rel] = 'parse: #!cfg 缺少 id'
                    continue
                if aid in actions:
                    problems[rel] = f'conflict: id 与 {actions[aid].path} 重复'
                    continue
                action.meta['_path'] = full   # 供自包含/测试绑定定位（docs/47）
                actions[aid] = action
                changed_files.append(rel)
                changed_ids.append(aid)
                # P3（T0r7）：解析成功 → 写入解析结果缓存（meta 已剔除 _path）
                new_parse_cache[rel] = _serialize_action(action)

    # 合并缓存命中
    # V-16（寻虫 2026-10-22）：旧实现 `if aid and aid not in actions` 静默丢弃
    # 重复 id / 缺 id 的缓存命中——第二轮全命中时 problems 蒸发（首轮 2 条、
    # 次轮 {}），同一本库的"问题名单"随缓存冷热抖动，重复动作隐身。
    # 与新鲜路径同判据登记（冲突按 rel 身份比较，跨根同 id 也报得出）。
    for rel in sorted(cached_actions):
        action = cached_actions[rel]
        aid = action.meta.get('id')
        if not aid:
            problems[rel] = 'parse: 缺少 id（缓存命中）'
            continue
        if aid in actions:
            problems[rel] = f'conflict: id 与 {actions[aid].path} 重复'
            continue
        action.meta['_path'] = _inject_cached_path(rel, roots)
        actions[aid] = action

    # ── 保存 mtime + 解析结果缓存 ──
    # 第 13/14 轮审计：读命令（info/tools/list/executor 解析）也会走这里，
    # write_cache=False 让只读路径不写 _meta/actions.mtimes.json（只读 FS 可用）。
    # P3（T0r7）：双缓存统一原子写（tmp + os.replace），避免并发读读到半截 JSON。
    if use_cache and write_cache and new_mtimes:
        # 同上：跟随 paths.meta_dir()，让 ACTUS_META_DIR 能真正隔离缓存
        from .paths import meta_dir as _paths_meta_dir
        meta_dir = _paths_meta_dir()
        cache_path = os.path.join(meta_dir, _MTIMES_CACHE)
        parse_cache_path = os.path.join(meta_dir, _PARSE_CACHE)
        try:
            os.makedirs(meta_dir, exist_ok=True)
            _atomic_write_json(cache_path, new_mtimes)
            if new_parse_cache:
                _atomic_write_json(parse_cache_path, new_parse_cache)
        except OSError:
            pass

    if validate:
        for aid, action in actions.items():
            errs = validate_action(action)
            # `runtime:` 是**环境提示**（裸仓库缺 contracts、没装 jsonschema…），
            # 不是动作缺陷：分开存，索引 status 只由真实错误决定。
            # 提示本身不丢 → `_runtime_notes`，由 build_index 透传到 brief.warnings。
            real_errors, runtime_notes = split_validation(errs)
            if real_errors:
                action.meta['_validation_errors'] = real_errors
            if runtime_notes:
                action.meta['_runtime_notes'] = runtime_notes

    scan_actions.problems = problems  # type: ignore[attr-defined]
    scan_actions._changed = changed_files  # type: ignore[attr-defined]
    # P3（T0r7）：命中免解析计数（mtime 命中且从解析结果缓存恢复的动作数）。
    scan_actions._parse_hits = parse_hits  # type: ignore[attr-defined]
    # P2（增量注册）：变更且解析成功的动作 id 列表；以及"缓存中存在的旧文件
    # 本次扫描未再出现"（= 有文件被删除/根切换）标记。上层据此决定增量注册
    # 还是全量重建：有删除时增量无法安全还原 router（旧文件 id 不可知），
    # 必须全量重建（仅注册变更集不会移除已删动作）。
    scan_actions._changed_ids = changed_ids  # type: ignore[attr-defined]
    scan_actions._has_removal = bool(
        use_cache and mtimes_cache and new_mtimes
        and any(rel not in new_mtimes for rel in mtimes_cache)
    )  # type: ignore[attr-defined]
    return actions


def build_index(actions_dir: str = None, meta_dir: str = None,
                write: bool = True, write_cache: bool = True,
                incremental: bool = False, atomic_write: bool = False) -> dict:
    """`write=False`：**只在内存构建索引**（不落盘、不写 mtimes 缓存）——
    供只读 RPC（MCP tools/list）冷启动使用；显式命令（registry build/validate）
    仍用默认 write=True 落盘。

    P3（T0r7）新增参数：
    - `incremental=True`：增量模式。若磁盘旧索引存在、parser_fingerprint 匹配、
      且本次扫描无任何变更（scan_actions._changed_ids 为空、_has_removal 为假）
      ——直接复用旧索引（仅刷新 generated_at），0 解析 / 0 校验；有变更时
      退化为全量构建（scan_actions 已通过解析结果缓存免解析未变更文件）。
    - `atomic_write=True`：索引落盘走 tmp + os.replace 原子替换（后台重建用）。"""
    """扫描 + 全量校验 + 依赖图校验 + 索引落盘 _meta/actions.index.json。

    扫描默认走全部动作根（用户项目 + 包内种子，见 _action_roots）；
    显式传 actions_dir 时只扫该目录（测试/单仓场景）。

    依赖图存在环时：索引照常落盘，受影响动作标记 invalid 并附错误
    （docs/05 §5.1：不合规动作从 MCP tools 下架，不得静默执行）。

    审计修复（假绿灯）：改前这里 `scan_actions(validate=False)` 之后**从未真正
    校验**，`entries[x]['status']` 恒为 'valid' —— 实测一个缺 `name`、entry tag
    不存在、trust 无测试绑定的动作（4 条真实错误）在索引里照样 status='valid'，
    `actus validate`（无 id 走 index）恒 rc=0。docstring 写的"全量校验"没有落地。
    现在每个动作校验一次，**真实错误**决定 status，`runtime:` 环境提示只进
    brief['warnings']（不丢、不影响 status）。
    """
    # 审计修（`_meta` 手写 → paths.meta_dir()）：显式 meta_dir 优先，
    # 默认跟随 ACTUS_META_DIR > repo_root()/_meta。
    from .paths import meta_dir as _paths_meta_dir
    meta = meta_dir or _paths_meta_dir()
    # 落盘门禁判断提前（增量短路分支也需要）：
    # **自定义 actions_dir 且未显式给 meta_dir 时不写盘**。
    _default_actions = os.path.join(_repo_root(), 'actions')
    _is_default_target = (
        actions_dir is None
        or os.path.abspath(actions_dir) == os.path.abspath(_default_actions))
    actions = scan_actions(actions_dir, validate=False,
                           write_cache=write_cache)

    # P3（T0r7）：增量短路——本次扫描无任何变更时直接复用旧索引，0 解析 / 0 校验。
    # 条件：磁盘旧索引存在 + parser_fingerprint 匹配 + 无变更 id + 无文件删除/根切换。
    # 复用旧索引只刷新 generated_at（保持 schema_version / 分类索引 / 指纹形状一致）。
    changed_ids = list(getattr(scan_actions, '_changed_ids', None) or [])
    has_removal = bool(getattr(scan_actions, '_has_removal', False))
    if incremental:
        old_index = _try_load_json(os.path.join(meta, 'actions.index.json'))
        if (old_index is not None
                and old_index.get(INDEX_FINGERPRINT_KEY) == _parser_fingerprint()
                and not changed_ids and not has_removal):
            index = dict(old_index)
            index['generated_at'] = datetime.now(_TZ).isoformat(timespec='seconds')
            if write and (meta_dir or _is_default_target):
                os.makedirs(meta, exist_ok=True)
                _write_index_file(meta, index, atomic_write)
            return index

    # 每动作校验一次（`runtime:` 提示与真实错误分开，见 validate.split_validation）
    validation = {}
    for aid, action in actions.items():
        # build 阶段索引正被重建：md5/link-target 这类"依赖索引"的检查跳过
        validation[aid] = split_validation(validate_action(action, check_index=False))

    # 依赖图按节点分析：只标记真正受坏边/环影响的动作（属主 + 其下游锥），
    # 不再「一条坏依赖连坐整个动作市场」（历史上 validate_graph 首错即抛后
    # 把全部 entries 标 invalid，导致上百个无关动作从 MCP / LLM 目录下架）。
    valid_actions = {aid: a for aid, a in actions.items() if not validation[aid][0]}
    graph_issues = analyze_graph(valid_actions)

    entries = {}
    problems = dict(getattr(scan_actions, 'problems', {}))
    for aid, action in actions.items():
        real_errors, runtime_notes = validation.get(aid, ([], []))
        errs = list(real_errors)
        issue = graph_issues.get(aid)
        if issue is not None:
            errs.append(f"dependency graph: {issue['message']}")
        brief = action.brief()
        # 索引扩展（ACTUS_REFACTOR_PLAN §3.5）：从代码块语言提取 languages，
        # 供按语言检索/展示；空清单不写键（保持旧索引形状，增量字段）。
        languages = sorted({
            str(block.get('language') or '').strip().lower()
            for block in (getattr(action, 'blocks', None) or [])
            if str(block.get('language') or '').strip()})
        if languages:
            brief['languages'] = languages
        brief['status'] = 'invalid' if errs else 'valid'
        if errs:
            brief['errors'] = errs
        if runtime_notes:
            # 环境提示照常进索引（不丢），但**不影响 status**；只在非空时加键，
            # 保持正常仓库下 brief 形状与改前一致。
            brief['warnings'] = runtime_notes

        # ── 资产化治理标注（docs/47 §7，future_plan §3 落地）────────
        # 1) 测试味 id 不进资产池（kind=demo/alias/template 豁免）：
        #    夹具/演示动作仍可被 validate 校验（不破坏引擎测试），
        #    但资产池消费方（MCP/curator/索引检索）据此过滤。
        kind = str(brief.get('kind') or 'exec').lower()
        if is_testish_id(aid) and kind not in ('demo', 'alias', 'template'):
            brief['asset_pool'] = 'excluded'
            brief['asset_pool_reason'] = (
                'testish_id: 含 test/generated/foo/example 等测试味片段，'
                '非资产池正式资产（docs/47 §3.4）')
        else:
            brief['asset_pool'] = 'included'

        # 2) trust↔测试绑定：verified / unverified / n-a
        trust = str(action.meta.get('trust') or '').lower()
        if kind in ('demo', 'template', 'alias', 'doc', 'link') or trust == 'sandbox':
            # sandbox 信任级动作（演示性/隔离性）不要求测试绑定
            brief['verification'] = 'n-a'
            if trust == 'sandbox':
                brief['verification_reason'] = 'trust=sandbox 豁免测试绑定'
        else:
            bound, refs = resolve_test_binding(action)
            brief['verification'] = 'verified' if bound else 'unverified'
            if refs:
                brief['test_refs'] = refs[:8]

        # 3) 治理警告（不判失败，随索引展示）
        notices = governance_notices(action.meta)
        if notices:
            brief['notices'] = notices

        entries[aid] = brief

    for rel, why in problems.items():
        entries[f'_invalid:{rel}'] = {'path': rel, 'status': 'invalid', 'errors': [why]}

    # ── 分类体系 v2.0：反向索引（docs/03 §2.6 索引扩展） ──
    # 多值字段归一后按值分组；无效动作也入组（标记 status），保证索引完整。
    by_kind: Dict[str, list] = {}
    by_purpose: Dict[str, list] = {}
    by_industry: Dict[str, list] = {}
    # ── T0r14：by_languages（代码块语言）/ by_trust（信任级别）反向索引 ──
    by_languages: Dict[str, list] = {}
    by_trust: Dict[str, list] = {}
    # ── docs/03 §2.6 索引扩展：by_name / by_md5（ACTUS_REFACTOR_PLAN §3.5）──
    # by_name：小写归一 → [action_id]（多命中保留全部，resolver 报 ambiguous）
    # by_md5：32 位 hex → action_id（单值，内容指纹唯一）
    by_name: Dict[str, list] = {}
    by_md5: Dict[str, str] = {}
    for aid, brief in entries.items():
        if aid.startswith('_invalid:'):
            continue
        # V-19（寻虫 2026-10-22）：建键必须归一（strip+lower）——校验端
        # normalize_multi_field/is_known_* 用 lower() 判合法，purpose/industry
        # 不在 schema enum（fallback 环境 kind 也不拦），'Transform' 能全绿入库；
        # 而建键用原值 → by_purpose 只有 'Transform' 键，
        # filter_by_dimension('purpose','transform') 恒空（动作从维度索引消失）。
        kind = str(brief.get('kind') or 'exec').strip().lower()
        by_kind.setdefault(kind, []).append(aid)
        for p in (brief.get('purpose') or ['utility']):
            by_purpose.setdefault(str(p).strip().lower(), []).append(aid)
        for ind in (brief.get('industry') or ['general']):
            by_industry.setdefault(str(ind).strip().lower(), []).append(aid)
        # T0r14：by_languages（代码块语言，多值）小写归一 → [action_id]
        for lang in (brief.get('languages') or []):
            by_languages.setdefault(str(lang).strip().lower(), []).append(aid)
        # T0r14：by_trust（信任级别，单值）缺省 community → [action_id]
        trust_val = str(brief.get('trust') or 'community').strip().lower()
        by_trust.setdefault(trust_val, []).append(aid)
        # by_name：brief.name 小写归一 → 多命中保留全部
        name_val = str(brief.get('name') or '').strip().lower()
        if name_val:
            by_name.setdefault(name_val, []).append(aid)
        # by_md5：brief.md5（32 hex）→ 单值（内容指纹唯一）
        md5_val = str(brief.get('md5') or '').strip().lower()
        if md5_val and len(md5_val) == 32:
            by_md5[md5_val] = aid

    index = {
        'schema_version': '2.0.0',
        'classification_version': '2.0',
        'generated_at': datetime.now(_TZ).isoformat(timespec='seconds'),
        # 解析器指纹（索引自动失效，REFACTOR_COMPLETION §六.4）：
        # load_index 读回与当前指纹比对，不匹配即自动重建。
        'parser_fingerprint': _parser_fingerprint(),
        'actions': entries,
        'by_kind': {k: sorted(v) for k, v in sorted(by_kind.items())},
        'by_purpose': {k: sorted(v) for k, v in sorted(by_purpose.items())},
        'by_industry': {k: sorted(v) for k, v in sorted(by_industry.items())},
        'by_languages': {k: sorted(v) for k, v in sorted(by_languages.items())},
        'by_trust': {k: sorted(v) for k, v in sorted(by_trust.items())},
        'by_name': {k: sorted(v) for k, v in sorted(by_name.items())},
        'by_md5': {k: v for k, v in sorted(by_md5.items())},
    }
    if graph_issues:
        # 摘要保留，便于体检/排障；逐节点详情已在各 action.errors 里
        codes = sorted({v['code'] for v in graph_issues.values()})
        index['dependency_graph'] = {
            'code': 'dependency_issues',
            'codes': codes,
            'affected': sorted(graph_issues),
            'count': len(graph_issues),
        }

    # 落盘门禁：**自定义 actions_dir 且未显式给 meta_dir 时不写盘**（判断已提前）。
    # 此前无条件写 `meta_dir or <repo>/_meta`，于是 `build_index(actions_dir=临时目录)`
    # 会把仓库主索引覆盖成临时目录的内容——实测测试里这么一调，后续
    # resolve_target('actus.basics.calculator') 就报「动作 id 不存在」。
    # 调用方要落盘就显式给 meta_dir，语义才明确。
    if write and (meta_dir or _is_default_target):
        os.makedirs(meta, exist_ok=True)
        # P3（T0r7）：atomic_write=True 走 tmp + os.replace 原子替换
        _write_index_file(meta, index, atomic_write)

    return index


def _load_index_file(path: str) -> _IndexCacheEntry:
    """读索引文件并**部分解析**：轻量标量 + actions 立即解析，重字段保留 raw。

    相比旧实现的全量 json.load，冷启动只反序列化 actions 与标量；
    by_* / dependency_graph 等重字段留在 heavy_raw，首次访问才解析。
    """
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    fields = _split_top_level(text)
    if not fields:
        # 扫描失败（异常 JSON）：回退全量解析，行为与旧实现一致（不劣化）。
        with open(path, 'r', encoding='utf-8') as f:
            index = json.load(f)
        return _entry_from_index(index, path)
    light = {}
    actions = {}
    heavy_raw = {}
    for key, (s, e) in fields.items():
        if key == 'actions':
            try:
                actions = json.loads(text[s:e]) or {}
            except ValueError:
                actions = {}
        elif key in _LAZY_HEAVY_FIELDS:
            heavy_raw[key] = text[s:e]
        else:
            try:
                light[key] = json.loads(text[s:e])
            except ValueError:
                continue
    try:
        st = os.stat(path)
    except OSError:
        st = None
    return _IndexCacheEntry(
        path=path,
        mtime_ns=st.st_mtime_ns if st else 0,
        size=st.st_size if st else 0,
        fingerprint=light.get(INDEX_FINGERPRINT_KEY),
        light=light,
        actions=actions,
        heavy_raw=heavy_raw,
    )


def _entry_from_index(index: dict, path: str) -> _IndexCacheEntry:
    """从已构建/已全量解析的 index dict 生成缓存条目（重字段视为已解析）。"""
    light = {k: v for k, v in index.items()
             if k != 'actions' and k not in _LAZY_HEAVY_FIELDS}
    actions = index.get('actions') or {}
    heavy_resolved = {k: v for k, v in index.items()
                      if k in _LAZY_HEAVY_FIELDS and v}
    try:
        st = os.stat(path)
    except OSError:
        st = None
    return _IndexCacheEntry(
        path=path,
        mtime_ns=st.st_mtime_ns if st else 0,
        size=st.st_size if st else 0,
        fingerprint=index.get(INDEX_FINGERPRINT_KEY),
        light=light,
        actions=actions,
        heavy_raw={},
        heavy_resolved=heavy_resolved,
    )


def get_load_cache_stats() -> dict:
    """进程级 load_index 缓存命中统计（验收打点）。

    返回 {'hits': N, 'misses': N, 'cached_entries': N}。
    hit = 未读文件、未反序列化、直接返回缓存；miss = 读文件或重建。
    """
    with _LOAD_CACHE_LOCK:
        return {'hits': _LOAD_STATS['hits'],
                'misses': _LOAD_STATS['misses'],
                'cached_entries': len(_LOAD_CACHE)}


def reset_load_cache() -> None:
    """清空进程级缓存与计数（测试隔离用；生产路径无需调用）。"""
    with _LOAD_CACHE_LOCK:
        _LOAD_CACHE.clear()
        _LOAD_STATS['hits'] = 0
        _LOAD_STATS['misses'] = 0


def load_index(meta_dir: str = None, build: bool = True) -> dict:
    """读取索引；不存在时默认先构建（`build=False` 时**返回空索引、不落盘**）。

    索引自动失效（REFACTOR_COMPLETION §六.4，仅 `build=True` 时生效）：
    缓存里的 parser_fingerprint 与当前格式解析链指纹不一致（含老缓存
    无该字段，按过期处理重建一次）⇒ 索引过期 ⇒ 自动重建，返回值附
    `rebuild_reason` 并记 logging.info —— 防「解析逻辑改了、旧索引继续
    用」的静默错配。`build=False` 只读路径不重建（零副作用契约不变）。

    T0r13（P5 加载与缓存优化）：
      * 进程级缓存：同进程二次 load_index 命中缓存（仅 os.stat 元数据校验
        mtime_ns+size，不读文件、不反序列化）→ 0 磁盘读/反序列化；
        索引文件被外部修改（stat 变化）或 parser_fingerprint 过期（build=True）
        ⇒ 自动失效重建。命中统计见 get_load_cache_stats()。
      * 懒加载：返回体 actions 立即可用；by_* 反向索引与 dependency_graph
        等重字段为 dict 子类懒包装，首次访问才解析（内容与全量解析等价，
        解析结果同进程共享）。返回结构契约与既有 load_index 完全一致。

    第 13/14 轮审计：`load_index` 被只读入口（MCP tools/list、resolve_target 等）
    调用，索引缺失时 `build_index` 会落盘 `_meta/actions.index.json` +
    `actions.mtimes.json` —— 只读 FS 上直接失败。只读路径应传 `build=False`，
    需要建索引的显式命令仍用默认 `build=True`。
    """
    # 审计修（`_meta` 手写 → paths.meta_dir()）：显式 meta_dir 优先，
    # 默认跟随 ACTUS_META_DIR > repo_root()/_meta。
    from .paths import meta_dir as _paths_meta_dir
    meta = meta_dir or _paths_meta_dir()
    path = os.path.join(meta, 'actions.index.json')
    if not os.path.exists(path):
        if not build:
            return {'actions': {}, 'problems': {}, 'built': False}
        return build_index(meta_dir=meta)

    with _LOAD_CACHE_LOCK:
        current_fp = _parser_fingerprint() if build else None
        entry = _LOAD_CACHE.get(path)
        if entry is not None:
            try:
                st = os.stat(path)
            except OSError:
                st = None
            if st is not None and st.st_mtime_ns == entry.mtime_ns \
                    and st.st_size == entry.size:
                # 文件未变更 → 缓存有效；指纹校验（仅 build=True）。
                if not build or entry.fingerprint == current_fp:
                    _LOAD_STATS['hits'] += 1
                    return entry.make_index()
                # 指纹过期（build=True）→ 自动重建（缓存失效记 miss）。
                if entry.fingerprint is None:
                    reason = ('no parser_fingerprint in cache '
                              '(pre-fingerprint index, treated as stale)')
                else:
                    reason = ('parser_fingerprint mismatch '
                              '(cached=%s current=%s)'
                              % (entry.fingerprint, current_fp))
                logging.getLogger(__name__).info(
                    'action index stale -> auto rebuild: %s', reason)
                rebuilt = build_index(meta_dir=meta)
                _LOAD_CACHE[path] = _entry_from_index(rebuilt, path)
                _LOAD_STATS['misses'] += 1
                # rebuild_reason 只进返回值（rebuild_reason 不落盘，避免
                # 过期标记残留在新鲜缓存里误导后续读取）。
                rebuilt['rebuild_reason'] = reason
                return rebuilt

        # 缓存未命中（首读 / stat 变化 / 未缓存）：读文件部分解析。
        _LOAD_STATS['misses'] += 1
        entry = _load_index_file(path)
        _LOAD_CACHE[path] = entry
        index = entry.make_index()
        # ── 解析器指纹失效判定（REFACTOR_COMPLETION §六.4）────────────
        # build=False 只读场景维持「读到什么返回什么」的零副作用契约，
        # 过期也照返（调用方自选是否重建）。
        if build and entry.fingerprint != current_fp:
            if entry.fingerprint is None:
                reason = ('no parser_fingerprint in cache '
                          '(pre-fingerprint index, treated as stale)')
            else:
                reason = ('parser_fingerprint mismatch '
                          '(cached=%s current=%s)'
                          % (entry.fingerprint, current_fp))
            logging.getLogger(__name__).info(
                'action index stale -> auto rebuild: %s', reason)
            index = build_index(meta_dir=meta)
            _LOAD_CACHE[path] = _entry_from_index(index, path)
            index['rebuild_reason'] = reason
        return index


def get_action(action_id: str, actions_dir: str = None,
               write_cache: bool = False) -> Action:
    """按 id 取动作（实时解析文件，保证最新内容）；不存在抛 action_not_found。

    `write_cache=False`（默认）：只读命令（info/preview/run 解析）不写 mtimes
    缓存；只有显式扫描/构建（build_index / scan_actions(use_cache=True)）才写。
    """
    actions = scan_actions(actions_dir, validate=False, write_cache=write_cache)
    if action_id not in actions:
        raise ActionError('action_not_found', f'动作不存在: {action_id}',
                          {'known': sorted(actions.keys())})
    return actions[action_id]


def filter_by_dimension(dimension: str, value: str, meta_dir: str = None) -> list:
    """按分类维度过滤（docs/03 §2.6）。

    Args:
        dimension: "kind" | "purpose" | "industry"
        value: 维度值（如 "exec"、"transform"、"devops"）
        meta_dir: 索引目录（默认 _meta/）

    Returns:
        命中的动作 id 列表（已排序）；索引不存在时先构建。
        旧索引缺反向索引键时返回空列表（不报错，兼容旧格式）。
    """
    index = load_index(meta_dir=meta_dir)
    key = f'by_{dimension}'
    reverse = index.get(key) or {}
    # V-19：查询端与建键端同口径归一（'Transform'/'transform' 命中同一键）
    return list(reverse.get(str(value).strip().lower()) or [])


# ──────────────────────────────────────────────────────────────
# P3（T0r7）：后台重建（双缓冲 + 原子切换 + 失败回退）
# ──────────────────────────────────────────────────────────────

class BackgroundIndexRebuilder:
    """后台重建索引，重建期间查询继续用旧索引，完成后原子切换；失败回退旧索引。

    设计（读写锁/双缓冲思路）：
    - 构建线程在**独立暂存目录**（<meta>/.index-staging/）构建新索引，全程
      不触碰线上 actions.index.json —— 查询方 load_index() 继续读旧索引，
      零阻塞（暂存区单独建索引，也顺便复用 scan_actions 免解析能力）。
    - 构建成功后一次性 os.replace 把暂存索引原子切换到线上路径（原子切换）；
      切换瞬间起查询方读到新索引，切换前始终旧索引。
    - 构建/切换任何一步失败都保留线上旧索引不动（回退旧索引），error 供查询。
    - start() 幂等：已有重建线程在跑时返回 False，不会叠线程。

    线程安全：并发 start 由 _lock 保护；查询方无需加锁（读旧文件天然安全）。
    """

    def __init__(self, actions_dir: str = None, meta_dir: str = None,
                 incremental: bool = False):
        self.actions_dir = actions_dir
        self.meta_dir = meta_dir
        self.incremental = incremental
        self._thread = None
        self._lock = threading.Lock()
        self._error = None
        self._last_index = None

    @property
    def running(self) -> bool:
        """是否正在后台重建。"""
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> Optional[str]:
        """最近一次重建失败原因；None 表示未失败/尚未失败。"""
        return self._error

    @property
    def last_index(self) -> Optional[dict]:
        """最近一次成功构建的索引（内存态，便于调用方直接使用）。"""
        return self._last_index

    def start(self) -> bool:
        """启动后台重建线程；已有线程在跑时返回 False（幂等）。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._error = None
            self._last_index = None
            self._thread = threading.Thread(
                target=self._run, name='actus-index-rebuild', daemon=True)
            self._thread.start()
            return True

    def join(self, timeout: float = None) -> None:
        """等待后台重建线程结束（测试/同步场景用）。"""
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        from .paths import meta_dir as _paths_meta_dir
        logger = logging.getLogger(__name__)
        try:
            online_meta = self.meta_dir or _paths_meta_dir()
            os.makedirs(online_meta, exist_ok=True)
            # 暂存区：与线上同级的私有目录，构建期不触碰线上索引文件
            staging = os.path.join(online_meta, '.index-staging')
            os.makedirs(staging, exist_ok=True)
            new_index = build_index(
                actions_dir=self.actions_dir,
                meta_dir=staging,
                write=True,
                # mtime/parse 缓存仍写线上 _meta（paths.meta_dir()），
                # 切换只换索引文件，缓存对下次前台扫描/构建继续生效。
                write_cache=True,
                incremental=self.incremental,
                atomic_write=True)
            # 原子切换：os.replace 把暂存索引换到线上路径（读方瞬间切新索引）
            src = os.path.join(staging, 'actions.index.json')
            dst = os.path.join(online_meta, 'actions.index.json')
            os.replace(src, dst)
            self._last_index = new_index
        except Exception as e:  # noqa: BLE001 - 后台任务失败不抛给调用方
            self._error = str(e)
            logger.warning('background index rebuild failed, '
                           'keep old index: %s', e)


def rebuild_index_background(actions_dir: str = None, meta_dir: str = None,
                             incremental: bool = False) -> BackgroundIndexRebuilder:
    """启动后台重建并返回重建器句柄（见 BackgroundIndexRebuilder 文档）。

    P3（T0r7）：调用后立即返回，重建线程在后台执行；重建期间查询方继续用
    旧索引，重建完成后原子切换，失败自动回退旧索引不崩溃。
    """
    rb = BackgroundIndexRebuilder(actions_dir=actions_dir, meta_dir=meta_dir,
                                  incremental=incremental)
    rb.start()
    return rb
