"""
vools.actus.actions — Actus 动作集

提供各种动作，包括：
- basics - 基础 GUI 动作
"""

from .basics import get_all_actions, CalculatorAction, TodoListAction, TextEditorAction, ImageViewerAction

__all__ = [
    # 基础动作
    'get_all_actions',
    'CalculatorAction',
    'TodoListAction',
    'TextEditorAction',
    'ImageViewerAction',
]


def load_action(action_id: str):
    """
    加载动作
    
    Args:
        action_id: 动作 ID
    
    Returns:
        Action 实例
    """
    from ..model import parse_cfg_from_file
    from ..indexer import get_action
    
    action_info = get_action(action_id)
    if action_info:
        return parse_cfg_from_file(action_info.path)
    
    raise ValueError(f"Action not found: {action_id}")


def list_actions() -> list:
    """
    列出所有动作
    
    Returns:
        动作列表
    """
    return get_all_actions()