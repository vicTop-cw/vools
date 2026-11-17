"""intent.py —— 自然语言意图路由器 (Phase G4)。

将用户的自然语言请求映射到具体的动作/工作流。
支持关键词匹配、标签匹配、描述模糊匹配。
"""

import re
import os
import json
import hashlib
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Any

# P2（推荐缓存与增量注册）：进程级 LRU 缓存需要 scan_actions 的变更属性
# （scan_actions._changed_ids / _has_removal）与轻量 mtime 快照工具。
# indexer 不反向 import intent，无循环导入。
from .indexer import scan_actions, _action_roots, _parser_fingerprint
from .tokenizer import tokenize

logger = logging.getLogger(__name__)


def _require_id(value, what: str) -> None:
    """id 必须是非空字符串（此前 None 会被当成合法 id 注册进去）。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} 必须是非空字符串，得到 {value!r}")


def _require_opt_str(value, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{what} 必须是字符串，得到 {type(value).__name__}")
    return value


def _require_tags(tags) -> List[str]:
    """tags 必须是字符串列表或 None；**字符串会被逐字符展开**，故显式拒绝。"""
    if tags is None:
        return []
    if isinstance(tags, (str, bytes)):
        raise TypeError(
            f"tags 必须是字符串列表，不能是字符串（会被逐字符展开），得到 {tags!r}")
    if not isinstance(tags, (list, tuple)):
        raise TypeError(f"tags 必须是 list/tuple，得到 {type(tags).__name__}")
    for t in tags:
        if not isinstance(t, str):
            raise TypeError(f"tags 的元素必须是字符串，得到 {t!r}")
    return list(tags)


class IntentRouter:
    """自然语言意图路由器。"""

    def __init__(self):
        self._actions: List[dict] = []
        self._workflows: List[dict] = []
        self._keyword_map: Dict[str, str] = {}
        # probe 集成（PROBE_PLAN.md §9 Phase 3）：ready 动作过滤
        self._ready_ids: Optional[set] = None
        # 依赖级门禁（PROBE_PLAN.md §4.7）：报告里明确判 blocked 的动作 id。
        # None = 不启用（报告没带 action_readiness 条目 / 条目不可用 / 结构异常），
        # 此时行为与升级前**逐字一致**（只看 _ready_ids）。
        self._blocked_ids: Optional[set] = None

    def set_ready_ids(self, ready_ids):
        """设置可推荐（ready）的动作 id 集合。

        来自 probe 报告（actions 探测）：只有探测为可用的动作才进入推荐面。
        传 None 或空集合表示不启用 ready 过滤（向后兼容）。

        入参校验：**字符串会被 set() 逐字符拆开**（`'abc'` → `{'a','b','c'}`），
        与 BUG-490/492 的 `args='abc'` 同族，故显式拒绝 str/bytes 与非可迭代。
        """
        if ready_ids is None:
            self._ready_ids = None
        else:
            if isinstance(ready_ids, (str, bytes)):
                raise TypeError(
                    f"ready_ids 必须是 id 的可迭代集合，不能是字符串"
                    f"（会被逐字符拆开），得到 {ready_ids!r}")
            try:
                ids = set(ready_ids)
            except TypeError:
                raise TypeError(
                    f"ready_ids 必须是可迭代对象，得到 {type(ready_ids).__name__}") from None
            for i in ids:
                if not isinstance(i, str) or not i:
                    raise ValueError(f"ready_ids 的元素必须是非空字符串，得到 {i!r}")
            self._ready_ids = ids
        # 手工设置的 ready 集合是**显式覆盖**：同时清掉报告派生的依赖级门禁，
        # 否则一份过期报告的 blocked 判定会偷偷盖掉调用方的显式选择。
        self._blocked_ids = None
        return self

    def set_probe_report(self, report):
        """从 ProbeReport 提取 ready 动作集合（PROBE_PLAN.md §9 Phase 3 集成）。

        probe 报告 actions 类别的 extra['actions'] 列出了探测到的动作 id，
        只有这些动作视为 ready，route() 推荐时仅推荐它们。

        **本轮升级（PROBE_PLAN.md §4.7）**：再读 `action_readiness` 条目的
        `extra['verdicts']`，把「在报告里、但声明的依赖不满足」的动作也挡在推荐面
        之外（依赖级门禁）。向后兼容的三条纪律：
          1. 报告里**没有** `action_readiness` 条目（旧缓存/旧报告）→ 门禁不启用，
             行为与升级前逐字一致；
          2. 该条目 `available=False`（分析失败）→ 同样不启用（**绝不因为分析本身
             失败就把所有动作误杀**，与 actions 条目 unavailable 时的处理同一条纪律）；
          3. 只认**显式** `verdict == "blocked"`，结构异常的条目一律忽略。
        """
        ready = []
        for item in getattr(report, "items", []):
            if item.category == "actions" and item.available:
                for act in ((item.extra or {}).get("actions", []) or []):
                    if isinstance(act, dict):
                        ready.append(act.get("id"))
                    else:
                        ready.append(act)
        ready = [x for x in ready if x]
        self._ready_ids = set(ready) if ready else None
        self._blocked_ids = self._extract_blocked_ids(report)
        return self

    @staticmethod
    def _extract_blocked_ids(report):
        """从报告提取「明确判 blocked」的动作 id；取不到/不可用/异常 → None。"""
        for item in getattr(report, "items", []) or []:
            if getattr(item, "category", None) != "actions":
                continue
            if getattr(item, "name", None) != "action_readiness":
                continue
            if not getattr(item, "available", False):
                return None                  # 分析失败：不启用门禁，别误杀
            verdicts = (getattr(item, "extra", None) or {}).get("verdicts")
            if not isinstance(verdicts, dict):
                return None                  # 结构异常：退回粗粒度行为
            blocked = set()
            for action_id, record in verdicts.items():
                if not isinstance(action_id, str) or not action_id:
                    continue
                if not isinstance(record, dict):
                    continue                 # 结构异常（如裸字符串）：忽略，不当 blocked
                if record.get("verdict") == "blocked":   # 只认显式 blocked
                    blocked.add(action_id)
            return blocked
        return None                          # 旧报告：没有这一条目

    def _is_ready(self, action_id: str) -> bool:
        """判断动作是否 ready（未启用过滤时恒为 True）。

        两道门（顺序即语义）：
          1. `_ready_ids`：动作是否出现在探测报告里（既有粗粒度判据，不变）；
          2. `_blocked_ids`：动作声明的依赖是否**明确**不满足（§4.7 依赖级门禁）；
             报告没带该信息时为 None → 只看第 1 道门，行为与升级前一致。
        """
        if self._ready_ids is None:
            return True
        if action_id not in self._ready_ids:
            return False
        if self._blocked_ids and action_id in self._blocked_ids:
            return False
        return True

    def register_action(self, action_id: str, description: str, usage: str = "", tags: List[str] = None):
        """注册动作的语义描述。

        入参校验：此前 `action_id=None` 会注册出 id 为 None 的动作、
        `tags='abc'` 会把字符串原样存进 tags（后续 `for tag in tags` 逐字符）。
        """
        _require_id(action_id, "action_id")
        if not isinstance(description, str):
            raise TypeError(
                f"description 必须是字符串，得到 {type(description).__name__}")
        self._actions.append({
            "id": action_id,
            "description": description,
            "usage": _require_opt_str(usage, "usage"),
            "tags": _require_tags(tags),
        })

    def register_workflow(self, workflow_id: str, description: str, tags: List[str] = None):
        """注册工作流的语义描述。"""
        _require_id(workflow_id, "workflow_id")
        if not isinstance(description, str):
            raise TypeError(
                f"description 必须是字符串，得到 {type(description).__name__}")
        self._workflows.append({
            "id": workflow_id,
            "description": description,
            "tags": _require_tags(tags),
        })

    def set_keyword_map(self, keyword_map: Dict[str, str]):
        """设置关键词映射。

        入参校验：此前传 None / list 会被收下，直到 `route()` 里访问 `.items()`
        才抛裸 AttributeError（看不出是哪个参数设错了）。
        """
        if not isinstance(keyword_map, dict):
            raise TypeError(
                f"keyword_map 必须是 dict，得到 {type(keyword_map).__name__}")
        for k, v in keyword_map.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise TypeError(
                    f"keyword_map 的键和值都必须是字符串，得到 {k!r}: {v!r}")
        self._keyword_map = dict(keyword_map)

    def route(self, query: str) -> dict:
        """根据自然语言查询路由到最佳匹配。

        Returns:
            {
                "match": "keyword" | "fuzzy" | "none",
                "action_id": str | None,
                "confidence": float,
                "reason": str
            }
        """
        if not isinstance(query, str):
            raise TypeError(
                f"query 必须是字符串，得到 {type(query).__name__}"
                f"（此前会在 .lower() 处抛裸 AttributeError）")
        query_lower = query.lower().strip()

        if not query_lower:
            return {"match": "none", "action_id": None, "confidence": 0, "reason": "空查询"}

        # 1. 精确关键词匹配
        for keyword, action_id in self._keyword_map.items():
            if keyword.lower() in query_lower:
                if not self._is_ready(action_id):
                    continue
                return {
                    "match": "keyword",
                    "action_id": action_id,
                    "confidence": 0.95,
                    "reason": f"关键词匹配: {keyword}"
                }

        # 2. 工作流匹配（第 11 轮接线：此前 `_workflows` 注册后 route() 从不读 ——
        # `register_workflow` 注册了永远不触发。工作流按 tags/description/id 匹配，
        # 命中返回 match='workflow' + workflow_id；action_id 置 None，避免调用方
        # 误把工作流当动作执行）。
        best_wf = None
        best_wf_score = 0
        best_wf_reason = ''
        for wf in self._workflows:
            score = 0
            for tag in wf.get('tags') or []:
                if str(tag).lower() in query_lower:
                    score += 0.4
            wf_desc = str(wf.get('description') or '').lower()
            if wf_desc and wf_desc in query_lower:
                score += 0.3
            elif wf_desc and any(w in wf_desc for w in tokenize(query_lower, expand_ngram=False) if len(w) > 2):
                score += 0.15
            wf_id = str(wf.get('id') or '').lower()
            if wf_id and wf_id in query_lower:
                score += 0.2
            if score > best_wf_score:
                best_wf_score = score
                best_wf = wf['id']
                best_wf_reason = '工作流匹配: %s' % wf['id']
        if best_wf and best_wf_score > 0.15:
            return {'match': 'workflow', 'workflow_id': best_wf,
                    'action_id': None,
                    'confidence': min(best_wf_score, 1.0),
                    'reason': best_wf_reason}

        # 3. 标签匹配
        best_match = None
        best_score = 0
        best_reason = ""

        for action in self._actions:
            if not self._is_ready(action["id"]):
                continue
            score = 0
            for tag in action.get("tags", []):
                tag_lower = tag.lower()
                if tag_lower in query_lower:
                    score += 0.4
                # 部分匹配（标签是 query 的子串或 query 是标签的子串）
                elif len(tag_lower) > 2 and (tag_lower[:3] in query_lower or query_lower[:3] in tag_lower):
                    score += 0.15

            # 描述匹配
            desc = action.get("description", "").lower()
            if desc and desc in query_lower:
                score += 0.3
            elif desc and any(word in desc for word in tokenize(query_lower, expand_ngram=False) if len(word) > 2):
                score += 0.1

            if score > best_score:
                best_score = score
                best_match = action["id"]
                best_reason = f"标签匹配: {action['id']}"

        if best_match and best_score > 0.15:
            return {
                "match": "fuzzy",
                "action_id": best_match,
                "confidence": min(best_score, 1.0),
                "reason": best_reason
            }

        return {"match": "none", "action_id": None, "confidence": 0, "reason": "无匹配"}

    def list_actions(self) -> List[dict]:
        """列出所有已注册的动作（未启用 ready 过滤时全量；启用时仅 ready 动作）。

        走 `_is_ready()` 而不是直接比 `_ready_ids`，这样依赖级门禁（§4.7）对
        `list_actions()` 与 `route()` 是**同一套判据**（两处口径分开写正是历史上
        最容易漂移的地方）。
        """
        if self._ready_ids is None:
            return self._actions.copy()
        return [a for a in self._actions if self._is_ready(a["id"])]

    def list_workflows(self) -> List[dict]:
        """列出所有已注册的工作流。"""
        return self._workflows.copy()


# ── 默认关键词映射 ──

DEFAULT_KEYWORD_MAP = {
    # 中文关键词
    "监控": "actus.system.folder_watch",
    "监视": "actus.system.folder_watch",
    "观察": "actus.system.folder_watch",
    "监听": "actus.system.folder_watch",
    "录制": "actus.system.macro_record",
    "记录": "actus.system.macro_record",
    "回放": "actus.system.macro_playback",
    "播放": "actus.system.macro_playback",
    "执行录制": "actus.system.macro_playback",
    "对话框": "actus.system.dialog_alert",
    "弹窗": "actus.system.dialog_alert",
    "提示": "actus.system.dialog_alert",
    "输入": "actus.system.dialog_input",
    "选择": "actus.system.dialog_single",
    "多选": "actus.system.dialog_multi",
    "表单": "actus.system.dialog_form",
    "进程": "actus.system.tool_process",
    "进程管理": "actus.system.tool_process",
    "任务管理器": "actus.system.tool_process",
    "窗口": "actus.system.tool_window",
    "窗口管理": "actus.system.tool_window",
    "剪贴板": "actus.system.tool_clipboard",
    "复制历史": "actus.system.tool_clipboard",
    "截图": "actus.system.tool_screen",
    "截屏": "actus.system.tool_screen",
    "屏幕": "actus.system.tool_screen",

    # 英文关键词
    "watch": "actus.system.folder_watch",
    "monitor": "actus.system.folder_watch",
    "record": "actus.system.macro_record",
    "playback": "actus.system.macro_playback",
    "replay": "actus.system.macro_playback",
    "dialog": "actus.system.dialog_alert",
    "alert": "actus.system.dialog_alert",
    "input": "actus.system.dialog_input",
    "process": "actus.system.tool_process",
    "window": "actus.system.tool_window",
    "clipboard": "actus.system.tool_clipboard",
    "screenshot": "actus.system.tool_screen",
    "screen": "actus.system.tool_screen",
}


def get_default_router() -> IntentRouter:
    """获取带默认关键词映射的路由器。"""
    router = IntentRouter()
    router.set_keyword_map(DEFAULT_KEYWORD_MAP)
    return router


# ─────────────────────────────────────────────────────────────────────
# P2：推荐缓存与增量注册（提升计划 P2，actus_recommend 缓存）
#
# 问题（V-17 相邻）：MCP actus_recommend 每次调用都 `scan_actions(validate=False)`
# 全量重扫 + 逐个 register_action，无任何进程级缓存 —— 每次推荐都触发全量
# 文件 IO + 解析。
#
# 方案：常驻进程级 LRU 缓存（键 = parser fingerprint + 动作文件 mtime 摘要）：
#   - 键未变（无文件变化、parser 未升级）→ 直接复用缓存 router，0 次 scan；
#   - 键变化且无文件删除 → 仅对变更文件增量注册（新增 1 个动作只注册该动作）；
#   - 有文件删除 / parser fingerprint 变化 → 全量重建（删除场景旧文件 id 不可知，
#     增量无法安全还原 router）；
#   - probe 结果仅在重建时执行一次，且作为缓存项签名：外部显式传入的 probe
#     报告与缓存不一致时强制重建（"probe 结果失效才重建"）。
# ─────────────────────────────────────────────────────────────────────
_ROUTER_CACHE_MAXSIZE = 4
# key -> (router, changes, probe_sig)；OrderedDict 用于 FIFO 淘汰（近似 LRU）。
_router_cache: "OrderedDict[str, tuple]" = OrderedDict()
# 打点计数器：验收标准用（连续两次 recommend 第二次不触发 scan 等）。
_cache_stats = {
    'hits': 0,
    'misses': 0,
    'scan_count': 0,
    'register_count': 0,
    'probe_count': 0,
}


def reset_router_cache() -> None:
    """清空进程级缓存与打点（测试隔离用）。"""
    _router_cache.clear()
    for _k in _cache_stats:
        _cache_stats[_k] = 0


def get_router_cache_stats() -> Dict[str, int]:
    """返回缓存打点快照（hits/misses/scan_count/register_count/probe_count）。"""
    return dict(_cache_stats)


def _snapshot_actions_fingerprint(actions_dir: str = None) -> str:
    """轻量扫描动作根的 (rel -> (mtime, size)) 摘要，不解析文件内容。

    只做目录遍历 + os.stat，成本远低于 scan_actions 的全量解析；作为缓存键
    的 mtime 摘要组成部分，判断"动作文件是否变化"。
    """
    roots = _action_roots(actions_dir)
    sig = {}
    for root_idx, root in enumerate(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if fn.endswith('.actus.md') or fn.endswith('.actus.schema.md'):
                    full = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    rel = f'r{root_idx}/' + os.path.relpath(full, root).replace(os.sep, '/')
                    sig[rel] = (st.st_mtime, st.st_size)
    return hashlib.sha256(
        json.dumps(sig, sort_keys=True).encode('utf-8')).hexdigest()


def _probe_sig(report) -> Optional[str]:
    """从 probe 报告提取 ready/blocked 集合摘要；None 表示无可用信息。"""
    if report is None:
        return None
    ready = set()
    blocked = set()
    for item in getattr(report, 'items', []) or []:
        if getattr(item, 'category', None) != 'actions':
            continue
        if not getattr(item, 'available', False):
            continue
        for act in ((getattr(item, 'extra', None) or {}).get('actions', []) or []):
            if isinstance(act, dict):
                if act.get('id'):
                    ready.add(act['id'])
            elif act:
                ready.add(act)
        if getattr(item, 'name', None) == 'action_readiness':
            verdicts = (getattr(item, 'extra', None) or {}).get('verdicts') or {}
            if isinstance(verdicts, dict):
                for action_id, record in verdicts.items():
                    if isinstance(record, dict) and record.get('verdict') == 'blocked':
                        blocked.add(action_id)
    if not ready and not blocked:
        return None
    return hashlib.sha256(json.dumps(
        {'ready': sorted(x for x in ready if x), 'blocked': sorted(blocked)},
        ensure_ascii=False).encode('utf-8')).hexdigest()


def _remove_registered(router: IntentRouter, action_id: str) -> None:
    """从路由器的动作/工作流注册表移除指定 id（增量更新的前置步骤）。"""
    router._actions[:] = [a for a in router._actions if a.get('id') != action_id]
    router._workflows[:] = [w for w in router._workflows if w.get('id') != action_id]


def _register_changes(router: IntentRouter, actions: Dict[str, Any],
                      changed_ids: Optional[List[str]], stats: Dict[str, int]) -> None:
    """注册动作到路由器。

    - changed_ids 为 None → 全量注册（首次构建 / 有删除的全量重建）；
    - changed_ids 为列表 → 仅对该变更集增量注册（remove + append）。
    与 mcp_server.actus_recommend 旧实现保持同一注册语义：
    bundle/workflow 类动作额外 register_workflow。
    """
    ids = changed_ids if changed_ids is not None else list(actions)
    for aid in ids:
        _remove_registered(router, aid)
        action = actions.get(aid)
        if action is None:
            continue  # 已删除/失效：仅移除旧条目
        tags = list(action.meta.get('tags') or []) if hasattr(action, 'meta') else []
        desc = action.meta.get('description', '') or ''
        usage = action.meta.get('usage', '') or ''
        router.register_action(aid, desc, usage, tags)
        if str(action.meta.get('kind') or 'exec').lower() in ('bundle', 'workflow'):
            router.register_workflow(aid, desc, tags)
        stats['register_count'] += 1


def get_router_with_cache(probe_report=None, actions_dir: str = None):
    """获取带进程级 LRU 缓存的 IntentRouter（P2 推荐缓存入口）。

    Returns:
        (router, changes, rebuilt)
          - router:   IntentRouter 实例（缓存命中时为缓存实例）
          - changes:  缓存命中为 None；重建时为
                      {'changed_aids': [...], 'rebuilt': bool}
          - rebuilt:  本次是否发生了构建/重建（缓存未命中）
    """
    fp = _parser_fingerprint()
    snap = _snapshot_actions_fingerprint(actions_dir)
    key = f'{fp}::{snap}'

    cached = _router_cache.get(key)
    if cached is not None:
        router, _changes, probe_sig, _fp = cached
        if probe_report is None or _probe_sig(probe_report) == probe_sig:
            _cache_stats['hits'] += 1
            return router, None, False
        # probe 结果失效 → 移除缓存项并强制重建
        del _router_cache[key]

    # miss：决定增量基础。仅当"最近一个缓存 router 的 parser fingerprint 与
    # 当前一致"时允许在其上增量（快照变化 = 动作文件增删改，变更集可安全
    # remove+append）；fingerprint 变化（parser 语义升级）时旧动作解析可能
    # 过时，必须全量重建；有文件删除时旧 id 不可知，也必须全量重建。
    base_router = None
    if _router_cache:
        _old_key = next(reversed(_router_cache))
        _old_router, _oc, _os, _old_fp = _router_cache[_old_key]
        if _old_fp == fp:
            base_router = _old_router

    _cache_stats['misses'] += 1
    _cache_stats['scan_count'] += 1
    actions = scan_actions(actions_dir=actions_dir, validate=False)
    changed_ids = list(getattr(scan_actions, '_changed_ids', None) or [])
    has_removal = bool(getattr(scan_actions, '_has_removal', False))

    if changed_ids and not has_removal and base_router is not None:
        # 增量注册：复用最近缓存 router，仅变更集 remove+append
        router = base_router
        _register_changes(router, actions, changed_ids, _cache_stats)
        changes = {'changed_aids': list(changed_ids), 'rebuilt': False}
    else:
        # 首次构建 / 有删除 / 指纹变化 / probe 失效：全新 router 全量注册
        router = get_default_router()
        _register_changes(router, actions, None, _cache_stats)
        changes = {'changed_aids': list(actions), 'rebuilt': True}

    # probe 集成（PROBE_PLAN.md §9 Phase 3）：重建时执行一次并绑定为缓存签名
    if probe_report is not None:
        router.set_probe_report(probe_report)
    else:
        try:
            from vools.actus.probe import probe
            _cache_stats['probe_count'] += 1
            probe_report = probe(force_refresh=False)
            router.set_probe_report(probe_report)
        except Exception:
            probe_report = None

    probe_sig = _probe_sig(probe_report)
    _router_cache[key] = (router, changes, probe_sig, fp)
    while len(_router_cache) > _ROUTER_CACHE_MAXSIZE:
        _router_cache.popitem(last=False)
    return router, changes, True


__all__ = [
    'DEFAULT_KEYWORD_MAP',
    'IntentRouter',
    'get_default_router',
    'logger',
    'get_router_with_cache',
    'reset_router_cache',
    'get_router_cache_stats',
]
