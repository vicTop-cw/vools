# -*- coding: utf-8 -*-
"""vools-actus 内置基础动作（actions/basics）冒烟测试。

历史问题：
  - 旧版只把 ``actus/`` 加进 sys.path，导致 ``vools.core`` 解析不到而收集失败；
  - 每个用例 try/except 后 ``return False`` 却不 assert，动作真失败时 pytest
    仍然判绿（假绿）。
现统一走 ``_ai_local_bootstrap``（本地源码优先命名空间）并用真实断言。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.actions.basics.calculator import CalculatorAction
from vools.actus.actions.basics.todo_list import TodoListAction
from vools.actus.actions.basics.text_editor import TextEditorAction
from vools.actus.actions.basics.image_viewer import ImageViewerAction

BASIC_ACTIONS = [
    ("calculator", "Calculator", CalculatorAction),
    ("todo-list", "Todo List", TodoListAction),
    ("text-editor", "Text Editor", TextEditorAction),
    ("image-viewer", "Image Viewer", ImageViewerAction),
]


@pytest.mark.parametrize("action_id,action_name,cls", BASIC_ACTIONS)
def test_basic_action_metadata(action_id, action_name, cls):
    action = cls()
    assert action.id == action_id
    assert action.name == action_name
    assert isinstance(action.version, str) and action.version
    assert isinstance(action.description, str) and action.description
