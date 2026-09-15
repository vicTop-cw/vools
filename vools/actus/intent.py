"""intent.py —— 自然语言意图路由器 (Phase G4)。

将用户的自然语言请求映射到具体的动作/工作流。
支持关键词匹配、标签匹配、描述模糊匹配。
"""

import re
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class IntentRouter:
    """自然语言意图路由器。"""

    def __init__(self):
        self._actions: List[dict] = []
        self._workflows: List[dict] = []
        self._keyword_map: Dict[str, str] = {}

    def register_action(self, action_id: str, description: str, usage: str = "", tags: List[str] = None):
        """注册动作的语义描述。"""
        self._actions.append({
            "id": action_id,
            "description": description,
            "usage": usage,
            "tags": tags or []
        })

    def register_workflow(self, workflow_id: str, description: str, tags: List[str] = None):
        """注册工作流的语义描述。"""
        self._workflows.append({
            "id": workflow_id,
            "description": description,
            "tags": tags or []
        })

    def set_keyword_map(self, keyword_map: Dict[str, str]):
        """设置关键词映射。"""
        self._keyword_map = keyword_map

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
        query_lower = query.lower().strip()

        if not query_lower:
            return {"match": "none", "action_id": None, "confidence": 0, "reason": "空查询"}

        # 1. 精确关键词匹配
        for keyword, action_id in self._keyword_map.items():
            if keyword.lower() in query_lower:
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
        """列出所有已注册的动作。"""
        return self._actions.copy()

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
