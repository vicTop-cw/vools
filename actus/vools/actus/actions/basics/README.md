# vools.actus.actions — 动作（Action）层

本子包提供可组合的「动作」对象——把一次可观测的系统操作（截图、复制粘贴、转换、编辑文本等）抽象成
统一的 `Action` 协议（`id / name / version / description / execute / preview`），
由 `get_all_actions()` 批量发现并注册。

## 子模块

| 模块 | 公开符号 | 说明 |
|---|---|---|
| `basics/calculator` | `CalculatorAction` | 调用系统计算器 |
| `basics/image_viewer` | `ImageViewerAction` | 打开/预览图片 |
| `basics/text_editor` | `TextEditorAction` | 唤起文本编辑器 |
| `basics/todo_list` | `TodoListAction` | 打开待办清单 |

## 协议

每个 Action 至少实现：

- `id: str` — 唯一动作标识
- `name: str` — 人类可读名称
- `version: str` — 动作版本
- `description: str` — 一句话说明
- `execute(...)` — 执行动作（返回结果对象）
- `preview(...)` — 返回预览字符串（不实际执行）

## 约定

- 每个模块显式声明 `__all__`（导出对应 Action 类）。
- 新动作放在 `basics/` 下并实现完整协议，避免破坏 `get_all_actions()` 的自动发现。
