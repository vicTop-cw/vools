"""
vools.actus.actions.basics — 基础 GUI 动作集

提供美观的 WebView2 GUI 动作，包括：
- Calculator - 现代化计算器
- TodoList - 待办事项管理器
- TextEditor - 文本编辑器
- ImageViewer - 图片浏览器
"""

from .calculator import CalculatorAction
from .todo_list import TodoListAction
from .text_editor import TextEditorAction
from .image_viewer import ImageViewerAction

__all__ = [
    'CalculatorAction',
    'TodoListAction',
    'TextEditorAction',
    'ImageViewerAction',
    'get_all_actions',
]


def get_all_actions():
    """获取所有基础动作"""
    return [
        CalculatorAction(),
        TodoListAction(),
        TextEditorAction(),
        ImageViewerAction(),
    ]