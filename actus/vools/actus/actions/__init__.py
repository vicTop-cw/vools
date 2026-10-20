"""
vools.actus.actions — Actus 动作集

三层动作边界（docs/08 §1）：
  1. **基座自带种子动作**：本包 `vools/actus/actions/`（随 wheel 分发）
  2. **用户项目动作**：`<ACTUS_REPO_ROOT>/actions/`（Git 仓，索引优先）
  3. **社区仓动作**：`curator.list_default_repos()` 指向的远程仓

单一真源：动作定义在 `.actus.schema.md`（front-matter 元数据 + 代码块实现），
Python 侧只提供兼容 façade（`CalculatorAction` 等惰性代理），不硬编码元数据。
引擎索引（`indexer.scan_actions`）同时扫本目录与用户项目 actions/。
"""

from .basics import (
    get_all_actions, load_action,
    CalculatorAction, TodoListAction, TextEditorAction, ImageViewerAction,
)

__all__ = [
    # 基础动作（兼容 façade，定义在同目录 .actus.schema.md）
    'get_all_actions',
    'load_action',
    'CalculatorAction',
    'TodoListAction',
    'TextEditorAction',
    'ImageViewerAction',
]
