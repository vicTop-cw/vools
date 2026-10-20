"""vools.actus.actions.basics — 基础 GUI 动作集。

单一真源（docs/08 §1 + ACTUS_SCHEMA_SPEC.md）：
动作定义在**同目录的 .actus.schema.md**（front-matter 元数据 + webview2 实现块），
本包只提供 Python 侧的兼容 façade——不再硬编码 id/name/version/description
（存量缺陷：.py 与 .md 各持一份元数据，改名即漂移）。

迁移记录（2026-10-19）：
- 原 4 个类（Calculator/TodoList/TextEditor/ImageViewerAction）是薄壳：
  硬编码元数据 + execute 转调引擎。现改为按 action_id 从 schema.md 解析，
  façade 只做"取元数据 + 转调 execute"，元数据永远跟 .md 走。
"""

__all__ = [
    'CalculatorAction',
    'TodoListAction',
    'TextEditorAction',
    'ImageViewerAction',
    'get_all_actions',
    'load_action',
]

import os
from typing import Any, Dict, Optional

_DIR = os.path.dirname(os.path.abspath(__file__))


def _schema_path(action_id: str) -> Optional[str]:
    """按 action_id 定位同目录的 .actus.schema.md（单真源）。"""
    fname = f'{action_id}.actus.schema.md'
    path = os.path.join(_DIR, fname)
    return path if os.path.isfile(path) else None


def load_action(action_id: str) -> '_SchemaAction':
    """按 action_id 从 .actus.schema.md 加载动作 façade。

    元数据（id/name/version/description）从 front-matter 读，不硬编码。
    """
    from ...model import parse_cfg_from_file
    path = _schema_path(action_id)
    if not path:
        raise ValueError(f'Action not found: {action_id}')
    return _SchemaAction(parse_cfg_from_file(path))


class _SchemaAction:
    """.actus.schema.md 动作的 Python façade（元数据来自 front-matter）。"""

    def __init__(self, action):
        self._action = action

    @property
    def id(self) -> str:
        return self._action.id

    @property
    def name(self) -> str:
        return self._action.meta.get('name', self._action.id)

    @property
    def version(self) -> str:
        return self._action.meta.get('version', '')

    @property
    def description(self) -> str:
        return self._action.meta.get('description', '')

    @property
    def trust(self) -> str:
        return self._action.trust

    def execute(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行动作（走引擎完整门禁链）。"""
        from ...executor import execute
        return execute(self.id, params or {})

    def preview(self) -> Dict[str, Any]:
        """预览动作。"""
        from ...executor import preview
        return preview(self.id)

    def __call__(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        return self.execute(params)

    def __repr__(self):
        return f'{type(self).__name__}(id={self.id!r}, name={self.name!r})'


# ── 兼容 façade：保留原 4 个类名，但改为按 id 惰性加载 schema.md ──

class _LazyActionProxy:
    """惰性动作代理：首次访问属性时才解析对应 .actus.schema.md。

    保持 `from vools.actus.actions import CalculatorAction` 可用，
    但不再在 import 期解析 4 个文件（import 变快，且元数据永远最新）。
    """

    _action_id = ''

    def _load(self) -> '_SchemaAction':
        return load_action(self._action_id)

    @property
    def id(self) -> str:
        return self._load().id

    @property
    def name(self) -> str:
        return self._load().name

    @property
    def version(self) -> str:
        return self._load().version

    @property
    def description(self) -> str:
        return self._load().description

    def execute(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._load().execute(params)

    def preview(self) -> Dict[str, Any]:
        return self._load().preview()

    def __call__(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._load().execute(params)


class CalculatorAction(_LazyActionProxy):
    """现代化计算器动作（定义见 calculator.actus.schema.md）"""
    _action_id = 'calculator'      # 文件名键（front-matter id 是 actus.basics.calculator）


class TodoListAction(_LazyActionProxy):
    """待办事项管理器动作（定义见 todo-list.actus.schema.md）"""
    _action_id = 'todo-list'


class TextEditorAction(_LazyActionProxy):
    """文本编辑器动作（定义见 text-editor.actus.schema.md）"""
    _action_id = 'text-editor'


class ImageViewerAction(_LazyActionProxy):
    """图片浏览器动作（定义见 image-viewer.actus.schema.md）"""
    _action_id = 'image-viewer'


def get_all_actions():
    """获取所有基础动作 façade 实例（元数据来自各自 .actus.schema.md）。"""
    return [
        CalculatorAction(),
        TodoListAction(),
        TextEditorAction(),
        ImageViewerAction(),
    ]
