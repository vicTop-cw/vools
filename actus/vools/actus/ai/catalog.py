"""动作索引 → LLM 工具目录。

这是本包把 Actus 接入 LLM 的关键一步：**动作的 `args` 字段本来就是
draft-07 JSON Schema，MCP 的 `_input_schema()` 已在做同一件事** ——
所以工具声明可以零转换地拿到，不必另造一套 tool schema 语言。

入口纪律（不要绕过）：动作清单一律从 `indexer.load_index()` 取，
**不得**自己再解析 `.actus.md`。索引里已经带齐了 `args`/`description`/
`usage`/`tags`/`trust`/`permissions`/`deprecated`/`status`。

两条过滤是安全边界，不是可选优化：

1. `status != 'valid'` 的条目不进目录 —— docs/05 §5.1 明说不合规动作
   要从 MCP tools 下架。喂给 LLM 一个执行不了的动作比不给更糟。
2. `_invalid:` 前缀的键是**解析失败**的残骸（indexer.py:152），不是动作。

重复检测刻意**不引入 embedding**：体检必须能离线跑、结果可复现。

Example:
    >>> normalize_tool_name('actus.system.json_util')
    'actus_system_json_util'
    >>> normalize_tool_name('cli.jq')
    'cli_jq'
"""

__all__ = ['ToolCatalog', 'CatalogEntry', 'build_catalog', 'load_catalog',
           'normalize_tool_name', 'detect_duplicates',
           'CAPABILITY_KEYS', 'NONSTANDARD_PREFIX', 'INTERNAL_PREFIX']

import os
import re

from vools.core.dataclass_compat import dataclass, field

from .base import ToolSpec

# 非字母数字一律转下划线（与 mcp_server._tool_name 的规则对齐）
_NON_ALNUM = re.compile(r'[^a-z0-9]+')

# 约定：内置动作 id 首段统一用 'actus'。其余视为命名不规范，
# 列进体检报告 —— 实测有 27 个动作没按此约定命名（其中 14 个是
# vools.vault.*，库的动作混进了动作市场）。
INTERNAL_PREFIX = 'actus'
NONSTANDARD_PREFIX = 'not_actus'

# 能力关键词 → 用于「疑似同能力」的聚类（不做判定，只提示）。
# 刻意保守：宁可漏报也不误报，误报会让人白改代码。
CAPABILITY_KEYS = {
    'http': ('http 请求', 'http请求', 'fetch', 'curl'),
    'json': ('json',),
    'mcp': ('mcp client', 'mcp 调用', 'mcp生态', 'mcp 生态'),
    'dialog': ('弹窗',),
    'screenshot': ('截图', 'screenshot'),
    'clipboard': ('剪贴板', 'clipboard'),
    'convert': ('文档转换', '格式互转', 'convert'),
    'download': ('下载',),
}

# 进程内缓存：meta_dir -> (mtime, ToolCatalog)
_CACHE = {}


def normalize_tool_name(action_id):
    """动作 id → LLM 工具名。

    规则与 `mcp_server._tool_name` 对齐：转小写、非字母数字转下划线。
    两边必须一致，否则同一个动作在 MCP 与 LLM 侧会有两个名字。

    Args:
        action_id: 动作 id，如 'actus.system.json_util'。

    Returns:
        str: 规范化后的工具名。

    Example:
        >>> normalize_tool_name('actus.system.json_util')
        'actus_system_json_util'
        >>> normalize_tool_name('http.fetch')
        'http_fetch'
    """
    return _NON_ALNUM.sub('_', str(action_id or '').strip().lower()).strip('_')


@dataclass(frozen=True)
class CatalogEntry(object):
    """单个动作在工具目录中的形态。

    Attributes:
        tool_name: 规范化工具名。
        action_id: 原始动作 id。
        description: 动作描述（已拼接 usage 并截断）。
        parameters: 动作 `args` 的 JSON Schema。
        trust: 动作 trust 字段。
        permissions: 动作声明的权限元组。
        tags: 动作分类标签。
        deprecated: 是否已下架。
        no_args: 是否没有可填参数（args 缺失或 properties 为空）——
            这类动作对 LLM 意义有限（只能调不能给参数）。
    """

    tool_name: str
    action_id: str = ''
    description: str = ''
    parameters: dict = field(default_factory=dict)
    trust: str = 'audit'
    permissions: tuple = ()
    tags: tuple = ()
    deprecated: bool = False
    no_args: bool = False

    def to_tool_spec(self):
        """转成给 LLM 的 ToolSpec。

        Returns:
            ToolSpec: 与动作契约同构的工具声明。
        """
        return ToolSpec(name=self.tool_name, description=self.description,
                        parameters=self.parameters, action_id=self.action_id,
                        trust=self.trust, permissions=self.permissions)


class ToolCatalog(object):
    """动作 → 工具目录。不可变快照，可跨线程共享。

    Attributes:
        meta_dir: 索引来源目录，仅用于 report() 标注。

    Example:
        >>> cat = ToolCatalog(())
        >>> len(cat)
        0
        >>> cat.names()
        []
    """

    def __init__(self, entries=(), meta_dir=''):
        """构造目录。

        Args:
            entries: CatalogEntry 序列。
            meta_dir: 索引来源目录。
        """
        self._entries = tuple(entries)
        self._by_name = dict((e.tool_name, e) for e in self._entries)
        self._by_action = dict((e.action_id, e) for e in self._entries if e.action_id)
        self.meta_dir = str(meta_dir or '')

    def __iter__(self):
        """产出 CatalogEntry。"""
        return iter(self._entries)

    def __len__(self):
        """int: 条目数。"""
        return len(self._entries)

    def __contains__(self, tool_name):
        """bool: 工具名是否在目录中。"""
        return tool_name in self._by_name

    def names(self):
        """List[str]: 全部工具名（已排序）。"""
        return sorted(e.tool_name for e in self._entries)

    def action_ids(self):
        """List[str]: 全部动作 id（已排序）。"""
        return sorted(e.action_id for e in self._entries if e.action_id)

    def get(self, tool_name):
        """按工具名取条目。

        Args:
            tool_name: 规范化工具名。

        Returns:
            CatalogEntry: 命中的条目。

        Raises:
            ActionError: code='action_not_found'，未收录该工具。
        """
        from ..errors import ActionError
        entry = self._by_name.get(tool_name)
        if entry is None:
            raise ActionError('action_not_found', '工具不在目录中: %s' % tool_name,
                              {'known_count': len(self._entries)})
        return entry

    def find_by_action(self, action_id):
        """按动作 id 取条目。

        Args:
            action_id: 动作 id。

        Returns:
            CatalogEntry 或 None（未收录时）。
        """
        return self._by_action.get(action_id)

    def by_trust(self, allowed):
        """按 trust 白名单过滤，返回新目录。

        Args:
            allowed: 允许的 trust 元组，如 ('trusted',)。空元组表示不过滤。

        Returns:
            ToolCatalog: 过滤后的新目录（原目录不变）。
        """
        allow = tuple(allowed or ())
        if not allow:
            return self
        return ToolCatalog([e for e in self._entries if e.trust in allow],
                           self.meta_dir)

    def grep(self, keyword, limit=20):
        """关键词粗筛，用于把候选集压到可塞进 prompt 的规模。

        排序：id 命中 > tag 命中 > description 命中。这不是打分模型，
        只是让最可能命中的排在前面，减少 LLM 的注意力稀释。

        Args:
            keyword: 关键词（大小写不敏感，空格视为两个独立词）。
            limit: 最多返回多少条。

        Returns:
            List[CatalogEntry]: 命中的条目，按命中质量降序。
        """
        kw = str(keyword or '').strip().lower()
        if not kw:
            return list(self._entries)[:limit]
        words = [w for w in kw.replace('/', ' ').replace(',', ' ').split() if w]
        if not words:
            return list(self._entries)[:limit]
        scored = []
        for e in self._entries:
            aid = e.action_id.lower()
            tags = ' '.join(e.tags).lower()
            desc = e.description.lower()
            rank = None
            if any(w in aid for w in words):
                rank = 0
            elif any(w in tags for w in words):
                rank = 1
            elif any(w in desc for w in words):
                rank = 2
            if rank is not None:
                scored.append((rank, e.action_id, e))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in scored[:limit]]

    def to_tool_specs(self, include_no_args=True):
        """整份目录转成 ToolSpec 列表。

        Args:
            include_no_args: 是否收录没有可填参数的动作。默认 True
                （有些动作确实无参，但 LLM 仍需要知道它们存在）。

        Returns:
            List[ToolSpec]: 工具声明列表。
        """
        return [e.to_tool_spec() for e in self._entries
                if include_no_args or not e.no_args]

    def duplicates(self):
        """Dict: 见 detect_duplicates。

        Returns:
            dict: {'exact': [...], 'suspect': [...], 'nonstandard_prefix': [...]}
        """
        return detect_duplicates(self._entries)


# ── 重复检测 ──

def _suffixes(action_id, min_segments=2):
    """动作 id 的所有长度 >= min_segments 的后缀集合。

    只取 >= 2 段是为了避开 'curl'/'jq' 这类过于通用的单词 —— 否则
    所有单段同名的动作都会被错误聚成一组。

    Args:
        action_id: 动作 id。
        min_segments: 最少段数。

    Returns:
        set: 后缀字符串集合。

    Example:
        >>> sorted(_suffixes('actus.cli.curl'))
        ['actus.cli.curl', 'cli.curl']
    """
    parts = str(action_id or '').split('.')
    if not parts or not parts[0]:
        return set()
    n = len(parts)
    if n < min_segments:
        return set()
    return set('.'.join(parts[i:]) for i in range(0, n - min_segments + 1))


def _cluster_by_suffix(entries, min_segments=2):
    """按共享后缀做并查集聚类。

    用传递闭包而不是「两两比对」：A 与 B 共享后缀、B 与 C 共享后缀时，
    三者应归成一组（A 与 C 未必直接共享）。

    Args:
        entries: CatalogEntry 序列。
        min_segments: 后缀最少段数。

    Returns:
        list: [(共享后缀元组, action_id 列表)]，仅含 >= 2 个成员的组。
    """
    ids = [e.action_id for e in entries if e.action_id]
    parent = dict((i, i) for i in range(len(ids)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    owner = {}
    for idx, aid in enumerate(ids):
        for suf in _suffixes(aid, min_segments):
            if suf in owner:
                union(owner[suf], idx)
            else:
                owner[suf] = idx

    groups = {}
    for idx, aid in enumerate(ids):
        groups.setdefault(find(idx), []).append(aid)

    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # 组内共享的后缀取最长者作为 key（信息量最大）
        best = ''
        for suf in owner:
            if sum(1 for m in members if suf in _suffixes(m)) == len(members):
                if len(suf) > len(best):
                    best = suf
        out.append((best or members[0], sorted(members)))
    out.sort(key=lambda t: t[0])
    return out


def detect_duplicates(entries):
    """检测同能力多实现。

    三层确定性规则，**不调 LLM、不引入 embedding** —— 体检必须能离线跑、
    每次结果一致，且不该被 API key 卡住。

    1. `exact`：共享 >= 2 段后缀的 id 归为一组（如 `actus.cli.curl`
       与 `cli.curl`、`http.fetch` 与 `actus.http.fetch`）
    2. `suspect`：description 命中同一组能力关键词但 id 不同源
       —— 只提示不当判定
    3. `nonstandard_prefix`：首段不是 'actus' 的动作

    Args:
        entries: CatalogEntry 序列。

    Returns:
        dict: 含 'exact' / 'suspect' / 'nonstandard_prefix' 三个键。
        'exact' 元素为 {'key': 共享后缀, 'action_ids': [...]}；
        'suspect' 元素为 {'capability': 能力名, 'action_ids': [...]}；
        'nonstandard_prefix' 为动作 id 列表。

    Example:
        >>> report = detect_duplicates([])
        >>> sorted(report)
        ['exact', 'nonstandard_prefix', 'suspect']
    """
    items = list(entries)

    exact = [{'key': key, 'action_ids': members}
             for key, members in _cluster_by_suffix(items)]

    suspected_ids = set()
    for item in exact:
        suspected_ids.update(item['action_ids'])

    suspect = []
    for cap, words in sorted(CAPABILITY_KEYS.items()):
        hits = []
        for e in items:
            if not e.action_id:
                continue
            desc = (e.description or '').lower()
            if any(w in desc for w in words):
                hits.append(e.action_id)
        # 已被 exact 覆盖的 id 不再重复报，避免同一问题出两行
        rest = [h for h in sorted(hits) if h not in suspected_ids]
        if len(rest) >= 2:
            suspect.append({'capability': cap, 'action_ids': rest})

    nonstandard = sorted(e.action_id for e in items
                         if e.action_id
                         and e.action_id.split('.')[0] != INTERNAL_PREFIX)

    return {'exact': exact, 'suspect': suspect, 'nonstandard_prefix': nonstandard}


# ── 构建 ──

def _entry_from_brief(action_id, brief):
    """把索引里的一条 brief 转成 CatalogEntry。"""
    args = brief.get('args') or {}
    props = args.get('properties') if isinstance(args, dict) else None
    desc = str(brief.get('description') or '')
    usage = str(brief.get('usage') or '')
    if usage:
        desc = (desc + '\n' + usage).strip()
    return CatalogEntry(
        tool_name=normalize_tool_name(action_id),
        action_id=action_id,
        # 工具描述塞进 prompt，有长度预算：超长会被 provider 拒绝
        description=desc[:1024],
        parameters=args if isinstance(args, dict) else {},
        trust=str(brief.get('trust') or 'audit'),
        permissions=tuple(brief.get('permissions') or ()),
        tags=tuple(brief.get('tags') or ()),
        deprecated=bool(brief.get('deprecated')),
        no_args=not bool(props),
    )


def _entries_from_index(index, include_deprecated=False):
    """把索引对象转成条目列表（统一的过滤入口）。

    Args:
        index: `indexer.load_index()` 的返回值。
        include_deprecated: 是否收录 deprecated 动作。

    Returns:
        List[CatalogEntry]: 按 action_id 升序排列。
    """
    actions = (index or {}).get('actions') or {}
    entries = []
    for action_id, brief in actions.items():
        if not action_id or action_id.startswith('_invalid:'):
            continue                      # 解析失败残骸，不是动作
        if not isinstance(brief, dict):
            continue
        status = brief.get('status')
        if status and status != 'valid':
            continue                      # docs/05 §5.1：不合规动作下架
        entry = _entry_from_brief(action_id, brief)
        if entry.deprecated and not include_deprecated:
            continue
        entries.append(entry)
    entries.sort(key=lambda e: e.action_id)
    return entries


def build_catalog(meta_dir=None, include_deprecated=False):
    """从 `indexer.load_index()` 构建工具目录。

    Args:
        meta_dir: 索引目录；None 时用 indexer 自身默认值
            （索引不存在会隐式 build）。
        include_deprecated: 是否收录 deprecated 动作。默认 False
            —— 下架动作不该进 LLM 工具面。

    Returns:
        ToolCatalog: 目录快照。索引不可用时返回空目录而不是抛异常
        —— 让体检与选择链看到「0 个动作」，比整体崩掉更可诊断。
    """
    from ..indexer import load_index
    try:
        index = load_index(meta_dir)
    except Exception:
        return ToolCatalog((), str(meta_dir or ''))
    return ToolCatalog(_entries_from_index(index, include_deprecated),
                       str(meta_dir or index.get('generated_at') or ''))


def load_catalog(meta_dir=None):
    """带进程内缓存的载入。

    缓存键是 (meta_dir, 索引的 generated_at)。`actus scan` 重建索引后
    generated_at 必变，因此缓存能正确失效，无需比对文件 mtime。

    Args:
        meta_dir: 索引目录；None 用 indexer 默认值。

    Returns:
        ToolCatalog: 目录快照（不可变，可安全跨线程复用）。
    """
    from ..indexer import load_index
    key = str(meta_dir or '')
    try:
        index = load_index(meta_dir)
        stamp = str(index.get('generated_at') or '')
    except Exception:
        stamp = ''

    cached = _CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    catalog = build_catalog(meta_dir)
    _CACHE[key] = (stamp, catalog)
    return catalog