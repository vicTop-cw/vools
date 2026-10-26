"""intent.py —— 自然语言意图路由器 (Phase G4)。

将用户的自然语言请求映射到具体的动作/工作流。
支持关键词匹配、标签匹配、描述模糊匹配。
"""

import re
import logging
from typing import Dict, List, Optional, Any

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
        return self

    def set_probe_report(self, report):
        """从 ProbeReport 提取 ready 动作集合（PROBE_PLAN.md §9 Phase 3 集成）。

        probe 报告 actions 类别的 extra['actions'] 列出了探测到的动作 id，
        只有这些动作视为 ready，route() 推荐时仅推荐它们。
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
        return self

    def _is_ready(self, action_id: str) -> bool:
        """判断动作是否 ready（未启用过滤时恒为 True）。"""
        if self._ready_ids is None:
            return True
        return action_id in self._ready_ids

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

        # 2. 标签匹配
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
            elif desc and any(word in desc for word in query_lower.split() if len(word) > 2):
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
        """列出所有已注册的动作（未启用 ready 过滤时全量；启用时仅 ready 动作）。"""
        if self._ready_ids is None:
            return self._actions.copy()
        return [a for a in self._actions if a["id"] in self._ready_ids]

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


__all__ = [
    'DEFAULT_KEYWORD_MAP',
    'IntentRouter',
    'get_default_router',
    'logger'
]
