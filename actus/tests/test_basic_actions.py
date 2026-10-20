# -*- coding: utf-8 -*-
"""vools-actus 内置基础动作（actions/basics）冒烟测试。

单一真源验证（2026-10-19 迁移后）：
- 动作定义在同目录 `.actus.schema.md`（front-matter 元数据 + webview2 实现块）；
- Python 侧 `CalculatorAction` 等是惰性 façade，元数据从 .md 读、不硬编码；
- 引擎索引（scan_actions）双后缀 + 多根扫描，种子动作必须被扫到。

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

from vools.actus.actions import (
    get_all_actions, load_action,
    CalculatorAction, TodoListAction, TextEditorAction, ImageViewerAction,
)

# 文件名键 → front-matter 里的真实 id（反域名风格，docs/03 §4.2）
BASIC_ACTIONS = [
    ("calculator", "actus.basics.calculator", "Calculator", CalculatorAction),
    ("todo-list", "actus.basics.todo_list", "Todo List", TodoListAction),
    ("text-editor", "actus.basics.text_editor", "Text Editor", TextEditorAction),
    ("image-viewer", "actus.basics.image_viewer", "Image Viewer", ImageViewerAction),
]


@pytest.mark.parametrize("file_key,action_id,action_name,cls", BASIC_ACTIONS)
def test_basic_action_metadata(file_key, action_id, action_name, cls):
    """façade 元数据来自 .actus.schema.md front-matter（单一真源）。"""
    action = cls()
    assert action.id == action_id
    assert action.name == action_name
    assert isinstance(action.version, str) and action.version
    assert isinstance(action.description, str) and action.description


@pytest.mark.parametrize("file_key,action_id,action_name,cls", BASIC_ACTIONS)
def test_facade_matches_schema_md(file_key, action_id, action_name, cls):
    """façade 读到的元数据必须与 .actus.schema.md front-matter 逐字一致。

    反证：若 Python 侧重新硬编码元数据（旧形态），本用例会因为 .md 改名
    而红——单一真源靠这条钉住。
    """
    from vools.actus.model import parse_cfg_from_file
    schema = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'vools', 'actus', 'actions', 'basics',
        f'{file_key}.actus.schema.md')
    if not os.path.isfile(schema):
        pytest.skip(f'schema 文件不在源树: {schema}')
    parsed = parse_cfg_from_file(os.path.normpath(schema))
    facade = cls()
    assert facade.id == parsed.meta['id']
    assert facade.name == parsed.meta['name']
    assert facade.version == parsed.meta['version']
    assert facade.description == parsed.meta['description']


def test_get_all_actions():
    actions = get_all_actions()
    assert len(actions) == 4
    ids = sorted(a.id for a in actions)
    assert ids == ['actus.basics.calculator', 'actus.basics.image_viewer',
                   'actus.basics.text_editor', 'actus.basics.todo_list']


def test_load_action():
    action = load_action('calculator')
    assert action.id == 'actus.basics.calculator'
    assert action.name == 'Calculator'


def test_load_action_unknown():
    with pytest.raises(ValueError):
        load_action('nonexistent-action')
